"""Generación reproducible de los casos sintéticos micro y demo.

Primero se construye un horario testigo y después se derivan datos compatibles con él. El testigo
se guarda solo como evidencia en el manifiesto; no es una tabla fuente ni una solución calculada.
"""

import csv
import hashlib
import io
import json
import random
import shutil
import tempfile
from dataclasses import asdict, dataclass
from itertools import product
from pathlib import Path

from academic_timetabling_demo.domain import (
    CONFIG_FILE,
    DEFAULT_CONFIG,
    TABLES,
    Block,
    DataValidationError,
    Day,
    Feature,
    Group,
    Instance,
    Pattern,
    PatternSession,
    Room,
    RoomAvailable,
    RoomFeature,
    RoomReservation,
    Row,
    Section,
    SectionBlocked,
    SectionFeature,
    SectionGroup,
    SectionPattern,
    SectionWeek,
    Teacher,
    TeacherAvailable,
    TeacherPenalty,
    Week,
    read_instance,
    validate_instance,
)

CASES = ("micro", "demo")
FORMAT_VERSION = 1
MANIFEST_FILE = "generation.json"

_DEMO_WEEKS = (1, 2, 3, 4)
_DEMO_DAYS = (1, 2, 3, 4, 5)
_DEMO_BLOCKS = (1, 2, 3, 4, 5, 6, 7)
_DAY_NAMES = {1: "Lunes", 2: "Martes", 3: "Miércoles", 4: "Jueves", 5: "Viernes"}
_DEMO_FEATURES = {"F01": "Proyector", "F02": "Laboratorio"}
_DEMO_ROOMS = (
    ("R01", 30, ("F01",)),
    ("R02", 40, ("F01",)),
    ("R03", 60, ("F01",)),
    ("R04", 30, ("F01", "F02")),
    ("R05", 80, ()),
    ("R06", 120, ("F01",)),
)
# Sesiones por semana, bloques por sesión y semanas activas de las 12 secciones.
_DEMO_SECTIONS = (
    (2, 1, _DEMO_WEEKS),
    (2, 1, _DEMO_WEEKS),
    (2, 1, _DEMO_WEEKS),
    (2, 1, _DEMO_WEEKS),
    (1, 2, _DEMO_WEEKS),
    (1, 2, _DEMO_WEEKS),
    (1, 2, _DEMO_WEEKS),
    (2, 2, _DEMO_WEEKS),
    (2, 2, _DEMO_WEEKS),
    (1, 2, (1, 2)),
    (1, 2, (3, 4)),
    (2, 1, (1, 2, 3)),
)
_DEMO_TEACHERS = 6
_DEMO_GROUPS = 4
_ALTERNATIVE_PATTERNS = 5


class GenerationError(RuntimeError):
    """El generador no pudo producir un caso válido."""


class OutputNotEmptyError(ValueError):
    """La salida indicada ya tiene contenido."""


@dataclass(frozen=True)
class WitnessAssignment:
    section_id: str
    pattern_id: str
    room_id: str


@dataclass(frozen=True)
class GeneratedCase:
    case: str
    seed: int
    instance: Instance
    witness: tuple[WitnessAssignment, ...]


def generate_case(case: str, seed: int) -> GeneratedCase:
    """Construye un caso. Micro es un diseño fijo; demo depende de la semilla."""
    if case == "micro":
        instance, witness = _micro()
    elif case == "demo":
        instance, witness = _demo(seed)
    else:
        raise ValueError(f"caso desconocido: {case}")
    issues = validate_instance(instance)
    if issues:
        raise GenerationError(str(DataValidationError(issues)))
    return GeneratedCase(case, seed, instance, witness)


def _instance(**tables: list[Row]) -> Instance:
    ordered = {}
    for spec in TABLES:
        rows = tables.get(spec.name, [])
        ordered[spec.name] = tuple(
            sorted(rows, key=lambda row: tuple(getattr(row, c) for c in spec.columns))
        )
    return Instance(config=DEFAULT_CONFIG, **ordered)


