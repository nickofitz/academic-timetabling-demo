"""Corridas: salidas, estados, códigos, snapshots y hashes."""

import csv
import hashlib
import io
import json
from pathlib import Path

import pytest

from academic_timetabling_demo import runner
from academic_timetabling_demo.baseline import BaselineResult, Choice
from academic_timetabling_demo.domain import (
    TABLES,
    Instance,
    SectionGroup,
    SectionPattern,
    read_instance,
)
from academic_timetabling_demo.metrics import combined_hash, relative_gap
from academic_timetabling_demo.model import Assignment, SolveResult
from academic_timetabling_demo.synthetic import (
    MANIFEST_FILE,
    GeneratedCase,
    generate_to_directory,
    manifest,
    source_files,
)

DATA = Path(__file__).resolve().parents[1] / "data" / "synthetic"
SOURCE_NAMES = {spec.file for spec in TABLES} | {"config.json"}


@pytest.fixture
def micro() -> Instance:
    return read_instance(DATA / "micro")


def write_input(directory: Path, instance: Instance, *, crlf: bool = False) -> Path:
    files = source_files(GeneratedCase("micro", 42, instance, ()))
    directory.mkdir(parents=True)
    for name, content in files.items():
        (directory / name).write_bytes(content.replace(b"\n", b"\r\n") if crlf else content)
    return directory


def strict_json(path: Path) -> dict:
    def reject(name: str) -> None:
        raise AssertionError(f"JSON no estricto: {name}")

    return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject)


def outputs(out: Path) -> tuple[dict, dict, dict]:
    return (
        strict_json(out / "metrics.json"),
        strict_json(out / "diagnostics.json"),
        strict_json(out / "audit.json"),
    )


def fake_result(status: str, assignments: tuple[Assignment, ...] = (), objective=None):
    has_solution = status in ("OPTIMAL", "FEASIBLE")
    return SolveResult(
        status=status,
        objective=objective,
        cost_d=0 if has_solution else None,
        cost_e=objective if has_solution else None,
        solver_objective=float(objective) if has_solution else None,
        best_bound=float(objective) if has_solution else None,
        assignments=assignments,
        num_variables=5,
        num_constraints=7,
        num_conflict_constraints=4,
        build_seconds=0.0,
        solve_seconds=0.0,
    )


# Corrida completa -----------------------------------------------------------------------


def test_micro_run_produces_audited_solution(tmp_path: Path) -> None:
    out = tmp_path / "corrida"

    outcome = runner.run(DATA / "micro", out)

    metrics, diagnostics, audit = outputs(out)
    assert outcome.exit_code == 0
    assert sorted(p.name for p in out.iterdir()) == [
        "assignments.csv",
        "audit.json",
        "diagnostics.json",
        "effective_config.json",
        "input",
        "metrics.json",
        "schedule.csv",
        "schedule.html",
    ]
    assert (out / "assignments.csv").read_text(encoding="utf-8") == (
        "section_id,pattern_id,room_id\nS1,P2,R1\nS2,P3,R2\nS3,P5,R1\n"
    )
    assert metrics["status"] == {
        "data": "VALID",
        "precheck": "READY",
        "solver": "OPTIMAL",
        "baseline": None,
        "audit": "PASSED",
        "integrity": "VERIFIED",
        "result_valid": True,
        "export": "WRITTEN",
        "deliverable": True,
    }
    assert metrics["input"]["snapshot_verified"] is True
    assert strict_json(out / "diagnostics.json")["integrity"] == {
        "snapshot_changed": [],
        "snapshot_check_error": None,
        "source_changed": [],
        "source_check_error": None,
    }
    assert metrics["costs"] == {
        "cost_d": 0,
        "cost_e": 3,
        "objective": 3,
        "solver_objective": 3.0,
        "best_bound": 3.0,
        "relative_gap": 0.0,
    }
    assert metrics["counts"]["coverage"] == 1.0
    assert metrics["model"]["variables"] == 5
    assert audit["status"] == "PASSED"
    assert audit["objective"] == 3
    assert diagnostics["precheck"]["alternatives_after"] == 5
    assert len(diagnostics["discarded_alternatives"]) == 7
    assert set(metrics["timings_seconds"]) >= {
        "snapshot",
        "validation",
        "load",
        "candidates",
        "build",
        "solve",
        "audit",
        "total",
    }
    assert metrics["environment"]["ortools"]
    assert metrics["environment"]["sqlite"]


def test_snapshot_has_exact_sources_and_no_witness(tmp_path: Path) -> None:
    out = tmp_path / "corrida"
    runner.run(DATA / "micro", out)
    metrics = strict_json(out / "metrics.json")
    snapshot = out / "input"

    assert {p.name for p in snapshot.iterdir()} == SOURCE_NAMES
    assert not (snapshot / MANIFEST_FILE).exists()
    for name, digest in metrics["input"]["files"].items():
        assert (snapshot / name).read_bytes() == (DATA / "micro" / name).read_bytes()
        assert hashlib.sha256((snapshot / name).read_bytes()).hexdigest() == digest
    assert metrics["input"]["combined_sha256"] == combined_hash(metrics["input"]["files"])
    assert metrics["input"]["complete"] is True
    assert metrics["input"]["snapshot_verified"] is True
    assert metrics["input"]["source_unchanged"] is True
    effective = (out / "effective_config.json").read_bytes()
    assert metrics["input"]["effective_config_sha256"] == hashlib.sha256(effective).hexdigest()


