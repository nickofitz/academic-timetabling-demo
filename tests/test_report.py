"""Exportaciones: schedule.csv fiel a fuentes y asignaciones, y schedule.html seguro y offline."""

import csv
import io
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from academic_timetabling_demo import report
from academic_timetabling_demo.domain import (
    Instance,
    SectionGroup,
    read_instance,
)
from academic_timetabling_demo.report import SCHEDULE_COLUMNS, schedule_csv, session_rows

DATA = Path(__file__).resolve().parents[1] / "data" / "synthetic"
GOOD = [("S1", "P2", "R1"), ("S2", "P3", "R2"), ("S3", "P5", "R1")]


@pytest.fixture
def micro() -> Instance:
    return read_instance(DATA / "micro")


def parse_csv(content: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(content.decode("utf-8"), newline="")))


def expected_coordinates(instance: Instance, assignments) -> list[tuple]:
    """Oráculo independiente: (semana, día, bloque inicial, duración, sección, sesión)."""
    expected = []
    for section_id, pattern_id, _ in assignments:
        weeks = [w.week_id for w in instance.section_weeks if w.section_id == section_id]
        for session in instance.pattern_sessions:
            if session.pattern_id != pattern_id:
                continue
            for week in weeks:
                expected.append(
                    (
                        week,
                        session.day_id,
                        session.start_block_id,
                        session.duration_blocks,
                        section_id,
                        session.session_id,
                    )
                )
    return sorted(expected)


# schedule.csv ---------------------------------------------------------------------------


def test_micro_rows_by_hand(micro: Instance) -> None:
    rows = parse_csv(schedule_csv("RUN", session_rows(micro, GOOD)))

    # S1: 1 sesión x 2 semanas; S2: 1 sesión doble x 2 semanas; S3: 2 sesiones x 1 semana.
    assert len(rows) == 6
    assert list(rows[0]) == list(SCHEDULE_COLUMNS)
    doubles = [r for r in rows if r["section_id"] == "S2"]
    assert [
        (r["week_id"], r["duration_blocks"], r["start_time"], r["end_time"]) for r in doubles
    ] == [
        ("1", "2", "08:00", "10:00"),
        ("2", "2", "08:00", "10:00"),
    ]
    assert {r["run_id"] for r in rows} == {"RUN"}
    s3 = [
        (r["day_id"], r["start_block_id"], r["session_id"]) for r in rows if r["section_id"] == "S3"
    ]
    assert s3 == [("1", "3", "1"), ("2", "1", "2")]


def test_rows_match_independent_reconstruction() -> None:
    demo = read_instance(DATA / "demo")
    assignments = [
        ("S01", "P2X1-D24-B7", "R04"),
        ("S05", "P1X2-D4-B1", "R06"),
        ("S08", "P2X2-D35-B5", "R03"),
    ]
    instance = demo

    rows = parse_csv(schedule_csv("RUN", session_rows(instance, assignments)))
    found = sorted(
        (
            int(r["week_id"]),
            int(r["day_id"]),
            int(r["start_block_id"]),
            int(r["duration_blocks"]),
            r["section_id"],
            r["session_id"],
        )
        for r in rows
    )

    assert found == expected_coordinates(instance, assignments)


def test_multiple_groups_do_not_duplicate_sessions(micro: Instance) -> None:
    groups = (*micro.section_groups, SectionGroup(section_id="S1", group_id="G2"))
    instance = micro.model_copy(update={"section_groups": groups})

    rows = parse_csv(schedule_csv("RUN", session_rows(instance, GOOD)))

    s1 = [r for r in rows if r["section_id"] == "S1"]
    assert len(s1) == 2
    assert {r["group_ids"] for r in s1} == {'["G1", "G2"]'}
    assert json.loads(s1[0]["group_ids"]) == ["G1", "G2"]


def test_rows_are_sorted_numerically(micro: Instance) -> None:
    rows = parse_csv(schedule_csv("RUN", session_rows(micro, GOOD)))
    keys = [
        (
            int(r["week_id"]),
            int(r["day_id"]),
            int(r["start_block_id"]),
            r["room_id"],
            r["section_id"],
        )
        for r in rows
    ]

    assert keys == sorted(keys)


def test_csv_bytes_are_utf8_lf_and_roundtrip_special_names(micro: Instance) -> None:
    hostile = 'Sección "uno", <b>&</b>\nlínea'
    sections = tuple(
        s.model_copy(update={"name": hostile}) if s.id == "S1" else s for s in micro.sections
    )
    content = schedule_csv(
        "RUN", session_rows(micro.model_copy(update={"sections": sections}), GOOD)
    )

    assert b"\r" not in content  # finales LF, incluso con un salto dentro de un nombre
    content.decode("utf-8")
    rows = parse_csv(content)
    assert {r["section_name"] for r in rows if r["section_id"] == "S1"} == {hostile}


