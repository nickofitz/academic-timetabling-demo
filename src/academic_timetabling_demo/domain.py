"""Modelos de las tablas fuente, lectura de CSV y validación estructural.

Las filas se numeran por registro CSV: el encabezado es la fila 1.
"""

import csv
import json
import math
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictInt,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

MAX_SQLITE_INTEGER = 2**63 - 1
CONFIG_FILE = "config.json"


@dataclass(frozen=True)
class Issue:
    """Un problema de datos, ubicado en su archivo y, si procede, fila y campo."""

    file: str
    message: str
    row: int | None = None
    field: str | None = None

    def __str__(self) -> str:
        place = self.file
        if self.row is not None:
            place += f", fila {self.row}"
        if self.field is not None:
            place += f", campo {self.field}"
        return f"{place}: {self.message}"


class DataValidationError(ValueError):
    """Los datos de entrada no cumplen el contrato."""

    def __init__(self, issues: Iterable[Issue]) -> None:
        self.issues = tuple(issues)
        super().__init__("\n".join(str(issue) for issue in self.issues))


def _parse_int(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and re.fullmatch(r"-?[0-9]+", value):
        return int(value)
    raise ValueError("se esperaba un número entero")


CsvInt = Annotated[int, BeforeValidator(_parse_int), Field(le=MAX_SQLITE_INTEGER)]
PositiveInt = Annotated[CsvInt, Field(gt=0)]
NonNegativeInt = Annotated[CsvInt, Field(ge=0)]
DayId = Annotated[CsvInt, Field(ge=1, le=7)]
Identifier = Annotated[str, StringConstraints(pattern=r"^\S(.*\S)?$")]
Text = Annotated[str, StringConstraints(pattern=r"\S")]
ClockTime = Annotated[str, StringConstraints(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")]


class Row(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Week(Row):
    id: PositiveInt


class Day(Row):
    id: DayId


class Block(Row):
    id: PositiveInt
    start_time: ClockTime
    end_time: ClockTime

    @model_validator(mode="after")
    def _start_before_end(self) -> "Block":
        if self.start_time >= self.end_time:
            raise ValueError("start_time debe ser anterior a end_time")
        return self


class Teacher(Row):
    id: Identifier
    name: Text


class Room(Row):
    id: Identifier
    name: Text
    capacity: PositiveInt


class Feature(Row):
    id: Identifier
    name: Text


class RoomFeature(Row):
    room_id: Identifier
    feature_id: Identifier


class Group(Row):
    id: Identifier
    name: Text
    basis: Literal["estudiantes_compartidos", "regla_curricular"]


class Section(Row):
    id: Identifier
    name: Text
    teacher_id: Identifier
    enrollment: PositiveInt
    sessions_per_week: PositiveInt
    blocks_per_session: PositiveInt


class SectionGroup(Row):
    section_id: Identifier
    group_id: Identifier


class SectionFeature(Row):
    section_id: Identifier
    feature_id: Identifier


class SectionWeek(Row):
    section_id: Identifier
    week_id: PositiveInt


class Pattern(Row):
    id: Identifier
    name: Text


class PatternSession(Row):
    pattern_id: Identifier
    session_id: Identifier
    day_id: DayId
    start_block_id: PositiveInt
    duration_blocks: PositiveInt


class SectionPattern(Row):
    section_id: Identifier
    pattern_id: Identifier


class TeacherAvailable(Row):
    teacher_id: Identifier
    week_id: PositiveInt
    day_id: DayId
    block_id: PositiveInt


class RoomAvailable(Row):
    room_id: Identifier
    week_id: PositiveInt
    day_id: DayId
    block_id: PositiveInt


class RoomReservation(Row):
    room_id: Identifier
    week_id: PositiveInt
    day_id: DayId
    block_id: PositiveInt
    reason: Text


class SectionBlocked(Row):
    section_id: Identifier
    week_id: PositiveInt
    day_id: DayId
    block_id: PositiveInt
    reason: Text


class TeacherPenalty(Row):
    teacher_id: Identifier
    day_id: DayId
    block_id: PositiveInt
    penalty: NonNegativeInt


class RunConfig(Row):
    alpha: StrictInt = Field(ge=0)
    beta: StrictInt = Field(ge=0)
    time_limit_seconds: StrictInt | float
    random_seed: StrictInt = Field(ge=0)
    num_search_workers: StrictInt = Field(gt=0)

    @field_validator("time_limit_seconds", mode="before")
    @classmethod
    def _time_limit_is_a_number(cls, value: Any) -> Any:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError("se esperaba un número")
        if not math.isfinite(value) or value <= 0:
            raise ValueError("debe ser un número positivo")
        return value


DEFAULT_CONFIG = RunConfig(
    alpha=10, beta=1, time_limit_seconds=30, random_seed=42, num_search_workers=1
)


class Instance(Row):
    """Las 20 tablas fuente y la configuración de una entrada."""

    weeks: tuple[Week, ...]
    days: tuple[Day, ...]
    blocks: tuple[Block, ...]
    teachers: tuple[Teacher, ...]
    rooms: tuple[Room, ...]
    features: tuple[Feature, ...]
    room_features: tuple[RoomFeature, ...]
    groups: tuple[Group, ...]
    sections: tuple[Section, ...]
    section_groups: tuple[SectionGroup, ...]
    section_features: tuple[SectionFeature, ...]
    section_weeks: tuple[SectionWeek, ...]
    patterns: tuple[Pattern, ...]
    pattern_sessions: tuple[PatternSession, ...]
    section_patterns: tuple[SectionPattern, ...]
    teacher_available: tuple[TeacherAvailable, ...]
    room_available: tuple[RoomAvailable, ...]
    room_reservations: tuple[RoomReservation, ...]
    section_blocked: tuple[SectionBlocked, ...]
    teacher_penalties: tuple[TeacherPenalty, ...]
    config: RunConfig


@dataclass(frozen=True)
class ForeignKey:
    columns: tuple[str, ...]
    table: str
    target: tuple[str, ...] = ("id",)


def _time_references(*, week: bool = True) -> tuple[ForeignKey, ...]:
    references = (
        ForeignKey(("day_id",), "days"),
        ForeignKey(("block_id",), "blocks"),
    )
    return (ForeignKey(("week_id",), "weeks"), *references) if week else references


@dataclass(frozen=True)
class TableSpec:
    name: str
    model: type[Row]
    primary_key: tuple[str, ...] = ("id",)
    foreign_keys: tuple[ForeignKey, ...] = ()

    @property
    def columns(self) -> tuple[str, ...]:
        return tuple(self.model.model_fields)

    @property
    def file(self) -> str:
        return f"{self.name}.csv"


_SECTION = ForeignKey(("section_id",), "sections")
_TEACHER = ForeignKey(("teacher_id",), "teachers")
_ROOM = ForeignKey(("room_id",), "rooms")
_FEATURE = ForeignKey(("feature_id",), "features")
_PATTERN = ForeignKey(("pattern_id",), "patterns")

# En orden referencial: cada tabla aparece después de las que referencia.
TABLES: tuple[TableSpec, ...] = (
    TableSpec("weeks", Week),
    TableSpec("days", Day),
    TableSpec("blocks", Block),
    TableSpec("teachers", Teacher),
    TableSpec("rooms", Room),
    TableSpec("features", Feature),
    TableSpec("room_features", RoomFeature, ("room_id", "feature_id"), (_ROOM, _FEATURE)),
    TableSpec("groups", Group),
    TableSpec("sections", Section, foreign_keys=(_TEACHER,)),
    TableSpec(
        "section_groups",
        SectionGroup,
        ("section_id", "group_id"),
        (_SECTION, ForeignKey(("group_id",), "groups")),
    ),
    TableSpec(
        "section_features", SectionFeature, ("section_id", "feature_id"), (_SECTION, _FEATURE)
    ),
    TableSpec(
        "section_weeks",
        SectionWeek,
        ("section_id", "week_id"),
        (_SECTION, ForeignKey(("week_id",), "weeks")),
    ),
    TableSpec("patterns", Pattern),
    TableSpec(
        "pattern_sessions",
        PatternSession,
        ("pattern_id", "session_id"),
        (
            _PATTERN,
            ForeignKey(("day_id",), "days"),
            ForeignKey(("start_block_id",), "blocks"),
        ),
    ),
    TableSpec(
        "section_patterns", SectionPattern, ("section_id", "pattern_id"), (_SECTION, _PATTERN)
    ),
    TableSpec(
        "teacher_available",
        TeacherAvailable,
        ("teacher_id", "week_id", "day_id", "block_id"),
        (_TEACHER, *_time_references()),
    ),
    TableSpec(
        "room_available",
        RoomAvailable,
        ("room_id", "week_id", "day_id", "block_id"),
        (_ROOM, *_time_references()),
    ),
    TableSpec(
        "room_reservations",
        RoomReservation,
        ("room_id", "week_id", "day_id", "block_id"),
        (_ROOM, *_time_references()),
    ),
    TableSpec(
        "section_blocked",
        SectionBlocked,
        ("section_id", "week_id", "day_id", "block_id"),
        (
            _SECTION,
            *_time_references(),
            ForeignKey(("section_id", "week_id"), "section_weeks", ("section_id", "week_id")),
        ),
    ),
    TableSpec(
        "teacher_penalties",
        TeacherPenalty,
        ("teacher_id", "day_id", "block_id"),
        (_TEACHER, *_time_references(week=False)),
    ),
)
_SPECS = {spec.name: spec for spec in TABLES}


def read_instance(directory: Path) -> Instance:
    """Lee y valida una entrada. Lanza DataValidationError con todos los problemas hallados."""
    if not directory.is_dir():
        raise DataValidationError([Issue(str(directory), "la carpeta de entrada no existe")])

    issues: list[Issue] = []
    tables = {spec.name: _read_table(directory, spec, issues) for spec in TABLES}
    config = read_config(directory / CONFIG_FILE, issues)
    if issues or config is None:
        raise DataValidationError(issues)

    instance = Instance(config=config, **tables)
    issues = validate_instance(instance)
    if issues:
        raise DataValidationError(issues)
    return instance


def _read_table(directory: Path, spec: TableSpec, issues: list[Issue]) -> tuple[Row, ...]:
    rows: list[Row] = []
    try:
        with (directory / spec.file).open(encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle, strict=True)
            header = next(reader, None)
            if tuple(header or ()) != spec.columns:
                expected = ",".join(spec.columns)
                issues.append(Issue(spec.file, f"encabezado incorrecto; se esperaba {expected}", 1))
                return ()
            for row_number, values in enumerate(reader, start=2):
                row = _parse_row(spec, row_number, values, issues)
                if row is not None:
                    rows.append(row)
    except FileNotFoundError:
        issues.append(Issue(spec.file, "falta el archivo fuente"))
    except UnicodeDecodeError:
        issues.append(Issue(spec.file, "el archivo no está codificado en UTF-8"))
    except csv.Error as error:
        issues.append(Issue(spec.file, f"CSV mal formado: {error}"))
    return tuple(rows)


def _parse_row(
    spec: TableSpec, row_number: int, values: list[str], issues: list[Issue]
) -> Row | None:
    if len(values) != len(spec.columns):
        message = f"se esperaban {len(spec.columns)} columnas y hay {len(values)}"
        issues.append(Issue(spec.file, message, row_number))
        return None
    try:
        return spec.model(**dict(zip(spec.columns, values, strict=True)))
    except ValidationError as error:
        issues.extend(_pydantic_issues(error, spec.file, row_number))
        return None


def _pydantic_issues(error: ValidationError, file: str, row: int | None) -> list[Issue]:
    return [
        Issue(
            file,
            detail["msg"].removeprefix("Value error, "),
            row,
            str(detail["loc"][0]) if detail["loc"] else None,
        )
        for detail in error.errors()
    ]


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    keys = [key for key, _ in pairs]
    repeated = sorted({key for key in keys if keys.count(key) > 1})
    if repeated:
        raise ValueError(f"claves repetidas: {', '.join(repeated)}")
    return dict(pairs)


def _reject_constant(name: str) -> None:
    raise ValueError(f"valor no permitido: {name}")


def read_config(path: Path, issues: list[Issue]) -> RunConfig | None:
    try:
        data = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
        return RunConfig.model_validate(data)
    except FileNotFoundError:
        issues.append(Issue(CONFIG_FILE, "falta el archivo de configuración"))
    except ValidationError as error:
        issues.extend(_pydantic_issues(error, CONFIG_FILE, None))
    except ValueError as error:
        issues.append(Issue(CONFIG_FILE, f"JSON inválido: {error}"))
    return None


def validate_instance(instance: Instance) -> list[Issue]:
    """Comprueba las reglas que involucran varias filas o tablas."""
    return [
        *_check_keys(instance),
        *_check_references(instance),
        *_check_horizon(instance),
        *_check_blocks(instance),
        *_check_section_memberships(instance),
        *_check_pattern_shape(instance),
        *_check_authorized_patterns(instance),
    ]


def _rows(instance: Instance, spec: TableSpec) -> Iterable[tuple[int, Row]]:
    return enumerate(getattr(instance, spec.name), start=2)


def _key(row: Row, columns: tuple[str, ...]) -> tuple[Any, ...]:
    return tuple(getattr(row, column) for column in columns)


def _check_keys(instance: Instance) -> list[Issue]:
    issues = []
    for spec in TABLES:
        seen: dict[tuple[Any, ...], int] = {}
        for row_number, row in _rows(instance, spec):
            key = _key(row, spec.primary_key)
            if key in seen:
                message = f"clave duplicada {key}; ya aparece en la fila {seen[key]}"
                issues.append(Issue(spec.file, message, row_number))
            seen.setdefault(key, row_number)
    return issues


def _check_references(instance: Instance) -> list[Issue]:
    issues = []
    for spec in TABLES:
        for foreign_key in spec.foreign_keys:
            target = _SPECS[foreign_key.table]
            known = {_key(row, foreign_key.target) for _, row in _rows(instance, target)}
            for row_number, row in _rows(instance, spec):
                value = _key(row, foreign_key.columns)
                if value in known:
                    continue
                if spec.name == "section_blocked" and foreign_key.table == "section_weeks":
                    message = f"bloqueo fuera de las semanas activas de la sección: {value}"
                else:
                    message = f"referencia rota: {value} no existe en {foreign_key.table}"
                issues.append(Issue(spec.file, message, row_number, ",".join(foreign_key.columns)))
    return issues


def _consecutive(ids: Iterable[int]) -> bool:
    distinct = sorted(set(ids))
    return distinct == list(range(1, len(distinct) + 1))


def _check_horizon(instance: Instance) -> list[Issue]:
    issues = [
        Issue(f"{name}.csv", "el horizonte necesita al menos un registro")
        for name in ("weeks", "days", "blocks")
        if not getattr(instance, name)
    ]
    if not _consecutive(week.id for week in instance.weeks):
        issues.append(Issue("weeks.csv", "las semanas deben ser consecutivas desde 1"))
    if not _consecutive(block.id for block in instance.blocks):
        issues.append(Issue("blocks.csv", "los bloques deben ser consecutivos desde 1"))
    return issues


def _minutes(clock_time: str) -> int:
    hours, minutes = clock_time.split(":")
    return int(hours) * 60 + int(minutes)


def _check_blocks(instance: Instance) -> list[Issue]:
    issues = []
    ordered = sorted(enumerate(instance.blocks, start=2), key=lambda item: item[1].id)
    if not ordered:
        return issues
    expected = _minutes(ordered[0][1].end_time) - _minutes(ordered[0][1].start_time)
    previous_end = None
    for row_number, block in ordered:
        if _minutes(block.end_time) - _minutes(block.start_time) != expected:
            message = f"el bloque {block.id} no dura {expected} minutos como el primero"
            issues.append(Issue("blocks.csv", message, row_number))
        if previous_end is not None and block.start_time < previous_end:
            message = f"el bloque {block.id} se superpone o está fuera de orden"
            issues.append(Issue("blocks.csv", message, row_number))
        previous_end = block.end_time
    return issues


def _check_section_memberships(instance: Instance) -> list[Issue]:
    requirements = (
        ("grupo", instance.section_groups),
        ("semana activa", instance.section_weeks),
        ("patrón autorizado", instance.section_patterns),
    )
    issues = []
    for label, memberships in requirements:
        present = {membership.section_id for membership in memberships}
        for row_number, section in enumerate(instance.sections, start=2):
            if section.id not in present:
                message = f"la sección {section.id} necesita al menos un(a) {label}"
                issues.append(Issue("sections.csv", message, row_number))
    return issues


def _sessions_by_pattern(instance: Instance) -> dict[str, list[tuple[int, PatternSession]]]:
    sessions: dict[str, list[tuple[int, PatternSession]]] = defaultdict(list)
    for row_number, session in enumerate(instance.pattern_sessions, start=2):
        sessions[session.pattern_id].append((row_number, session))
    return sessions


def _check_pattern_shape(instance: Instance) -> list[Issue]:
    issues = []
    last_block = max((block.id for block in instance.blocks), default=0)
    for pattern_id, sessions in _sessions_by_pattern(instance).items():
        occupied: dict[tuple[int, int], str] = {}
        for row_number, session in sessions:
            final_block = session.start_block_id + session.duration_blocks - 1
            if final_block > last_block:
                message = f"la sesión {session.session_id} del patrón {pattern_id} sale del día"
                issues.append(Issue("pattern_sessions.csv", message, row_number))
            for block_id in range(session.start_block_id, final_block + 1):
                slot = (session.day_id, block_id)
                if slot in occupied:
                    message = (
                        f"las sesiones {occupied[slot]} y {session.session_id} "
                        f"del patrón {pattern_id} se solapan"
                    )
                    issues.append(Issue("pattern_sessions.csv", message, row_number))
                    break
                occupied[slot] = session.session_id
    return issues


def _check_authorized_patterns(instance: Instance) -> list[Issue]:
    issues = []
    sections = {section.id: section for section in instance.sections}
    sessions = _sessions_by_pattern(instance)
    for row_number, authorization in enumerate(instance.section_patterns, start=2):
        section = sections.get(authorization.section_id)
        if section is None:
            continue
        pattern_sessions = [session for _, session in sessions[authorization.pattern_id]]
        if len(pattern_sessions) != section.sessions_per_week:
            message = (
                f"el patrón {authorization.pattern_id} tiene {len(pattern_sessions)} sesiones "
                f"y la sección {section.id} requiere {section.sessions_per_week}"
            )
            issues.append(Issue("section_patterns.csv", message, row_number))
        if any(s.duration_blocks != section.blocks_per_session for s in pattern_sessions):
            message = (
                f"el patrón {authorization.pattern_id} no tiene sesiones de "
                f"{section.blocks_per_session} bloques como exige la sección {section.id}"
            )
            issues.append(Issue("section_patterns.csv", message, row_number))
    return issues