def test_overrides_are_recorded_and_used(tmp_path: Path, monkeypatch) -> None:
    seen = []
    real = runner.build_and_solve

    def spy(connection, config):
        seen.append(config)
        return real(connection, config)

    monkeypatch.setattr(runner, "build_and_solve", spy)
    out = tmp_path / "corrida"

    runner.run(DATA / "micro", out, time_limit=5.5, seed=7)

    metrics = strict_json(out / "metrics.json")
    effective = strict_json(out / "effective_config.json")
    assert (seen[0].time_limit_seconds, seen[0].random_seed) == (5.5, 7)
    assert (effective["time_limit_seconds"], effective["random_seed"]) == (5.5, 7)
    assert metrics["parameters"]["applied_overrides"] == {
        "time_limit_seconds": 5.5,
        "random_seed": 7,
    }
    assert metrics["parameters"]["original_config"]["random_seed"] == 42
    assert strict_json(out / "input" / "config.json")["random_seed"] == 42


def test_each_run_gets_its_own_identity(tmp_path: Path) -> None:
    first = runner.run(DATA / "micro", tmp_path / "a")
    second = runner.run(DATA / "micro", tmp_path / "b")

    assert first.metrics["run_id"] != second.metrics["run_id"]


# Finales de línea -----------------------------------------------------------------------


def test_snapshot_hashes_exact_bytes_for_lf_and_crlf(tmp_path: Path, micro: Instance) -> None:
    lf = runner.run(write_input(tmp_path / "lf", micro), tmp_path / "out-lf")
    crlf = runner.run(write_input(tmp_path / "crlf", micro, crlf=True), tmp_path / "out-crlf")

    assert (tmp_path / "out-crlf" / "input" / "rooms.csv").read_bytes().count(b"\r\n") == 3
    assert lf.metrics["input"]["files"] != crlf.metrics["input"]["files"]
    assert lf.metrics["costs"]["objective"] == crlf.metrics["costs"]["objective"] == 3
    # El manifiesto del generador mantiene su política normalizada a LF para ambos.
    files = source_files(GeneratedCase("micro", 42, micro, ()))
    crlf_files = {k: v.replace(b"\n", b"\r\n") for k, v in files.items()}
    generated = GeneratedCase("micro", 42, micro, ())
    assert manifest(generated, files)["sources"] == manifest(generated, crlf_files)["sources"]


# Casos sin solución ---------------------------------------------------------------------


