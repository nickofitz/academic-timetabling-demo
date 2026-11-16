"""Modelo CP-SAT: óptimo verificado por enumeración, estados y parámetros."""

import itertools
import math
from pathlib import Path

import pytest

from academic_timetabling_demo.candidates import build_candidates
from academic_timetabling_demo.db import connect, load_instance
from academic_timetabling_demo.domain import (
    Instance,
    SectionGroup,
    SectionPattern,
    SectionWeek,
    read_instance,
)
from academic_timetabling_demo.model import (
    MAX_EXACT_OBJECTIVE,
    MAX_INT32,
    Alternative,
    ModelError,
    SolverConsistencyError,
    SolverParameterError,
    build_and_solve,
    check_parameters,
    interpret,
)
from academic_timetabling_demo.validate import audit

DATA = Path(__file__).resolve().parents[1] / "data" / "synthetic"


@pytest.fixture
def micro() -> Instance:
    return read_instance(DATA / "micro")


def solve(instance: Instance, **config: object):
    connection = connect(":memory:")
    load_instance(connection, instance)
    precheck = build_candidates(connection)
    effective = instance.config.model_copy(update=config)
    try:
        return precheck, build_and_solve(connection, effective)
    finally:
        connection.close()


def enumerate_optimum(instance: Instance) -> int:
    """Óptimo por fuerza bruta sobre patrones autorizados y todas las salas, desde las fuentes."""
    options = [
        [
            (section.id, authorization.pattern_id, room.id)
            for authorization in instance.section_patterns
            if authorization.section_id == section.id
            for room in instance.rooms
        ]
        for section in instance.sections
    ]
    feasible = [
        report.objective
        for combination in itertools.product(*options)
        if (report := audit(instance, combination)).passed
    ]
    return min(feasible)


# Óptimo y caso demo ---------------------------------------------------------------------


def test_micro_optimum_matches_enumeration(micro: Instance) -> None:
    _, result = solve(micro)

    # La enumeración recorre 4 x 4 x 4 = 64 combinaciones sin usar alternative ni occupancy.
    assert result.status == "OPTIMAL"
    assert result.objective == enumerate_optimum(micro) == 3
    assert (result.cost_d, result.cost_e) == (0, 3)
    assert result.solver_objective == 3.0
    assert result.best_bound == 3.0
    assert [(a.section_id, a.pattern_id) for a in result.assignments] == [
        ("S1", "P2"),
        ("S2", "P3"),
        ("S3", "P5"),
    ]
    assert result.num_variables == 5


def test_weights_change_the_objective(micro: Instance) -> None:
    _, preferences_only = solve(micro, alpha=1, beta=0)
    _, seats_only = solve(micro, alpha=0, beta=1)

    assert preferences_only.objective == preferences_only.cost_d == 0
    assert seats_only.objective == seats_only.cost_e == 3
    assert (
        enumerate_optimum(
            micro.model_copy(
                update={"config": micro.config.model_copy(update={"alpha": 1, "beta": 0})}
            )
        )
        == 0
    )


def test_demo_is_complete_and_audited() -> None:
    demo = read_instance(DATA / "demo")
    precheck, result = solve(demo)
    rows = [(a.section_id, a.pattern_id, a.room_id) for a in result.assignments]

    report = audit(demo, rows, result.objective)

    assert precheck.status == "READY"
    assert result.status in ("OPTIMAL", "FEASIBLE")
    assert len(rows) == len(demo.sections) == 12
    assert report.passed, report.findings
    assert report.objective == result.objective


# Dominio vacío e infactibilidad --------------------------------------------------------


def test_model_refuses_sections_without_alternatives(micro: Instance) -> None:
    sections = tuple(
        s.model_copy(update={"enrollment": 100}) if s.id == "S2" else s for s in micro.sections
    )
    connection = connect(":memory:")
    load_instance(connection, micro.model_copy(update={"sections": sections}))
    assert build_candidates(connection).status == "NO_CANDIDATES"

    with pytest.raises(ModelError, match="S2"):
        build_and_solve(connection, micro.config)


