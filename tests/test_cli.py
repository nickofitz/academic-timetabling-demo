import os
import subprocess
import sys
from pathlib import Path

import pytest

from academic_timetabling_demo import cli
from academic_timetabling_demo.domain import read_instance
from academic_timetabling_demo.synthetic import MANIFEST_FILE

PROGRAM_NAME = "academic_timetabling_demo"


def run_python(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        capture_output=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=60,
    )


def test_help_describes_program() -> None:
    result = run_python("-m", PROGRAM_NAME, "--help")

    assert result.returncode == 0, result.stderr
    assert PROGRAM_NAME in result.stdout
    assert "programación académica" in result.stdout
    assert "datos sintéticos" in result.stdout
    assert "generate" in result.stdout


def test_generate_help() -> None:
    result = run_python("-m", PROGRAM_NAME, "generate", "--help")

    assert result.returncode == 0, result.stderr
    assert "--case" in result.stdout


def test_future_commands_are_rejected() -> None:
    result = run_python("-m", PROGRAM_NAME, "compare")

    assert result.returncode == 2
    assert PROGRAM_NAME in result.stderr


@pytest.mark.parametrize("command", ["run", "audit"])
def test_commands_require_their_arguments(command: str) -> None:
    result = run_python("-m", PROGRAM_NAME, command)

    assert result.returncode == 2
    assert "--input" in result.stderr


def test_import_has_no_side_effects() -> None:
    code = (
        f"import {PROGRAM_NAME}, {PROGRAM_NAME}.cli, {PROGRAM_NAME}.__main__, sys; "
        "assert 'ortools' not in sys.modules"
    )

    result = run_python("-c", code)

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""