def _blocks(count: int) -> list[Block]:
    return [
        Block(id=index, start_time=f"{7 + index:02d}:00", end_time=f"{8 + index:02d}:00")
        for index in range(1, count + 1)
    ]


def _micro() -> tuple[Instance, tuple[WitnessAssignment, ...]]:
    """Tres secciones y dos salas; ver el dominio completo en `docs/entregas/hito-1.md`."""
    weeks, days, block_ids = (1, 2), (1, 2), (1, 2, 3)
    grid = list(product(weeks, days, block_ids))
    pattern_sessions = {
        "P1": ((1, 1, 1),),
        "P2": ((1, 2, 1),),
        "P3": ((1, 1, 2),),
        "P4": ((2, 2, 2),),
        "P5": ((1, 3, 1), (2, 1, 1)),
        "P6": ((1, 1, 1), (2, 1, 1)),
    }
    instance = _instance(
        weeks=[Week(id=week) for week in weeks],
        days=[Day(id=day) for day in days],
        blocks=_blocks(len(block_ids)),
        teachers=[Teacher(id="T1", name="Docente 1"), Teacher(id="T2", name="Docente 2")],
        rooms=[
            Room(id="R1", name="Sala 1", capacity=30),
            Room(id="R2", name="Sala 2", capacity=50),
        ],
        features=[Feature(id="F1", name="Proyector")],
        room_features=[RoomFeature(room_id="R1", feature_id="F1")],
        groups=[
            Group(id="G1", name="Grupo 1", basis="estudiantes_compartidos"),
            Group(id="G2", name="Grupo 2", basis="regla_curricular"),
        ],
        sections=[
            Section(
                id="S1",
                name="Sección 1",
                teacher_id="T1",
                enrollment=25,
                sessions_per_week=1,
                blocks_per_session=1,
            ),
            Section(
                id="S2",
                name="Sección 2",
                teacher_id="T2",
                enrollment=40,
                sessions_per_week=1,
                blocks_per_session=2,
            ),
            Section(
                id="S3",
                name="Sección 3",
                teacher_id="T1",
                enrollment=20,
                sessions_per_week=2,
                blocks_per_session=1,
            ),
        ],
        section_groups=[
            SectionGroup(section_id="S1", group_id="G1"),
            SectionGroup(section_id="S2", group_id="G2"),
            SectionGroup(section_id="S3", group_id="G1"),
        ],
        section_features=[SectionFeature(section_id="S1", feature_id="F1")],
        section_weeks=[
            SectionWeek(section_id="S1", week_id=1),
            SectionWeek(section_id="S1", week_id=2),
            SectionWeek(section_id="S2", week_id=1),
            SectionWeek(section_id="S2", week_id=2),
            SectionWeek(section_id="S3", week_id=1),
        ],
        patterns=[Pattern(id=pattern_id, name=pattern_id) for pattern_id in pattern_sessions],
        pattern_sessions=[
            PatternSession(
                pattern_id=pattern_id,
                session_id=str(index),
                day_id=day,
                start_block_id=start,
                duration_blocks=duration,
            )
            for pattern_id, sessions in pattern_sessions.items()
            for index, (day, start, duration) in enumerate(sessions, start=1)
        ],
        section_patterns=[
            SectionPattern(section_id=section_id, pattern_id=pattern_id)
            for section_id, pattern_ids in (
                ("S1", ("P1", "P2")),
                ("S2", ("P3", "P4")),
                ("S3", ("P5", "P6")),
            )
            for pattern_id in pattern_ids
        ],
        teacher_available=[
            TeacherAvailable(teacher_id=teacher, week_id=week, day_id=day, block_id=block)
            for teacher in ("T1", "T2")
            for week, day, block in grid
        ],
        room_available=[
            RoomAvailable(room_id=room, week_id=week, day_id=day, block_id=block)
            for room in ("R1", "R2")
            for week, day, block in grid
        ],
        room_reservations=[
            RoomReservation(
                room_id="R2", week_id=2, day_id=2, block_id=3, reason="Reserva externa sintética"
            )
        ],
        section_blocked=[
            SectionBlocked(
                section_id="S3",
                week_id=1,
                day_id=1,
                block_id=1,
                reason="Franja protegida sintética",
            )
        ],
        teacher_penalties=[
            TeacherPenalty(teacher_id="T1", day_id=1, block_id=1, penalty=2),
            TeacherPenalty(teacher_id="T2", day_id=2, block_id=2, penalty=1),
        ],
    )
    witness = (
        WitnessAssignment("S1", "P2", "R1"),
        WitnessAssignment("S2", "P3", "R2"),
        WitnessAssignment("S3", "P5", "R1"),
    )
    return instance, witness