def test_globally_infeasible_with_nonempty_domains(micro: Instance) -> None:
    # S1 comparte G2 con S2: todos sus patrones chocan con la única alternativa de S2.
    groups = (*micro.section_groups, SectionGroup(section_id="S1", group_id="G2"))
    precheck, result = solve(micro.model_copy(update={"section_groups": groups}))

    assert precheck.status == "READY"
    assert result.status == "INFEASIBLE"
    assert result.assignments == ()
    assert (result.objective, result.cost_d, result.cost_e, result.best_bound) == (
        None,
        None,
        None,
        None,
    )


# Semanas disjuntas y coincidentes, por tipo de recurso ---------------------------------


def two_sections(micro: Instance, resource: str, s2_week: int) -> Instance:
    """S1 solo en la semana 1 con P2 (día 1, bloque 2); S2 usa P3 (día 1, bloques 1-2).

    Ambas comparten únicamente el recurso indicado, en el segundo bloque de la sesión de S2.
    """
    sections = []
    for section in micro.sections:
        if section.id == "S1" and resource == "room":
            section = section.model_copy(update={"enrollment": 40})  # solo cabe en R2
        if section.id == "S1" and resource == "teacher":
            section = section.model_copy(update={"teacher_id": "T2"})
        if section.id != "S3":
            sections.append(section)
    groups = [g for g in micro.section_groups if g.section_id != "S3"]
    if resource == "group":
        groups = [g for g in groups if g.section_id != "S1"]
        groups.append(SectionGroup(section_id="S1", group_id="G2"))
    features = [] if resource == "room" else list(micro.section_features)
    return micro.model_copy(
        update={
            "sections": tuple(sections),
            "section_groups": tuple(groups),
            "section_features": tuple(features),
            "section_weeks": (
                SectionWeek(section_id="S1", week_id=1),
                SectionWeek(section_id="S2", week_id=s2_week),
            ),
            "section_patterns": (
                SectionPattern(section_id="S1", pattern_id="P2"),
                SectionPattern(section_id="S2", pattern_id="P3"),
            ),
            "section_blocked": (),
        }
    )


@pytest.mark.parametrize("resource", ["room", "teacher", "group"])
def test_shared_resource_in_same_week_is_infeasible(micro: Instance, resource: str) -> None:
    _, result = solve(two_sections(micro, resource, s2_week=1))

    assert result.status == "INFEASIBLE"


@pytest.mark.parametrize("resource", ["room", "teacher", "group"])
def test_shared_resource_in_disjoint_weeks_is_allowed(micro: Instance, resource: str) -> None:
    instance = two_sections(micro, resource, s2_week=2)
    _, result = solve(instance)
    rows = [(a.section_id, a.pattern_id, a.room_id) for a in result.assignments]

    assert result.status == "OPTIMAL"
    assert audit(instance, rows, result.objective).passed


# Adaptador de estados con un lector simulado --------------------------------------------

ALTERNATIVES = [
    Alternative(1, "S1", "P1", "R1", cost_d=2, cost_e=1),
    Alternative(2, "S1", "P2", "R1", cost_d=0, cost_e=1),
    Alternative(3, "S2", "P3", "R2", cost_d=0, cost_e=1),
]


class FakeReader:
    def __init__(self, chosen: set[int], objective: float, bound: float) -> None:
        self.chosen, self.objective, self.bound = chosen, objective, bound

    def boolean_value(self, alt_id: int) -> bool:
        return alt_id in self.chosen

    def objective_value(self) -> float:
        return self.objective

    def best_objective_bound(self) -> float:
        return self.bound


class ForbiddenReader:
    """Falla si se consulta: sin solución no se leen valores ni objetivo."""

    def boolean_value(self, alt_id: int) -> bool:
        raise AssertionError("se leyó un valor sin solución")

    def objective_value(self) -> float:
        raise AssertionError("se leyó el objetivo sin solución")

    def best_objective_bound(self) -> float:
        raise AssertionError("se leyó la cota sin solución")


