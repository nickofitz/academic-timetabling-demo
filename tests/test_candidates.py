"""Pruebas del Hito 2. Los valores esperados del caso micro se calcularon a mano."""

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from academic_timetabling_demo.candidates import (
    DERIVED_TABLES,
    NO_PATTERNS,
    NO_ROOMS,
    CandidatesError,
    Precheck,
    build_candidates,
)
from academic_timetabling_demo.db import connect, load_instance
from academic_timetabling_demo.domain import (
    TABLES,
    Instance,
    RoomReservation,
    SectionBlocked,
    SectionFeature,
    SectionGroup,
    SectionPattern,
    SectionWeek,
    TeacherPenalty,
    read_instance,
)
from academic_timetabling_demo.synthetic import MANIFEST_FILE, generate_case

REPOSITORY = Path(__file__).resolve().parents[1]

Triple = tuple[str, str, str]


@pytest.fixture
def micro() -> Instance:
    return generate_case("micro", 42).instance


def prepare(instance: Instance) -> tuple[sqlite3.Connection, Precheck]:
    connection = connect(":memory:")
    load_instance(connection, instance)
    return connection, build_candidates(connection)


def change(instance: Instance, **tables: object) -> Instance:
    return instance.model_copy(update=tables)


def section_change(instance: Instance, section_id: str, **fields: object) -> Instance:
    sections = tuple(
        s.model_copy(update=fields) if s.id == section_id else s for s in instance.sections
    )
    return change(instance, sections=sections)


def alternatives(connection: sqlite3.Connection) -> dict[Triple, tuple[int, int]]:
    rows = connection.execute(
        "SELECT section_id, pattern_id, room_id, cost_d, cost_e FROM alternative"
    )
    return {(s, p, r): (d, e) for s, p, r, d, e in rows}


def discards(connection: sqlite3.Connection) -> dict[Triple, dict[str, object]]:
    found: dict[Triple, dict[str, object]] = {}
    for s, p, r, rule, evidence in connection.execute(
        "SELECT section_id, pattern_id, room_id, rule, evidence_json FROM discarded_alternative"
    ):
        found.setdefault((s, p, r), {})[rule] = json.loads(evidence)
    return found


def table_rows(connection: sqlite3.Connection, table: str) -> list[tuple]:
    return sorted(connection.execute(f'SELECT * FROM "{table}"').fetchall())


def snapshot(connection: sqlite3.Connection, tables: tuple[str, ...]) -> dict[str, list]:
    return {table: table_rows(connection, table) for table in tables}


SOURCE_TABLES = tuple(spec.name for spec in TABLES)


# Caso micro revisado a mano -------------------------------------------------------------


def test_micro_alternatives_and_costs(micro: Instance) -> None:
    connection, _ = prepare(micro)

    # cost_d: T1 penaliza día 1, bloque 1 con 2 (solo P1). cost_e: ceil(sobrante / 10).
    assert alternatives(connection) == {
        ("S1", "P1", "R1"): (2, 1),  # 30 - 25 = 5 asientos
        ("S1", "P2", "R1"): (0, 1),
        ("S2", "P3", "R2"): (0, 1),  # 50 - 40 = 10 asientos
        ("S3", "P5", "R1"): (0, 1),  # 30 - 20 = 10 asientos
        ("S3", "P5", "R2"): (0, 3),  # 50 - 20 = 30 asientos
    }


def test_micro_discards_and_evidence(micro: Instance) -> None:
    connection, _ = prepare(micro)

    assert discards(connection) == {
        ("S1", "P1", "R2"): {"FEATURES": {"missing": ["F1"]}},
        ("S1", "P2", "R2"): {"FEATURES": {"missing": ["F1"]}},
        ("S2", "P3", "R1"): {"CAPACITY": {"capacity": 30, "enrollment": 40}},
        ("S2", "P4", "R1"): {"CAPACITY": {"capacity": 30, "enrollment": 40}},
        # P4 ocupa día 2, bloques 2 y 3; la reserva toca solo el segundo bloque.
        ("S2", "P4", "R2"): {"ROOM_RESERVED": {"slots": [[2, 2, 3]]}},
        ("S3", "P6", "R1"): {"PROTECTED_SLOT": {"slots": [[1, 1, 1]]}},
        ("S3", "P6", "R2"): {"PROTECTED_SLOT": {"slots": [[1, 1, 1]]}},
    }


