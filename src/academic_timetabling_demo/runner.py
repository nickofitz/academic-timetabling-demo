"""Corridas reproducibles: snapshot, preparación, CP-SAT o voraz, auditoría y evidencia.

El orden es: validar entrada y configuración, cargar SQLite, preparar candidatos, resolver con
el método elegido si corresponde, auditar si hay asignación y exportar. Todo se lee del snapshot
`input/`, nunca del directorio original después de copiarlo.
"""

import csv
import io
import json
import math
import os
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from academic_timetabling_demo import report
from academic_timetabling_demo.baseline import COMPLETE, BaselineResult, run_greedy
from academic_timetabling_demo.candidates import build_candidates
from academic_timetabling_demo.compare import (
    CompareError,
    load_run,
    recheck,
    validate_costs,
    validate_status,
)
from academic_timetabling_demo.db import connect, load_instance
from academic_timetabling_demo.domain import (
    CONFIG_FILE,
    TABLES,
    DataValidationError,
    Instance,
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
    SolveResult,
    SolverParameterError,
    build_and_solve,
)
from academic_timetabling_demo.synthetic import FORMAT_VERSION, MANIFEST_FILE, source_hash
from academic_timetabling_demo.validate import (
    ASSIGNMENT_COLUMNS,
    NOT_RUN,
    audit,
    read_assignments,
)

SOLVERS = ("cp-sat", "greedy")
SCHEDULE_FILES = ("schedule.csv", "schedule.html")
INPUT_FILES = (*(spec.file for spec in TABLES), CONFIG_FILE)
HASH_POLICY = "sha256 de los bytes exactos de cada archivo del snapshot"
GREEDY_NOTE = (
    "La heurística voraz no usa time_limit_seconds, random_seed ni num_search_workers; "
    "se registran solo para trazabilidad."
)

EXIT_OK = 0
EXIT_INVALID = 2
EXIT_NO_SOLUTION = 3
EXIT_AUDIT_FAILED = 4
EXIT_INTERNAL = 5


class RunInputError(ValueError):
    """Argumentos de corrida inválidos detectados antes de crear la salida."""


class EnvironmentCheckError(RuntimeError):
    """El entorno no admite una función que la preparación necesita."""


class ExportError(RuntimeError):
    """Las exportaciones no pudieron generarse o verificarse."""


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
            "baseline": None,
            "audit": "NOT_RUN",
            "integrity": None,
            "result_valid": None,
        }
    )
    diagnostics: dict[str, object] = field(default_factory=dict)
    audit_report: dict[str, object] = field(default_factory=lambda: dict(NOT_RUN))
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


def _snapshot(input_dir: Path, target: Path) -> tuple[dict[str, object], dict[str, bytes]]:
    """Copia las fuentes leyendo cada archivo una vez; el hash es de esos bytes exactos."""
    target.mkdir()
    contents: dict[str, bytes] = {}
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
        contents[name] = content
    hashes = {name: sha256_bytes(content) for name, content in contents.items()}
    snapshot = {
        "hash_policy": HASH_POLICY,
        "files": hashes,
        "combined_sha256": combined_hash(hashes),
        "missing": missing,
        "unreadable": unreadable,
        "complete": not missing and not unreadable,
    }
    return snapshot, contents


def _os_error(error: OSError) -> str:
    return f"{type(error).__name__}: {error.strerror or error}"


def _provenance_record(status: str, detail: str, manifest: str | None = None) -> dict[str, object]:
    return {
        "status": status,
        "data_seed": None,
        "case": None,
        "format_version": None,
        "manifest_sha256": manifest,
        "detail": detail,
    }


