"""Comparación greedy contra CP-SAT: elegibilidad, integridad, auditoría y diferencias."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from academic_timetabling_demo import runner
from academic_timetabling_demo.compare import (
    OutputError,
    check_output,
    compare_runs,
    cost_difference,
)
from academic_timetabling_demo.domain import (
    Instance,
    SectionGroup,
    SectionPattern,
    read_instance,
)
from academic_timetabling_demo.metrics import json_bytes, sha256_bytes
from academic_timetabling_demo.model import SolveResult
from academic_timetabling_demo.synthetic import GeneratedCase, source_files

DATA = Path(__file__).resolve().parents[1] / "data" / "synthetic"


@pytest.fixture
def micro() -> Instance:
    return read_instance(DATA / "micro")


def write_input(directory: Path, instance: Instance) -> Path:
    directory.mkdir(parents=True)
    for name, content in source_files(GeneratedCase("micro", 42, instance, ())).items():
        (directory / name).write_bytes(content)
    return directory


def make_run(path: Path, source: Path, solver: str, **options) -> Path:
    runner.run(source, path, solver=solver, **options)
    return path


@pytest.fixture
def pair(tmp_path: Path) -> tuple[Path, Path]:
    greedy = make_run(tmp_path / "greedy", DATA / "micro", "greedy")
    cpsat = make_run(tmp_path / "cpsat", DATA / "micro", "cp-sat")
    return greedy, cpsat


def load(path: Path) -> dict:
    return json.loads((path / "metrics.json").read_text(encoding="utf-8"))


def save(path: Path, metrics: dict) -> None:
    (path / "metrics.json").write_bytes(json_bytes(metrics))


def edit_metrics(path: Path, change) -> None:
    metrics = load(path)
    change(metrics)
    save(path, metrics)


def stuck_instance(micro: Instance) -> Instance:
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


# Comparación válida ---------------------------------------------------------------------


@pytest.mark.parametrize("reverse", [False, True])
def test_valid_comparison_in_either_order(pair, reverse: bool) -> None:
    paths = list(reversed(pair)) if reverse else list(pair)

    code, report = compare_runs(paths)

    assert code == 0
    assert report["status"] == "COMPARED"
    assert set(report["runs"]) == {"greedy", "cp-sat"}
    assert report["runs"]["greedy"]["costs"]["objective"] == 3
    assert report["runs"]["cp-sat"]["status"]["solver"] == "OPTIMAL"
    assert report["difference"] == {
        "absolute": 0,
        "percent": 0.0,
        "verdict": "empate",
        "note": None,
    }
    assert report["weights"] == {"alpha": 10, "beta": 1}
    assert report["input_sha256"] == load(pair[0])["input"]["combined_sha256"]
    assert report["runs"]["greedy"]["audit_recheck"]["status"] == "PASSED"


def test_hito3_cpsat_run_without_new_fields_is_accepted(pair) -> None:
    greedy, cpsat = pair

    def strip(metrics: dict) -> None:
        metrics["status"].pop("baseline")
        metrics["status"].pop("integrity")
        metrics.pop("provenance")

    edit_metrics(cpsat, strip)

    code, report = compare_runs([greedy, cpsat])

    assert code == 0, report["reason"]


def test_different_solver_parameters_are_allowed(tmp_path: Path) -> None:
    greedy = make_run(tmp_path / "g", DATA / "micro", "greedy")
    cpsat = make_run(tmp_path / "c", DATA / "micro", "cp-sat", time_limit=5.0, seed=7)

    code, report = compare_runs([greedy, cpsat])

    assert code == 0, report["reason"]
    assert (
        load(greedy)["input"]["effective_config_sha256"]
        != load(cpsat)["input"]["effective_config_sha256"]
    )
    assert report["runs"]["cp-sat"]["effective_config"]["random_seed"] == 7
    assert report["runs"]["cp-sat"]["effective_config"]["time_limit_seconds"] == 5.0


def test_feasible_label_is_kept(pair) -> None:
    greedy, cpsat = pair
    edit_metrics(cpsat, lambda m: m["status"].update(solver="FEASIBLE"))

    code, report = compare_runs([greedy, cpsat])

    assert code == 0
    assert report["runs"]["cp-sat"]["status"]["solver"] == "FEASIBLE"
    assert report["cpsat_status_note"] == "FEASIBLE no prueba optimalidad"


@pytest.mark.parametrize(
    ("greedy", "cpsat", "absolute", "percent", "verdict"),
    [
        (10, 7, 3, 30.0, "CP-SAT obtiene menor costo"),
        (7, 7, 0, 0.0, "empate"),
        (7, 10, -3, -100 * 3 / 7, "la heurística obtiene menor costo"),
        (0, 0, 0, None, "empate"),
    ],
)
def test_cost_difference(greedy, cpsat, absolute, percent, verdict) -> None:
    result = cost_difference(greedy, cpsat)

    assert result["absolute"] == absolute
    assert result["percent"] == percent
    assert result["verdict"] == verdict
    assert (result["note"] is None) == (greedy > 0)


# Entradas, pesos y tipos de corrida -----------------------------------------------------


def test_different_inputs_are_rejected(tmp_path: Path, micro: Instance) -> None:
    rooms = tuple(r.model_copy(update={"name": "Otra"}) if r.id == "R1" else r for r in micro.rooms)
    other = write_input(tmp_path / "otra", micro.model_copy(update={"rooms": rooms}))
    greedy = make_run(tmp_path / "g", DATA / "micro", "greedy")
    cpsat = make_run(tmp_path / "c", other, "cp-sat")

    code, report = compare_runs([greedy, cpsat])

    assert code == 2
    assert "entradas difieren" in report["reason"]
    assert "difference" not in report


def test_different_effective_weights_are_rejected(pair) -> None:
    greedy, cpsat = pair
    path = cpsat / "effective_config.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    config["alpha"] = 1
    content = json_bytes(config)
    path.write_bytes(content)

    def record(metrics: dict) -> None:
        metrics["input"]["effective_config_sha256"] = sha256_bytes(content)
        metrics["parameters"]["effective_config"] = config

    edit_metrics(cpsat, record)

    code, report = compare_runs([greedy, cpsat])

    assert code == 2
    assert "pesos" in report["reason"]


def test_two_runs_of_the_same_method_are_rejected(tmp_path: Path) -> None:
    a = make_run(tmp_path / "a", DATA / "micro", "greedy")
    b = make_run(tmp_path / "b", DATA / "micro", "greedy")

    code, report = compare_runs([a, b])

    assert code == 2
    assert "greedy y una cp-sat" in report["reason"]


def test_same_directory_and_duplicate_run_id_are_rejected(pair, tmp_path: Path) -> None:
    greedy, _ = pair
    assert compare_runs([greedy, greedy])[0] == 2

    copy = tmp_path / "copia"
    shutil.copytree(greedy, copy)
    edit_metrics(copy, lambda m: m["parameters"].update(solver="cp-sat"))
    code, report = compare_runs([greedy, copy])

    assert code == 2
    assert "run_id duplicado" in report["reason"]


def test_unexpected_method_is_rejected(pair) -> None:
    greedy, cpsat = pair
    edit_metrics(cpsat, lambda m: m["parameters"].update(solver="otro"))

    code, report = compare_runs([greedy, cpsat])

    assert code == 2
    assert "método inesperado" in report["reason"]


# Sin solución completa ------------------------------------------------------------------


def test_incomplete_greedy_is_not_comparable(tmp_path: Path, micro: Instance) -> None:
    source = write_input(tmp_path / "entrada", stuck_instance(micro))
    greedy = make_run(tmp_path / "g", source, "greedy")
    cpsat = make_run(tmp_path / "c", source, "cp-sat")

    code, report = compare_runs([greedy, cpsat])

    assert code == 3
    assert report["status"] == "NOT_COMPARABLE"
    assert "INCOMPLETE" in report["reason"]
    assert "difference" not in report
    assert report["runs"]["cp-sat"]["costs"]["objective"] == 22


def test_empty_domain_is_not_comparable(tmp_path: Path, micro: Instance) -> None:
    sections = tuple(
        s.model_copy(update={"enrollment": 60}) if s.id == "S2" else s for s in micro.sections
    )
    source = write_input(tmp_path / "entrada", micro.model_copy(update={"sections": sections}))

    code, report = compare_runs(
        [make_run(tmp_path / "g", source, "greedy"), make_run(tmp_path / "c", source, "cp-sat")]
    )

    assert code == 3
    assert "NO_CANDIDATES" in report["reason"]


def test_infeasible_is_not_comparable(tmp_path: Path, micro: Instance) -> None:
    groups = (*micro.section_groups, SectionGroup(section_id="S1", group_id="G2"))
    source = write_input(tmp_path / "entrada", micro.model_copy(update={"section_groups": groups}))

    code, report = compare_runs(
        [make_run(tmp_path / "g", source, "greedy"), make_run(tmp_path / "c", source, "cp-sat")]
    )

    assert code == 3
    assert "INFEASIBLE" in report["reason"]
    assert "INCOMPLETE" in report["reason"]


def test_unknown_is_not_comparable(tmp_path: Path, monkeypatch) -> None:
    greedy = make_run(tmp_path / "g", DATA / "micro", "greedy")

    def unknown(connection, config):
        return SolveResult("UNKNOWN", None, None, None, None, None, (), 5, 7, 4, 0.0, 0.0)

    monkeypatch.setattr(runner, "build_and_solve", unknown)
    cpsat = make_run(tmp_path / "c", DATA / "micro", "cp-sat")

    code, report = compare_runs([greedy, cpsat])

    assert code == 3
    assert "UNKNOWN" in report["reason"]


def test_corruption_takes_priority_over_incompleteness(tmp_path: Path, micro: Instance) -> None:
    source = write_input(tmp_path / "entrada", stuck_instance(micro))
    greedy = make_run(tmp_path / "g", source, "greedy")
    cpsat = make_run(tmp_path / "c", source, "cp-sat")
    (greedy / "input" / "rooms.csv").write_text("id,name,capacity\nR1,Sala,99\n", "utf-8")

    code, report = compare_runs([greedy, cpsat])

    assert code == 2
    assert "snapshot cambió" in report["reason"]


# Evidencia alterada después de la corrida -----------------------------------------------


def test_manipulated_assignments_fail_new_audit(pair) -> None:
    greedy, cpsat = pair
    (cpsat / "assignments.csv").write_text(
        "section_id,pattern_id,room_id\nS1,P1,R1\nS2,P3,R2\nS3,P6,R1\n", encoding="utf-8"
    )

    code, report = compare_runs([greedy, cpsat])

    assert code == 4
    assert report["status"] == "AUDIT_FAILED"
    assert "ROOM_CLASH" in report["reason"]


def test_false_cost_fails_new_audit(pair) -> None:
    greedy, cpsat = pair
    edit_metrics(cpsat, lambda m: m["costs"].update(objective=1, cost_e=1))

    code, report = compare_runs([greedy, cpsat])

    assert code == 4
    assert "OBJECTIVE_MISMATCH" in report["reason"]


def test_stored_failed_audit_is_not_compared(pair) -> None:
    greedy, cpsat = pair
    audit = json.loads((greedy / "audit.json").read_text(encoding="utf-8"))
    audit["audit_valid"] = False
    (greedy / "audit.json").write_bytes(json_bytes(audit))

    code, _ = compare_runs([greedy, cpsat])

    assert code == 4


@pytest.mark.parametrize(
    "tamper",
    ["snapshot", "global_hash", "effective_file", "effective_record", "integrity", "extra_file"],
)
def test_incoherent_evidence_is_rejected(pair, tamper: str) -> None:
    greedy, cpsat = pair
    if tamper == "snapshot":
        rooms = cpsat / "input" / "rooms.csv"
        rooms.write_bytes(rooms.read_bytes().replace(b",30\n", b",31\n"))
    elif tamper == "global_hash":
        edit_metrics(cpsat, lambda m: m["input"].update(combined_sha256="0" * 64))
    elif tamper == "effective_file":
        path = cpsat / "effective_config.json"
        path.write_bytes(path.read_bytes().replace(b'"beta": 1', b'"beta": 2'))
    elif tamper == "effective_record":
        edit_metrics(cpsat, lambda m: m["parameters"]["effective_config"].update(beta=2))
    elif tamper == "integrity":
        edit_metrics(cpsat, lambda m: m["status"].update(integrity="FAILED"))
    else:
        (cpsat / "input" / "generation.json").write_text("{}", encoding="utf-8")

    code, report = compare_runs([greedy, cpsat])

    # Las banderas guardadas siguen diciendo válido, pero la evidencia no es coherente.
    assert load(cpsat)["status"]["result_valid"] is True
    assert code == 2, report["reason"]
    assert report["status"] == "INVALID"


@pytest.mark.parametrize("problem", ["malformed", "directory", "missing"])
def test_unreadable_metrics_are_invalid(pair, problem: str) -> None:
    greedy, cpsat = pair
    target = cpsat / "metrics.json"
    target.unlink()
    if problem == "malformed":
        target.write_text("{", encoding="utf-8")
    elif problem == "directory":
        target.mkdir()

    code, report = compare_runs([greedy, cpsat])

    assert code == 2
    assert report["status"] == "INVALID"


# Salida ---------------------------------------------------------------------------------


def test_existing_output_is_rejected(pair, tmp_path: Path) -> None:
    out = tmp_path / "comparacion.json"
    out.write_text("anterior", encoding="utf-8")

    with pytest.raises(OutputError, match="ya existe"):
        check_output(out, list(pair))

    assert out.read_text(encoding="utf-8") == "anterior"


def test_output_inside_a_run_is_rejected(pair) -> None:
    with pytest.raises(OutputError, match="dentro"):
        check_output(pair[1] / "comparacion.json", list(pair))


def test_compare_does_not_import_solver_or_runner() -> None:
    code = (
        "import sys, academic_timetabling_demo.compare; "
        "forbidden = {'ortools', 'academic_timetabling_demo.model', "
        "'academic_timetabling_demo.candidates', 'academic_timetabling_demo.runner'}; "
        "loaded = forbidden & set(sys.modules); assert not loaded, loaded"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, encoding="utf-8", env={**os.environ}
    )

    assert result.returncode == 0, result.stderr
