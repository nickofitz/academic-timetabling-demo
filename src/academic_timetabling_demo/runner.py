"""Corridas reproducibles: snapshot, preparación, CP-SAT, auditoría y evidencia (Hito 3).

El orden es: validar entrada y configuración, cargar SQLite, preparar candidatos, resolver si
corresponde, auditar si hay asignación y exportar. Todo se lee del snapshot `input/`, nunca del
directorio original después de copiarlo.
"""

import csv
import io
import json
import math
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from academic_timetabling_demo.candidates import build_candidates
from academic_timetabling_demo.db import connect, load_instance
from academic_timetabling_demo.domain import (
    CONFIG_FILE,
    TABLES,
    DataValidationError,
    Issue,
    RunConfig,
    read_instance,
)
from academic_timetabling_demo.metrics import (
    combined_hash,
    environment,
    json_bytes,
    relative_gap,
    sha256_bytes,
)
from academic_timetabling_demo.model import (
    SOLUTION_STATUSES,
    ModelError,
    SolverParameterError,
    build_and_solve,
)
from academic_timetabling_demo.validate import ASSIGNMENT_COLUMNS, NOT_RUN, audit

SOLVERS = ("cp-sat",)
INPUT_FILES = (*(spec.file for spec in TABLES), CONFIG_FILE)
HASH_POLICY = "sha256 de los bytes exactos de cada archivo del snapshot"

EXIT_OK = 0
EXIT_INVALID = 2
EXIT_NO_SOLUTION = 3
EXIT_AUDIT_FAILED = 4
EXIT_INTERNAL = 5


class RunInputError(ValueError):
    """Argumentos de corrida inválidos detectados antes de crear la salida."""


class EnvironmentCheckError(RuntimeError):
    """El entorno no admite una función que la preparación necesita."""


@dataclass(frozen=True)
class RunOutcome:
    exit_code: int
    out: Path
    metrics: dict[str, object]


@dataclass
class _Run:
    out: Path
    run_id: str
    created_utc: str
    started: float
    timings: dict[str, float] = field(default_factory=dict)
    status: dict[str, object] = field(
        default_factory=lambda: {
            "data": None,
            "precheck": None,
            "solver": None,
            "audit": "NOT_RUN",
            "integrity": None,
            "result_valid": None,
        }
    )
    diagnostics: dict[str, object] = field(default_factory=dict)
    audit_report: dict[str, object] = field(default_factory=lambda: dict(NOT_RUN))
    sections: dict[str, object] = field(default_factory=dict)
    error: str | None = None

    def timed(self, name: str, started: float) -> None:
        self.timings[name] = time.perf_counter() - started


def check_sqlite() -> None:
    """La preparación del Hito 2 ordena dentro de json_group_array (SQLite >= 3.44)."""
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("SELECT json_group_array(x ORDER BY x) FROM (SELECT 1 AS x)")
    except sqlite3.Error as error:
        raise EnvironmentCheckError(
            f"SQLite {sqlite3.sqlite_version} no admite ORDER BY dentro de json_group_array "
            f"({error}); se requiere SQLite 3.44 o posterior"
        ) from None
    finally:
        connection.close()


