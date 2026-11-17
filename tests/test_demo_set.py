"""El conjunto docs/demo conserva sus bytes exactos y sigue siendo comparable."""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from academic_timetabling_demo.compare import compare_runs
from academic_timetabling_demo.metrics import combined_hash

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "docs" / "demo"
RUNS = ("cpsat", "greedy", "changed/changed-run")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metrics(run: str) -> dict:
    return json.loads((DEMO / run / "metrics.json").read_text(encoding="utf-8"))


@pytest.mark.skipif(shutil.which("git") is None, reason="git no está disponible")
def test_git_does_not_convert_the_demo_set() -> None:
    files = [
        "docs/demo/cpsat/input/rooms.csv",
        "docs/demo/cpsat/metrics.json",
        "docs/demo/cpsat/schedule.html",
        "docs/demo/preview.png",
    ]
    result = subprocess.run(
        ["git", "-C", str(ROOT), "check-attr", "text", "--", *files],
        capture_output=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        pytest.skip("no es un repositorio Git")

    assert result.stdout.splitlines() == [f"{name}: text: unset" for name in files]


@pytest.mark.parametrize("run", RUNS)
def test_recorded_hashes_match_the_bytes(run: str) -> None:
    record = metrics(run)
    directory = DEMO / run

    files = record["input"]["files"]
    assert {name: sha(directory / "input" / name) for name in files} == files
    assert combined_hash(files) == record["input"]["combined_sha256"]
    assert sha(directory / "effective_config.json") == record["input"]["effective_config_sha256"]
    for name, digest in record["export"]["files"].items():
        assert sha(directory / name) == digest


def test_demo_runs_remain_comparable() -> None:
    code, report = compare_runs([DEMO / "greedy", DEMO / "cpsat"])

    assert code == 0, report["reason"]
    assert report["difference"]["absolute"] == 4


def test_changed_run_is_rejected_against_the_base() -> None:
    code, report = compare_runs([DEMO / "greedy", DEMO / "changed" / "changed-run"])

    assert code == 2
    assert "entradas difieren" in report["reason"]
