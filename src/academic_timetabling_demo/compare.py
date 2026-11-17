"""Comparación entre una corrida voraz y una CP-SAT de los mismos datos y pesos (Hito 4).

No vuelve a optimizar ni importa candidatos, modelo o corredor. Por cada corrida valida, en este
orden: estructura e integridad del snapshot y de la configuración efectiva; que haya una solución
completa; y, por último, una nueva auditoría contra el snapshot. Solo entonces compara costos.
"""

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from academic_timetabling_demo.domain import (
    CONFIG_FILE,
    TABLES,
    DataValidationError,
    RunConfig,
    read_instance,
)
from academic_timetabling_demo.metrics import combined_hash, json_bytes, sha256_bytes
from academic_timetabling_demo.validate import AssignmentsError, audit, read_assignments

INPUT_FILES = frozenset((*(spec.file for spec in TABLES), CONFIG_FILE))
METHODS = ("greedy", "cp-sat")
CPSAT_SOLUTIONS = ("OPTIMAL", "FEASIBLE")

EXIT_OK = 0
EXIT_INVALID = 2
EXIT_NOT_COMPARABLE = 3
EXIT_AUDIT_FAILED = 4
EXIT_INTERNAL = 5


class CompareError(Exception):
    """La comparación no puede hacerse; `code` es el código de salida que corresponde."""

    def __init__(self, code: int, reason: str) -> None:
        self.code = code
        self.reason = reason
        super().__init__(reason)


class OutputError(ValueError):
    """--out no es utilizable: se informa por stderr sin escribir nada."""


@dataclass
class RunEvidence:
    path: Path
    run_id: str
    method: str
    metrics: dict
    config: RunConfig
    input_sha256: str
    audit_check: dict = field(default_factory=dict)

    def summary(self) -> dict[str, object]:
        metrics = self.metrics
        status = metrics.get("status", {})
        return {
            "path": str(self.path),
            "run_id": self.run_id,
            "method": self.method,
            "status": {
                "solver": status.get("solver"),
                "baseline": status.get("baseline"),
                "audit": status.get("audit"),
                "integrity": status.get("integrity"),
                "result_valid": status.get("result_valid"),
            },
            "coverage": (metrics.get("counts") or {}).get("coverage"),
            "costs": metrics.get("costs"),
            "effective_config": self.config.model_dump(),
            "timings_seconds": metrics.get("timings_seconds"),
            "provenance": metrics.get("provenance"),
            "environment": metrics.get("environment"),
            "audit_recheck": self.audit_check or None,
        }


def _invalid(reason: str) -> CompareError:
    return CompareError(EXIT_INVALID, reason)


def _read_json(path: Path) -> object:
    def reject(name: str) -> None:
        raise ValueError(f"valor no permitido: {name}")

    try:
        return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject)
    except FileNotFoundError:
        raise _invalid(f"falta {path}") from None
    except OSError as error:
        raise _invalid(
            f"no se pudo leer {path}: {type(error).__name__}: {error.strerror}"
        ) from None
    except (UnicodeDecodeError, ValueError) as error:
        raise _invalid(f"{path} no es JSON válido: {error}") from None


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        raise _invalid(f"falta {path}") from None
    except OSError as error:
        raise _invalid(
            f"no se pudo leer {path}: {type(error).__name__}: {error.strerror}"
        ) from None


