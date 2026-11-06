import csv
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from academic_timetabling_demo.domain import (
    TABLES,
    DataValidationError,
    read_instance,
)
from academic_timetabling_demo.synthetic import generate_to_directory

Rows = list[dict[str, str]]


@pytest.fixture
def micro(tmp_path: Path) -> Path:
    out = tmp_path / "micro"
    generate_to_directory("micro", 42, out)
    return out


def edit(directory: Path, table: str, change: Callable[[Rows], None]) -> None:
    path = directory / f"{table}.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or ())
        rows = list(reader)
    change(rows)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def set_cell(directory: Path, table: str, column: str, value: str, index: int = 0) -> None:
    edit(directory, table, lambda rows: rows[index].update({column: value}))


def rejected(directory: Path, file: str, text: str) -> None:
    with pytest.raises(DataValidationError) as caught:
        read_instance(directory)
    matching = [i for i in caught.value.issues if i.file == file and text in i.message]
    assert matching, str(caught.value)


def test_valid_instance_is_read(micro: Path) -> None:
    instance = read_instance(micro)

    assert len(instance.sections) == 3
    assert len(instance.rooms) == 2
    assert instance.config.alpha == 10


@pytest.mark.parametrize(
    "table",
    [
        "features",
        "room_features",
        "section_features",
        "room_reservations",
        "section_blocked",
        "teacher_penalties",
    ],
)
def test_optional_table_may_have_only_header(micro: Path, table: str) -> None:
    if table == "features":
        edit(micro, "room_features", lambda rows: rows.clear())
        edit(micro, "section_features", lambda rows: rows.clear())
    edit(micro, table, lambda rows: rows.clear())

    instance = read_instance(micro)

    assert getattr(instance, table) == ()


def test_identifiers_keep_leading_zeros(micro: Path) -> None:
    for spec in TABLES:
        path = micro / spec.file
        text = path.read_text(encoding="utf-8").replace("T1", "007")
        path.write_text(text, encoding="utf-8", newline="")

    instance = read_instance(micro)

    assert {teacher.id for teacher in instance.teachers} == {"007", "T2"}
    assert instance.sections[0].teacher_id == "007"


def test_missing_availability_is_preserved(micro: Path) -> None:
    edit(micro, "teacher_available", lambda rows: rows.clear())
    edit(micro, "room_available", lambda rows: rows.clear())

    instance = read_instance(micro)

    assert instance.teacher_available == ()
    assert instance.room_available == ()


def test_reservation_on_available_room_is_valid(micro: Path) -> None:
    instance = read_instance(micro)
    reservation = instance.room_reservations[0]

    assert any(
        (slot.room_id, slot.week_id, slot.day_id, slot.block_id)
        == (reservation.room_id, reservation.week_id, reservation.day_id, reservation.block_id)
        for slot in instance.room_available
    )


def test_demand_above_every_room_is_structurally_valid(micro: Path) -> None:
    set_cell(micro, "sections", "enrollment", "9999")

    assert read_instance(micro).sections[0].enrollment == 9999


def test_missing_source_file(micro: Path) -> None:
    (micro / "rooms.csv").unlink()

    rejected(micro, "rooms.csv", "falta el archivo")


def test_missing_config(micro: Path) -> None:
    (micro / "config.json").unlink()

    rejected(micro, "config.json", "falta el archivo")


def test_wrong_header(micro: Path) -> None:
    path = micro / "rooms.csv"
    path.write_text("id,nombre,capacity\nR1,Sala,30\n", encoding="utf-8")

    rejected(micro, "rooms.csv", "encabezado incorrecto")


def test_malformed_row_reports_row(micro: Path) -> None:
    path = micro / "rooms.csv"
    path.write_text("id,name,capacity\nR1,Sala 1,30\nR2,Sala 2\n", encoding="utf-8")

    with pytest.raises(DataValidationError) as caught:
        read_instance(micro)

    assert [i.row for i in caught.value.issues if i.file == "rooms.csv"] == [3]


def test_invalid_encoding(micro: Path) -> None:
    (micro / "rooms.csv").write_bytes("id,name,capacity\nR1,Sal\xe1,30\n".encode("latin-1"))

    rejected(micro, "rooms.csv", "UTF-8")


@pytest.mark.parametrize("value", ["30.0", "30.5", "true", "", "abc", "1e2", "٣٠"])
def test_invalid_integer_text_is_rejected(micro: Path, value: str) -> None:
    set_cell(micro, "rooms", "capacity", value)

    with pytest.raises(DataValidationError) as caught:
        read_instance(micro)

    issue = caught.value.issues[0]
    assert (issue.file, issue.row, issue.field) == ("rooms.csv", 2, "capacity")


@pytest.mark.parametrize(
    ("table", "column", "value"),
    [
        ("rooms", "capacity", "0"),
        ("rooms", "capacity", "-5"),
        ("sections", "enrollment", "0"),
        ("days", "id", "8"),
        ("weeks", "id", "0"),
        ("teacher_penalties", "penalty", "-1"),
        ("groups", "basis", "mismo_nivel"),
        ("teachers", "id", " T1"),
        ("teachers", "name", ""),
        ("blocks", "start_time", "8:00"),
        ("blocks", "end_time", "24:00"),
        ("blocks", "end_time", "07:00"),
    ],
)
def test_out_of_range_value_is_rejected(micro: Path, table: str, column: str, value: str) -> None:
    set_cell(micro, table, column, value)

    with pytest.raises(DataValidationError) as caught:
        read_instance(micro)

    assert any(issue.file == f"{table}.csv" for issue in caught.value.issues)