def test_empty_domain_never_calls_solver(tmp_path: Path, micro: Instance, monkeypatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("no debía invocarse el solver")

    monkeypatch.setattr(runner, "build_and_solve", forbidden)
    sections = tuple(
        s.model_copy(update={"enrollment": 60}) if s.id == "S2" else s for s in micro.sections
    )
    source = write_input(tmp_path / "entrada", micro.model_copy(update={"sections": sections}))
    out = tmp_path / "corrida"

    outcome = runner.run(source, out)

    metrics, diagnostics, audit = outputs(out)
    assert outcome.exit_code == 3
    assert metrics["status"]["precheck"] == "NO_CANDIDATES"
    assert metrics["status"]["solver"] is None
    assert diagnostics["precheck"]["empty_sections"] == {"S2": ["CAPACITY", "ROOM_RESERVED"]}
    assert audit == {
        "status": "NOT_RUN",
        "audit_valid": None,
        "cost_d": None,
        "cost_e": None,
        "objective": None,
        "reported_objective": None,
        "findings": [],
    }
    assert not (out / "assignments.csv").exists()
    assert metrics["costs"]["objective"] is None


def test_globally_infeasible_run(tmp_path: Path, micro: Instance) -> None:
    groups = (*micro.section_groups, SectionGroup(section_id="S1", group_id="G2"))
    source = write_input(tmp_path / "entrada", micro.model_copy(update={"section_groups": groups}))
    out = tmp_path / "corrida"

    outcome = runner.run(source, out)

    metrics, _, audit = outputs(out)
    assert outcome.exit_code == 3
    assert metrics["status"]["solver"] == "INFEASIBLE"
    assert metrics["status"]["audit"] == "NOT_RUN"
    assert metrics["costs"]["objective"] is None
    assert metrics["costs"]["relative_gap"] is None
    assert audit["status"] == "NOT_RUN"
    assert not (out / "assignments.csv").exists()


@pytest.mark.parametrize(("status", "code"), [("UNKNOWN", 3), ("MODEL_INVALID", 5)])
def test_statuses_without_solution(tmp_path: Path, monkeypatch, status: str, code: int) -> None:
    monkeypatch.setattr(runner, "build_and_solve", lambda connection, config: fake_result(status))
    out = tmp_path / "corrida"

    outcome = runner.run(DATA / "micro", out)

    metrics = strict_json(out / "metrics.json")
    assert outcome.exit_code == code
    assert metrics["status"]["solver"] == status
    assert not (out / "assignments.csv").exists()


def test_failed_audit_blocks_success(tmp_path: Path, monkeypatch) -> None:
    clashing = (
        Assignment("S1", "P1", "R1"),
        Assignment("S2", "P3", "R2"),
        Assignment("S3", "P6", "R1"),
    )
    monkeypatch.setattr(
        runner, "build_and_solve", lambda c, config: fake_result("OPTIMAL", clashing, 3)
    )
    out = tmp_path / "corrida"

    outcome = runner.run(DATA / "micro", out)

    metrics, _, audit = outputs(out)
    assert outcome.exit_code == 4
    assert metrics["status"]["solver"] == "OPTIMAL"  # el estado del solver no se reescribe
    assert metrics["status"]["audit"] == "FAILED"
    assert metrics["status"]["result_valid"] is False
    assert audit["audit_valid"] is False
    assert {"ROOM_CLASH", "OBJECTIVE_MISMATCH"} <= {f["rule"] for f in audit["findings"]}
    assert (out / "assignments.csv").exists()  # conservado como evidencia inválida
    assert "inválida" in metrics["error"]


# Integridad final del snapshot -----------------------------------------------------------


def audit_then(action, monkeypatch) -> None:
    """Ejecuta la auditoría real y luego `action`, devolviendo el informe real sin cambios."""
    real = runner.audit

    def wrapped(instance, rows, objective, config):
        report = real(instance, rows, objective, config)
        action()
        return report

    monkeypatch.setattr(runner, "audit", wrapped)


def test_modified_snapshot_blocks_success(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "corrida"
    rooms = out / "input" / "rooms.csv"

    def tamper() -> None:
        rooms.write_bytes(rooms.read_bytes().replace(b",30\n", b",31\n"))

    audit_then(tamper, monkeypatch)

    outcome = runner.run(DATA / "micro", out)

    metrics, diagnostics, audit = outputs(out)
    assert outcome.exit_code == 5
    # Los estados describen lo ocurrido: el solver y la auditoría no fallaron.
    assert metrics["status"]["solver"] == "OPTIMAL"
    assert metrics["status"]["audit"] == "PASSED"
    assert audit["status"] == "PASSED"
    assert metrics["status"]["integrity"] == "FAILED"
    assert metrics["status"]["result_valid"] is False
    assert metrics["input"]["snapshot_verified"] is False
    assert metrics["input"]["source_unchanged"] is True
    assert diagnostics["integrity"]["snapshot_changed"] == ["rooms.csv"]
    assert "integridad" in metrics["error"] and "rooms.csv" in metrics["error"]
    assert (out / "assignments.csv").exists()  # la evidencia se conserva


def test_unverifiable_snapshot_blocks_success(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "corrida"
    real = runner._rehash

    def failing(directory: Path, names: list[str]):
        if directory == out / "input":
            raise PermissionError(13, "Permission denied", str(directory / "rooms.csv"))
        return real(directory, names)

    monkeypatch.setattr(runner, "_rehash", failing)

    outcome = runner.run(DATA / "micro", out)

    metrics, diagnostics, _ = outputs(out)
    assert outcome.exit_code == 5
    assert metrics["status"]["solver"] == "OPTIMAL"
    assert metrics["status"]["audit"] == "PASSED"
    assert metrics["status"]["integrity"] == "NOT_VERIFIED"
    assert metrics["status"]["result_valid"] is False
    assert metrics["input"]["snapshot_verified"] is None
    assert "PermissionError" in diagnostics["integrity"]["snapshot_check_error"]
    assert "no se pudo verificar" in metrics["error"]


def test_changed_source_with_intact_snapshot_is_only_recorded(
    tmp_path: Path, micro: Instance, monkeypatch
) -> None:
    source = write_input(tmp_path / "entrada", micro)
    out = tmp_path / "corrida"

    def edit_original() -> None:
        (source / "rooms.csv").write_text("id,name,capacity\nR1,Sala,99\n", encoding="utf-8")

    audit_then(edit_original, monkeypatch)

    outcome = runner.run(source, out)

    metrics, diagnostics, _ = outputs(out)
    assert outcome.exit_code == 0
    assert metrics["status"]["integrity"] == "VERIFIED"
    assert metrics["status"]["result_valid"] is True
    assert metrics["input"]["snapshot_verified"] is True
    assert metrics["input"]["source_unchanged"] is False
    assert diagnostics["integrity"]["source_changed"] == ["rooms.csv"]
    assert metrics["error"] is None


def test_unreadable_source_is_invalid_data(tmp_path: Path, micro: Instance, monkeypatch) -> None:
    source = write_input(tmp_path / "entrada", micro)
    blocked = source / "rooms.csv"
    real = Path.read_bytes

    def read_bytes(path: Path) -> bytes:
        if path == blocked:
            raise PermissionError(13, "Permission denied", str(path))
        return real(path)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    out = tmp_path / "corrida"

    outcome = runner.run(source, out)

    metrics, diagnostics, _ = outputs(out)
    assert outcome.exit_code == 2
    assert metrics["status"]["data"] == "INVALID"
    assert metrics["input"]["complete"] is False
    assert metrics["input"]["unreadable"] == {"rooms.csv": "PermissionError: Permission denied"}
    assert any(e["file"] == "rooms.csv" for e in diagnostics["data_errors"])


# Datos y rutas inválidos ----------------------------------------------------------------


def test_invalid_data_writes_diagnostics(tmp_path: Path, micro: Instance) -> None:
    source = write_input(tmp_path / "entrada", micro)
    (source / "rooms.csv").write_text("id,name,capacity\nR1,Sala,0\n", encoding="utf-8")
    out = tmp_path / "corrida"

    outcome = runner.run(source, out)

    metrics, diagnostics, audit = outputs(out)
    assert outcome.exit_code == 2
    assert metrics["status"]["data"] == "INVALID"
    assert diagnostics["data_errors"][0]["file"] == "rooms.csv"
    assert audit["status"] == "NOT_RUN"
    assert not (out / "effective_config.json").exists()


def test_missing_source_file_is_recorded(tmp_path: Path, micro: Instance) -> None:
    source = write_input(tmp_path / "entrada", micro)
    (source / "teachers.csv").unlink()
    out = tmp_path / "corrida"

    outcome = runner.run(source, out)

    metrics = strict_json(out / "metrics.json")
    assert outcome.exit_code == 2
    assert metrics["input"]["complete"] is False
    assert metrics["input"]["missing"] == ["teachers.csv"]


def test_non_empty_output_is_left_intact(tmp_path: Path) -> None:
    out = tmp_path / "corrida"
    out.mkdir()
    (out / "assignments.csv").write_text("antiguo", encoding="utf-8")

    with pytest.raises(runner.RunInputError, match="no está vacía"):
        runner.run(DATA / "micro", out)

    assert [p.name for p in out.iterdir()] == ["assignments.csv"]
    assert (out / "assignments.csv").read_text(encoding="utf-8") == "antiguo"


@pytest.mark.parametrize("relative", [".", "corrida"])
def test_output_inside_input_is_rejected(tmp_path: Path, micro: Instance, relative: str) -> None:
    source = write_input(tmp_path / "entrada", micro)

    with pytest.raises(runner.RunInputError, match="dentro"):
        runner.run(source, source / relative)

    assert {p.name for p in source.iterdir()} == SOURCE_NAMES


def test_other_solvers_are_not_implemented(tmp_path: Path) -> None:
    with pytest.raises(runner.RunInputError, match="no implementado"):
        runner.run(DATA / "micro", tmp_path / "corrida", solver="otro")

    assert not (tmp_path / "corrida").exists()


def test_unsupported_sqlite_is_an_environment_error(tmp_path: Path, monkeypatch) -> None:
    def unsupported() -> None:
        raise runner.EnvironmentCheckError("SQLite 3.40.0 no admite ORDER BY")

    monkeypatch.setattr(runner, "check_sqlite", unsupported)
    out = tmp_path / "corrida"

    outcome = runner.run(DATA / "micro", out)

    assert outcome.exit_code == 5
    assert "3.40.0" in strict_json(out / "metrics.json")["error"]


def test_parameters_beyond_solver_range_are_invalid(tmp_path: Path) -> None:
    out = tmp_path / "corrida"

    outcome = runner.run(DATA / "micro", out, seed=2**31)

    assert outcome.exit_code == 2
    assert "random_seed" in strict_json(out / "metrics.json")["error"]
    assert not (out / "assignments.csv").exists()


# Heurística voraz en corridas -----------------------------------------------------------


def stuck_instance(micro: Instance) -> Instance:
    """Igual que en test_baseline: S1 toma P2 y S2, con el mismo docente, queda sin opción."""
    sections = []
    for section in micro.sections:
        if section.id == "S2":
            section = section.model_copy(
                update={"teacher_id": "T1", "enrollment": 20, "blocks_per_session": 1}
            )
        if section.id != "S3":
            sections.append(section)
    return micro.model_copy(
        update={
            "sections": tuple(sections),
            "section_groups": tuple(g for g in micro.section_groups if g.section_id != "S3"),
            "section_weeks": tuple(w for w in micro.section_weeks if w.section_id != "S3"),
            "section_patterns": (
                SectionPattern(section_id="S1", pattern_id="P1"),
                SectionPattern(section_id="S1", pattern_id="P2"),
                SectionPattern(section_id="S2", pattern_id="P2"),
            ),
            "section_blocked": (),
        }
    )


def forbid_cpsat(monkeypatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("no debía invocarse CP-SAT")

    monkeypatch.setattr(runner, "build_and_solve", forbidden)


def test_greedy_run_is_complete_and_audited(tmp_path: Path, monkeypatch) -> None:
    forbid_cpsat(monkeypatch)
    out = tmp_path / "corrida"

    outcome = runner.run(DATA / "micro", out, solver="greedy")

    metrics, diagnostics, audit = outputs(out)
    assert outcome.exit_code == 0
    assert metrics["parameters"]["solver"] == "greedy"
    assert metrics["status"]["solver"] is None
    assert metrics["status"]["baseline"] == "COMPLETE"
    assert metrics["status"]["result_valid"] is True
    assert metrics["costs"] == {
        "cost_d": 0,
        "cost_e": 3,
        "objective": 3,
        "solver_objective": None,
        "best_bound": None,
        "relative_gap": None,
    }
    assert "model" not in metrics
    assert "baseline" in metrics["timings_seconds"]
    assert not {"build", "solve"} & set(metrics["timings_seconds"])
    assert audit["status"] == "PASSED"
    assert diagnostics["baseline"]["partial_costs"] is None
    assert diagnostics["baseline"]["order"] == ["S2", "S1", "S3"]
    assert "no usa" in metrics["parameters"]["note"]


def test_greedy_ignores_solver_seed_and_time(tmp_path: Path) -> None:
    runner.run(DATA / "micro", tmp_path / "a", solver="greedy")
    runner.run(DATA / "micro", tmp_path / "b", solver="greedy", seed=9, time_limit=1.0)

    metrics = strict_json(tmp_path / "b" / "metrics.json")
    assert metrics["parameters"]["applied_overrides"] == {
        "time_limit_seconds": 1.0,
        "random_seed": 9,
    }
    assert (tmp_path / "a" / "assignments.csv").read_bytes() == (
        tmp_path / "b" / "assignments.csv"
    ).read_bytes()


def test_stuck_greedy_keeps_prefix_and_returns_three(tmp_path: Path, micro: Instance) -> None:
    source = write_input(tmp_path / "entrada", stuck_instance(micro))
    out = tmp_path / "corrida"

    outcome = runner.run(source, out, solver="greedy")

    metrics, diagnostics, audit = outputs(out)
    assert outcome.exit_code == 3
    assert metrics["status"]["baseline"] == "INCOMPLETE"
    assert metrics["status"]["solver"] is None
    assert metrics["status"]["result_valid"] is False
    assert (out / "assignments.csv").read_text(encoding="utf-8") == (
        "section_id,pattern_id,room_id\nS1,P2,R1\n"
    )
    assert metrics["costs"]["objective"] is None
    assert metrics["counts"]["coverage"] == 0.5
    assert diagnostics["baseline"]["blocked_section"] == "S2"
    assert diagnostics["baseline"]["remaining_sections"] == ["S2"]
    assert diagnostics["baseline"]["partial_costs"]["objective"] == 1
    assert diagnostics["baseline"]["partial_costs"]["comparable"] is False
    assert audit["audit_valid"] is False
    assert [(f["rule"], f["section_ids"]) for f in audit["findings"]] == [
        ("MISSING_ASSIGNMENT", ["S2"])
    ]


def fake_baseline(status: str, choices: tuple[Choice, ...], objective: int, remaining=()):
    return lambda connection, config: BaselineResult(
        status=status,
        assignments=choices,
        order=("S2", "S1", "S3"),
        blocked_section=remaining[0] if remaining else None,
        remaining_sections=tuple(remaining),
        cost_d=0,
        cost_e=objective,
        objective=objective,
        seconds=0.0,
    )


def test_empty_prefix_is_kept_as_evidence(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        runner, "run_greedy", fake_baseline("INCOMPLETE", (), 0, remaining=("S2", "S1", "S3"))
    )
    out = tmp_path / "corrida"

    outcome = runner.run(DATA / "micro", out, solver="greedy")

    assert outcome.exit_code == 3
    assert (out / "assignments.csv").read_text(
        encoding="utf-8"
    ) == "section_id,pattern_id,room_id\n"


@pytest.mark.parametrize("status", ["COMPLETE", "INCOMPLETE"])
def test_greedy_conflict_is_an_audit_failure(tmp_path: Path, monkeypatch, status: str) -> None:
    clashing = (Choice("S1", "P1", "R1"), Choice("S3", "P6", "R1"))
    if status == "COMPLETE":
        clashing = (*clashing, Choice("S2", "P3", "R2"))
    remaining = () if status == "COMPLETE" else ("S2",)
    monkeypatch.setattr(runner, "run_greedy", fake_baseline(status, clashing, 0, remaining))
    out = tmp_path / "corrida"

    outcome = runner.run(DATA / "micro", out, solver="greedy")

    metrics, _, audit = outputs(out)
    assert outcome.exit_code == 4
    assert metrics["status"]["baseline"] == status  # el estado del método no se reescribe
    assert metrics["status"]["result_valid"] is False
    assert "ROOM_CLASH" in {f["rule"] for f in audit["findings"]}


def test_empty_domain_runs_no_algorithm(tmp_path: Path, micro: Instance, monkeypatch) -> None:
    forbid_cpsat(monkeypatch)

    def forbidden(*args, **kwargs):
        raise AssertionError("no debía ejecutarse la heurística")

    monkeypatch.setattr(runner, "run_greedy", forbidden)
    sections = tuple(
        s.model_copy(update={"enrollment": 60}) if s.id == "S2" else s for s in micro.sections
    )
    source = write_input(tmp_path / "entrada", micro.model_copy(update={"sections": sections}))
    out = tmp_path / "corrida"

    outcome = runner.run(source, out, solver="greedy")

    metrics = strict_json(out / "metrics.json")
    assert outcome.exit_code == 3
    assert (metrics["status"]["baseline"], metrics["status"]["solver"]) == (None, None)
    assert not (out / "assignments.csv").exists()


def test_integrity_check_also_protects_greedy(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "corrida"
    rooms = out / "input" / "rooms.csv"

    def tamper() -> None:
        rooms.write_bytes(rooms.read_bytes().replace(b",30\n", b",31\n"))

    audit_then(tamper, monkeypatch)

    outcome = runner.run(DATA / "micro", out, solver="greedy")

    metrics = strict_json(out / "metrics.json")
    assert outcome.exit_code == 5
    assert metrics["status"]["baseline"] == "COMPLETE"
    assert metrics["status"]["integrity"] == "FAILED"
    assert metrics["status"]["result_valid"] is False


# Exportaciones del Hito 5 ---------------------------------------------------------------

SCHEDULE = ("schedule.csv", "schedule.html")


def no_export(out: Path) -> dict:
    metrics = strict_json(out / "metrics.json")
    assert not any((out / name).exists() for name in SCHEDULE)
    assert not list(out.glob(".*.tmp"))
    assert metrics["status"]["deliverable"] is False
    return metrics


@pytest.mark.parametrize(
    ("case", "solver"), [("micro", "cp-sat"), ("micro", "greedy"), ("demo", "greedy")]
)
def test_valid_runs_export_consistent_files(tmp_path: Path, case: str, solver: str) -> None:
    out = tmp_path / "corrida"

    outcome = runner.run(DATA / case, out, solver=solver)

    metrics = strict_json(out / "metrics.json")
    assert outcome.exit_code == 0
    assert (metrics["status"]["export"], metrics["status"]["deliverable"]) == ("WRITTEN", True)
    for name in SCHEDULE:
        content = (out / name).read_bytes()
        assert metrics["export"]["files"][name] == hashlib.sha256(content).hexdigest()
    rows = list(csv.DictReader(io.StringIO((out / "schedule.csv").read_text(encoding="utf-8"))))
    assert {r["run_id"] for r in rows} == {metrics["run_id"]}
    assert len(rows) == metrics["export"]["sessions"]
    assigned = {
        line.split(",")[0] for line in (out / "assignments.csv").read_text("utf-8").split()[1:]
    }
    assert {r["section_id"] for r in rows} == assigned
    html = (out / "schedule.html").read_text(encoding="utf-8")
    assert metrics["run_id"] in html
    assert f"{metrics['costs']['objective']} = " in html
    assert "export" in metrics["timings_seconds"]
    assert metrics["timings_seconds"]["total"] >= metrics["timings_seconds"]["export"]
    assert not list(out.glob(".*.tmp"))


def test_no_export_for_empty_domain(tmp_path: Path, micro: Instance) -> None:
    sections = tuple(
        s.model_copy(update={"enrollment": 60}) if s.id == "S2" else s for s in micro.sections
    )
    source = write_input(tmp_path / "entrada", micro.model_copy(update={"sections": sections}))

    assert runner.run(source, tmp_path / "o").exit_code == 3
    assert no_export(tmp_path / "o")["status"]["export"] == "NOT_APPLICABLE"


def test_no_export_for_infeasible(tmp_path: Path, micro: Instance) -> None:
    groups = (*micro.section_groups, SectionGroup(section_id="S1", group_id="G2"))
    source = write_input(tmp_path / "entrada", micro.model_copy(update={"section_groups": groups}))

    assert runner.run(source, tmp_path / "o").exit_code == 3
    no_export(tmp_path / "o")


def test_no_export_for_incomplete_greedy(tmp_path: Path, micro: Instance) -> None:
    source = write_input(tmp_path / "entrada", stuck_instance(micro))

    assert runner.run(source, tmp_path / "o", solver="greedy").exit_code == 3
    no_export(tmp_path / "o")


@pytest.mark.parametrize(("status", "code"), [("UNKNOWN", 3), ("MODEL_INVALID", 5)])
def test_no_export_without_solution(tmp_path: Path, monkeypatch, status: str, code: int) -> None:
    monkeypatch.setattr(runner, "build_and_solve", lambda c, config: fake_result(status))

    assert runner.run(DATA / "micro", tmp_path / "o").exit_code == code
    no_export(tmp_path / "o")


def test_no_export_after_failed_audit(tmp_path: Path, monkeypatch) -> None:
    clashing = (
        Assignment("S1", "P1", "R1"),
        Assignment("S2", "P3", "R2"),
        Assignment("S3", "P6", "R1"),
    )
    monkeypatch.setattr(
        runner, "build_and_solve", lambda c, config: fake_result("OPTIMAL", clashing, 3)
    )

    assert runner.run(DATA / "micro", tmp_path / "o").exit_code == 4
    no_export(tmp_path / "o")


def test_no_export_after_integrity_failure(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "o"
    rooms = out / "input" / "rooms.csv"
    audit_then(
        lambda: rooms.write_bytes(rooms.read_bytes().replace(b",30\n", b",31\n")), monkeypatch
    )

    assert runner.run(DATA / "micro", out).exit_code == 5
    no_export(out)


def assert_export_failed(out: Path) -> dict:
    metrics = no_export(out)
    assert metrics["exit_code"] == 5
    assert metrics["status"]["export"] == "FAILED"
    # Fallo de exportación, no matemático: solver y auditoría conservan su estado real.
    assert (metrics["status"]["solver"], metrics["status"]["audit"]) == ("OPTIMAL", "PASSED")
    assert (out / "assignments.csv").exists()
    assert (out / "audit.json").exists()
    assert "no está lista para entregar" in metrics["error"]
    return metrics


def test_render_failure_leaves_no_export(tmp_path: Path, monkeypatch) -> None:
    def broken(data):
        raise RuntimeError("fallo de plantilla simulado")

    monkeypatch.setattr(runner.report, "render_html", broken)
    out = tmp_path / "o"

    assert runner.run(DATA / "micro", out).exit_code == 5
    assert "fallo de plantilla simulado" in assert_export_failed(out)["error"]


def test_failure_between_both_files_removes_the_first(tmp_path: Path, monkeypatch) -> None:
    real = runner._replace
    calls = []

    def second_fails(source: Path, target: Path) -> None:
        calls.append(target.name)
        if target.name == "schedule.html":
            raise OSError(28, "No space left on device")
        real(source, target)

    monkeypatch.setattr(runner, "_replace", second_fails)
    out = tmp_path / "o"

    assert runner.run(DATA / "micro", out).exit_code == 5
    assert calls == ["schedule.csv", "schedule.html"]
    assert_export_failed(out)


def test_snapshot_changed_during_presentation(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "o"
    real = runner.report.render_html

    def tamper_then_render(data):
        rooms = out / "input" / "rooms.csv"
        rooms.write_bytes(rooms.read_bytes().replace(b",30\n", b",31\n"))
        return real(data)

    monkeypatch.setattr(runner.report, "render_html", tamper_then_render)

    assert runner.run(DATA / "micro", out).exit_code == 5
    assert "snapshot cambió" in assert_export_failed(out)["error"]


def tamper_during_render(monkeypatch, action) -> None:
    """Llama al render real y altera la evidencia antes de devolver el HTML."""
    real = runner.report.render_html

    def wrapped(data):
        html = real(data)
        action()
        return html

    monkeypatch.setattr(runner.report, "render_html", wrapped)


@pytest.mark.parametrize(
    ("content", "kind"),
    [
        # Reproducción de la revisión: triples con choques.
        ("section_id,pattern_id,room_id\nS1,P1,R1\nS2,P3,R2\nS3,P6,R1\n", "inválido"),
        # Otro horario válido (S1 en P1, costo 23): tampoco puede quedar desacoplado del export.
        ("section_id,pattern_id,room_id\nS1,P1,R1\nS2,P3,R2\nS3,P5,R1\n", "válido"),
    ],
)
def test_assignments_changed_during_render_block_export(
    tmp_path: Path, monkeypatch, content: str, kind: str
) -> None:
    out = tmp_path / "o"
    tamper_during_render(
        monkeypatch, lambda: (out / "assignments.csv").write_text(content, encoding="utf-8")
    )

    assert runner.run(DATA / "micro", out).exit_code == 5

    metrics = assert_export_failed(out)
    assert "assignments.csv cambió durante la exportación" in metrics["error"]
    # La evidencia alterada se conserva para diagnóstico; el resultado auditado era otro.
    assert (out / "assignments.csv").read_text(encoding="utf-8") == content
    assert metrics["status"]["result_valid"] is True
    assert metrics["export"]["files"] == {}


def test_effective_config_changed_during_render_blocks_export(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "o"

    def tamper() -> None:
        path = out / "effective_config.json"
        path.write_bytes(path.read_bytes().replace(b'"alpha": 10', b'"alpha": 1'))

    tamper_during_render(monkeypatch, tamper)

    assert runner.run(DATA / "micro", out).exit_code == 5
    assert (
        "effective_config.json cambió durante la exportación" in assert_export_failed(out)["error"]
    )


def test_assignments_changed_before_validation_reading_is_detected(
    tmp_path: Path, monkeypatch
) -> None:
    # Cambio entre la captura inicial y la lectura de las asignaciones a presentar.
    out = tmp_path / "o"
    real = runner.read_assignments
    calls = []

    def tamper_on_read(path: Path):
        calls.append(path)
        rows = real(path)
        if len(calls) == 1:
            (out / "assignments.csv").write_text(
                "section_id,pattern_id,room_id\nS1,P1,R1\nS2,P3,R2\nS3,P5,R1\n", encoding="utf-8"
            )
        return rows

    monkeypatch.setattr(runner, "read_assignments", tamper_on_read)

    assert runner.run(DATA / "micro", out).exit_code == 5
    assert "mientras se validaba y leía" in assert_export_failed(out)["error"]


def test_manipulated_assignments_are_not_presented(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "o"

    def tamper() -> None:
        (out / "assignments.csv").write_text(
            "section_id,pattern_id,room_id\nS1,P1,R1\nS2,P3,R2\nS3,P6,R1\n", encoding="utf-8"
        )

    audit_then(tamper, monkeypatch)

    assert runner.run(DATA / "micro", out).exit_code == 5
    assert "ROOM_CLASH" in assert_export_failed(out)["error"]


def test_export_reads_the_snapshot_not_the_source(
    tmp_path: Path, micro: Instance, monkeypatch
) -> None:
    source = write_input(tmp_path / "entrada", micro)
    out = tmp_path / "o"
    rooms = source / "rooms.csv"
    audit_then(
        lambda: rooms.write_bytes(rooms.read_bytes().replace(b"Sala 1", b"Sala Cambiada")),
        monkeypatch,
    )

    assert runner.run(source, out).exit_code == 0

    csv_text = (out / "schedule.csv").read_text(encoding="utf-8")
    assert "Sala Cambiada" not in csv_text
    assert "Sala 1" in csv_text
    assert strict_json(out / "metrics.json")["input"]["source_unchanged"] is False


# Procedencia de datos --------------------------------------------------------------------


def test_data_seed_and_solver_seed_are_separate(tmp_path: Path) -> None:
    source = tmp_path / "micro-7"
    generate_to_directory("micro", 7, source)
    out = tmp_path / "corrida"

    runner.run(source, out, seed=3)

    metrics = strict_json(out / "metrics.json")
    assert metrics["provenance"]["status"] == "VERIFIED"
    assert (metrics["provenance"]["data_seed"], metrics["provenance"]["case"]) == (7, "micro")
    assert metrics["provenance"]["format_version"] == 1
    digest = hashlib.sha256((source / MANIFEST_FILE).read_bytes()).hexdigest()
    assert metrics["provenance"]["manifest_sha256"] == digest
    assert metrics["parameters"]["effective_config"]["random_seed"] == 3
    assert not (out / "input" / MANIFEST_FILE).exists()


def provenance_of(source: Path, out: Path) -> tuple[int, dict]:
    outcome = runner.run(source, out)
    return outcome.exit_code, strict_json(out / "metrics.json")["provenance"]


def assert_unknown(provenance: dict, status: str) -> None:
    assert provenance["status"] == status
    assert (provenance["data_seed"], provenance["case"], provenance["format_version"]) == (
        None,
        None,
        None,
    )
    assert provenance["detail"]


def test_absent_manifest(tmp_path: Path, micro: Instance) -> None:
    code, provenance = provenance_of(write_input(tmp_path / "e", micro), tmp_path / "o")

    assert code == 0
    assert_unknown(provenance, "ABSENT")


@pytest.mark.parametrize(
    "content",
    [b"{", b'{"case": "micro", "seed": "7", "format_version": 1, "sources": {}}', b"[]"],
)
def test_invalid_manifest(tmp_path: Path, micro: Instance, content: bytes) -> None:
    source = write_input(tmp_path / "e", micro)
    (source / MANIFEST_FILE).write_bytes(content)

    code, provenance = provenance_of(source, tmp_path / "o")

    assert code == 0
    assert_unknown(provenance, "INVALID")


def test_outdated_manifest_does_not_lend_its_seed(tmp_path: Path) -> None:
    source = tmp_path / "micro-7"
    generate_to_directory("micro", 7, source)
    rooms = source / "rooms.csv"
    rooms.write_bytes(rooms.read_bytes().replace(b"Sala 1", b"Sala Uno"))

    code, provenance = provenance_of(source, tmp_path / "o")

    assert code == 0
    assert_unknown(provenance, "MISMATCH")
    assert "rooms.csv" in provenance["detail"]


def test_crlf_sources_still_match_lf_manifest(tmp_path: Path) -> None:
    source = tmp_path / "micro-crlf"
    generate_to_directory("micro", 5, source)
    for path in source.iterdir():
        if path.name != MANIFEST_FILE:
            path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    out = tmp_path / "o"

    code, provenance = provenance_of(source, out)

    metrics = strict_json(out / "metrics.json")
    assert code == 0
    assert provenance["status"] == "VERIFIED"
    assert provenance["data_seed"] == 5
    rooms = (out / "input" / "rooms.csv").read_bytes()
    assert b"\r\n" in rooms
    assert metrics["input"]["files"]["rooms.csv"] == hashlib.sha256(rooms).hexdigest()


# Brecha ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("objective", "bound", "gap"),
    [(10, 8.0, 0.2), (10, 10.0, 0.0), (0, 0.0, 0.0), (10, 11.0, 0.0), (None, 3.0, None)],
)
def test_relative_gap(objective, bound, gap) -> None:
    assert relative_gap(objective, bound) == gap


def test_gap_without_finite_bound() -> None:
    assert relative_gap(5, float("inf")) is None
    assert relative_gap(5, None) is None
