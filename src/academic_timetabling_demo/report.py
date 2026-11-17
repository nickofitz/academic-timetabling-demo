"""Exportaciones de una corrida válida: schedule.csv y schedule.html (Hito 5).

Se construyen solo desde el snapshot `input/`, la configuración efectiva y las asignaciones de
la propia corrida. Esta reconstrucción es de presentación: el auditor no la importa.
"""

import csv
import io
import json
from collections import defaultdict
from dataclasses import dataclass
from importlib import resources

import jinja2

from academic_timetabling_demo.domain import Instance, RunConfig

SCHEDULE_COLUMNS = (
    "run_id",
    "section_id",
    "section_name",
    "pattern_id",
    "session_id",
    "week_id",
    "day_id",
    "start_block_id",
    "duration_blocks",
    "start_time",
    "end_time",
    "room_id",
    "room_name",
    "teacher_id",
    "teacher_name",
    "group_ids",
    "enrollment",
    "room_capacity",
)
DAY_NAMES = {1: "Lunes", 2: "Martes", 3: "Miércoles", 4: "Jueves", 5: "Viernes", 6: "Sábado"}
DAY_NAMES[7] = "Domingo"


class ReportError(RuntimeError):
    """Las asignaciones no se pueden presentar con las fuentes del snapshot."""


@dataclass(frozen=True)
class SessionRow:
    section_id: str
    section_name: str
    pattern_id: str
    session_id: str
    week_id: int
    day_id: int
    start_block_id: int
    duration_blocks: int
    start_time: str
    end_time: str
    room_id: str
    room_name: str
    teacher_id: str
    teacher_name: str
    group_ids: tuple[str, ...]
    enrollment: int
    room_capacity: int

    def sort_key(self) -> tuple:
        return (
            self.week_id,
            self.day_id,
            self.start_block_id,
            self.room_id,
            self.section_id,
            self.session_id,
        )


def session_rows(instance: Instance, assignments: list[tuple[str, str, str]]) -> list[SessionRow]:
    """Una fila por sesión y semana activa; una sesión doble es una fila de duración 2."""
    sections = {s.id: s for s in instance.sections}
    rooms = {r.id: r for r in instance.rooms}
    teachers = {t.id: t for t in instance.teachers}
    blocks = {b.id: b for b in instance.blocks}
    sessions = defaultdict(list)
    for session in instance.pattern_sessions:
        sessions[session.pattern_id].append(session)
    weeks = defaultdict(list)
    for membership in instance.section_weeks:
        weeks[membership.section_id].append(membership.week_id)
    groups = defaultdict(list)
    for membership in instance.section_groups:
        groups[membership.section_id].append(membership.group_id)

    rows = []
    for section_id, pattern_id, room_id in assignments:
        section, room = sections.get(section_id), rooms.get(room_id)
        if section is None or room is None or not sessions.get(pattern_id):
            raise ReportError(f"asignación no presentable: {section_id}, {pattern_id}, {room_id}")
        teacher = teachers[section.teacher_id]
        for session in sessions[pattern_id]:
            last = session.start_block_id + session.duration_blocks - 1
            if session.start_block_id not in blocks or last not in blocks:
                raise ReportError(f"la sesión {pattern_id}/{session.session_id} sale del día")
            for week in sorted(weeks[section_id]):
                rows.append(
                    SessionRow(
                        section_id=section_id,
                        section_name=section.name,
                        pattern_id=pattern_id,
                        session_id=session.session_id,
                        week_id=week,
                        day_id=session.day_id,
                        start_block_id=session.start_block_id,
                        duration_blocks=session.duration_blocks,
                        start_time=blocks[session.start_block_id].start_time,
                        end_time=blocks[last].end_time,
                        room_id=room_id,
                        room_name=room.name,
                        teacher_id=teacher.id,
                        teacher_name=teacher.name,
                        group_ids=tuple(sorted(groups[section_id])),
                        enrollment=section.enrollment,
                        room_capacity=room.capacity,
                    )
                )
    return sorted(rows, key=SessionRow.sort_key)


