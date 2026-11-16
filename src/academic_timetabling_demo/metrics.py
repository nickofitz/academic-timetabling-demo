"""Evidencia de corridas: hashes, entorno, brecha y JSON estricto."""

import hashlib
import json
import math
import os
import platform
import sqlite3
import subprocess
import sys
from importlib import metadata
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def combined_hash(hashes: dict[str, str]) -> str:
    """Hash global de la lista ordenada de pares, una línea `nombre<TAB>hash` por archivo."""
    lines = "".join(f"{name}\t{digest}\n" for name, digest in sorted(hashes.items()))
    return sha256_bytes(lines.encode("utf-8"))


def relative_gap(objective: int | None, bound: float | None) -> float | None:
    """Brecha max(0, z - L) / max(1, |z|); null sin solución o sin cota finita."""
    if objective is None or bound is None or not math.isfinite(bound):
        return None
    return max(0.0, objective - bound) / max(1, abs(objective))


def json_bytes(data: object) -> bytes:
    """JSON estricto: rechaza NaN e infinitos en lugar de escribirlos."""
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
    return f"{text}\n".encode()


def _version(package: str) -> str | None:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return None


def _git(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(REPOSITORY), *args],
            capture_output=True,
            encoding="utf-8",
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def git_state() -> dict[str, object]:
    revision = _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain", "--untracked-files=no")
    return {
        "revision": revision.strip() if revision else None,
        "dirty": None if status is None else bool(status.strip()),
    }


def environment() -> dict[str, object]:
    """Versiones y sistema observados; null cuando un dato no está disponible."""
    return {
        "python": sys.version.split()[0],
        "ortools": _version("ortools"),
        "sqlite": sqlite3.sqlite_version,
        "package": _version("academic-timetabling-demo"),
        "git": git_state(),
        "system": platform.platform() or None,
        "machine": platform.machine() or None,
        "processor": platform.processor() or None,
        "cpu_count": os.cpu_count(),
    }