def test_micro_precheck_counts(micro: Instance) -> None:
    _, precheck = prepare(micro)

    assert precheck.status == "READY"
    assert precheck.pairs_before == 12
    assert precheck.alternatives_after == 5
    assert precheck.discarded_pairs == 7
    assert precheck.pairs_before == precheck.alternatives_after + precheck.discarded_pairs
    assert precheck.discards_by_rule == {
        "CAPACITY": 2,
        "FEATURES": 2,
        "TEACHER_UNAVAILABLE": 0,
        "ROOM_UNAVAILABLE": 0,
        "ROOM_RESERVED": 1,
        "PROTECTED_SLOT": 2,
    }
    assert {s.section_id: s.alternatives_after for s in precheck.sections} == {
        "S1": 2,
        "S2": 1,
        "S3": 2,
    }
    assert all(s.pairs_before == 4 and s.reasons == () for s in precheck.sections)
    assert precheck.empty_sections == {}


def test_micro_occupancy(micro: Instance) -> None:
    connection, precheck = prepare(micro)

    # S1: 2 semanas x 1 bloque x 3 recursos, por cada una de sus 2 alternativas = 12.
    # S2: 2 semanas x 2 bloques x 3 recursos = 12. S3: 1 semana x 2 bloques x 3 x 2 alt. = 12.
    assert precheck.occupancy_rows == 36
    rows = connection.execute(
        """
        SELECT o.resource_type, o.resource_id, o.week_id, o.day_id, o.block_id
        FROM occupancy AS o JOIN alternative AS a ON a.alt_id = o.alt_id
        WHERE a.section_id = 'S2'
        ORDER BY 1, 2, 3, 4, 5
        """
    ).fetchall()
    assert rows == [
        (kind, resource, week, 1, block)
        for kind, resource in (("group", "G2"), ("room", "R2"), ("teacher", "T2"))
        for week in (1, 2)
        for block in (1, 2)
    ]


def test_precheck_serializes_to_dict(micro: Instance) -> None:
    _, precheck = prepare(micro)

    data = precheck.as_dict()

    assert json.loads(json.dumps(data))["sections"][0]["section_id"] == "S1"


# Reglas de descarte ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("enrollment", "accepted", "cost_e"),
    [(30, True, 0), (31, False, None)],
)
def test_exact_and_insufficient_capacity(
    micro: Instance, enrollment: int, accepted: bool, cost_e: int | None
) -> None:
    connection, _ = prepare(section_change(micro, "S1", enrollment=enrollment))

    if accepted:
        assert alternatives(connection)[("S1", "P2", "R1")] == (0, cost_e)
    else:
        assert ("S1", "P2", "R1") not in alternatives(connection)
        assert "CAPACITY" in discards(connection)[("S1", "P2", "R1")]


@pytest.mark.parametrize(("surplus", "cost_e"), [(0, 0), (1, 1), (10, 1), (11, 2)])
def test_excess_seats_in_tens_rounded_up(micro: Instance, surplus: int, cost_e: int) -> None:
    connection, _ = prepare(section_change(micro, "S1", enrollment=30 - surplus))

    assert alternatives(connection)[("S1", "P2", "R1")] == (0, cost_e)


def test_missing_feature(micro: Instance) -> None:
    features = (*micro.section_features, SectionFeature(section_id="S3", feature_id="F1"))
    connection, _ = prepare(change(micro, section_features=features))

    assert discards(connection)[("S3", "P5", "R2")] == {"FEATURES": {"missing": ["F1"]}}
    assert ("S3", "P5", "R1") in alternatives(connection)


def test_teacher_unavailable_in_one_week(micro: Instance) -> None:
    available = tuple(
        slot
        for slot in micro.teacher_available
        if (slot.teacher_id, slot.week_id, slot.day_id, slot.block_id) != ("T1", 2, 1, 2)
    )
    connection, _ = prepare(change(micro, teacher_available=available))

    expected = {"TEACHER_UNAVAILABLE": {"teacher_id": "T1", "slots": [[2, 1, 2]]}}
    assert discards(connection)[("S1", "P2", "R1")] == expected
    assert ("S1", "P1", "R1") in alternatives(connection)


def test_room_unavailable(micro: Instance) -> None:
    available = tuple(
        slot
        for slot in micro.room_available
        if (slot.room_id, slot.week_id, slot.day_id, slot.block_id) != ("R1", 1, 1, 1)
    )
    connection, _ = prepare(change(micro, room_available=available))

    assert discards(connection)[("S1", "P1", "R1")] == {"ROOM_UNAVAILABLE": {"slots": [[1, 1, 1]]}}


def test_missing_availability_discards_everything(micro: Instance) -> None:
    connection, precheck = prepare(change(micro, teacher_available=(), room_available=()))

    assert precheck.alternatives_after == 0
    assert precheck.status == "NO_CANDIDATES"
    assert all(
        {"TEACHER_UNAVAILABLE", "ROOM_UNAVAILABLE"} <= set(reasons)
        for reasons in discards(connection).values()
    )