def test_duplicate_key(micro: Path) -> None:
    edit(micro, "rooms", lambda rows: rows.append(dict(rows[0])))

    rejected(micro, "rooms.csv", "clave duplicada")


@pytest.mark.parametrize(
    ("table", "column", "value"),
    [
        ("sections", "teacher_id", "T9"),
        ("room_features", "feature_id", "F9"),
        ("section_groups", "group_id", "G9"),
        ("pattern_sessions", "day_id", "3"),
        ("teacher_available", "week_id", "3"),
    ],
)
def test_broken_reference(micro: Path, table: str, column: str, value: str) -> None:
    set_cell(micro, table, column, value)

    rejected(micro, f"{table}.csv", "referencia rota")


@pytest.mark.parametrize("table", ["weeks", "days", "blocks"])
def test_empty_horizon(micro: Path, table: str) -> None:
    edit(micro, table, lambda rows: rows.clear())

    rejected(micro, f"{table}.csv", "el horizonte")


def test_weeks_must_be_consecutive(micro: Path) -> None:
    set_cell(micro, "weeks", "id", "3", index=1)

    rejected(micro, "weeks.csv", "consecutivas")


def test_blocks_must_be_consecutive(micro: Path) -> None:
    set_cell(micro, "blocks", "id", "4", index=2)

    rejected(micro, "blocks.csv", "consecutivos")


def test_block_with_different_duration(micro: Path) -> None:
    set_cell(micro, "blocks", "end_time", "11:30", index=2)

    rejected(micro, "blocks.csv", "no dura")


def test_overlapping_blocks(micro: Path) -> None:
    def overlap(rows: Rows) -> None:
        rows[1].update({"start_time": "08:30", "end_time": "09:30"})

    edit(micro, "blocks", overlap)

    rejected(micro, "blocks.csv", "se superpone")


def test_session_outside_day(micro: Path) -> None:
    set_cell(micro, "pattern_sessions", "start_block_id", "3", index=2)

    rejected(micro, "pattern_sessions.csv", "sale del día")


def test_overlapping_sessions(micro: Path) -> None:
    def overlap(rows: Rows) -> None:
        second = next(r for r in rows if (r["pattern_id"], r["session_id"]) == ("P5", "2"))
        second.update({"day_id": "1", "start_block_id": "3"})

    edit(micro, "pattern_sessions", overlap)

    rejected(micro, "pattern_sessions.csv", "se solapan")


def test_pattern_with_wrong_frequency(micro: Path) -> None:
    edit(micro, "section_patterns", lambda rows: rows[0].update({"pattern_id": "P5"}))

    rejected(micro, "section_patterns.csv", "sesiones")


def test_pattern_with_wrong_duration(micro: Path) -> None:
    edit(micro, "section_patterns", lambda rows: rows[0].update({"pattern_id": "P3"}))

    rejected(micro, "section_patterns.csv", "bloques")


@pytest.mark.parametrize(
    ("table", "label"),
    [
        ("section_groups", "grupo"),
        ("section_patterns", "patrón"),
    ],
)
def test_section_needs_membership(micro: Path, table: str, label: str) -> None:
    edit(micro, table, lambda rows: rows.__setitem__(slice(None), rows[1:]))
    if table == "section_patterns":
        edit(micro, table, lambda rows: rows.__setitem__(slice(None), rows[1:]))

    rejected(micro, "sections.csv", label)


def test_section_needs_active_weeks(micro: Path) -> None:
    edit(micro, "section_weeks", lambda rows: rows.__setitem__(slice(None), rows[2:]))

    rejected(micro, "sections.csv", "semana activa")


def test_block_outside_active_weeks(micro: Path) -> None:
    set_cell(micro, "section_blocked", "week_id", "2")

    rejected(micro, "section_blocked.csv", "fuera de las semanas activas")


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("alpha", -1),
        ("alpha", 1.5),
        ("alpha", True),
        ("beta", "1"),
        ("time_limit_seconds", 0),
        ("time_limit_seconds", True),
        ("random_seed", -1),
        ("num_search_workers", 0),
    ],
)
def test_invalid_config_value(micro: Path, key: str, value: object) -> None:
    path = micro / "config.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**config, key: value}), encoding="utf-8")

    with pytest.raises(DataValidationError) as caught:
        read_instance(micro)

    assert caught.value.issues[0].file == "config.json"
    assert caught.value.issues[0].field == key


def test_config_rejects_unknown_key_and_bad_json(micro: Path) -> None:
    path = micro / "config.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**config, "gamma": 1}), encoding="utf-8")
    rejected(micro, "config.json", "")

    path.write_text("{", encoding="utf-8")
    rejected(micro, "config.json", "JSON inválido")


def test_all_problems_are_reported_together(micro: Path) -> None:
    set_cell(micro, "rooms", "capacity", "0")
    set_cell(micro, "sections", "enrollment", "0")

    with pytest.raises(DataValidationError) as caught:
        read_instance(micro)

    assert {issue.file for issue in caught.value.issues} == {"rooms.csv", "sections.csv"}
