"""Heurística voraz: orden, desempates, recursos, costos y atascos sin retroceso."""

import itertools
import os
import random
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from academic_timetabling_demo.baseline import (
    COMPLETE,
    INCOMPLETE,
    Candidate,
    Choice,
    choose,
    read_candidates,
    run_greedy,
)
from academic_timetabling_demo.candidates import build_candidates
from academic_timetabling_demo.db import connect, load_instance
from academic_timetabling_demo.domain import (
    TABLES,
    Instance,
    SectionGroup,
    SectionPattern,
    SectionWeek,
    TeacherPenalty,
    read_instance,
)
from academic_timetabling_demo.model import build_and_solve
from academic_timetabling_demo.validate import audit

DATA = Path(__file__).resolve().parents[1] / "data" / "synthetic"


@pytest.fixture
def micro() -> Instance:
    return read_instance(DATA / "micro")


def prepared(instance: Instance) -> sqlite3.Connection:
    connection = connect(":memory:")
    load_instance(connection, instance)
    assert build_candidates(connection).status == "READY"
    return connection


def greedy(instance: Instance, **config: object):
    connection = prepared(instance)
    try:
        return run_greedy(connection, instance.config.model_copy(update=config))
    finally:
        connection.close()


def rows(result) -> list[tuple[str, str, str]]:
    return [(c.section_id, c.pattern_id, c.room_id) for c in result.assignments]


def stuck_instance(micro: Instance) -> Instance:
    """S1 elige P2 (más barato); S2 comparte docente y solo puede usar P2: queda bloqueada.

    Existe solución: S1 en P1 y S2 en P2. La heurística no la encuentra porque no retrocede.
    """
    sections = []
    for section in micro.sections:
        if section.id == "S2":
            section = section.model_copy(
                update={"teacher_id": "T1", "enrollment": 20, "blocks_per_session": 1}
            )
        if section.id != "S3":
            sections.append(section)
    return micro.model_copy(
        update={
            "sections": tuple(sections),
            "section_groups": tuple(g for g in micro.section_groups if g.section_id != "S3"),
            "section_weeks": tuple(w for w in micro.section_weeks if w.section_id != "S3"),
            "section_patterns": (
                SectionPattern(section_id="S1", pattern_id="P1"),
                SectionPattern(section_id="S1", pattern_id="P2"),
                SectionPattern(section_id="S2", pattern_id="P2"),
            ),
            "section_blocked": (),
        }
    )


def two_sections(micro: Instance, resource: str, s2_week: int) -> Instance:
    """S1 (P2: día 1, bloque 2) y S2 (P3: día 1, bloques 1-2) comparten solo `resource`."""
    sections = []
    for section in micro.sections:
        if section.id == "S1" and resource == "room":
            section = section.model_copy(update={"enrollment": 40})
        if section.id == "S1" and resource == "teacher":
            section = section.model_copy(update={"teacher_id": "T2"})
        if section.id != "S3":
            sections.append(section)
    groups = [g for g in micro.section_groups if g.section_id != "S3"]
    if resource == "group":
        groups = [g for g in groups if g.section_id != "S1"]
        groups.append(SectionGroup(section_id="S1", group_id="G2"))
    return micro.model_copy(
        update={
            "sections": tuple(sections),
            "section_groups": tuple(groups),
            "section_features": () if resource == "room" else micro.section_features,
            "section_weeks": (
                SectionWeek(section_id="S1", week_id=1),
                SectionWeek(section_id="S2", week_id=s2_week),
            ),
            "section_patterns": (
                SectionPattern(section_id="S1", pattern_id="P2"),
                SectionPattern(section_id="S2", pattern_id="P3"),
            ),
            "section_blocked": (),
        }
    )


# Núcleo puro: orden y desempates ---------------------------------------------------------


def candidate(alt_id, section, pattern, room, d=0, e=0, slots=()) -> Candidate:
    return Candidate(alt_id, section, pattern, room, d, e, frozenset(slots))