def load_run(path: Path) -> RunEvidence:
    """Lee una corrida y comprueba su estructura e integridad (errores de código 2)."""
    if not path.is_dir():
        raise _invalid(f"no es un directorio de corrida: {path}")
    metrics = _read_json(path / "metrics.json")
    if not isinstance(metrics, dict):
        raise _invalid(f"{path / 'metrics.json'} no es un objeto")
    run_id = metrics.get("run_id")
    parameters = metrics.get("parameters")
    status = metrics.get("status")
    record = metrics.get("input")
    if not isinstance(run_id, str) or not run_id:
        raise _invalid(f"{path}: falta run_id")
    if (
        not isinstance(parameters, dict)
        or not isinstance(status, dict)
        or not isinstance(record, dict)
    ):
        raise _invalid(f"{path}: metrics.json no tiene parameters, status e input")
    method = parameters.get("solver")
    if method not in METHODS:
        raise _invalid(f"{path}: método inesperado {method!r}")

    # Integridad registrada por la propia corrida (ausente en corridas anteriores a la corrección).
    if (
        status.get("integrity", "VERIFIED") != "VERIFIED"
        or record.get("snapshot_verified") is False
    ):
        raise _invalid(f"{path}: la corrida registró un fallo de integridad del snapshot")
    if status.get("data") != "VALID":
        raise _invalid(f"{path}: la corrida no tiene datos válidos")

    # Snapshot: se recalculan los hashes desde input/ y se cotejan con lo registrado.
    files = record.get("files")
    if record.get("complete") is not True or not isinstance(files, dict):
        raise _invalid(f"{path}: el snapshot no está completo")
    snapshot_dir = path / "input"
    if not snapshot_dir.is_dir():
        raise _invalid(f"{path}: falta input/")
    present = {p.name for p in snapshot_dir.iterdir()}
    if set(files) != INPUT_FILES or present != INPUT_FILES:
        raise _invalid(f"{path}: input/ no contiene exactamente las 21 fuentes registradas")
    actual = {name: sha256_bytes(_read_bytes(snapshot_dir / name)) for name in sorted(files)}
    changed = sorted(name for name in files if files[name] != actual[name])
    if changed:
        raise _invalid(f"{path}: el snapshot cambió después de la corrida: {', '.join(changed)}")
    recorded_global = record.get("combined_sha256")
    if recorded_global != combined_hash(actual):
        raise _invalid(f"{path}: el hash global registrado no coincide con input/")

    # Configuración efectiva: bytes contra su hash y contenido contra lo registrado.
    config_bytes = _read_bytes(path / "effective_config.json")
    if sha256_bytes(config_bytes) != record.get("effective_config_sha256"):
        raise _invalid(f"{path}: effective_config.json no coincide con su hash registrado")
    try:
        config = RunConfig.model_validate_json(config_bytes)
    except ValueError as error:
        raise _invalid(f"{path}: effective_config.json inválido: {error}") from None
    if config.model_dump() != parameters.get("effective_config"):
        raise _invalid(f"{path}: effective_config.json difiere de la configuración registrada")
    return RunEvidence(path, run_id, method, metrics, config, recorded_global)


def not_comparable_reason(run: RunEvidence) -> str | None:
    """Motivo por el que una corrida legítima no tiene solución completa, o None."""
    status = run.metrics["status"]
    if run.method == "greedy":
        if status.get("baseline") != "COMPLETE":
            precheck = status.get("precheck")
            label = status.get("baseline") or f"sin ejecutar (precheck {precheck})"
            return f"greedy {run.run_id}: {label}"
        return None
    solver = status.get("solver")
    if solver not in CPSAT_SOLUTIONS:
        label = solver or f"sin ejecutar (precheck {status.get('precheck')})"
        return f"cp-sat {run.run_id}: {label}"
    return None


def recheck(run: RunEvidence) -> None:
    """Vuelve a auditar assignments.csv contra el snapshot; lanza código 4 si es inválido."""
    status = run.metrics["status"]
    costs = run.metrics.get("costs") or {}
    try:
        instance = read_instance(run.path / "input")
    except DataValidationError as error:
        raise _invalid(f"{run.path}: el snapshot no es una entrada válida: {error}") from None
    except OSError as error:
        raise _invalid(f"{run.path}: no se pudo leer input/: {error}") from None
    try:
        rows = read_assignments(run.path / "assignments.csv")
    except AssignmentsError as error:
        raise _invalid(f"{run.path}: {error}") from None
    stored = _read_json(run.path / "audit.json")
    reported = costs.get("objective")
    report = audit(instance, rows, reported if isinstance(reported, int) else None, run.config)
    run.audit_check = {
        "status": report.status,
        "cost_d": report.cost_d,
        "cost_e": report.cost_e,
        "objective": report.objective,
        "findings": sorted({f.rule for f in report.findings}),
    }
    problems = []
    if not report.passed:
        problems.append(f"la nueva auditoría falla ({', '.join(run.audit_check['findings'])})")
    if (costs.get("cost_d"), costs.get("cost_e")) != (report.cost_d, report.cost_e):
        problems.append("los costos registrados no coinciden con los recalculados")
    if not isinstance(stored, dict) or stored.get("audit_valid") is not True:
        problems.append("audit.json no registra una auditoría válida")
    if status.get("result_valid") is not True:
        problems.append("la corrida no registra result_valid=true")
    if problems:
        raise CompareError(EXIT_AUDIT_FAILED, f"{run.method} {run.run_id}: {'; '.join(problems)}")


