"""Alternativas admisibles, descartes y ocupaciones calculados en SQL (Hito 2).

Una alternativa es un triple (sección, patrón, sala). Se descarta completa si falla
alguna regla de la especificación, sección 4, y se registra cada motivo con su evidencia.
La preparación reemplaza las tablas derivadas en una sola transacción y no toca las fuentes.
"""

import sqlite3
from dataclasses import asdict, dataclass

RULES = (
    "CAPACITY",
    "FEATURES",
    "TEACHER_UNAVAILABLE",
    "ROOM_UNAVAILABLE",
    "ROOM_RESERVED",
    "PROTECTED_SLOT",
)
# Motivos de una sección sin alternativas que no provienen de descartar pares.
NO_PATTERNS = "NO_PATTERNS"
NO_ROOMS = "NO_ROOMS"
# En orden de borrado: occupancy referencia alternative.
DERIVED_TABLES = ("occupancy", "discarded_alternative", "alternative")

# Vistas temporales: expanden cada sesión a sus bloques y cada sección a sus semanas activas.
_VIEWS = """
CREATE TEMP VIEW IF NOT EXISTS pattern_slot AS
SELECT ps.pattern_id, ps.day_id, b.id AS block_id
FROM pattern_sessions AS ps
JOIN blocks AS b
  ON b.id BETWEEN ps.start_block_id AND ps.start_block_id + ps.duration_blocks - 1;

CREATE TEMP VIEW IF NOT EXISTS section_slot AS
SELECT sp.section_id, sp.pattern_id, sw.week_id, slot.day_id, slot.block_id
FROM section_patterns AS sp
JOIN section_weeks AS sw ON sw.section_id = sp.section_id
JOIN pattern_slot AS slot ON slot.pattern_id = sp.pattern_id;

CREATE TEMP VIEW IF NOT EXISTS pair AS
SELECT sp.section_id, sp.pattern_id, r.id AS room_id
FROM section_patterns AS sp
CROSS JOIN rooms AS r;
"""

# Cada consulta devuelve (section_id, pattern_id, room_id, rule, evidence_json).
_SLOTS = (
    "json_group_array(json_array(week_id, day_id, block_id) ORDER BY week_id, day_id, block_id)"
)


def _slot_rule(rule: str, condition: str, extra: str = "") -> str:
    """Pares con al menos un bloque semanal que cumple `condition`; evidencia con esos bloques."""
    return f"""
        SELECT section_id, pattern_id, room_id, '{rule}',
               json_object({extra}'slots', {_SLOTS})
        FROM (
            SELECT p.section_id, p.pattern_id, p.room_id, s.teacher_id,
                   ss.week_id, ss.day_id, ss.block_id
            FROM pair AS p
            JOIN sections AS s ON s.id = p.section_id
            JOIN section_slot AS ss
              ON ss.section_id = p.section_id AND ss.pattern_id = p.pattern_id
            WHERE {condition}
        )
        GROUP BY section_id, pattern_id, room_id
    """