def test_static_order_by_domain_size_then_section_id(micro: Instance) -> None:
    candidates = [
        candidate(1, "A", "P1", "R1"),
        candidate(2, "A", "P2", "R1"),
        candidate(3, "C", "P1", "R2"),
        candidate(4, "B", "P1", "R3"),
    ]

    result = choose(candidates, ["A", "B", "C"], micro.config)

    # B y C tienen una alternativa: van primero, en orden de section_id.
    assert result.order == ("B", "C", "A")


def test_ties_break_by_cost_then_pattern_then_room(micro: Instance) -> None:
    candidates = [
        candidate(1, "S", "A", "R9", d=1),  # alpha=10: costo 10
        candidate(2, "S", "Z", "R2", e=3),  # costo 3: el más barato aunque su patrón sea "Z"
        candidate(3, "S", "Z", "R1", e=3),  # mismo costo y patrón: gana la sala R1
        candidate(4, "T", "B", "R1", e=1),
        candidate(5, "T", "A", "R1", e=1),  # mismo costo: gana el patrón A
    ]

    result = choose(candidates, ["S", "T"], micro.config)

    # T tiene menos alternativas, así que se elige primero.
    assert result.assignments == (Choice("T", "A", "R1"), Choice("S", "Z", "R1"))


def test_row_order_and_alt_ids_do_not_change_choices(micro: Instance) -> None:
    connection = prepared(micro)
    candidates, sections = read_candidates(connection)
    connection.close()
    expected = choose(candidates, sections, micro.config).assignments

    for seed in range(5):
        shuffled = list(candidates)
        random.Random(seed).shuffle(shuffled)
        renumbered = [
            Candidate(
                1000 - i, c.section_id, c.pattern_id, c.room_id, c.cost_d, c.cost_e, c.occupancy
            )
            for i, c in enumerate(shuffled)
        ]
        order = list(reversed(sections))
        assert choose(renumbered, order, micro.config).assignments == expected


def test_section_without_candidates_blocks_immediately(micro: Instance) -> None:
    result = choose([candidate(1, "B", "P1", "R1")], ["A", "B"], micro.config)

    assert result.status == INCOMPLETE
    assert result.blocked_section == "A"
    assert result.assignments == ()
    assert result.remaining_sections == ("A", "B")


# Caso micro y costos --------------------------------------------------------------------


def test_micro_is_complete_with_exact_costs(micro: Instance) -> None:
    result = greedy(micro)

    # Orden: S2 (1 alternativa), luego S1 y S3 (2 cada una).
    assert result.status == COMPLETE
    assert result.order == ("S2", "S1", "S3")
    assert rows(result) == [("S2", "P3", "R2"), ("S1", "P2", "R1"), ("S3", "P5", "R1")]
    assert (result.cost_d, result.cost_e, result.objective) == (0, 3, 3)
    report = audit(micro, rows(result), result.objective)
    assert report.passed
    assert (report.cost_d, report.cost_e) == (result.cost_d, result.cost_e)


def test_uses_same_candidates_and_weights_as_cpsat(micro: Instance) -> None:
    connection = prepared(micro)
    baseline = run_greedy(connection, micro.config)
    solved = build_and_solve(connection, micro.config)
    connection.close()

    assert (
        baseline.objective
        == micro.config.alpha * baseline.cost_d + micro.config.beta * baseline.cost_e
    )
    assert baseline.objective >= solved.objective