def read_provenance(input_dir: Path, contents: dict[str, bytes]) -> dict[str, object]:
    """Procedencia declarada por generation.json, verificada contra los bytes copiados.

    El manifiesto es solo metadato: no se copia a input/, no entra en el hash de entradas y su
    testigo no se entrega a ningún método. Sin un manifiesto coherente, la semilla queda null.
    """
    path = input_dir / MANIFEST_FILE
    if not path.is_file():
        return _provenance_record("ABSENT", f"la entrada no tiene {MANIFEST_FILE}")
    try:
        raw = path.read_bytes()
    except OSError as error:
        return _provenance_record("INVALID", f"no se pudo leer {MANIFEST_FILE}: {_os_error(error)}")
    digest = sha256_bytes(raw)

    def reject(name: str) -> None:
        raise ValueError(f"valor no permitido: {name}")

    try:
        data = json.loads(raw.decode("utf-8"), parse_constant=reject)
    except (UnicodeDecodeError, ValueError) as error:
        return _provenance_record("INVALID", f"{MANIFEST_FILE} no es JSON válido: {error}", digest)

    def integer(value: object) -> bool:
        return isinstance(value, int) and not isinstance(value, bool)

    sources = data.get("sources") if isinstance(data, dict) else None
    problems = []
    if not isinstance(data, dict):
        problems.append("no es un objeto")
    else:
        if not isinstance(data.get("case"), str) or not data["case"]:
            problems.append("case")
        if not integer(data.get("seed")) or data["seed"] < 0:
            problems.append("seed")
        if data.get("format_version") != FORMAT_VERSION or not integer(data["format_version"]):
            problems.append("format_version")
        if not isinstance(sources, dict) or not all(
            isinstance(k, str) and isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}", v)
            for k, v in sources.items()
        ):
            problems.append("sources")
    if problems:
        return _provenance_record(
            "INVALID", f"estructura inválida en {MANIFEST_FILE}: {', '.join(problems)}", digest
        )

    declared = set(sources)
    if declared != set(INPUT_FILES):
        detail = f"{MANIFEST_FILE} declara otras fuentes: {sorted(declared ^ set(INPUT_FILES))}"
        return _provenance_record("MISMATCH", detail, digest)
    changed = sorted(
        name
        for name in INPUT_FILES
        if name not in contents or source_hash(contents[name]) != sources[name]
    )
    if changed:
        detail = f"las fuentes no coinciden con {MANIFEST_FILE}: {', '.join(changed)}"
        return _provenance_record("MISMATCH", detail, digest)
    return {
        "status": "VERIFIED",
        "data_seed": data["seed"],
        "case": data["case"],
        "format_version": data["format_version"],
        "manifest_sha256": digest,
        "detail": f"{MANIFEST_FILE} coincide con las 21 fuentes (hash normalizado a LF)",
    }


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
        raise RunInputError(f"solver no implementado: {solver}")
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
    if solver == "greedy":
        parameters["note"] = GREEDY_NOTE
    snapshot: dict[str, object] = {}
    provenance: dict[str, object] | None = None
    result_summary: dict[str, object] = {}
    exit_code = EXIT_INTERNAL

    try:
        check_sqlite()
        started = time.perf_counter()
        snapshot, contents = _snapshot(input_dir, out / "input")
        provenance = read_provenance(input_dir, contents)
        state.timed("snapshot", started)
        exit_code = _execute(state, parameters, snapshot, result_summary)
    except EnvironmentCheckError as error:
        state.error = str(error)
        exit_code = EXIT_INTERNAL
    except Exception as error:
        state.error = f"error interno: {type(error).__name__}: {error}"
        exit_code = EXIT_INTERNAL

    if not _check_integrity(state, input_dir, snapshot):
        # Fallo de integridad, no matemático: los estados del método y de auditoría se conservan.
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

    # Las exportaciones solo se intentan para una corrida completa, auditada e íntegra.
    state.status["export"] = "PENDING" if exit_code == EXIT_OK else "NOT_APPLICABLE"
    state.status["deliverable"] = False
    state.timings["total"] = time.perf_counter() - state.started
    metrics = {
        "run_id": state.run_id,
        "created_utc": state.created_utc,
        "exit_code": exit_code,
        "error": state.error,
        "status": state.status,
        "parameters": parameters,
        "provenance": provenance,
        "input": {"directory": str(input_dir), **snapshot},
        "environment": environment(),
        "timings_seconds": state.timings,
        "export": {"files": {}, "error": None},
        **result_summary,
    }
    (out / "metrics.json").write_bytes(json_bytes(metrics))
    (out / "diagnostics.json").write_bytes(json_bytes(state.diagnostics))
    (out / "audit.json").write_bytes(json_bytes(state.audit_report))
    if exit_code == EXIT_OK:
        exit_code = _export(state, metrics, snapshot)
        metrics["exit_code"] = exit_code
        metrics["error"] = state.error
        state.timings["total"] = time.perf_counter() - state.started
        (out / "metrics.json").write_bytes(json_bytes(metrics))
    return RunOutcome(exit_code, out, metrics)


