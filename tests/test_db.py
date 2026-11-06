import sqlite3
from pathlib import Path

import pytest

from academic_timetabling_demo.db import (
    DERIVED_TABLES,
    DatabaseLoadError,
    connect,
    count_rows,
    ensure_schema,
    load_database,
    load_instance,
)
from academic_timetabling_demo.domain import (
    TABLES,
    DataValidationError,
    Instance,
    Room,
    read_instance,
)
from academic_timetabling_demo.synthetic import generate_case, generate_to_directory


@pytest.fixture
def instance() -> Instance:
    return generate_case("micro", 42).instance


def source_totals(connection: sqlite3.Connection) -> int:
    return sum(count_rows(connection, spec.name) for spec in TABLES)


def test_models_match_schema_columns(tmp_path: Path) -> None:
    connection = connect(tmp_path / "base.sqlite")
    ensure_schema(connection)
    for spec in TABLES:
        columns = [row[1] for row in connection.execute(f'PRAGMA table_info("{spec.name}")')]
        assert tuple(columns) == spec.columns
    connection.close()


def test_schema_has_exactly_twenty_source_tables(tmp_path: Path) -> None:
    connection = connect(tmp_path / "base.sqlite")
    ensure_schema(connection)
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    )
    tables = {name for (name,) in rows}
    connection.close()

    assert tables - set(DERIVED_TABLES) == {spec.name for spec in TABLES}
    assert len(TABLES) == 20


def test_every_connection_enforces_foreign_keys(tmp_path: Path) -> None:
    path = tmp_path / "base.sqlite"
    for _ in range(2):
        connection = connect(path)
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
        ensure_schema(connection)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO room_features VALUES ('R9', 'F9')")
        connection.close()


@pytest.mark.parametrize("case", ["micro", "demo"])
def test_real_load_from_generated_files(tmp_path: Path, case: str) -> None:
    out = tmp_path / case
    generate_to_directory(case, 42, out)
    loaded = read_instance(out)
    path = tmp_path / "base.sqlite"

    counts = load_database(path, loaded)

    connection = connect(path)
    assert counts == {spec.name: len(getattr(loaded, spec.name)) for spec in TABLES}
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    assert all(count_rows(connection, table) == 0 for table in DERIVED_TABLES)
    connection.close()


def test_integer_and_text_types_are_kept(tmp_path: Path, instance: Instance) -> None:
    path = tmp_path / "base.sqlite"
    load_database(path, instance)

    connection = connect(path)
    row = connection.execute(
        "SELECT typeof(id), typeof(capacity) FROM rooms ORDER BY id LIMIT 1"
    ).fetchone()
    connection.close()

    assert row == ("text", "integer")


def test_failure_during_insert_rolls_back_everything(tmp_path: Path, instance: Instance) -> None:
    connection = connect(tmp_path / "base.sqlite")
    ensure_schema(connection)
    # La última tabla falla de verdad cuando las anteriores ya recibieron filas.
    connection.execute(
        """
        CREATE TRIGGER fail_load BEFORE INSERT ON teacher_penalties
        BEGIN SELECT RAISE(ABORT, 'fallo forzado'); END
        """
    )

    with pytest.raises(sqlite3.IntegrityError, match="fallo forzado"):
        load_instance(connection, instance)

    assert source_totals(connection) == 0
    assert not connection.in_transaction

    connection.execute("DROP TRIGGER fail_load")
    assert load_instance(connection, instance)["sections"] == 3
    connection.close()


def test_invalid_data_is_rejected_before_inserting(tmp_path: Path, instance: Instance) -> None:
    duplicate = Room(id="R1", name="Otra", capacity=10)
    invalid = instance.model_copy(update={"rooms": (*instance.rooms, duplicate)})
    connection = connect(tmp_path / "base.sqlite")
    ensure_schema(connection)

    with pytest.raises(DataValidationError, match="clave duplicada"):
        load_instance(connection, invalid)

    assert source_totals(connection) == 0
    connection.close()


def test_non_empty_base_is_rejected_and_kept(tmp_path: Path, instance: Instance) -> None:
    path = tmp_path / "base.sqlite"
    load_database(path, instance)
    connection = connect(path)
    before = source_totals(connection)

    with pytest.raises(DatabaseLoadError, match="no está vacía"):
        load_instance(connection, instance)

    assert source_totals(connection) == before
    connection.close()


def test_base_with_foreign_schema_is_rejected(tmp_path: Path, instance: Instance) -> None:
    connection = connect(tmp_path / "base.sqlite")
    connection.execute("CREATE TABLE other (id INTEGER)")

    with pytest.raises(DatabaseLoadError, match="faltan tablas"):
        load_instance(connection, instance)

    connection.close()