def test_importing_solver_modules_runs_and_writes_nothing(tmp_path: Path) -> None:
    modules = ", ".join(
        f"{PROGRAM_NAME}.{name}" for name in ("model", "validate", "runner", "metrics")
    )

    result = subprocess.run(
        [sys.executable, "-c", f"import {modules}"],
        capture_output=True,
        encoding="utf-8",
        cwd=tmp_path,
        env={**os.environ},
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert (result.stdout, result.stderr) == ("", "")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("command", ["run", "audit"])
def test_run_and_audit_help(command: str) -> None:
    result = run_python("-m", PROGRAM_NAME, command, "--help")

    assert result.returncode == 0, result.stderr
    assert "--input" in result.stdout


DATA = Path(__file__).resolve().parents[1] / "data" / "synthetic"


def test_run_and_standalone_audit(tmp_path: Path) -> None:
    out = tmp_path / "corrida"

    run = run_python(
        "-m", PROGRAM_NAME, "run", "--input", str(DATA / "micro"), "--solver", "cp-sat",
        "--time-limit", "10", "--seed", "3", "--out", str(out),
    )  # fmt: skip
    audit = run_python(
        "-m", PROGRAM_NAME, "audit", "--input", str(DATA / "micro"),
        "--assignments", str(out / "assignments.csv"),
        "--config", str(out / "effective_config.json"), "--reported-objective", "3",
    )  # fmt: skip

    assert run.returncode == 0, run.stderr
    assert "OPTIMAL" in run.stdout
    assert audit.returncode == 0, audit.stderr
    assert '"status": "PASSED"' in audit.stdout
    assert '"reported_objective": 3' in audit.stdout


def test_audit_detects_manipulated_assignments(tmp_path: Path) -> None:
    path = tmp_path / "assignments.csv"
    path.write_text("section_id,pattern_id,room_id\nS1,P1,R1\nS2,P3,R2\nS3,P6,R1\n", "utf-8")

    result = run_python(
        "-m", PROGRAM_NAME, "audit", "--input", str(DATA / "micro"), "--assignments", str(path)
    )

    assert result.returncode == 4
    assert '"audit_valid": false' in result.stdout
    assert "ROOM_CLASH" in result.stdout


def test_audit_reports_false_objective(tmp_path: Path) -> None:
    path = tmp_path / "assignments.csv"
    path.write_text("section_id,pattern_id,room_id\nS1,P2,R1\nS2,P3,R2\nS3,P5,R1\n", "utf-8")

    result = run_python(
        "-m", PROGRAM_NAME, "audit", "--input", str(DATA / "micro"),
        "--assignments", str(path), "--reported-objective", "1",
    )  # fmt: skip

    assert result.returncode == 4
    assert "OBJECTIVE_MISMATCH" in result.stdout


def test_audit_rejects_unreadable_assignments(tmp_path: Path) -> None:
    path = tmp_path / "assignments.csv"
    path.write_text("seccion\nS1\n", "utf-8")

    result = run_python(
        "-m", PROGRAM_NAME, "audit", "--input", str(DATA / "micro"), "--assignments", str(path)
    )

    assert result.returncode == 2
    assert "encabezado" in result.stderr


@pytest.mark.parametrize(
    "extra",
    [
        ["--time-limit", "0"],
        ["--time-limit", "-1"],
        ["--time-limit", "inf"],
        ["--time-limit", "nan"],
        ["--time-limit", "abc"],
        ["--seed", "-1"],
        ["--seed", "1.5"],
        ["--solver", "otro"],
    ],
)
def test_run_rejects_invalid_parameters(tmp_path: Path, extra: list[str]) -> None:
    out = tmp_path / "corrida"

    result = run_python(
        "-m", PROGRAM_NAME, "run", "--input", str(DATA / "micro"), "--out", str(out), *extra
    )

    assert result.returncode == 2
    assert not out.exists()


def test_run_greedy_is_not_implemented(tmp_path: Path) -> None:
    out = tmp_path / "corrida"

    result = run_python(
        "-m", PROGRAM_NAME, "run", "--input", str(DATA / "micro"),
        "--solver", "greedy", "--out", str(out),
    )  # fmt: skip

    assert result.returncode == 2
    assert "no está implementado" in result.stderr
    assert not out.exists()


def test_run_rejects_non_empty_output(tmp_path: Path) -> None:
    (tmp_path / "assignments.csv").write_text("antiguo", "utf-8")

    result = run_python(
        "-m", PROGRAM_NAME, "run", "--input", str(DATA / "micro"), "--out", str(tmp_path)
    )

    assert result.returncode == 2
    assert [p.name for p in tmp_path.iterdir()] == ["assignments.csv"]


@pytest.mark.parametrize("case", ["micro", "demo"])
def test_generate_creates_valid_case(tmp_path: Path, case: str) -> None:
    out = tmp_path / case

    result = run_python("-m", PROGRAM_NAME, "generate", "--case", case, "--out", str(out))

    assert result.returncode == 0, result.stderr
    assert (out / MANIFEST_FILE).exists()
    read_instance(out)


def test_generate_rejects_non_empty_output(tmp_path: Path) -> None:
    (tmp_path / "nota.txt").write_text("conservar", encoding="utf-8")

    result = run_python("-m", PROGRAM_NAME, "generate", "--case", "micro", "--out", str(tmp_path))

    assert result.returncode == 2
    assert "no está vacía" in result.stderr
    assert [path.name for path in tmp_path.iterdir()] == ["nota.txt"]


@pytest.mark.parametrize(
    "arguments",
    [
        ["generate", "--case", "enorme", "--out", "x"],
        ["generate", "--case", "micro"],
        ["generate", "--case", "micro", "--seed", "-1", "--out", "x"],
        ["generate", "--case", "micro", "--seed", "abc", "--out", "x"],
    ],
)
def test_generate_rejects_invalid_arguments(arguments: list[str]) -> None:
    result = run_python("-m", PROGRAM_NAME, *arguments)

    assert result.returncode == 2


def test_internal_failure_returns_five(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(*_: object) -> None:
        raise RuntimeError("fallo simulado")

    monkeypatch.setattr(cli, "generate_to_directory", fail)

    code = cli.main(["generate", "--case", "micro", "--out", str(tmp_path / "x")])

    assert code == 5
    assert "fallo simulado" in capsys.readouterr().err
