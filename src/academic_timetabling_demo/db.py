"""Carga transaccional de una entrada validada en SQLite."""

import sqlite3
from pathlib import Path

from academic_timetabling_demo.domain import (
    TABLES,
    DataValidationError,
    Instance,
    validate_instance,
)

# `schema.sql` de la raíz es la única fuente del esquema: la carga se ejecuta desde el repositorio.
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema.sql"
DERIVED_TABLES = ("alternative", "discarded_alternative", "occupancy")


class DatabaseLoadError(RuntimeError):
    """La base no admite la carga o esta falló."""


def connect(path: Path | str) -> sqlite3.Connection:
    """Abre una conexión con claves foráneas activas y transacciones explícitas."""
    connection = sqlite3.connect(path, isolation_level=None)
    connection.execute("PRAGMA foreign_keys = ON")
    if connection.execute("PRAGMA foreign_keys").fetchone() != (1,):
        connection.close()
        raise DatabaseLoadError("SQLite no activó foreign_keys en la conexión")
    return connection


def _existing_tables(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    )
    return {name for (name,) in rows}


def ensure_schema(connection: sqlite3.Connection) -> None:
    """Crea el esquema en una base vacía; rechaza una base con un esquema distinto."""
    existing = _existing_tables(connection)
    if not existing:
        connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        return
    missing = {spec.name for spec in TABLES}.union(DERIVED_TABLES) - existing
    if missing:
        raise DatabaseLoadError(f"faltan tablas en la base: {', '.join(sorted(missing))}")


def count_rows(connection: sqlite3.Connection, table: str) -> int:
    return connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]


def load_instance(connection: sqlite3.Connection, instance: Instance) -> dict[str, int]:
    """Carga todas las tablas fuente o ninguna. Devuelve las filas cargadas por tabla."""
    issues = validate_instance(instance)
    if issues:
        raise DataValidationError(issues)

    ensure_schema(connection)
    occupied = [
        table
        for table in (*(spec.name for spec in TABLES), *DERIVED_TABLES)
        if count_rows(connection, table)
    ]
    if occupied:
        raise DatabaseLoadError(f"la base no está vacía: {', '.join(occupied)}")

    connection.execute("BEGIN IMMEDIATE")
    try:
        for spec in TABLES:
            columns = ", ".join(spec.columns)
            placeholders = ", ".join("?" for _ in spec.columns)
            connection.executemany(
                f'INSERT INTO "{spec.name}" ({columns}) VALUES ({placeholders})',
                [
                    tuple(getattr(row, column) for column in spec.columns)
                    for row in getattr(instance, spec.name)
                ],
            )
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise DatabaseLoadError(f"claves foráneas incumplidas: {violations[:5]}")
        counts = {spec.name: count_rows(connection, spec.name) for spec in TABLES}
        connection.execute("COMMIT")
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    return counts


def load_database(path: Path | str, instance: Instance) -> dict[str, int]:
    """Abre la base indicada, carga la entrada y cierra la conexión."""
    connection = connect(path)
    try:
        return load_instance(connection, instance)
    finally:
        connection.close()