def _replace(source: Path, target: Path) -> None:
    os.replace(source, target)


EVIDENCE_FILES = ("assignments.csv", "effective_config.json")


def _evidence_hashes(out: Path) -> dict[str, str]:
    return {name: sha256_bytes((out / name).read_bytes()) for name in EVIDENCE_FILES}


def _check_evidence(out: Path, captured: dict[str, str], moment: str) -> None:
    """Las asignaciones y la configuración efectiva siguen siendo las validadas y exportadas."""
    current = _evidence_hashes(out)
    changed = sorted(name for name in EVIDENCE_FILES if current[name] != captured[name])
    if changed:
        raise ExportError(
            f"{', '.join(changed)} cambió {moment}: no corresponde a la evidencia validada"
        )


def _export(state: _Run, metrics: dict[str, object], snapshot: dict[str, object]) -> int:
    """Genera schedule.csv y schedule.html en temporales y los publica solo si todo verifica.

    La corrida se revalida con las mismas comprobaciones públicas de `compare` (integridad,
    estados, costos enteros y nueva auditoría contra el snapshot). Ante cualquier fallo no queda
    ningún archivo final de exportación: código 5 y la corrida no es entregable.
    """
    out = state.out
    started = time.perf_counter()
    staging = {name: out / f".{name}.tmp" for name in SCHEDULE_FILES}
    created: list[Path] = []
    try:
        # Bytes de la evidencia antes de validarla: lo exportado debe corresponder a ellos.
        captured = _evidence_hashes(out)
        evidence = load_run(out)
        validate_status(evidence)
        validate_costs(evidence)
        recheck(evidence)
        instance = read_instance(out / "input")
        assignments = read_assignments(out / "assignments.csv")
        _check_evidence(out, captured, "mientras se validaba y leía")
        rows = report.session_rows(instance, assignments)
        contents = {
            "schedule.csv": report.schedule_csv(state.run_id, rows),
            "schedule.html": report.render_html(
                report.presentation(instance, rows, evidence.config, metrics)
            ),
        }
        for name in SCHEDULE_FILES:
            staging[name].write_bytes(contents[name])
            created.append(staging[name])
        verified, changed, problem = _compare(out / "input", snapshot["files"])
        if not verified:
            raise ExportError(f"el snapshot cambió durante la exportación: {changed or problem}")
        _check_evidence(out, captured, "durante la exportación")
        # Contraste explícito con lo exportado: mismos triples y misma configuración efectiva.
        if sorted(read_assignments(out / "assignments.csv")) != sorted(assignments):
            raise ExportError("assignments.csv ya no contiene los triples exportados")
        effective = RunConfig.model_validate_json((out / "effective_config.json").read_bytes())
        if effective != evidence.config:
            raise ExportError("effective_config.json ya no es la configuración exportada")
        for name in SCHEDULE_FILES:
            if staging[name].read_bytes() != contents[name]:
                raise ExportError(f"{name} no quedó escrito con los bytes generados")
        for name in SCHEDULE_FILES:
            _replace(staging[name], out / name)
            created.remove(staging[name])
            created.append(out / name)
    except Exception as error:
        # Se eliminan solo los temporales y finales creados por este intento.
        for path in created:
            path.unlink(missing_ok=True)
        detail = error.reason if isinstance(error, CompareError) else str(error)
        state.status["export"] = "FAILED"
        state.status["deliverable"] = False
        state.error = (
            f"la exportación falló ({type(error).__name__}: {detail}); "
            "la corrida no está lista para entregar"
        )
        metrics["export"] = {"files": {}, "error": state.error}
        state.timed("export", started)
        return EXIT_INTERNAL
    state.status["export"] = "WRITTEN"
    state.status["deliverable"] = True
    metrics["export"] = {
        "files": {name: sha256_bytes(contents[name]) for name in SCHEDULE_FILES},
        "sessions": len(rows),
        "error": None,
    }
    state.timed("export", started)
    return EXIT_OK