def test_reservation_in_second_block(micro: Instance) -> None:
    reservation = RoomReservation(room_id="R2", week_id=1, day_id=1, block_id=2, reason="Evento")
    rooms = (*micro.room_reservations, reservation)
    connection, _ = prepare(change(micro, room_reservations=rooms))

    # P3 ocupa día 1, bloques 1 y 2.
    assert discards(connection)[("S2", "P3", "R2")] == {"ROOM_RESERVED": {"slots": [[1, 1, 2]]}}


def test_protected_slot_in_second_block(micro: Instance) -> None:
    blocked = SectionBlocked(section_id="S2", week_id=2, day_id=1, block_id=2, reason="Franja")
    connection, _ = prepare(change(micro, section_blocked=(*micro.section_blocked, blocked)))

    assert discards(connection)[("S2", "P3", "R2")] == {"PROTECTED_SLOT": {"slots": [[2, 1, 2]]}}


def test_multiple_reasons_count_one_pair(micro: Instance) -> None:
    reservation = RoomReservation(room_id="R1", week_id=1, day_id=2, block_id=2, reason="Evento")
    rooms = (*micro.room_reservations, reservation)
    connection, precheck = prepare(change(micro, room_reservations=rooms))

    assert set(discards(connection)[("S2", "P4", "R1")]) == {"CAPACITY", "ROOM_RESERVED"}
    assert precheck.discarded_pairs == 7
    assert sum(precheck.discards_by_rule.values()) == 8
    distinct = connection.execute(
        "SELECT count(*) FROM (SELECT DISTINCT section_id, pattern_id, room_id, rule "
        "FROM discarded_alternative)"
    ).fetchone()[0]
    assert distinct == 8


# Ocupaciones y costos -------------------------------------------------------------------


def _s3_on_p6(micro: Instance, s3_week: int) -> Instance:
    """S1 queda solo en la semana 1; S3 usa P6 (día 1, bloque 1, como P1) en `s3_week`."""
    weeks = tuple(w for w in micro.section_weeks if w.section_id not in ("S1", "S3")) + (
        SectionWeek(section_id="S1", week_id=1),
        SectionWeek(section_id="S3", week_id=s3_week),
    )
    patterns = tuple(p for p in micro.section_patterns if p.section_id != "S3") + (
        SectionPattern(section_id="S3", pattern_id="P6"),
    )
    return change(micro, section_weeks=weeks, section_patterns=patterns, section_blocked=())


@pytest.mark.parametrize(("s3_week", "shared"), [(2, 0), (1, 1)])
def test_occupancy_coincides_only_in_shared_weeks(
    micro: Instance, s3_week: int, shared: int
) -> None:
    connection, _ = prepare(_s3_on_p6(micro, s3_week))

    common = connection.execute(
        """
        SELECT count(*) FROM occupancy AS o1
        JOIN alternative AS a1 ON a1.alt_id = o1.alt_id
        JOIN occupancy AS o2
          ON (o2.resource_type, o2.resource_id, o2.week_id, o2.day_id, o2.block_id)
           = (o1.resource_type, o1.resource_id, o1.week_id, o1.day_id, o1.block_id)
        JOIN alternative AS a2 ON a2.alt_id = o2.alt_id
        WHERE a1.section_id = 'S1' AND a1.pattern_id = 'P1' AND a1.room_id = 'R1'
          AND a2.section_id = 'S3' AND a2.pattern_id = 'P6' AND a2.room_id = 'R1'
          AND o1.resource_type = 'teacher'
        """
    ).fetchone()[0]

    assert common == shared


def test_occupancy_lists_every_declared_group_and_teacher(micro: Instance) -> None:
    groups = (*micro.section_groups, SectionGroup(section_id="S1", group_id="G2"))
    connection, _ = prepare(change(micro, section_groups=groups))

    rows = connection.execute(
        """
        SELECT DISTINCT o.resource_type, o.resource_id
        FROM occupancy AS o JOIN alternative AS a ON a.alt_id = o.alt_id
        WHERE a.section_id = 'S1' AND o.resource_type IN ('group', 'teacher')
        ORDER BY 1, 2
        """
    ).fetchall()
    assert rows == [("group", "G1"), ("group", "G2"), ("teacher", "T1")]
    # S3 comparte G1 con S1, pero no recibe G2: no se deducen grupos.
    s3_groups = connection.execute(
        """
        SELECT DISTINCT o.resource_id FROM occupancy AS o
        JOIN alternative AS a ON a.alt_id = o.alt_id
        WHERE a.section_id = 'S3' AND o.resource_type = 'group'
        """
    ).fetchall()
    assert s3_groups == [("G1",)]


