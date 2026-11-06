import os
import subprocess
import sys

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


def test_unknown_argument_is_rejected() -> None:
    result = run_python("-m", PROGRAM_NAME, "generate")

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