def schedule_csv(run_id: str, rows: list[SessionRow]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(SCHEDULE_COLUMNS)
    for row in rows:
        writer.writerow(
            [
                run_id,
                row.section_id,
                row.section_name,
                row.pattern_id,
                row.session_id,
                row.week_id,
                row.day_id,
                row.start_block_id,
                row.duration_blocks,
                row.start_time,
                row.end_time,
                row.room_id,
                row.room_name,
                row.teacher_id,
                row.teacher_name,
                json.dumps(list(row.group_ids), ensure_ascii=False),
                row.enrollment,
                row.room_capacity,
            ]
        )
    return buffer.getvalue().encode("utf-8")


def script_json(data: object) -> str:
    """JSON seguro dentro de <script>: sin '<', '>' ni '&' literales que cierren el bloque."""
    text = json.dumps(data, ensure_ascii=False, sort_keys=True)
    for char, escaped in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026")):
        text = text.replace(char, escaped)
    return text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def _status_label(method: str, status: dict) -> str:
    if method == "greedy":
        return "COMPLETE: heurística voraz completa, sin garantía de optimalidad"
    if status.get("solver") == "OPTIMAL":
        return "OPTIMAL: óptimo demostrado por CP-SAT para estos datos y pesos"
    return "FEASIBLE: solución factible de CP-SAT, sin prueba de optimalidad"


def presentation(
    instance: Instance,
    rows: list[SessionRow],
    config: RunConfig,
    metrics: dict,
) -> dict[str, object]:
    """Proyección mínima para la vista: no incluye hashes ni una copia de metrics.json."""
    method = metrics["parameters"]["solver"]
    status = metrics["status"]
    costs = metrics["costs"]
    timings = metrics["timings_seconds"]
    provenance = metrics.get("provenance") or {}
    group_names = {g.id: g.name for g in instance.groups}
    if method == "greedy":
        timing = {"label": "Tiempo de la heurística voraz", "seconds": timings.get("baseline")}
    else:
        timing = {"label": "Tiempo de resolución de CP-SAT", "seconds": timings.get("solve")}
    return {
        "run": {
            "run_id": metrics["run_id"],
            "created_utc": metrics["created_utc"],
            "method": "Heurística voraz" if method == "greedy" else "CP-SAT",
            "status": _status_label(method, status),
            "assigned": metrics["counts"]["assigned_sections"],
            "total": metrics["counts"]["sections"],
            "audit": status["audit"],
            "integrity": status.get("integrity"),
            "objective": costs["objective"],
            "cost_d": costs["cost_d"],
            "cost_e": costs["cost_e"],
            "alpha": config.alpha,
            "beta": config.beta,
            "timing": timing,
            "data_seed": provenance.get("data_seed")
            if provenance.get("status") == "VERIFIED"
            else None,
        },
        "weeks": sorted(w.id for w in instance.weeks),
        "days": [
            {"id": d.id, "label": DAY_NAMES[d.id]}
            for d in sorted(instance.days, key=lambda d: d.id)
        ],
        "blocks": [
            {"id": b.id, "start": b.start_time, "end": b.end_time}
            for b in sorted(instance.blocks, key=lambda b: b.id)
        ],
        "rooms": [
            {"id": r.id, "name": r.name, "capacity": r.capacity}
            for r in sorted(instance.rooms, key=lambda r: r.id)
        ],
        "teachers": [
            {"id": t.id, "name": t.name} for t in sorted(instance.teachers, key=lambda t: t.id)
        ],
        "groups": [
            {"id": g.id, "name": g.name} for g in sorted(instance.groups, key=lambda g: g.id)
        ],
        "sessions": [
            {
                "section_id": row.section_id,
                "section_name": row.section_name,
                "pattern_id": row.pattern_id,
                "session_id": row.session_id,
                "week": row.week_id,
                "day": row.day_id,
                "start_block": row.start_block_id,
                "duration": row.duration_blocks,
                "start_time": row.start_time,
                "end_time": row.end_time,
                "room_id": row.room_id,
                "room_name": row.room_name,
                "teacher_id": row.teacher_id,
                "teacher_name": row.teacher_name,
                "group_ids": list(row.group_ids),
                "group_names": [group_names[g] for g in row.group_ids],
                "enrollment": row.enrollment,
            }
            for row in rows
        ],
    }


def _template() -> jinja2.Template:
    source = resources.files("academic_timetabling_demo").joinpath("templates/schedule.html")
    environment = jinja2.Environment(autoescape=True, undefined=jinja2.StrictUndefined)
    return environment.from_string(source.read_text(encoding="utf-8"))


def render_html(data: dict[str, object]) -> bytes:
    """HTML autocontenido: textos con autoescape y datos en JSON seguro para <script>."""
    html = _template().render(run=data["run"], data_json=script_json(data))
    return html.encode("utf-8")
