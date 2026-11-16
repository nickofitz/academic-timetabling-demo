"""Auditor independiente del solver y del preprocesamiento (Hito 3).

Recibe la entrada original, la configuración y las asignaciones (sección, patrón, sala).
No importa el modelo, los candidatos ni OR-Tools, y no consulta alternativas, descartes u
ocupaciones derivados: reconstruye sesiones, ocupaciones y costos por su cuenta, semana a
semana (especificación, sección 6).
"""

import csv
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from academic_timetabling_demo.domain import Instance, Issue, RunConfig

Slot = tuple[int, int, int]  # (semana, día, bloque)
ASSIGNMENT_COLUMNS = ("section_id", "pattern_id", "room_id")


@dataclass(frozen=True)
class Finding:
    rule: str
    section_ids: tuple[str, ...]
    detail: str
    resource: str | None = None
    slot: Slot | None = None
    resource_type: str | None = None

    def as_dict(self) -> dict[str, object]:
        week, day, block = self.slot or (None, None, None)
        return {
            "rule": self.rule,
            "section_ids": list(self.section_ids),
            "resource_type": self.resource_type,
            "resource_id": self.resource,
            "week_id": week,
            "day_id": day,
            "block_id": block,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class AuditReport:
    passed: bool
    findings: tuple[Finding, ...]
    cost_d: int
    cost_e: int
    objective: int
    reported_objective: int | None = None

    @property
    def status(self) -> str:
        return "PASSED" if self.passed else "FAILED"

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "audit_valid": self.passed,
            "cost_d": self.cost_d,
            "cost_e": self.cost_e,
            "objective": self.objective,
            "reported_objective": self.reported_objective,
            "findings": [finding.as_dict() for finding in self.findings],
        }


NOT_RUN = {
    "status": "NOT_RUN",
    "audit_valid": None,
    "cost_d": None,
    "cost_e": None,
    "objective": None,
    "reported_objective": None,
    "findings": [],
}


class AssignmentsError(ValueError):
    """El archivo de asignaciones no se puede leer como tabla de tres columnas."""

    def __init__(self, issues: Iterable[Issue]) -> None:
        self.issues = tuple(issues)
        super().__init__("\n".join(str(issue) for issue in self.issues))


def read_assignments(path: Path) -> list[tuple[str, str, str]]:
    """Lee un assignments.csv. No descarta filas repetidas: el auditor las informa."""
    name = path.name
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle, strict=True)
            header = tuple(next(reader, None) or ())
            if header != ASSIGNMENT_COLUMNS:
                expected = ",".join(ASSIGNMENT_COLUMNS)
                message = f"encabezado incorrecto; se esperaba {expected}"
                raise AssignmentsError([Issue(name, message, 1)])
            rows, issues = [], []
            for row_number, values in enumerate(reader, start=2):
                if len(values) != 3 or any(not value.strip() for value in values):
                    message = "se esperaban tres identificadores no vacíos"
                    issues.append(Issue(name, message, row_number))
                    continue
                rows.append((values[0], values[1], values[2]))
    except FileNotFoundError:
        raise AssignmentsError([Issue(name, "falta el archivo de asignaciones")]) from None
    except OSError as error:
        # Carpeta, permiso denegado u otro fallo de E/S: error de entrada, no del auditor.
        cause = f"{type(error).__name__}: {error.strerror or error}"
        message = f"no se pudo leer {path}: {cause}"
        raise AssignmentsError([Issue(name, message)]) from None
    except UnicodeDecodeError:
        raise AssignmentsError([Issue(name, "el archivo no está codificado en UTF-8")]) from None
    except csv.Error as error:
        raise AssignmentsError([Issue(name, f"CSV mal formado: {error}")]) from None
    if issues:
        raise AssignmentsError(issues)
    return rows