def _inside(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def check_paths(input_dir: Path, out: Path) -> None:
    if not input_dir.is_dir():
        raise RunInputError(f"la carpeta de entrada no existe: {input_dir}")
    source, target = input_dir.resolve(), out.resolve()
    if _inside(target, source):
        raise RunInputError("la salida no puede ser la entrada ni estar dentro de ella")
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise RunInputError(f"la salida ya existe y no está vacía: {out}")


def effective_config(
    original: RunConfig, time_limit: float | None, seed: int | None
) -> tuple[RunConfig, dict[str, object]]:
    """Aplica los overrides de CLI y devuelve también cuáles se aplicaron."""
    overrides: dict[str, object] = {}
    if time_limit is not None:
        if not math.isfinite(time_limit) or time_limit <= 0:
            raise RunInputError("--time-limit debe ser positivo y finito")
        overrides["time_limit_seconds"] = time_limit
    if seed is not None:
        overrides["random_seed"] = seed
    config = RunConfig.model_validate({**original.model_dump(), **overrides})
    return config, overrides


def _snapshot(input_dir: Path, target: Path) -> dict[str, object]:
    """Copia las fuentes leyendo cada archivo una vez; el hash es de esos bytes exactos."""
    target.mkdir()
    hashes: dict[str, str] = {}
    missing = []
    unreadable: dict[str, str] = {}
    for name in INPUT_FILES:
        source = input_dir / name
        if not source.is_file():
            missing.append(name)
            continue
        try:
            content = source.read_bytes()
        except OSError as error:
            # Queda fuera del snapshot; la validación lo informará como fuente ausente.
            unreadable[name] = _os_error(error)
            continue
        (target / name).write_bytes(content)
        hashes[name] = sha256_bytes(content)
    return {
        "hash_policy": HASH_POLICY,
        "files": hashes,
        "combined_sha256": combined_hash(hashes),
        "missing": missing,
        "unreadable": unreadable,
        "complete": not missing and not unreadable,
    }


def _os_error(error: OSError) -> str:
    return f"{type(error).__name__}: {error.strerror or error}"


def _rehash(directory: Path, names: list[str]) -> dict[str, str | None]:
    return {
        name: sha256_bytes((directory / name).read_bytes())
        if (directory / name).is_file()
        else None
        for name in names
    }


def _compare(
    directory: Path, expected: dict[str, str]
) -> tuple[bool | None, list[str], str | None]:
    """Compara hashes actuales con los esperados: (coinciden, archivos distintos, error)."""
    try:
        actual = _rehash(directory, sorted(expected))
    except OSError as error:
        return None, [], _os_error(error)
    changed = sorted(name for name, digest in expected.items() if actual.get(name) != digest)
    return not changed, changed, None


def _check_integrity(state: _Run, input_dir: Path, snapshot: dict[str, object]) -> bool:
    """Verifica al final que el snapshot conservado es el que se resolvió y auditó.

    Un cambio solo en el directorio original se registra, pero no invalida la corrida.
    Devuelve False si el snapshot cambió o no pudo verificarse.
    """
    expected = snapshot.get("files")
    if not expected:
        return True
    verified, changed, problem = _compare(state.out / "input", expected)
    unchanged, source_changed, source_problem = _compare(input_dir, expected)
    snapshot["snapshot_verified"] = verified
    snapshot["source_unchanged"] = unchanged
    state.diagnostics["integrity"] = {
        "snapshot_changed": changed,
        "snapshot_check_error": problem,
        "source_changed": source_changed,
        "source_check_error": source_problem,
    }
    if verified:
        state.status["integrity"] = "VERIFIED"
        return True
    state.status["integrity"] = "FAILED" if verified is False else "NOT_VERIFIED"
    return False


def _assignments_csv(rows: list[tuple[str, str, str]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(ASSIGNMENT_COLUMNS)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _issues(issues: tuple[Issue, ...]) -> list[dict[str, object]]:
    return [{"file": i.file, "row": i.row, "field": i.field, "message": i.message} for i in issues]


def run(
    input_dir: Path,
    out: Path,
    *,
    solver: str = "cp-sat",
    time_limit: float | None = None,
    seed: int | None = None,
) -> RunOutcome:
    """Ejecuta una corrida completa. Lanza RunInputError antes de crear la salida."""
    if solver not in SOLVERS:
        raise RunInputError(f"solver no implementado en este hito: {solver}")
    if seed is not None and seed < 0:
        raise RunInputError("--seed debe ser un entero no negativo")
    check_paths(input_dir, out)

    out.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    state = _Run(
        out=out,
        run_id=f"{now:%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}",
        created_utc=now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        started=time.perf_counter(),
    )
    parameters: dict[str, object] = {
        "solver": solver,
        "requested_overrides": {"time_limit_seconds": time_limit, "random_seed": seed},
    }
    snapshot: dict[str, object] = {}
    result_summary: dict[str, object] = {}
    exit_code = EXIT_INTERNAL

    try:
        check_sqlite()
        started = time.perf_counter()
        snapshot = _snapshot(input_dir, out / "input")
        state.timed("snapshot", started)
        exit_code = _execute(state, input_dir, parameters, snapshot, result_summary)
    except EnvironmentCheckError as error:
        state.error = str(error)
        exit_code = EXIT_INTERNAL
    except Exception as error:
        state.error = f"error interno: {type(error).__name__}: {error}"
        exit_code = EXIT_INTERNAL

    if not _check_integrity(state, input_dir, snapshot):
        # Fallo de integridad, no matemático: los estados de solver y auditoría se conservan.
        integrity = state.diagnostics["integrity"]
        if state.status["integrity"] == "FAILED":
            detail = f"el snapshot cambió tras copiarse: {', '.join(integrity['snapshot_changed'])}"
        else:
            detail = f"no se pudo verificar el snapshot: {integrity['snapshot_check_error']}"
        problem = f"integridad: {detail}; la corrida no es reproducible ni válida"
        state.error = f"{state.error}; {problem}" if state.error else problem
        if state.status["result_valid"] is True:
            state.status["result_valid"] = False
        exit_code = EXIT_INTERNAL
    state.timings["total"] = time.perf_counter() - state.started
    metrics = {
        "run_id": state.run_id,
        "created_utc": state.created_utc,
        "exit_code": exit_code,
        "error": state.error,
        "status": state.status,
        "parameters": parameters,
        "input": {"directory": str(input_dir), **snapshot},
        "environment": environment(),
        "timings_seconds": state.timings,
        **result_summary,
    }
    (out / "metrics.json").write_bytes(json_bytes(metrics))
    (out / "diagnostics.json").write_bytes(json_bytes(state.diagnostics))
    (out / "audit.json").write_bytes(json_bytes(state.audit_report))
    return RunOutcome(exit_code, out, metrics)


def _execute(
    state: _Run,
    input_dir: Path,
    parameters: dict[str, object],
    snapshot: dict[str, object],
    summary: dict[str, object],
) -> int:
    out = state.out
    started = time.perf_counter()
    try:
        instance = read_instance(out / "input")
    except DataValidationError as error:
        state.status["data"] = "INVALID"
        state.diagnostics["data_errors"] = _issues(error.issues)
        state.error = "datos de entrada inválidos"
        return EXIT_INVALID
    state.timed("validation", started)
    state.status["data"] = "VALID"

    try:
        config, overrides = effective_config(
            instance.config,
            parameters["requested_overrides"]["time_limit_seconds"],
            parameters["requested_overrides"]["random_seed"],
        )
    except (RunInputError, ValueError) as error:
        state.error = f"configuración efectiva inválida: {error}"
        return EXIT_INVALID
    effective_bytes = json_bytes(config.model_dump())
    (out / "effective_config.json").write_bytes(effective_bytes)
    parameters["original_config"] = instance.config.model_dump()
    parameters["applied_overrides"] = overrides
    parameters["effective_config"] = config.model_dump()
    snapshot["effective_config_sha256"] = sha256_bytes(effective_bytes)

    connection = connect(":memory:")
    try:
        started = time.perf_counter()
        load_instance(connection, instance)
        state.timed("load", started)

        started = time.perf_counter()
        precheck = build_candidates(connection)
        state.timed("candidates", started)
        state.status["precheck"] = precheck.status
        state.diagnostics["precheck"] = precheck.as_dict()
        state.diagnostics["discarded_alternatives"] = [
            {
                "section_id": s,
                "pattern_id": p,
                "room_id": r,
                "rule": rule,
                "evidence": json.loads(evidence),
            }
            for s, p, r, rule, evidence in connection.execute(
                "SELECT section_id, pattern_id, room_id, rule, evidence_json "
                "FROM discarded_alternative ORDER BY 1, 2, 3, 4"
            )
        ]
        summary["counts"] = {
            "sections": len(instance.sections),
            "assigned_sections": 0,
            "coverage": 0.0 if instance.sections else None,
            "pairs_before": precheck.pairs_before,
            "alternatives_after": precheck.alternatives_after,
            "discarded_pairs": precheck.discarded_pairs,
            "occupancy_rows": precheck.occupancy_rows,
        }
        summary["costs"] = {
            "cost_d": None,
            "cost_e": None,
            "objective": None,
            "solver_objective": None,
            "best_bound": None,
            "relative_gap": None,
        }
        if precheck.status != "READY":
            state.error = "hay secciones sin alternativas; no se invocó el solver"
            return EXIT_NO_SOLUTION

        try:
            result = build_and_solve(connection, config)
        except SolverParameterError as error:
            state.error = f"parámetros incompatibles con CP-SAT: {error}"
            return EXIT_INVALID
        except ModelError as error:
            state.error = f"error del modelo: {error}"
            return EXIT_INTERNAL
    finally:
        connection.close()

    state.timings["build"] = result.build_seconds
    state.timings["solve"] = result.solve_seconds
    state.status["solver"] = result.status
    summary["model"] = {
        "variables": result.num_variables,
        "constraints": result.num_constraints,
        "conflict_constraints": result.num_conflict_constraints,
    }
    if result.status not in SOLUTION_STATUSES:
        state.error = f"CP-SAT terminó con estado {result.status}, sin solución"
        return EXIT_INTERNAL if result.status == "MODEL_INVALID" else EXIT_NO_SOLUTION

    rows = [(a.section_id, a.pattern_id, a.room_id) for a in result.assignments]
    (out / "assignments.csv").write_bytes(_assignments_csv(rows))
    summary["counts"]["assigned_sections"] = len(rows)
    total = len(instance.sections)
    summary["counts"]["coverage"] = len(rows) / total if total else None
    summary["costs"] = {
        "cost_d": result.cost_d,
        "cost_e": result.cost_e,
        "objective": result.objective,
        "solver_objective": result.solver_objective,
        "best_bound": result.best_bound,
        "relative_gap": relative_gap(result.objective, result.best_bound),
    }

    started = time.perf_counter()
    report = audit(instance, rows, result.objective, config)
    state.timed("audit", started)
    state.audit_report = report.as_dict()
    state.status["audit"] = report.status
    state.status["result_valid"] = report.passed
    if not report.passed:
        state.error = "la auditoría falló: assignments.csv se conserva solo como evidencia inválida"
        return EXIT_AUDIT_FAILED
    return EXIT_OK