def cost_difference(greedy: int, cpsat: int) -> dict[str, object]:
    """Diferencia z_greedy - z_cpsat; positiva favorece a CP-SAT, negativa a la heurística."""
    absolute = greedy - cpsat
    percent = 100 * absolute / greedy if greedy > 0 else None
    if absolute > 0:
        verdict = "CP-SAT obtiene menor costo"
    elif absolute < 0:
        verdict = "la heurística obtiene menor costo"
    else:
        verdict = "empate"
    note = None if greedy > 0 else "costo base cero: el porcentaje no está definido"
    if percent is not None and not math.isfinite(percent):
        percent = None
    return {"absolute": absolute, "percent": percent, "verdict": verdict, "note": note}


def check_output(out: Path, runs: list[Path]) -> None:
    if out.exists():
        raise OutputError(f"--out ya existe y no se sobrescribe: {out}")
    target = out.resolve()
    for run in runs:
        root = run.resolve()
        if target == root or root in target.parents:
            raise OutputError(f"--out no puede quedar dentro de una corrida: {out}")


def compare_runs(paths: list[Path]) -> tuple[int, dict[str, object]]:
    """Compara dos corridas; devuelve el código y el informe, nunca resultados parciales."""
    report: dict[str, object] = {"runs_read": [str(p) for p in paths]}
    try:
        if len(paths) != 2:
            raise _invalid("compare necesita exactamente dos corridas")
        if paths[0].resolve() == paths[1].resolve():
            raise _invalid("las dos rutas apuntan a la misma corrida")
        runs = [load_run(path) for path in paths]
        report["run_ids"] = {run.method: run.run_id for run in runs}
        if runs[0].run_id == runs[1].run_id:
            raise _invalid(f"run_id duplicado: {runs[0].run_id}")
        if {run.method for run in runs} != set(METHODS):
            raise _invalid("se necesita una corrida greedy y una cp-sat")
        by_method = {run.method: run for run in runs}
        greedy, cpsat = by_method["greedy"], by_method["cp-sat"]
        if greedy.input_sha256 != cpsat.input_sha256:
            raise _invalid("las entradas difieren: el hash global de input/ no coincide")
        weights = {"alpha": greedy.config.alpha, "beta": greedy.config.beta}
        if weights != {"alpha": cpsat.config.alpha, "beta": cpsat.config.beta}:
            raise _invalid("los pesos efectivos alpha/beta difieren")
        report["input_sha256"] = greedy.input_sha256
        report["weights"] = weights

        reasons = [r for r in (not_comparable_reason(greedy), not_comparable_reason(cpsat)) if r]
        if reasons:
            report["runs"] = {"greedy": greedy.summary(), "cp-sat": cpsat.summary()}
            raise CompareError(EXIT_NOT_COMPARABLE, "; ".join(reasons))

        for run in (greedy, cpsat):
            recheck(run)
    except CompareError as error:
        status = {
            EXIT_INVALID: "INVALID",
            EXIT_NOT_COMPARABLE: "NOT_COMPARABLE",
            EXIT_AUDIT_FAILED: "AUDIT_FAILED",
        }[error.code]
        return error.code, {
            "status": status,
            "exit_code": error.code,
            "reason": error.reason,
            **report,
        }

    z_greedy = greedy.metrics["costs"]["objective"]
    z_cpsat = cpsat.metrics["costs"]["objective"]
    env_g, env_c = greedy.metrics.get("environment") or {}, cpsat.metrics.get("environment") or {}
    keys = ("python", "ortools", "sqlite", "package", "git", "system", "machine", "processor")
    differing = [key for key in keys if env_g.get(key) != env_c.get(key)]
    return EXIT_OK, {
        "status": "COMPARED",
        "exit_code": EXIT_OK,
        "reason": None,
        **report,
        "runs": {"greedy": greedy.summary(), "cp-sat": cpsat.summary()},
        "difference": cost_difference(z_greedy, z_cpsat),
        "cpsat_status_note": "FEASIBLE no prueba optimalidad"
        if cpsat.metrics["status"]["solver"] == "FEASIBLE"
        else None,
        "conditions": {
            "environment_differences": differing,
            "timing_note": "tiempos observados en ejecuciones separadas; no son una medición "
            "controlada",
        },
    }


def write_report(out: Path, report: dict[str, object]) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(json_bytes(report))