@dataclass(frozen=True)
class _PatternShape:
    id: str
    name: str
    sessions: tuple[tuple[int, int, int], ...]

    def slots(self) -> list[tuple[int, int]]:
        return [
            (day, start + offset)
            for day, start, duration in self.sessions
            for offset in range(duration)
        ]


def _pattern_catalog() -> dict[tuple[int, int], list[_PatternShape]]:
    """Patrones disponibles por (sesiones por semana, bloques por sesión)."""
    day_pairs = ((1, 3), (2, 4), (3, 5))
    double_starts = (1, 3, 5)
    catalog: dict[tuple[int, int], list[_PatternShape]] = {(1, 2): [], (2, 1): [], (2, 2): []}
    for day, start in product(_DEMO_DAYS, double_starts):
        catalog[(1, 2)].append(
            _PatternShape(
                f"P1X2-D{day}-B{start}",
                f"{_DAY_NAMES[day]}, bloques {start} y {start + 1}",
                ((day, start, 2),),
            )
        )
    for (first, second), block in product(day_pairs, _DEMO_BLOCKS):
        catalog[(2, 1)].append(
            _PatternShape(
                f"P2X1-D{first}{second}-B{block}",
                f"{_DAY_NAMES[first]} y {_DAY_NAMES[second]}, bloque {block}",
                ((first, block, 1), (second, block, 1)),
            )
        )
    for (first, second), start in product(day_pairs, double_starts):
        catalog[(2, 2)].append(
            _PatternShape(
                f"P2X2-D{first}{second}-B{start}",
                f"{_DAY_NAMES[first]} y {_DAY_NAMES[second]}, bloques {start} y {start + 1}",
                ((first, start, 2), (second, start, 2)),
            )
        )
    return catalog


