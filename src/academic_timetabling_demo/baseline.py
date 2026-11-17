"""Heurística voraz determinista (Hito 4).

Usa las mismas tablas `alternative` y `occupancy` que CP-SAT y los mismos pesos efectivos:

1. Ordena una vez las secciones por cantidad inicial de alternativas y luego `section_id`.
2. Para cada sección ordena sus alternativas por (alpha*D + beta*E, pattern_id, room_id).
3. Elige la primera cuya ocupación no toca recursos ya ocupados (sala, docente y grupos, por
   semana, día y bloque) y agrega esa ocupación.
4. Sin retroceso: si ninguna alternativa es compatible, se detiene en esa sección y conserva
   el prefijo elegido. Atascarse no demuestra infactibilidad.

No importa OR-Tools ni el modelo, no usa el testigo del generador y no escribe en la base.
"""

import sqlite3
import time
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass, replace

from academic_timetabling_demo.domain import RunConfig

COMPLETE = "COMPLETE"
INCOMPLETE = "INCOMPLETE"

Occupation = tuple[str, str, int, int, int]  # (tipo, recurso, semana, día, bloque)


@dataclass(frozen=True)
class Candidate:
    alt_id: int
    section_id: str
    pattern_id: str
    room_id: str
    cost_d: int
    cost_e: int
    occupancy: frozenset[Occupation]


@dataclass(frozen=True)
class Choice:
    section_id: str
    pattern_id: str
    room_id: str


@dataclass(frozen=True)
class BaselineResult:
    status: str  # COMPLETE | INCOMPLETE
    assignments: tuple[Choice, ...]  # en orden de elección
    order: tuple[str, ...]  # orden estático de secciones
    blocked_section: str | None
    remaining_sections: tuple[str, ...]  # bloqueada y posteriores, sin asignar
    cost_d: int  # del prefijo elegido; igual al total solo si status es COMPLETE
    cost_e: int
    objective: int
    seconds: float

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def choose(
    candidates: Iterable[Candidate], sections: Iterable[str], config: RunConfig
) -> BaselineResult:
    """Núcleo puro de la heurística: no depende del orden de entrada ni de los alt_id."""
    started = time.perf_counter()
    by_section: dict[str, list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        by_section[candidate.section_id].append(candidate)

    order = tuple(sorted(sections, key=lambda section: (len(by_section[section]), section)))
    occupied: set[Occupation] = set()
    chosen: list[Candidate] = []
    blocked = None
    for section_id in order:
        ranked = sorted(
            by_section[section_id],
            key=lambda c: (
                config.alpha * c.cost_d + config.beta * c.cost_e,
                c.pattern_id,
                c.room_id,
            ),
        )
        pick = next((c for c in ranked if occupied.isdisjoint(c.occupancy)), None)
        if pick is None:
            blocked = section_id
            break
        chosen.append(pick)
        occupied |= pick.occupancy

    cost_d = sum(c.cost_d for c in chosen)
    cost_e = sum(c.cost_e for c in chosen)
    remaining = order[len(chosen) :] if blocked else ()
    return BaselineResult(
        status=INCOMPLETE if blocked else COMPLETE,
        assignments=tuple(Choice(c.section_id, c.pattern_id, c.room_id) for c in chosen),
        order=order,
        blocked_section=blocked,
        remaining_sections=remaining,
        cost_d=cost_d,
        cost_e=cost_e,
        objective=config.alpha * cost_d + config.beta * cost_e,
        seconds=time.perf_counter() - started,
    )


def read_candidates(connection: sqlite3.Connection) -> tuple[list[Candidate], list[str]]:
    """Lee las alternativas y ocupaciones ya preparadas, sin modificarlas."""
    occupancy: dict[int, set[Occupation]] = defaultdict(set)
    for alt_id, kind, resource, week, day, block in connection.execute(
        "SELECT alt_id, resource_type, resource_id, week_id, day_id, block_id FROM occupancy"
    ):
        occupancy[alt_id].add((kind, resource, week, day, block))
    candidates = [
        Candidate(alt_id, section, pattern, room, cost_d, cost_e, frozenset(occupancy[alt_id]))
        for alt_id, section, pattern, room, cost_d, cost_e in connection.execute(
            "SELECT alt_id, section_id, pattern_id, room_id, cost_d, cost_e FROM alternative"
        )
    ]
    sections = [section for (section,) in connection.execute("SELECT id FROM sections")]
    return candidates, sections


def run_greedy(connection: sqlite3.Connection, config: RunConfig) -> BaselineResult:
    """Aplica la heurística sobre la base preparada de una corrida."""
    started = time.perf_counter()
    candidates, sections = read_candidates(connection)
    result = choose(candidates, sections, config)
    return replace(result, seconds=time.perf_counter() - started)
