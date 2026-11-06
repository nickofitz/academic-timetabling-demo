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


@pytest.mark.parametrize("command", ["run", "audit", "compare"])
def test_future_commands_are_rejected(command: str) -> None:
    result = run_python("-m", PROGRAM_NAME, command)

    assert result.returncode == 2
    assert PROGRAM_NAME in result.stderr


def test_import_has_no_side_effects() -> None:
    code = (
        f"import {PROGRAM_NAME}, {PROGRAM_NAME}.cli, {PROGRAM_NAME}.__main__, sys; "
        "assert 'ortools' not in sys.modules"
    )

    result = run_python("-c", code)

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""


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