def _demo(seed: int) -> tuple[Instance, tuple[WitnessAssignment, ...]]:
    rng = random.Random(seed)
    capacities = {room: capacity + rng.choice((0, 5, 10)) for room, capacity, _ in _DEMO_ROOMS}
    room_features = {room: features for room, _, features in _DEMO_ROOMS}
    catalog = _pattern_catalog()
    teachers = [f"T{index:02d}" for index in range(1, _DEMO_TEACHERS + 1)]
    groups = [f"G{index:02d}" for index in range(1, _DEMO_GROUPS + 1)]

    busy: set[tuple[str, str, int, int, int]] = set()
    sections: list[Section] = []
    section_groups: list[SectionGroup] = []
    section_features: list[SectionFeature] = []
    section_weeks: list[SectionWeek] = []
    section_patterns: list[SectionPattern] = []
    witness: list[WitnessAssignment] = []
    used_patterns: dict[str, _PatternShape] = {}
    section_slots: dict[str, set[tuple[int, int]]] = {}
    teacher_slots: dict[str, set[tuple[int, int]]] = {teacher: set() for teacher in teachers}

    for index, (sessions, blocks, weeks) in enumerate(_DEMO_SECTIONS):
        section_id = f"S{index + 1:02d}"
        teacher = teachers[index % len(teachers)]
        members = [groups[index % len(groups)]]
        if index % 3 == 0:
            members.append(groups[(index + 1) % len(groups)])

        shapes = catalog[(sessions, blocks)]
        options = list(product(shapes, capacities))
        rng.shuffle(options)
        for shape, room in options:
            resources = [("room", room), ("teacher", teacher)]
            resources += [("group", group) for group in members]
            occupied = {
                (kind, resource, week, day, block)
                for kind, resource in resources
                for week in weeks
                for day, block in shape.slots()
            }
            if not occupied & busy:
                busy |= occupied
                break
        else:
            raise GenerationError(f"no se pudo ubicar la sección {section_id} en el testigo")

        witness.append(WitnessAssignment(section_id, shape.id, room))
        section_slots[section_id] = set(shape.slots())
        teacher_slots[teacher] |= set(shape.slots())
        capacity = capacities[room]
        sections.append(
            Section(
                id=section_id,
                name=f"Sección {index + 1:02d}",
                teacher_id=teacher,
                enrollment=rng.randint(capacity // 2, capacity),
                sessions_per_week=sessions,
                blocks_per_session=blocks,
            )
        )
        section_groups += [SectionGroup(section_id=section_id, group_id=g) for g in members]
        section_weeks += [SectionWeek(section_id=section_id, week_id=week) for week in weeks]
        if index % 2 == 0 and room_features[room]:
            feature = rng.choice(room_features[room])
            section_features.append(SectionFeature(section_id=section_id, feature_id=feature))

        others = [candidate for candidate in shapes if candidate.id != shape.id]
        authorized = [shape, *rng.sample(others, _ALTERNATIVE_PATTERNS)]
        section_patterns += [
            SectionPattern(section_id=section_id, pattern_id=candidate.id)
            for candidate in authorized
        ]
        used_patterns.update({candidate.id: candidate for candidate in authorized})

    all_slots = list(product(_DEMO_DAYS, _DEMO_BLOCKS))

    teacher_available = []
    teacher_penalties = []
    for teacher in teachers:
        free = [slot for slot in all_slots if slot not in teacher_slots[teacher]]
        unavailable = set(rng.sample(free, 3))
        teacher_available += [
            TeacherAvailable(teacher_id=teacher, week_id=week, day_id=day, block_id=block)
            for week, (day, block) in product(_DEMO_WEEKS, all_slots)
            if (day, block) not in unavailable
        ]
        teacher_penalties += [
            TeacherPenalty(
                teacher_id=teacher, day_id=day, block_id=block, penalty=rng.randint(1, 5)
            )
            for day, block in rng.sample(all_slots, 4)
        ]

    room_available = []
    free_room_slots = []
    for room in capacities:
        used = {
            (day, block) for kind, name, _, day, block in busy if (kind, name) == ("room", room)
        }
        unavailable = set(rng.sample([slot for slot in all_slots if slot not in used], 2))
        for week, (day, block) in product(_DEMO_WEEKS, all_slots):
            if (day, block) in unavailable:
                continue
            room_available.append(
                RoomAvailable(room_id=room, week_id=week, day_id=day, block_id=block)
            )
            if ("room", room, week, day, block) not in busy:
                free_room_slots.append((room, week, day, block))

    room_reservations = [
        RoomReservation(
            room_id=room,
            week_id=week,
            day_id=day,
            block_id=block,
            reason="Reserva externa sintética",
        )
        for room, week, day, block in rng.sample(free_room_slots, 4)
    ]

    protected_group = groups[0]
    protected_sections = [
        membership.section_id
        for membership in section_groups
        if membership.group_id == protected_group
    ]
    used_by_group = set().union(*(section_slots[section] for section in protected_sections))
    protected_free = [slot for slot in all_slots if slot not in used_by_group]
    if len(protected_free) < 2:
        raise GenerationError("no quedan franjas libres para proteger en el grupo")
    protected_slots = rng.sample(protected_free, 2)
    active_weeks = {
        section_id: weeks
        for (_, _, weeks), section_id in zip(
            _DEMO_SECTIONS, (section.id for section in sections), strict=True
        )
    }
    section_blocked = [
        SectionBlocked(
            section_id=section,
            week_id=week,
            day_id=day,
            block_id=block,
            reason="Franja protegida sintética",
        )
        for section in protected_sections
        for week in active_weeks[section]
        for day, block in protected_slots
    ]

    instance = _instance(
        weeks=[Week(id=week) for week in _DEMO_WEEKS],
        days=[Day(id=day) for day in _DEMO_DAYS],
        blocks=_blocks(len(_DEMO_BLOCKS)),
        teachers=[Teacher(id=t, name=f"Docente {t[1:]}") for t in teachers],
        rooms=[
            Room(id=room, name=f"Sala {room[1:]}", capacity=capacity)
            for room, capacity in capacities.items()
        ],
        features=[Feature(id=key, name=name) for key, name in _DEMO_FEATURES.items()],
        room_features=[
            RoomFeature(room_id=room, feature_id=feature)
            for room, features in room_features.items()
            for feature in features
        ],
        groups=[
            Group(
                id=group,
                name=f"Grupo {group[1:]}",
                basis="estudiantes_compartidos" if index % 2 == 0 else "regla_curricular",
            )
            for index, group in enumerate(groups)
        ],
        sections=sections,
        section_groups=section_groups,
        section_features=section_features,
        section_weeks=section_weeks,
        patterns=[Pattern(id=p.id, name=p.name) for p in used_patterns.values()],
        pattern_sessions=[
            PatternSession(
                pattern_id=pattern.id,
                session_id=str(index),
                day_id=day,
                start_block_id=start,
                duration_blocks=duration,
            )
            for pattern in used_patterns.values()
            for index, (day, start, duration) in enumerate(pattern.sessions, start=1)
        ],
        section_patterns=section_patterns,
        teacher_available=teacher_available,
        room_available=room_available,
        room_reservations=room_reservations,
        section_blocked=section_blocked,
        teacher_penalties=teacher_penalties,
    )
    return instance, tuple(witness)


def _csv_bytes(columns: tuple[str, ...], rows: tuple[Row, ...]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows([getattr(row, column) for column in columns] for row in rows)
    return buffer.getvalue().encode("utf-8")


def _json_bytes(data: object) -> bytes:
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
    return f"{text}\n".encode()


def source_hash(content: bytes) -> str:
    """SHA-256 con finales de línea LF, para no depender de la conversión de Git en Windows."""
    return hashlib.sha256(content.replace(b"\r\n", b"\n")).hexdigest()


def source_files(generated: GeneratedCase) -> dict[str, bytes]:
    """Contenido exacto de cada archivo fuente."""
    instance = generated.instance
    files = {spec.file: _csv_bytes(spec.columns, getattr(instance, spec.name)) for spec in TABLES}
    files[CONFIG_FILE] = _json_bytes(instance.config.model_dump())
    return files


def manifest(generated: GeneratedCase, files: dict[str, bytes]) -> dict[str, object]:
    return {
        "case": generated.case,
        "seed": generated.seed,
        "format_version": FORMAT_VERSION,
        "hash": {"algorithm": "sha256", "line_endings": "LF"},
        "sources": {name: source_hash(content) for name, content in sorted(files.items())},
        "witness": [asdict(assignment) for assignment in generated.witness],
    }


def generate_to_directory(case: str, seed: int, out: Path) -> GeneratedCase:
    """Genera y valida un caso en una carpeta nueva o vacía, sin dejar salidas parciales."""
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise OutputNotEmptyError(f"la salida ya existe y no está vacía: {out}")

    generated = generate_case(case, seed)
    files = source_files(generated)
    out.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".generate-", dir=out.parent))
    try:
        for name, content in files.items():
            (staging / name).write_bytes(content)
        (staging / MANIFEST_FILE).write_bytes(_json_bytes(manifest(generated, files)))
        try:
            read_instance(staging)
        except DataValidationError as error:
            raise GenerationError(f"el caso escrito no es válido:\n{error}") from error
        if out.exists():
            out.rmdir()
        staging.rename(out)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return generated