def _execute(
    state: _Run,
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
            state.error = "hay secciones sin alternativas; no se ejecutó ningún método"
            return EXIT_NO_SOLUTION

        if parameters["solver"] == "greedy":
            baseline = run_greedy(connection, config)
        else:
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

    if parameters["solver"] == "greedy":
        return _finish_greedy(state, instance, config, baseline, summary)
    return _finish_cpsat(state, instance, config, result, summary)


def _record_assignments(
    state: _Run, instance: Instance, rows: list[tuple[str, str, str]], summary: dict[str, object]
) -> None:
    (state.out / "assignments.csv").write_bytes(_assignments_csv(sorted(rows)))
    summary["counts"]["assigned_sections"] = len(rows)
    total = len(instance.sections)
    summary["counts"]["coverage"] = len(rows) / total if total else None


def _finish_cpsat(
    state: _Run,
    instance: Instance,
    config: RunConfig,
    result: SolveResult,
    summary: dict[str, object],
) -> int:
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
    _record_assignments(state, instance, rows, summary)
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


def _finish_greedy(
    state: _Run,
    instance: Instance,
    config: RunConfig,
    baseline: BaselineResult,
    summary: dict[str, object],
) -> int:
    state.timings["baseline"] = baseline.seconds
    state.status["baseline"] = baseline.status
    rows = [(c.section_id, c.pattern_id, c.room_id) for c in baseline.assignments]
    _record_assignments(state, instance, rows, summary)
    complete = baseline.status == COMPLETE
    state.diagnostics["baseline"] = {
        "status": baseline.status,
        "order": list(baseline.order),
        "chosen_in_order": [list(row) for row in rows],
        "blocked_section": baseline.blocked_section,
        "remaining_sections": list(baseline.remaining_sections),
        "partial_costs": None
        if complete
        else {
            "cost_d": baseline.cost_d,
            "cost_e": baseline.cost_e,
            "objective": baseline.objective,
            "comparable": False,
            "note": "costo del prefijo elegido; no es el costo de un horario completo",
        },
        "note": GREEDY_NOTE,
    }
    if complete:
        summary["costs"].update(
            cost_d=baseline.cost_d, cost_e=baseline.cost_e, objective=baseline.objective
        )

    # El prefijo también pasa por el auditor completo, con su propio costo como contraste.
    started = time.perf_counter()
    report = audit(instance, rows, baseline.objective, config)
    state.timed("audit", started)
    state.audit_report = report.as_dict()
    state.status["audit"] = report.status

    if complete:
        state.status["result_valid"] = report.passed
        if not report.passed:
            state.error = (
                "la auditoría falló: assignments.csv se conserva solo como evidencia inválida"
            )
            return EXIT_AUDIT_FAILED
        return EXIT_OK

    state.status["result_valid"] = False
    missing = {f.section_ids[0] for f in report.findings if f.rule == "MISSING_ASSIGNMENT"}
    other = [f for f in report.findings if f.rule != "MISSING_ASSIGNMENT"]
    if not other and missing == set(baseline.remaining_sections):
        state.error = (
            f"la heurística se atascó en {baseline.blocked_section}; assignments.csv contiene "
            "solo el prefijo elegido y no es comparable"
        )
        return EXIT_NO_SOLUTION
    state.error = "el prefijo de la heurística no es válido según la auditoría"
    return EXIT_AUDIT_FAILED