@pytest.mark.parametrize("status", ["OPTIMAL", "FEASIBLE"])
def test_solution_statuses_extract_assignments(micro: Instance, status: str) -> None:
    result = interpret(
        status, ALTERNATIVES, ["S1", "S2"], micro.config, FakeReader({2, 3}, 2.0, 1.0)
    )

    assert result.status == status  # FEASIBLE nunca se anuncia como óptimo
    assert result.objective == 10 * 0 + 1 * 2
    assert (result.cost_d, result.cost_e, result.best_bound) == (0, 2, 1.0)
    assert [a.pattern_id for a in result.assignments] == ["P2", "P3"]


@pytest.mark.parametrize("status", ["INFEASIBLE", "UNKNOWN", "MODEL_INVALID"])
def test_statuses_without_solution_read_nothing(micro: Instance, status: str) -> None:
    result = interpret(status, ALTERNATIVES, ["S1", "S2"], micro.config, ForbiddenReader())

    assert result.status == status
    assert result.assignments == ()
    assert result.objective is None
    assert result.best_bound is None


def test_unknown_status_name_is_an_error(micro: Instance) -> None:
    with pytest.raises(ModelError, match="desconocido"):
        interpret("SOMETHING", ALTERNATIVES, ["S1", "S2"], micro.config, ForbiddenReader())


def test_objective_mismatch_is_not_rounded_away(micro: Instance) -> None:
    with pytest.raises(SolverConsistencyError, match="2.4"):
        interpret("OPTIMAL", ALTERNATIVES, ["S1", "S2"], micro.config, FakeReader({2, 3}, 2.4, 2.0))


def test_solution_must_cover_each_section_once(micro: Instance) -> None:
    with pytest.raises(SolverConsistencyError):
        interpret(
            "FEASIBLE", ALTERNATIVES, ["S1", "S2"], micro.config, FakeReader({1, 2, 3}, 24.0, 0)
        )


def test_infinite_bound_is_reported_as_null(micro: Instance) -> None:
    result = interpret(
        "FEASIBLE", ALTERNATIVES, ["S1", "S2"], micro.config, FakeReader({2, 3}, 2.0, math.inf)
    )

    assert result.best_bound is None


# Parámetros y aritmética ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"random_seed": MAX_INT32 + 1}, "random_seed"),
        ({"num_search_workers": MAX_INT32 + 1}, "num_search_workers"),
        ({"time_limit_seconds": math.inf}, "time_limit_seconds"),
        ({"time_limit_seconds": math.nan}, "time_limit_seconds"),
        ({"alpha": 2**60}, "2\\*\\*53"),
    ],
)
def test_incompatible_parameters_are_reported(
    micro: Instance, update: dict[str, object], message: str
) -> None:
    config = micro.config.model_copy(update=update)

    with pytest.raises(SolverParameterError, match=message):
        check_parameters(config, ALTERNATIVES)


def test_objective_bound_is_exact_at_the_limit(micro: Instance) -> None:
    # Peor caso: S1 aporta alpha * 2 + 1 y S2 aporta 1.
    alpha = (MAX_EXACT_OBJECTIVE - 2) // 2
    check_parameters(micro.config.model_copy(update={"alpha": alpha}), ALTERNATIVES)

    with pytest.raises(SolverParameterError):
        check_parameters(micro.config.model_copy(update={"alpha": alpha + 1}), ALTERNATIVES)


def test_large_exact_weights_solve_without_loss(micro: Instance) -> None:
    alpha = 2**40
    _, result = solve(micro, alpha=alpha, beta=1)

    assert result.status == "OPTIMAL"
    assert result.objective == alpha * result.cost_d + result.cost_e
    assert result.solver_objective == float(result.objective)


def test_time_limit_override_is_applied(micro: Instance) -> None:
    connection = connect(":memory:")
    load_instance(connection, micro)
    build_candidates(connection)

    with pytest.raises(SolverParameterError, match="time_limit_seconds"):
        build_and_solve(connection, micro.config, time_limit_seconds=-1.0)
