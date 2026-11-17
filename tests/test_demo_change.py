"""Script reproducible de cambio de disponibilidad (scripts/demo_change.py)."""

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from academic_timetabling_demo import runner
from academic_timetabling_demo.domain import Instance, SectionPattern, read_instance
from academic_timetabling_demo.metrics import json_bytes, sha256_bytes
from academic_timetabling_demo.synthetic import GeneratedCase, source_files

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "synthetic"
SCRIPT = ROOT / "scripts" / "demo_change.py"

_spec = importlib.util.spec_from_file_location("demo_change", SCRIPT)
demo_change = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(demo_change)


@pytest.fixture
def micro() -> Instance:
    return read_instance(DATA / "micro")


def tree_hashes(directory: Path) -> dict[str, str]:
    return {
        str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_input(directory: Path, instance: Instance) -> Path:
    directory.mkdir(parents=True)
    for name, content in source_files(GeneratedCase("micro", 42, instance, ())).items():
        (directory / name).write_bytes(content)
    return directory


@pytest.fixture
def base(tmp_path: Path) -> Path:
    path = tmp_path / "base"
    assert runner.run(DATA / "micro", path).exit_code == 0
    return path


# Camino con nueva solución --------------------------------------------------------------


def test_change_is_exact_and_new_run_is_audited(base: Path, tmp_path: Path) -> None:
    before = tree_hashes(base)
    out = tmp_path / "cambio"

    code = demo_change.main(["--base-run", str(base), "--out", str(out)])

    record = load(out / "change.json")
    assert code == 0
    assert tree_hashes(base) == before  # la base queda intacta byte por byte

    # Primera sección S1 (P2: día 1, bloque 2), primera semana 1, docente T1.
    change = record["change"]
    assert (change["section_id"], change["teacher_id"]) == ("S1", "T1")
    assert (change["week_id"], change["day_id"], change["block_id"]) == (1, 1, 2)
    assert change["removed_row"] == "T1,1,1,2"

    original = (base / "input" / "teacher_available.csv").read_text("utf-8").splitlines()
    changed = (out / "changed-input" / "teacher_available.csv").read_text("utf-8").splitlines()
    assert [line for line in original if line not in changed] == ["T1,1,1,2"]
    assert len(changed) == len(original) - 1
    for path in (base / "input").iterdir():
        if path.name != "teacher_available.csv":
            assert (out / "changed-input" / path.name).read_bytes() == path.read_bytes()
    assert not (out / "changed-input" / "generation.json").exists()

    new = load(out / "changed-run" / "metrics.json")
    base_metrics = load(base / "metrics.json")
    assert new["parameters"]["effective_config"] == base_metrics["parameters"]["effective_config"]
    assert new["run_id"] != base_metrics["run_id"]
    assert new["input"]["combined_sha256"] != base_metrics["input"]["combined_sha256"]
    assert new["provenance"]["status"] != "VERIFIED"
    assert new["status"]["audit"] == "PASSED"
    assert (out / "changed-run" / "schedule.html").exists()

    # S1 ya no puede usar P2 en la semana 1: pasa a P1 (D=2), objetivo 23.
    reassigned = record["reassignments"]
    assert reassigned["counts"] == {
        "unchanged": 2,
        "pattern_changed": 1,
        "room_changed": 0,
        "both_changed": 0,
    }
    assert sum(reassigned["counts"].values()) == reassigned["total_sections"] == 3
    moved = reassigned["sections"]["pattern_changed"][0]
    assert moved == {
        "section_id": "S1",
        "before": {"pattern_id": "P2", "room_id": "R1"},
        "after": {"pattern_id": "P1", "room_id": "R1"},
    }
    assert record["changed_run"]["objective"] == 23
    assert record["base"]["run_id"] == base_metrics["run_id"]
    assert record["changed_run"]["run_id"] == new["run_id"]


def test_numerically_equal_override_keeps_identical_effective_config(tmp_path: Path) -> None:
    # config.json dice 30 (entero); la base usó --time-limit 30, guardado como 30.0.
    base = tmp_path / "base"
    assert runner.run(DATA / "micro", base, time_limit=30.0).exit_code == 0
    out = tmp_path / "cambio"

    assert demo_change.main(["--base-run", str(base), "--out", str(out)]) == 0

    new = load(out / "changed-run" / "metrics.json")
    old = load(base / "metrics.json")
    assert new["input"]["effective_config_sha256"] == old["input"]["effective_config_sha256"]
    assert (out / "changed-run" / "effective_config.json").read_bytes() == (
        base / "effective_config.json"
    ).read_bytes()


def test_solver_overrides_of_the_base_are_kept(tmp_path: Path) -> None:
    base = tmp_path / "base"
    assert runner.run(DATA / "micro", base, time_limit=5.0, seed=7).exit_code == 0
    out = tmp_path / "cambio"

    assert demo_change.main(["--base-run", str(base), "--out", str(out)]) == 0

    new = load(out / "changed-run" / "metrics.json")
    assert (
        new["parameters"]["effective_config"]
        == load(base / "metrics.json")["parameters"]["effective_config"]
    )
    assert new["parameters"]["applied_overrides"] == {"time_limit_seconds": 5.0, "random_seed": 7}


# Camino sin solución --------------------------------------------------------------------


def test_change_without_solution_keeps_diagnosis(tmp_path: Path, micro: Instance) -> None:
    # S1 solo puede usar P2: al retirar T1 en su bloque queda sin alternativas.
    patterns = tuple(p for p in micro.section_patterns if p.section_id != "S1") + (
        SectionPattern(section_id="S1", pattern_id="P2"),
    )
    source = write_input(
        tmp_path / "entrada", micro.model_copy(update={"section_patterns": patterns})
    )
    base = tmp_path / "base"
    assert runner.run(source, base).exit_code == 0
    out = tmp_path / "cambio"

    code = demo_change.main(["--base-run", str(base), "--out", str(out)])

    record = load(out / "change.json")
    assert code == 3
    assert record["reassignments"] is None
    assert "no aplicable" in record["reassignments_note"]
    assert record["changed_run"]["status"]["precheck"] == "NO_CANDIDATES"
    assert record["changed_run"]["objective"] is None
    assert not (out / "changed-run" / "assignments.csv").exists()


# Rechazos -------------------------------------------------------------------------------


def test_existing_output_is_rejected_intact(base: Path, tmp_path: Path) -> None:
    out = tmp_path / "cambio"
    out.mkdir()
    (out / "nota.txt").write_text("conservar", encoding="utf-8")

    assert demo_change.main(["--base-run", str(base), "--out", str(out)]) == 2
    assert [p.name for p in out.iterdir()] == ["nota.txt"]


@pytest.mark.parametrize("inside", ["", "input", "input/cambio"])
def test_output_inside_base_is_rejected(base: Path, inside: str) -> None:
    before = tree_hashes(base)

    assert demo_change.main(["--base-run", str(base), "--out", str(base / inside)]) == 2
    assert tree_hashes(base) == before


def test_greedy_or_incomplete_base_is_rejected(tmp_path: Path, micro: Instance) -> None:
    greedy = tmp_path / "greedy"
    runner.run(DATA / "micro", greedy, solver="greedy")
    assert demo_change.main(["--base-run", str(greedy), "--out", str(tmp_path / "a")]) == 2

    patterns = tuple(p for p in micro.section_patterns if p.section_id != "S1") + (
        SectionPattern(section_id="S1", pattern_id="P2"),
        SectionPattern(section_id="S1", pattern_id="P1"),
    )
    sections = tuple(
        s.model_copy(update={"enrollment": 60}) if s.id == "S2" else s for s in micro.sections
    )
    source = write_input(
        tmp_path / "e",
        micro.model_copy(update={"sections": sections, "section_patterns": patterns}),
    )
    empty = tmp_path / "vacia"
    assert runner.run(source, empty).exit_code == 3
    assert demo_change.main(["--base-run", str(empty), "--out", str(tmp_path / "b")]) == 2


def test_manipulated_base_is_rejected(base: Path, tmp_path: Path) -> None:
    rooms = base / "input" / "rooms.csv"
    rooms.write_bytes(rooms.read_bytes().replace(b",30\n", b",31\n"))
    out = tmp_path / "cambio"

    assert demo_change.main(["--base-run", str(base), "--out", str(out)]) == 2
    assert not out.exists()


def test_unrepresentable_base_parameters_are_rejected(base: Path, tmp_path: Path) -> None:
    path = base / "effective_config.json"
    config = load(path)
    config["num_search_workers"] = 4
    content = json_bytes(config)
    path.write_bytes(content)
    metrics = load(base / "metrics.json")
    metrics["input"]["effective_config_sha256"] = sha256_bytes(content)
    metrics["parameters"]["effective_config"] = config
    (base / "metrics.json").write_bytes(json_bytes(metrics))

    code = demo_change.main(["--base-run", str(base), "--out", str(tmp_path / "cambio")])

    assert code == 2


def test_invalid_base_via_cli_has_no_traceback(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--base-run",
            str(tmp_path / "nada"),
            "--out",
            str(tmp_path / "o"),
        ],
        capture_output=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=120,
    )

    assert result.returncode == 2
    assert "error:" in result.stderr
    assert "Traceback" not in result.stderr


# Recuento de reasignaciones -------------------------------------------------------------


def test_diff_assignments_categories() -> None:
    before = [("A", "P1", "R1"), ("B", "P1", "R1"), ("C", "P1", "R1"), ("D", "P1", "R1")]
    after = [("A", "P1", "R1"), ("B", "P2", "R1"), ("C", "P1", "R2"), ("D", "P2", "R2")]

    result = demo_change.diff_assignments(before, after)

    assert result["counts"] == {
        "unchanged": 1,
        "pattern_changed": 1,
        "room_changed": 1,
        "both_changed": 1,
    }
    assert result["total_sections"] == 4


def test_diff_requires_the_same_sections() -> None:
    with pytest.raises(ValueError):
        demo_change.diff_assignments([("A", "P1", "R1")], [("B", "P1", "R1")])


def test_remove_availability_requires_exactly_one_row() -> None:
    content = b"teacher_id,week_id,day_id,block_id\nT1,1,1,2\n"
    slot = {"teacher_id": "T1", "week_id": 1, "day_id": 1, "block_id": 3}

    with pytest.raises(demo_change.ChangeError, match="inconsistencia"):
        demo_change.remove_availability(content, slot)
