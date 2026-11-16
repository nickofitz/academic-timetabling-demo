"""Auditor independiente: reglas, costos, hallazgos e independencia del solver."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from academic_timetabling_demo.candidates import build_candidates
from academic_timetabling_demo.db import connect, load_instance
from academic_timetabling_demo.domain import (
    Instance,
    PatternSession,
    RoomReservation,
    SectionBlocked,
    SectionGroup,
    read_instance,
)
from academic_timetabling_demo.model import build_and_solve
from academic_timetabling_demo.validate import AssignmentsError, audit, read_assignments

DATA = Path(__file__).resolve().parents[1] / "data" / "synthetic"
GOOD = [("S1", "P2", "R1"), ("S2", "P3", "R2"), ("S3", "P5", "R1")]


@pytest.fixture
def micro() -> Instance:
    return read_instance(DATA / "micro")


def rules(instance: Instance, rows, objective: int | None = None) -> set[str]:
    return {finding.rule for finding in audit(instance, rows, objective).findings}


def findings(instance: Instance, rows, rule: str):
    return [f for f in audit(instance, rows).findings if f.rule == rule]


# Costos recalculados desde las fuentes --------------------------------------------------


def test_good_schedule_passes_with_expected_costs(micro: Instance) -> None:
    report = audit(micro, GOOD, 3)

    assert report.passed
    assert report.status == "PASSED"
    assert (report.cost_d, report.cost_e, report.objective) == (0, 3, 3)


def test_costs_are_computed_by_hand_rules(micro: Instance) -> None:
    # P1: T1 penaliza día 1, bloque 1 con 2, contado una vez aunque S1 tenga 2 semanas.
    # E: S1 en R1 sobran 5 -> 1; S2 en R2 sobran 10 -> 1; S3 en R2 sobran 30 -> 3.
    report = audit(micro, [("S1", "P1", "R1"), ("S2", "P3", "R2"), ("S3", "P5", "R2")])

    assert report.passed
    assert (report.cost_d, report.cost_e, report.objective) == (2, 5, 25)


def test_configured_weights_change_objective(micro: Instance) -> None:
    config = micro.config.model_copy(update={"alpha": 1, "beta": 7})
    rows = [("S1", "P1", "R1"), ("S2", "P3", "R2"), ("S3", "P5", "R2")]

    assert audit(micro, rows, config=config).objective == 1 * 2 + 7 * 5


def test_false_objective_is_detected(micro: Instance) -> None:
    assert rules(micro, GOOD, objective=2) == {"OBJECTIVE_MISMATCH"}


# Identificadores y cobertura -----------------------------------------------------------


@pytest.mark.parametrize(
    "row",
    [("S9", "P2", "R1"), ("S1", "P9", "R1"), ("S1", "P2", "R9")],
)
def test_unknown_identifier(micro: Instance, row: tuple[str, str, str]) -> None:
    result = rules(micro, [row, *GOOD[1:]])

    assert "UNKNOWN_ID" in result
    assert "MISSING_ASSIGNMENT" in result  # una fila desconocida no cuenta como asignación


def test_missing_and_duplicate_sections(micro: Instance) -> None:
    assert "MISSING_ASSIGNMENT" in rules(micro, GOOD[:2])
    assert "DUPLICATE_ASSIGNMENT" in rules(micro, [*GOOD, ("S1", "P1", "R1")])


def test_empty_assignment_list_fails(micro: Instance) -> None:
    report = audit(micro, [])

    assert not report.passed
    assert {f.section_ids for f in report.findings} == {("S1",), ("S2",), ("S3",)}


# Patrón ---------------------------------------------------------------------------------


def test_changed_pattern_is_unauthorized_and_wrong_shape(micro: Instance) -> None:
    # P3 es de dos bloques; S1 exige uno y no lo autoriza.
    assert {"UNAUTHORIZED_PATTERN", "PATTERN_SHAPE"} <= rules(
        micro, [("S1", "P3", "R1"), *GOOD[1:]]
    )


def test_known_pattern_with_manipulated_sessions(micro: Instance) -> None:
    # Se altera la fuente: P5 pasa a tener sus dos sesiones en el mismo bloque.
    sessions = tuple(
        s.model_copy(update={"day_id": 1, "start_block_id": 3})
        if (s.pattern_id, s.session_id) == ("P5", "2")
        else s
        for s in micro.pattern_sessions
    )
    manipulated = micro.model_copy(update={"pattern_sessions": sessions})

    assert "PATTERN_OVERLAP" in rules(manipulated, GOOD)


def test_session_outside_the_day(micro: Instance) -> None:
    extra = PatternSession(
        pattern_id="P2", session_id="9", day_id=1, start_block_id=3, duration_blocks=2
    )
    manipulated = micro.model_copy(update={"pattern_sessions": (*micro.pattern_sessions, extra)})

    assert {"PATTERN_OUT_OF_DAY", "PATTERN_SHAPE"} <= rules(manipulated, GOOD)


# Sala y disponibilidad -----------------------------------------------------------------


def test_insufficient_capacity(micro: Instance) -> None:
    found = findings(micro, [GOOD[0], ("S2", "P3", "R1"), GOOD[2]], "CAPACITY")

    assert [(f.section_ids, f.resource) for f in found] == [(("S2",), "R1")]


def test_missing_feature(micro: Instance) -> None:
    found = findings(micro, [("S1", "P2", "R2"), *GOOD[1:]], "FEATURES")

    assert [(f.section_ids, f.resource) for f in found] == [(("S1",), "R2")]


def test_teacher_unavailable_reports_slot(micro: Instance) -> None:
    available = tuple(
        a
        for a in micro.teacher_available
        if (a.teacher_id, a.week_id, a.day_id, a.block_id) != ("T2", 2, 1, 2)
    )
    found = findings(
        micro.model_copy(update={"teacher_available": available}), GOOD, "TEACHER_UNAVAILABLE"
    )

    assert [(f.resource_type, f.resource, f.slot) for f in found] == [("teacher", "T2", (2, 1, 2))]


def test_room_unavailable_reports_slot(micro: Instance) -> None:
    available = tuple(
        a
        for a in micro.room_available
        if (a.room_id, a.week_id, a.day_id, a.block_id) != ("R1", 1, 2, 1)
    )
    found = findings(
        micro.model_copy(update={"room_available": available}), GOOD, "ROOM_UNAVAILABLE"
    )

    assert [(f.section_ids, f.resource, f.slot) for f in found] == [(("S3",), "R1", (1, 2, 1))]


def test_reservation_in_second_block(micro: Instance) -> None:
    reservation = RoomReservation(room_id="R2", week_id=1, day_id=1, block_id=2, reason="Evento")
    manipulated = micro.model_copy(
        update={"room_reservations": (*micro.room_reservations, reservation)}
    )

    found = findings(manipulated, GOOD, "ROOM_RESERVED")

    assert [(f.section_ids, f.slot) for f in found] == [(("S2",), (1, 1, 2))]


def test_protected_slot_in_second_block(micro: Instance) -> None:
    blocked = SectionBlocked(section_id="S2", week_id=2, day_id=1, block_id=2, reason="Franja")
    manipulated = micro.model_copy(update={"section_blocked": (*micro.section_blocked, blocked)})

    found = findings(manipulated, GOOD, "PROTECTED_SLOT")

    assert [(f.section_ids, f.slot) for f in found] == [(("S2",), (2, 1, 2))]


# Choques de cada recurso por separado ---------------------------------------------------


def clash_rules(instance: Instance, rows) -> set[str]:
    return {f.rule for f in audit(instance, rows).findings if f.rule.endswith("_CLASH")}


def test_room_clash_alone(micro: Instance) -> None:
    # S3 (T1, G1) en R2 con P6 y S2 (T2, G2) en R2 con P3 coinciden en la semana 1, día 1,
    # bloque 1: solo comparten la sala. Se quita la franja protegida para aislar el choque.
    instance = micro.model_copy(update={"section_blocked": ()})
    rows = [GOOD[0], ("S2", "P3", "R2"), ("S3", "P6", "R2")]

    assert clash_rules(instance, rows) == {"ROOM_CLASH"}
    assert clash_rules(instance, [GOOD[0], ("S2", "P3", "R2"), ("S3", "P5", "R2")]) == set()


def test_group_clash_alone(micro: Instance) -> None:
    # S1 pasa al grupo G2; S1 en R2 (P1) y S2 en R1 (P3) comparten solo ese grupo.
    groups = tuple(g for g in micro.section_groups if g.section_id != "S1")
    groups += (SectionGroup(section_id="S1", group_id="G2"),)
    instance = micro.model_copy(update={"section_groups": groups})
    rows = [("S1", "P1", "R2"), ("S2", "P3", "R1"), GOOD[2]]

    assert clash_rules(instance, rows) == {"GROUP_CLASH"}


def test_each_clash_type_reports_resource_and_slot(micro: Instance) -> None:
    rows = [("S1", "P1", "R1"), GOOD[1], ("S3", "P6", "R1")]
    report = audit(micro, rows)
    clashes = {
        (f.rule, f.resource_type, f.resource, f.slot, f.section_ids)
        for f in report.findings
        if f.rule.endswith("_CLASH")
    }

    assert clashes == {
        ("ROOM_CLASH", "room", "R1", (1, 1, 1), ("S1", "S3")),
        ("TEACHER_CLASH", "teacher", "T1", (1, 1, 1), ("S1", "S3")),
        ("GROUP_CLASH", "group", "G1", (1, 1, 1), ("S1", "S3")),
    }


def test_teacher_clash_alone(micro: Instance) -> None:
    sections = tuple(
        s.model_copy(update={"teacher_id": "T2"}) if s.id == "S1" else s for s in micro.sections
    )
    instance = micro.model_copy(update={"sections": sections})
    # S1 en P2 (día 1, bloque 2) y S2 en P3 (día 1, bloques 1-2): solo comparten docente.
    found = {f.rule for f in audit(instance, GOOD).findings}

    assert found == {"TEACHER_CLASH"}


def test_findings_serialize_with_coordinates(micro: Instance) -> None:
    data = audit(micro, [("S1", "P1", "R1"), GOOD[1], ("S3", "P6", "R1")]).as_dict()

    clash = next(f for f in data["findings"] if f["rule"] == "ROOM_CLASH")
    assert (clash["week_id"], clash["day_id"], clash["block_id"]) == (1, 1, 1)
    assert data["status"] == "FAILED"
    assert data["audit_valid"] is False


# Independencia --------------------------------------------------------------------------


def test_auditor_does_not_import_solver_or_preprocessing() -> None:
    code = (
        "import sys, academic_timetabling_demo.validate as v; "
        "forbidden = {'ortools', 'academic_timetabling_demo.model', "
        "'academic_timetabling_demo.candidates', 'academic_timetabling_demo.db'}; "
        "loaded = forbidden & set(sys.modules); "
        "assert not loaded, loaded"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, encoding="utf-8", env={**os.environ}
    )

    assert result.returncode == 0, result.stderr


def test_auditor_detects_altered_derived_cost(micro: Instance) -> None:
    connection = connect(":memory:")
    load_instance(connection, micro)
    build_candidates(connection)
    # Se manipula una tabla derivada: el solver cree que S3 en R2 no tiene holgura.
    connection.execute(
        "UPDATE alternative SET cost_e = 0 WHERE section_id = 'S3' AND room_id = 'R2'"
    )
    result = build_and_solve(connection, micro.config)
    connection.close()
    rows = [(a.section_id, a.pattern_id, a.room_id) for a in result.assignments]

    report = audit(micro, rows, result.objective)

    # Con el costo alterado: 1 + 1 + 0 = 2. Desde las fuentes: 1 + 1 + 3 = 5.
    assert result.objective == 2
    assert ("S3", "P5", "R2") in rows
    assert report.objective == 5
    assert {f.rule for f in report.findings} == {"OBJECTIVE_MISMATCH"}


# Lectura de assignments.csv -------------------------------------------------------------


def test_read_assignments_keeps_duplicates(tmp_path: Path) -> None:
    path = tmp_path / "assignments.csv"
    path.write_text("section_id,pattern_id,room_id\nS1,P2,R1\nS1,P2,R1\n", encoding="utf-8")

    assert read_assignments(path) == [("S1", "P2", "R1"), ("S1", "P2", "R1")]


@pytest.mark.parametrize(
    "content",
    [
        "section,pattern,room\nS1,P2,R1\n",
        "section_id,pattern_id,room_id\nS1,P2\n",
        "section_id,pattern_id,room_id\nS1,,R1\n",
        "",
    ],
)
def test_malformed_assignments_are_rejected(tmp_path: Path, content: str) -> None:
    path = tmp_path / "assignments.csv"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(AssignmentsError):
        read_assignments(path)


def test_missing_or_non_utf8_assignments(tmp_path: Path) -> None:
    with pytest.raises(AssignmentsError, match="falta"):
        read_assignments(tmp_path / "nada.csv")

    path = tmp_path / "latin.csv"
    path.write_bytes("section_id,pattern_id,room_id\nS\xe1,P2,R1\n".encode("latin-1"))
    with pytest.raises(AssignmentsError, match="UTF-8"):
        read_assignments(path)