def test_occupancy_has_no_duplicates(micro: Instance) -> None:
    connection, _ = prepare(micro)

    total, distinct = connection.execute(
        """
        SELECT count(*), (SELECT count(*) FROM (SELECT DISTINCT * FROM occupancy))
        FROM occupancy
        """
    ).fetchone()
    assert total == distinct


def test_weekly_penalty_counted_once_over_all_blocks(micro: Instance) -> None:
    penalties = (
        *micro.teacher_penalties,
        TeacherPenalty(teacher_id="T2", day_id=1, block_id=1, penalty=3),
        TeacherPenalty(teacher_id="T2", day_id=1, block_id=2, penalty=4),
    )
    connection, _ = prepare(change(micro, teacher_penalties=penalties))

    # P3 ocupa día 1, bloques 1 y 2 durante 2 semanas: 3 + 4, sin multiplicar por semanas.
    assert alternatives(connection)[("S2", "P3", "R2")] == (7, 1)


# Diagnóstico de dominio vacío ----------------------------------------------------------


def test_empty_domain_is_no_candidates(micro: Instance) -> None:
    _, precheck = prepare(section_change(micro, "S2", enrollment=60))

    assert precheck.status == "NO_CANDIDATES"
    assert precheck.empty_sections == {"S2": ("CAPACITY", "ROOM_RESERVED")}
    s2 = next(s for s in precheck.sections if s.section_id == "S2")
    assert (s2.pairs_before, s2.alternatives_after, s2.discarded_pairs) == (4, 0, 4)


def test_zero_rooms_reports_sections_without_pairs(micro: Instance) -> None:
    empty = change(
        micro,
        rooms=(),
        room_features=(),
        room_available=(),
        room_reservations=(),
    )
    _, precheck = prepare(empty)

    assert precheck.status == "NO_CANDIDATES"
    assert precheck.pairs_before == 0
    assert precheck.empty_sections == {"S1": (NO_ROOMS,), "S2": (NO_ROOMS,), "S3": (NO_ROOMS,)}


def test_section_without_patterns_is_diagnosed(micro: Instance) -> None:
    # El cargador rechaza esta entrada; se altera la base para probar solo el diagnóstico.
    connection = connect(":memory:")
    load_instance(connection, micro)
    connection.execute("DELETE FROM section_patterns WHERE section_id = 'S1'")

    precheck = build_candidates(connection)

    assert precheck.empty_sections == {"S1": (NO_PATTERNS,)}


def test_candidates_module_does_not_import_ortools() -> None:
    code = "import academic_timetabling_demo.candidates, sys; assert 'ortools' not in sys.modules"

    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        encoding="utf-8",
        env={**os.environ},
        timeout=60,
    )

    assert result.returncode == 0, result.stderr


# Repetición y atomicidad ---------------------------------------------------------------


def test_repeating_preparation_is_idempotent(micro: Instance) -> None:
    connection, first = prepare(micro)
    sources = snapshot(connection, SOURCE_TABLES)
    derived = snapshot(connection, DERIVED_TABLES)

    second = build_candidates(connection)

    assert second == first
    assert snapshot(connection, DERIVED_TABLES) == derived
    assert snapshot(connection, SOURCE_TABLES) == sources


def test_failure_keeps_previous_derived_tables(micro: Instance) -> None:
    connection, _ = prepare(micro)
    before = snapshot(connection, (*SOURCE_TABLES, *DERIVED_TABLES))
    connection.execute(
        """
        CREATE TRIGGER fail_prepare BEFORE INSERT ON occupancy
        BEGIN SELECT RAISE(ABORT, 'fallo forzado'); END
        """
    )

    with pytest.raises(sqlite3.IntegrityError, match="fallo forzado"):
        build_candidates(connection)

    assert not connection.in_transaction
    assert snapshot(connection, (*SOURCE_TABLES, *DERIVED_TABLES)) == before


def test_open_transaction_is_rejected(micro: Instance) -> None:
    connection, _ = prepare(micro)
    connection.execute("BEGIN")

    with pytest.raises(CandidatesError, match="transacción abierta"):
        build_candidates(connection)


# Caso demo -----------------------------------------------------------------------------


def test_demo_keeps_witness_alternative() -> None:
    directory = REPOSITORY / "data" / "synthetic" / "demo"
    witness = json.loads((directory / MANIFEST_FILE).read_text(encoding="utf-8"))["witness"]
    connection, precheck = prepare(read_instance(directory))

    found = alternatives(connection)
    assert precheck.status == "READY"
    assert precheck.pairs_before == precheck.alternatives_after + precheck.discarded_pairs
    for item in witness:
        assert (item["section_id"], item["pattern_id"], item["room_id"]) in found
