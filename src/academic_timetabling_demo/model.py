"""Modelo CP-SAT sobre las alternativas admisibles (Hito 3).

Formulación (especificación, sección 5):

    min  sum_s sum_{a in A_s} (alpha * D_sa + beta * E_sa) * x_sa
    s.a. sum_{a in A_s} x_sa = 1                        para cada sección s
         sum_{(s,a) que usan q} x_sa <= 1               para cada ocupación q
         x_sa en {0, 1}

Una ocupación q es (tipo de recurso, recurso, semana, día, bloque), con tipo sala, docente
o grupo. Capacidad, equipamiento, disponibilidad, reservas y franjas protegidas no aparecen
como restricciones: ya quedaron fuera de A_s en el preprocesamiento SQL.
"""

import math
import sqlite3
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Protocol

from ortools.sat.python import cp_model

from academic_timetabling_demo.domain import RunConfig

SOLUTION_STATUSES = ("OPTIMAL", "FEASIBLE")
SOLVER_STATUSES = ("OPTIMAL", "FEASIBLE", "INFEASIBLE", "UNKNOWN", "MODEL_INVALID")
# CP-SAT informa el objetivo como double: hasta 2**53 todo entero se representa exactamente.
MAX_EXACT_OBJECTIVE = 2**53
MAX_INT32 = 2**31 - 1


class ModelError(RuntimeError):
    """El modelo no puede construirse con las tablas derivadas actuales."""


class SolverParameterError(ValueError):
    """La configuración o los costos no son representables por CP-SAT sin pérdida."""


class SolverConsistencyError(RuntimeError):
    """La solución devuelta contradice el modelo construido."""


@dataclass(frozen=True)
class Assignment:
    section_id: str
    pattern_id: str
    room_id: str


@dataclass(frozen=True)
class Alternative:
    alt_id: int
    section_id: str
    pattern_id: str
    room_id: str
    cost_d: int
    cost_e: int


@dataclass(frozen=True)
class SolveResult:
    status: str  # OPTIMAL | FEASIBLE | INFEASIBLE | UNKNOWN | MODEL_INVALID, sin reinterpretar
    objective: int | None  # reconstruido desde los costos enteros de las alternativas elegidas
    cost_d: int | None
    cost_e: int | None
    solver_objective: float | None  # valor informado por CP-SAT, solo para contraste
    best_bound: float | None
    assignments: tuple[Assignment, ...]
    num_variables: int
    num_constraints: int
    num_conflict_constraints: int
    build_seconds: float
    solve_seconds: float

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


class SolutionReader(Protocol):
    """Acceso a la solución. Solo se consulta cuando el estado trae una solución."""

    def boolean_value(self, alt_id: int) -> bool: ...

    def objective_value(self) -> float: ...

    def best_objective_bound(self) -> float: ...


@dataclass(frozen=True)
class Interpretation:
    status: str
    objective: int | None
    cost_d: int | None
    cost_e: int | None
    solver_objective: float | None
    best_bound: float | None
    assignments: tuple[Assignment, ...]


def check_parameters(config: RunConfig, alternatives: list[Alternative]) -> None:
    """Rechaza parámetros que CP-SAT no admite o costos que no se representan exactamente."""
    limit = config.time_limit_seconds
    if not math.isfinite(limit) or limit <= 0:
        raise SolverParameterError(f"time_limit_seconds debe ser positivo y finito: {limit}")
    if not 0 <= config.random_seed <= MAX_INT32:
        raise SolverParameterError(f"random_seed debe estar entre 0 y {MAX_INT32}")
    if not 1 <= config.num_search_workers <= MAX_INT32:
        raise SolverParameterError(f"num_search_workers debe estar entre 1 y {MAX_INT32}")

    worst: dict[str, int] = defaultdict(int)
    for alternative in alternatives:
        coefficient = config.alpha * alternative.cost_d + config.beta * alternative.cost_e
        worst[alternative.section_id] = max(worst[alternative.section_id], coefficient)
    largest = sum(worst.values())
    if largest > MAX_EXACT_OBJECTIVE:
        raise SolverParameterError(
            f"el objetivo puede llegar a {largest}, sobre 2**53: CP-SAT no lo informaría "
            "con exactitud. Reducir alpha o beta."
        )