_DISCARDS = {
    "CAPACITY": """
        SELECT p.section_id, p.pattern_id, p.room_id, 'CAPACITY',
               json_object('capacity', r.capacity, 'enrollment', s.enrollment)
        FROM pair AS p
        JOIN rooms AS r ON r.id = p.room_id
        JOIN sections AS s ON s.id = p.section_id
        WHERE r.capacity < s.enrollment
    """,
    "FEATURES": """
        SELECT p.section_id, p.pattern_id, p.room_id, 'FEATURES',
               json_object('missing', json_group_array(sf.feature_id ORDER BY sf.feature_id))
        FROM pair AS p
        JOIN section_features AS sf ON sf.section_id = p.section_id
        WHERE NOT EXISTS (
            SELECT 1 FROM room_features AS rf
            WHERE rf.room_id = p.room_id AND rf.feature_id = sf.feature_id
        )
        GROUP BY p.section_id, p.pattern_id, p.room_id
    """,
    "TEACHER_UNAVAILABLE": _slot_rule(
        "TEACHER_UNAVAILABLE",
        """NOT EXISTS (
            SELECT 1 FROM teacher_available AS ta
            WHERE ta.teacher_id = s.teacher_id AND ta.week_id = ss.week_id
              AND ta.day_id = ss.day_id AND ta.block_id = ss.block_id
        )""",
        extra="'teacher_id', teacher_id, ",
    ),
    "ROOM_UNAVAILABLE": _slot_rule(
        "ROOM_UNAVAILABLE",
        """NOT EXISTS (
            SELECT 1 FROM room_available AS ra
            WHERE ra.room_id = p.room_id AND ra.week_id = ss.week_id
              AND ra.day_id = ss.day_id AND ra.block_id = ss.block_id
        )""",
    ),
    "ROOM_RESERVED": _slot_rule(
        "ROOM_RESERVED",
        """EXISTS (
            SELECT 1 FROM room_reservations AS rr
            WHERE rr.room_id = p.room_id AND rr.week_id = ss.week_id
              AND rr.day_id = ss.day_id AND rr.block_id = ss.block_id
        )""",
    ),
    "PROTECTED_SLOT": _slot_rule(
        "PROTECTED_SLOT",
        """EXISTS (
            SELECT 1 FROM section_blocked AS sb
            WHERE sb.section_id = p.section_id AND sb.week_id = ss.week_id
              AND sb.day_id = ss.day_id AND sb.block_id = ss.block_id
        )""",
    ),
}

# D: penalizaciones del docente en los bloques semanales del patrón, una sola vez.
# E: decenas de asientos sobrantes, redondeadas hacia arriba; solo con capacidad suficiente.
_ALTERNATIVES = """
    INSERT INTO alternative (section_id, pattern_id, room_id, cost_d, cost_e)
    SELECT p.section_id, p.pattern_id, p.room_id,
           (SELECT coalesce(sum(tp.penalty), 0)
            FROM pattern_slot AS slot
            JOIN teacher_penalties AS tp
              ON tp.teacher_id = s.teacher_id AND tp.day_id = slot.day_id
             AND tp.block_id = slot.block_id
            WHERE slot.pattern_id = p.pattern_id),
           (r.capacity - s.enrollment + 9) / 10
    FROM pair AS p
    JOIN sections AS s ON s.id = p.section_id
    JOIN rooms AS r ON r.id = p.room_id
    WHERE NOT EXISTS (
        SELECT 1 FROM discarded_alternative AS d
        WHERE d.section_id = p.section_id AND d.pattern_id = p.pattern_id
          AND d.room_id = p.room_id
    )
    ORDER BY p.section_id, p.pattern_id, p.room_id
"""

# UNION elimina filas repetidas; los grupos son los declarados en section_groups.
_OCCUPANCY = """
    INSERT INTO occupancy (alt_id, resource_type, resource_id, week_id, day_id, block_id)
    SELECT a.alt_id, 'room', a.room_id, ss.week_id, ss.day_id, ss.block_id
    FROM alternative AS a
    JOIN section_slot AS ss ON ss.section_id = a.section_id AND ss.pattern_id = a.pattern_id
    UNION
    SELECT a.alt_id, 'teacher', s.teacher_id, ss.week_id, ss.day_id, ss.block_id
    FROM alternative AS a
    JOIN sections AS s ON s.id = a.section_id
    JOIN section_slot AS ss ON ss.section_id = a.section_id AND ss.pattern_id = a.pattern_id
    UNION
    SELECT a.alt_id, 'group', sg.group_id, ss.week_id, ss.day_id, ss.block_id
    FROM alternative AS a
    JOIN section_groups AS sg ON sg.section_id = a.section_id
    JOIN section_slot AS ss ON ss.section_id = a.section_id AND ss.pattern_id = a.pattern_id
"""

_SECTION_COUNTS = """
    SELECT s.id,
           (SELECT count(*) FROM section_patterns AS sp WHERE sp.section_id = s.id),
           (SELECT count(*) FROM pair AS p WHERE p.section_id = s.id),
           (SELECT count(*) FROM alternative AS a WHERE a.section_id = s.id),
           (SELECT count(*) FROM (
                SELECT DISTINCT pattern_id, room_id FROM discarded_alternative AS d
                WHERE d.section_id = s.id
           ))
    FROM sections AS s
    ORDER BY s.id
"""