def audit(
    instance: Instance,
    assignments: Iterable[tuple[str, str, str]],
    reported_objective: int | None = None,
    config: RunConfig | None = None,
) -> AuditReport:
    """Audita un horario completo. `passed` es verdadero solo si no hay hallazgos."""
    config = config or instance.config
    findings: list[Finding] = []

    sections = {s.id: s for s in instance.sections}
    rooms = {r.id: r for r in instance.rooms}
    patterns = {p.id for p in instance.patterns}
    days = {d.id for d in instance.days}
    last_block = max((b.id for b in instance.blocks), default=0)
    authorized = {(sp.section_id, sp.pattern_id) for sp in instance.section_patterns}
    sessions: dict[str, list] = defaultdict(list)
    for ps in instance.pattern_sessions:
        sessions[ps.pattern_id].append(ps)
    weeks: dict[str, list[int]] = defaultdict(list)
    for sw in instance.section_weeks:
        weeks[sw.section_id].append(sw.week_id)
    groups: dict[str, list[str]] = defaultdict(list)
    for sg in instance.section_groups:
        groups[sg.section_id].append(sg.group_id)
    required = defaultdict(set)
    for sf in instance.section_features:
        required[sf.section_id].add(sf.feature_id)
    equipped = defaultdict(set)
    for rf in instance.room_features:
        equipped[rf.room_id].add(rf.feature_id)
    teacher_ok = {
        (t.teacher_id, t.week_id, t.day_id, t.block_id) for t in instance.teacher_available
    }
    room_ok = {(r.room_id, r.week_id, r.day_id, r.block_id) for r in instance.room_available}
    reserved = {(r.room_id, r.week_id, r.day_id, r.block_id) for r in instance.room_reservations}
    blocked = {(b.section_id, b.week_id, b.day_id, b.block_id) for b in instance.section_blocked}
    penalty = {(p.teacher_id, p.day_id, p.block_id): p.penalty for p in instance.teacher_penalties}

    # 1. Identificadores y exactamente una asignación por sección.
    count: dict[str, int] = defaultdict(int)
    valid: list[tuple[str, str, str]] = []
    for section_id, pattern_id, room_id in assignments:
        unknown = [
            label
            for label, ok in (
                (f"sección {section_id}", section_id in sections),
                (f"patrón {pattern_id}", pattern_id in patterns),
                (f"sala {room_id}", room_id in rooms),
            )
            if not ok
        ]
        if unknown:
            findings.append(Finding("UNKNOWN_ID", (section_id,), ", ".join(unknown)))
            continue
        count[section_id] += 1
        valid.append((section_id, pattern_id, room_id))
    for section_id in sorted(sections):
        if count[section_id] == 0:
            findings.append(Finding("MISSING_ASSIGNMENT", (section_id,), "sección sin asignar"))
        elif count[section_id] > 1:
            findings.append(
                Finding("DUPLICATE_ASSIGNMENT", (section_id,), f"{count[section_id]} asignaciones")
            )

    # 2. Reglas por sección, reconstruyendo cada bloque ocupado semana a semana.
    usage: dict[tuple[str, str, Slot], set[str]] = defaultdict(set)
    cost_d = cost_e = 0
    for section_id, pattern_id, room_id in valid:
        section, room = sections[section_id], rooms[room_id]
        own = sessions[pattern_id]

        if (section_id, pattern_id) not in authorized:
            findings.append(Finding("UNAUTHORIZED_PATTERN", (section_id,), f"patrón {pattern_id}"))
        if len(own) != section.sessions_per_week or any(
            ps.duration_blocks != section.blocks_per_session for ps in own
        ):
            findings.append(
                Finding(
                    "PATTERN_SHAPE",
                    (section_id,),
                    f"patrón {pattern_id}: {len(own)} sesiones; la sección exige "
                    f"{section.sessions_per_week} de {section.blocks_per_session} bloques",
                )
            )
        if room.capacity < section.enrollment:
            findings.append(
                Finding(
                    "CAPACITY",
                    (section_id,),
                    f"capacidad {room.capacity} < matrícula {section.enrollment}",
                    room_id,
                    resource_type="room",
                )
            )
        missing = required[section_id] - equipped[room_id]
        if missing:
            findings.append(
                Finding(
                    "FEATURES",
                    (section_id,),
                    f"falta {', '.join(sorted(missing))}",
                    room_id,
                    resource_type="room",
                )
            )

        weekly: list[tuple[int, int]] = []
        for ps in own:
            end = ps.start_block_id + ps.duration_blocks - 1
            if ps.day_id not in days or ps.start_block_id < 1 or end > last_block:
                findings.append(
                    Finding(
                        "PATTERN_OUT_OF_DAY",
                        (section_id,),
                        f"patrón {pattern_id}, sesión {ps.session_id}: día {ps.day_id}, "
                        f"bloques {ps.start_block_id}-{end}",
                    )
                )
            for block in range(ps.start_block_id, end + 1):
                if (ps.day_id, block) in weekly:
                    findings.append(
                        Finding(
                            "PATTERN_OVERLAP",
                            (section_id,),
                            f"patrón {pattern_id}: sesiones superpuestas en el día "
                            f"{ps.day_id}, bloque {block}",
                        )
                    )
                else:
                    weekly.append((ps.day_id, block))

        for week in sorted(weeks[section_id]):
            for day, block in weekly:
                slot = (week, day, block)
                checks = (
                    (
                        "TEACHER_UNAVAILABLE",
                        (section.teacher_id, *slot) not in teacher_ok,
                        "teacher",
                        section.teacher_id,
                    ),
                    ("ROOM_UNAVAILABLE", (room_id, *slot) not in room_ok, "room", room_id),
                    ("ROOM_RESERVED", (room_id, *slot) in reserved, "room", room_id),
                    ("PROTECTED_SLOT", (section_id, *slot) in blocked, None, None),
                )
                for rule, failed, kind, resource in checks:
                    if failed:
                        findings.append(
                            Finding(rule, (section_id,), rule.lower(), resource, slot, kind)
                        )
                usage[("room", room_id, slot)].add(section_id)
                usage[("teacher", section.teacher_id, slot)].add(section_id)
                for group_id in groups[section_id]:
                    usage[("group", group_id, slot)].add(section_id)

        # D: bloques semanales del patrón, una vez. E: decenas sobrantes redondeadas arriba.
        cost_d += sum(penalty.get((section.teacher_id, day, block), 0) for day, block in weekly)
        cost_e += max(0, (room.capacity - section.enrollment + 9) // 10)

    # 3. Choques: un recurso no puede servir a dos secciones en el mismo bloque.
    for (kind, resource, slot), users in sorted(usage.items()):
        if len(users) > 1:
            findings.append(
                Finding(
                    f"{kind.upper()}_CLASH", tuple(sorted(users)), "choque", resource, slot, kind
                )
            )

    # 4. Costo recalculado frente al informado.
    objective = config.alpha * cost_d + config.beta * cost_e
    if reported_objective is not None and reported_objective != objective:
        findings.append(
            Finding(
                "OBJECTIVE_MISMATCH",
                (),
                f"informado {reported_objective}, recalculado {objective}",
            )
        )

    return AuditReport(not findings, tuple(findings), cost_d, cost_e, objective, reported_objective)