def s1_tradeoff(micro: Instance) -> Instance:
    """Solo S1: P1 cabe únicamente en R2 (E=3); P2 cabe en R1 (E=1) pero penaliza D=1."""
    unavailable = {("R1", week, 1, 1) for week in (1, 2)}
    return micro.model_copy(
        update={
            "sections": tuple(
                s.model_copy(update={"enrollment": 25}) for s in micro.sections if s.id == "S1"
            ),
            "section_groups": tuple(g for g in micro.section_groups if g.section_id == "S1"),
            "section_weeks": tuple(w for w in micro.section_weeks if w.section_id == "S1"),
            "section_patterns": tuple(p for p in micro.section_patterns if p.section_id == "S1"),
            "section_features": (),
            "section_blocked": (),
            "teacher_penalties": (
                TeacherPenalty(teacher_id="T1", day_id=1, block_id=2, penalty=1),
            ),
            "room_available": tuple(
                a
                for a in micro.room_available
                if (a.room_id, a.week_id, a.day_id, a.block_id) not in unavailable
            ),
        }
    )


@pytest.mark.parametrize(
    ("alpha", "beta", "expected"),
    [(10, 1, ("S1", "P1", "R2")), (1, 10, ("S1", "P2", "R1"))],
)
def test_weights_change_the_decision(micro: Instance, alpha: int, beta: int, expected) -> None:
    # alpha=10, beta=1: P1/R2 cuesta 3 y P2/R1 cuesta 11. alpha=1, beta=10: 30 contra 11.
    result = greedy(s1_tradeoff(micro), alpha=alpha, beta=beta)

    assert rows(result) == [expected]
    assert result.objective == alpha * result.cost_d + beta * result.cost_e


# Recursos -------------------------------------------------------------------------------


@pytest.mark.parametrize("resource", ["room", "teacher", "group"])
def test_shared_resource_in_same_week_blocks(micro: Instance, resource: str) -> None:
    # El choque cae en el segundo bloque de la sesión doble de S2.
    result = greedy(two_sections(micro, resource, s2_week=1))

    assert result.status == INCOMPLETE
    assert len(result.assignments) == 1


@pytest.mark.parametrize("resource", ["room", "teacher", "group"])
def test_shared_resource_in_disjoint_weeks_is_allowed(micro: Instance, resource: str) -> None:
    instance = two_sections(micro, resource, s2_week=2)
    result = greedy(instance)

    assert result.status == COMPLETE
    assert audit(instance, rows(result), result.objective).passed


# Atasco sin retroceso -------------------------------------------------------------------


def test_greedy_gets_stuck_where_a_solution_exists(micro: Instance) -> None:
    instance = stuck_instance(micro)
    result = greedy(instance)

    assert result.status == INCOMPLETE
    assert result.order == ("S1", "S2")
    assert rows(result) == [("S1", "P2", "R1")]
    assert result.blocked_section == "S2"
    assert result.remaining_sections == ("S2",)

    # Comprobación independiente: CP-SAT y la enumeración sí completan el horario.
    connection = prepared(instance)
    solved = build_and_solve(connection, instance.config)
    connection.close()
    options = [
        [
            (s.id, p.pattern_id, r.id)
            for p in instance.section_patterns
            if p.section_id == s.id
            for r in instance.rooms
        ]
        for s in instance.sections
    ]
    feasible = [
        report.objective
        for combination in itertools.product(*options)
        if (report := audit(instance, combination)).passed
    ]
    assert solved.status == "OPTIMAL"
    assert solved.objective == min(feasible) == 22


def test_greedy_does_not_modify_tables(micro: Instance) -> None:
    connection = prepared(micro)
    names = [spec.name for spec in TABLES] + ["alternative", "discarded_alternative", "occupancy"]

    def snapshot() -> dict[str, list]:
        return {n: sorted(connection.execute(f'SELECT * FROM "{n}"').fetchall()) for n in names}

    before = snapshot()
    run_greedy(connection, micro.config)
    after = snapshot()
    connection.close()

    assert after == before


def test_baseline_does_not_import_solver() -> None:
    code = (
        "import sys, academic_timetabling_demo.baseline; "
        "loaded = {'ortools', 'academic_timetabling_demo.model'} & set(sys.modules); "
        "assert not loaded, loaded"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, encoding="utf-8", env={**os.environ}
    )

    assert result.returncode == 0, result.stderr