def test_unknown_assignment_cannot_be_presented(micro: Instance) -> None:
    with pytest.raises(report.ReportError):
        session_rows(micro, [("S1", "P9", "R1")])


# schedule.html --------------------------------------------------------------------------


class _Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.scripts: list[dict] = []
        self.tags: list[str] = []
        self._current: dict | None = None

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == "script":
            self._current = {"attrs": dict(attrs), "text": ""}

    def handle_endtag(self, tag):
        if tag == "script" and self._current is not None:
            self.scripts.append(self._current)
            self._current = None

    def handle_data(self, data):
        if self._current is not None:
            self._current["text"] += data


METRICS = {
    "run_id": "20260101T000000Z-abc",
    "created_utc": "2026-01-01T00:00:00Z",
    "parameters": {"solver": "cp-sat"},
    "status": {"solver": "OPTIMAL", "audit": "PASSED", "integrity": "VERIFIED"},
    "costs": {"objective": 3, "cost_d": 0, "cost_e": 3},
    "counts": {"assigned_sections": 3, "sections": 3},
    "timings_seconds": {"solve": 0.01, "total": 0.05},
    "provenance": {"status": "VERIFIED", "data_seed": 42},
}


def render(instance: Instance, metrics: dict = METRICS) -> str:
    rows = session_rows(instance, GOOD)
    return report.render_html(
        report.presentation(instance, rows, instance.config, metrics)
    ).decode()


def test_html_is_self_contained(micro: Instance) -> None:
    html = render(micro)

    assert not re.search(r"(https?:)?//[a-z0-9.-]+\.[a-z]{2,}", html, re.I)
    for forbidden in (
        "fetch(",
        "XMLHttpRequest",
        "import(",
        "eval(",
        "innerHTML",
        " onclick=",
        "<link",
    ):
        assert forbidden not in html
    assert "Datos sintéticos" in html
    assert 'lang="es"' in html


def test_html_shows_real_run_indicators(micro: Instance) -> None:
    html = render(micro)

    assert "20260101T000000Z-abc" in html
    assert "OPTIMAL: óptimo demostrado por CP-SAT" in html
    assert "3 = 10·0 + 1·3" in html
    assert "3 de 3" in html
    assert "42 (verificada por el manifiesto)" in html


@pytest.mark.parametrize(
    ("solver", "status", "label"),
    [
        ("cp-sat", {"solver": "FEASIBLE"}, "FEASIBLE: solución factible de CP-SAT, sin prueba"),
        ("greedy", {"baseline": "COMPLETE"}, "COMPLETE: heurística voraz completa, sin garantía"),
    ],
)
def test_html_never_calls_feasible_or_greedy_optimal(micro, solver, status, label) -> None:
    metrics = {
        **METRICS,
        "parameters": {"solver": solver},
        "status": {**status, "audit": "PASSED", "integrity": "VERIFIED"},
        "timings_seconds": {"baseline": 0.001, "solve": 0.01},
    }

    html = render(micro, metrics)

    assert label in html
    assert "óptimo demostrado" not in html


def test_unverified_data_seed_is_not_shown(micro: Instance) -> None:
    metrics = {**METRICS, "provenance": {"status": "MISMATCH", "data_seed": None}}

    assert "no acreditada" in render(micro, metrics)


def test_hostile_names_stay_inside_json_and_text(micro: Instance) -> None:
    payload = "</script><script>window.x=1</script><img src=x onerror=alert(1)> & \"q\" 's'"
    sections = tuple(s.model_copy(update={"name": payload}) for s in micro.sections)
    rooms = tuple(r.model_copy(update={"name": payload}) for r in micro.rooms)
    instance = micro.model_copy(update={"sections": sections, "rooms": rooms})
    metrics = {**METRICS, "run_id": payload}

    html = render(instance, metrics)
    parser = _Collector()
    parser.feed(html)

    assert len(parser.scripts) == 2  # solo los bloques de la plantilla
    assert "img" not in parser.tags
    data = json.loads(
        next(s["text"] for s in parser.scripts if s["attrs"].get("type") == "application/json")
    )
    assert data["run"]["run_id"] == payload
    assert {s["section_name"] for s in data["sessions"]} == {payload}
    assert "&lt;/script&gt;" in html  # en los textos renderizados con autoescape


def test_script_json_escapes_closing_tags() -> None:
    text = report.script_json({"a": "</script><!-- &  "})

    assert "<" not in text and ">" not in text and "&" not in text
    assert json.loads(text) == {"a": "</script><!-- &  "}