class CandidatesError(RuntimeError):
    """La preparación no puede ejecutarse o dejó datos inconsistentes."""


@dataclass(frozen=True)
class SectionDiagnostic:
    """Conteos de una sección. `reasons` se llena solo si no le queda ninguna alternativa."""

    section_id: str
    authorized_patterns: int
    pairs_before: int
    alternatives_after: int
    discarded_pairs: int
    discards_by_rule: dict[str, int]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class Precheck:
    """Diagnóstico previo al solver. READY no prueba factibilidad global.

    Los conteos de pares y alternativas son triples distintos; `discards_by_rule` cuenta
    motivos, y un mismo triple puede tener varios.
    """

    status: str  # READY | NO_CANDIDATES
    pairs_before: int
    alternatives_after: int
    discarded_pairs: int
    discards_by_rule: dict[str, int]
    empty_sections: dict[str, tuple[str, ...]]  # sección sin alternativas -> motivos
    occupancy_rows: int
    sections: tuple[SectionDiagnostic, ...]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def build_candidates(connection: sqlite3.Connection) -> Precheck:
    """Reemplaza alternative, discarded_alternative y occupancy en una sola transacción.

    Requiere una conexión de `db.connect` sobre una base ya cargada. Si algo falla, las
    tablas derivadas conservan su contenido anterior.
    """
    if connection.in_transaction:
        raise CandidatesError("la conexión tiene una transacción abierta")

    connection.executescript(_VIEWS)
    connection.execute("BEGIN IMMEDIATE")
    try:
        for table in DERIVED_TABLES:
            connection.execute(f'DELETE FROM "{table}"')
        for query in _DISCARDS.values():
            connection.execute(
                "INSERT INTO discarded_alternative "
                "(section_id, pattern_id, room_id, rule, evidence_json) " + query
            )
        connection.execute(_ALTERNATIVES)
        connection.execute(_OCCUPANCY)
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise CandidatesError(f"claves foráneas incumplidas: {violations[:5]}")
        precheck = _diagnose(connection)
        connection.execute("COMMIT")
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    return precheck


def _diagnose(connection: sqlite3.Connection) -> Precheck:
    def scalar(sql: str) -> int:
        return connection.execute(sql).fetchone()[0]

    by_section_rule: dict[str, dict[str, int]] = {}
    for section_id, rule, count in connection.execute(
        "SELECT section_id, rule, count(*) FROM discarded_alternative GROUP BY section_id, rule"
    ):
        by_section_rule.setdefault(section_id, dict.fromkeys(RULES, 0))[rule] = count

    sections = []
    for section_id, patterns, pairs, alternatives, discarded in connection.execute(
        _SECTION_COUNTS
    ).fetchall():
        rules = by_section_rule.get(section_id, dict.fromkeys(RULES, 0))
        reasons: tuple[str, ...] = ()
        if alternatives == 0:
            if patterns == 0:
                reasons = (NO_PATTERNS,)
            elif pairs == 0:
                reasons = (NO_ROOMS,)
            else:
                reasons = tuple(rule for rule in sorted(rules) if rules[rule])
        sections.append(
            SectionDiagnostic(section_id, patterns, pairs, alternatives, discarded, rules, reasons)
        )

    discards = dict.fromkeys(RULES, 0)
    for rule, count in connection.execute(
        "SELECT rule, count(*) FROM discarded_alternative GROUP BY rule"
    ):
        discards[rule] = count

    empty = {s.section_id: s.reasons for s in sections if s.alternatives_after == 0}
    return Precheck(
        status="NO_CANDIDATES" if empty else "READY",
        pairs_before=scalar("SELECT count(*) FROM pair"),
        alternatives_after=scalar("SELECT count(*) FROM alternative"),
        discarded_pairs=scalar(
            "SELECT count(*) FROM (SELECT DISTINCT section_id, pattern_id, room_id "
            "FROM discarded_alternative)"
        ),
        discards_by_rule=discards,
        empty_sections=empty,
        occupancy_rows=scalar("SELECT count(*) FROM occupancy"),
        sections=tuple(sections),
    )