def interpret(
    status: str,
    alternatives: list[Alternative],
    sections: list[str],
    config: RunConfig,
    reader: SolutionReader,
) -> Interpretation:
    """Traduce el estado del solver sin reinterpretarlo y extrae la solución si existe."""
    if status not in SOLVER_STATUSES:
        raise ModelError(f"estado de solver desconocido: {status}")
    if status not in SOLUTION_STATUSES:
        return Interpretation(status, None, None, None, None, None, ())

    chosen = [a for a in alternatives if reader.boolean_value(a.alt_id)]
    if sorted(a.section_id for a in chosen) != sorted(sections):
        raise SolverConsistencyError("la solución no elige exactamente una alternativa por sección")
    cost_d = sum(a.cost_d for a in chosen)
    cost_e = sum(a.cost_e for a in chosen)
    objective = config.alpha * cost_d + config.beta * cost_e
    solver_objective = reader.objective_value()
    if solver_objective != float(objective):
        raise SolverConsistencyError(
            f"CP-SAT informó objetivo {solver_objective!r}; los costos elegidos suman {objective}"
        )
    bound = reader.best_objective_bound()
    return Interpretation(
        status=status,
        objective=objective,
        cost_d=cost_d,
        cost_e=cost_e,
        solver_objective=solver_objective,
        best_bound=bound if math.isfinite(bound) else None,
        assignments=tuple(
            Assignment(a.section_id, a.pattern_id, a.room_id)
            for a in sorted(chosen, key=lambda a: a.section_id)
        ),
    )


class _OrToolsReader:
    def __init__(self, solver: cp_model.CpSolver, variables: dict[int, cp_model.IntVar]) -> None:
        self._solver = solver
        self._variables = variables

    def boolean_value(self, alt_id: int) -> bool:
        return bool(self._solver.boolean_value(self._variables[alt_id]))

    def objective_value(self) -> float:
        return self._solver.objective_value

    def best_objective_bound(self) -> float:
        return self._solver.best_objective_bound


def build_and_solve(
    connection: sqlite3.Connection,
    config: RunConfig,
    time_limit_seconds: float | None = None,
) -> SolveResult:
    """Construye el modelo desde `alternative` y `occupancy` y lo resuelve con CP-SAT.

    `time_limit_seconds` sustituye al de `config`; el llamador debe registrarlo.
    """
    if time_limit_seconds is not None:
        config = config.model_copy(update={"time_limit_seconds": time_limit_seconds})

    started = time.perf_counter()
    alternatives = [
        Alternative(*row)
        for row in connection.execute(
            "SELECT alt_id, section_id, pattern_id, room_id, cost_d, cost_e "
            "FROM alternative ORDER BY alt_id"
        )
    ]
    sections = [row[0] for row in connection.execute("SELECT id FROM sections ORDER BY id")]

    by_section: dict[str, list[int]] = defaultdict(list)
    for alternative in alternatives:
        by_section[alternative.section_id].append(alternative.alt_id)
    empty = [section_id for section_id in sections if not by_section[section_id]]
    if empty:
        raise ModelError(
            f"secciones sin alternativas: {', '.join(empty)}; el precheck debió detenerse"
        )
    check_parameters(config, alternatives)

    model = cp_model.CpModel()
    x = {
        a.alt_id: model.new_bool_var(f"x[{a.section_id},{a.pattern_id},{a.room_id}]")
        for a in alternatives
    }

    # 1. Cada sección elige exactamente una alternativa.
    for section_id in sections:
        model.add_exactly_one(x[alt_id] for alt_id in by_section[section_id])

    # 2. Ninguna sala, docente o grupo se usa dos veces en el mismo bloque de una semana.
    #    Solo las ocupaciones que comparten dos o más alternativas generan restricción.
    conflicts = connection.execute(
        "SELECT group_concat(alt_id) FROM occupancy "
        "GROUP BY resource_type, resource_id, week_id, day_id, block_id "
        "HAVING count(*) > 1"
    ).fetchall()
    for (alt_ids,) in conflicts:
        model.add_at_most_one(x[int(alt_id)] for alt_id in alt_ids.split(","))

    # 3. Objetivo entero: preferencia docente (D) y holgura de capacidad (E).
    model.minimize(
        sum((config.alpha * a.cost_d + config.beta * a.cost_e) * x[a.alt_id] for a in alternatives)
    )
    build_seconds = time.perf_counter() - started

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(config.time_limit_seconds)
    solver.parameters.random_seed = config.random_seed
    solver.parameters.num_workers = config.num_search_workers

    started = time.perf_counter()
    status = solver.solve(model)
    solve_seconds = time.perf_counter() - started

    result = interpret(
        solver.status_name(status), alternatives, sections, config, _OrToolsReader(solver, x)
    )
    return SolveResult(
        status=result.status,
        objective=result.objective,
        cost_d=result.cost_d,
        cost_e=result.cost_e,
        solver_objective=result.solver_objective,
        best_bound=result.best_bound,
        assignments=result.assignments,
        num_variables=len(x),
        num_constraints=len(model.proto.constraints),
        num_conflict_constraints=len(conflicts),
        build_seconds=build_seconds,
        solve_seconds=solve_seconds,
    )
