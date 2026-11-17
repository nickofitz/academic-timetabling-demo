"""Cambio de disponibilidad reproducible para la demostración (Hito 5).

Uso:
    uv run python scripts/demo_change.py --base-run runs/demo-cpsat --out runs/demo-change

Toma una corrida CP-SAT completa, auditada e íntegra, copia sus 21 fuentes, retira exactamente
una fila de teacher_available.csv que la solución base usa y ejecuta una nueva corrida CP-SAT con
los mismos parámetros efectivos. change.json registra el cambio y, si la nueva corrida es válida,
el recuento de reasignaciones por sección. No es una comparación de calidad: las entradas
difieren, y `compare` debe seguir rechazándolas. Tampoco minimiza cambios.

Códigos: los de la nueva corrida (0/2/3/4/5); 2 si la base o la salida no son válidas; 5 si
falla algo interno.
"""

import argparse
import csv
import io
import json
import sys
from pathlib import Path

from academic_timetabling_demo.compare import (
    CompareError,
    load_run,
    recheck,
    validate_costs,
    validate_status,
)
from academic_timetabling_demo.domain import CONFIG_FILE, TABLES, read_instance
from academic_timetabling_demo.metrics import combined_hash, json_bytes, sha256_bytes
from academic_timetabling_demo.runner import RunInputError, run
from academic_timetabling_demo.validate import read_assignments

EXIT_OK = 0
EXIT_INVALID = 2
EXIT_INTERNAL = 5
INPUT_FILES = (*(spec.file for spec in TABLES), CONFIG_FILE)
AVAILABILITY = "teacher_available.csv"


class ChangeError(Exception):
    """La base o la salida no permiten preparar el cambio (código 2)."""


def _inside(path: Path, parent: Path) -> bool:
    path, parent = path.resolve(), parent.resolve()
    return path == parent or parent in path.parents


def check_output(base: Path, out: Path) -> None:
    if _inside(out, base):
        raise ChangeError("--out no puede ser la corrida base ni estar dentro de ella")
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ChangeError(f"--out ya existe y no está vacío: {out}")


def validate_base(base: Path):
    """Revalida la corrida base: CP-SAT completa, íntegra y auditada otra vez."""
    try:
        evidence = load_run(base)
        validate_status(evidence)
        validate_costs(evidence)
    except CompareError as error:
        raise ChangeError(f"corrida base inválida: {error.reason}") from None
    if evidence.method != "cp-sat":
        raise ChangeError("la corrida base debe ser CP-SAT")
    if evidence.metrics["status"].get("solver") not in ("OPTIMAL", "FEASIBLE"):
        raise ChangeError("la corrida base no tiene una solución completa de CP-SAT")
    try:
        recheck(evidence)
    except CompareError as error:
        raise ChangeError(f"la corrida base no pasa la nueva auditoría: {error.reason}") from None
    return evidence


def representable_overrides(evidence) -> dict[str, object]:
    """Overrides de run que reproducen la configuración efectiva de la base, o error."""
    original = json.loads((evidence.path / "input" / CONFIG_FILE).read_text(encoding="utf-8"))
    effective = evidence.config.model_dump()
    # También cuenta el tipo: 30.0 y 30 son iguales en Python, pero no producen el mismo JSON.
    differing = sorted(
        key
        for key in effective
        if effective[key] != original.get(key)
        or type(effective[key]) is not type(original.get(key))
    )
    unsupported = [key for key in differing if key not in ("time_limit_seconds", "random_seed")]
    if unsupported:
        raise ChangeError(
            "la configuración efectiva de la base difiere de su config.json en campos que run "
            f"no puede sustituir: {', '.join(unsupported)}"
        )
    return {
        "time_limit": effective["time_limit_seconds"]
        if "time_limit_seconds" in differing
        else None,
        "seed": effective["random_seed"] if "random_seed" in differing else None,
    }


def choose_slot(evidence) -> dict[str, object]:
    """Primera sección asignada, primera semana activa, primera sesión y su primer bloque."""
    instance = read_instance(evidence.path / "input")
    assignments = sorted(read_assignments(evidence.path / "assignments.csv"))
    section_id, pattern_id, room_id = assignments[0]
    section = next(s for s in instance.sections if s.id == section_id)
    week = min(w.week_id for w in instance.section_weeks if w.section_id == section_id)
    session = min(
        (s for s in instance.pattern_sessions if s.pattern_id == pattern_id),
        key=lambda s: (s.day_id, s.start_block_id, s.session_id),
    )
    return {
        "section_id": section_id,
        "pattern_id": pattern_id,
        "room_id": room_id,
        "teacher_id": section.teacher_id,
        "session_id": session.session_id,
        "week_id": week,
        "day_id": session.day_id,
        "block_id": session.start_block_id,
    }


def remove_availability(content: bytes, slot: dict[str, object]) -> tuple[bytes, str]:
    """Quita exactamente una línea de teacher_available.csv; el resto de bytes no cambia."""
    lines = content.splitlines(keepends=True)
    target = [
        str(slot["teacher_id"]),
        str(slot["week_id"]),
        str(slot["day_id"]),
        str(slot["block_id"]),
    ]
    matches = [
        index
        for index, line in enumerate(lines[1:], start=1)
        if next(csv.reader(io.StringIO(line.decode("utf-8")))) == target
    ]
    if len(matches) != 1:
        raise ChangeError(
            f"inconsistencia: se esperaba una fila {target} en {AVAILABILITY} y hay {len(matches)}"
        )
    removed = lines.pop(matches[0])
    return b"".join(lines), removed.decode("utf-8").rstrip("\r\n")


def diff_assignments(
    before: list[tuple[str, str, str]], after: list[tuple[str, str, str]]
) -> dict[str, object]:
    """Recuento de reasignaciones por sección entre dos horarios completos."""
    old = {section: (pattern, room) for section, pattern, room in before}
    new = {section: (pattern, room) for section, pattern, room in after}
    if set(old) != set(new):
        raise ValueError("los horarios no cubren las mismas secciones")
    categories = {"unchanged": [], "pattern_changed": [], "room_changed": [], "both_changed": []}
    for section in sorted(old):
        (p0, r0), (p1, r1) = old[section], new[section]
        entry = {
            "section_id": section,
            "before": {"pattern_id": p0, "room_id": r0},
            "after": {"pattern_id": p1, "room_id": r1},
        }
        if p0 == p1 and r0 == r1:
            categories["unchanged"].append(entry)
        elif p0 != p1 and r0 != r1:
            categories["both_changed"].append(entry)
        elif p0 != p1:
            categories["pattern_changed"].append(entry)
        else:
            categories["room_changed"].append(entry)
    counts = {key: len(value) for key, value in categories.items()}
    return {"total_sections": len(old), "counts": counts, "sections": categories}


def prepare_change(base: Path, out: Path) -> tuple[dict[str, object], dict[str, object]]:
    """Valida y escribe changed-input/; devuelve el registro inicial y los overrides."""
    check_output(base, out)
    evidence = validate_base(base)
    overrides = representable_overrides(evidence)
    slot = choose_slot(evidence)
    sources = {name: (evidence.path / "input" / name).read_bytes() for name in INPUT_FILES}
    changed, removed = remove_availability(sources[AVAILABILITY], slot)
    out.mkdir(parents=True, exist_ok=True)
    target = out / "changed-input"
    target.mkdir()
    for name in INPUT_FILES:
        (target / name).write_bytes(changed if name == AVAILABILITY else sources[name])
    hashes = {name: sha256_bytes((target / name).read_bytes()) for name in INPUT_FILES}
    record = {
        "base": {
            "path": str(base),
            "run_id": evidence.run_id,
            "input_sha256": evidence.input_sha256,
            "solver_status": evidence.metrics["status"]["solver"],
            "objective": evidence.verified_objective,
        },
        "change": {
            **slot,
            "file": AVAILABILITY,
            "removed_row": removed,
            "description": "se retira una disponibilidad docente usada por la solución base",
        },
        "changed_input": {"path": str(target), "combined_sha256": combined_hash(hashes)},
        "parameters": {
            "effective_config": evidence.config.model_dump(),
            "overrides_for_run": overrides,
        },
        "note": "Recuento de reasignaciones entre entradas distintas; no es una comparación de "
        "calidad ni minimiza cambios.",
    }
    return record, overrides


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="demo_change", description=__doc__.split("\n\n")[0])
    parser.add_argument("--base-run", required=True, type=Path, help="corrida CP-SAT válida")
    parser.add_argument("--out", required=True, type=Path, help="carpeta nueva o vacía")
    args = parser.parse_args(argv)

    try:
        record, overrides = prepare_change(args.base_run, args.out)
    except ChangeError as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_INVALID
    except OSError as error:
        print(f"error: no se pudo leer o escribir: {error}", file=sys.stderr)
        return EXIT_INVALID

    try:
        new_run = args.out / "changed-run"
        outcome = run(
            args.out / "changed-input",
            new_run,
            solver="cp-sat",
            time_limit=overrides["time_limit"],
            seed=overrides["seed"],
        )
        status = outcome.metrics["status"]
        record["changed_run"] = {
            "path": str(new_run),
            "run_id": outcome.metrics["run_id"],
            "exit_code": outcome.exit_code,
            "status": status,
            "objective": (outcome.metrics.get("costs") or {}).get("objective"),
            "error": outcome.metrics["error"],
            "provenance_status": (outcome.metrics.get("provenance") or {}).get("status"),
        }
        if outcome.exit_code == EXIT_OK:
            before = read_assignments(args.base_run / "assignments.csv")
            after = read_assignments(new_run / "assignments.csv")
            record["reassignments"] = diff_assignments(before, after)
        else:
            record["reassignments"] = None
            record["reassignments_note"] = (
                "no aplicable: la nueva corrida no es un horario completo válido"
            )
        (args.out / "change.json").write_bytes(json_bytes(record))
    except RunInputError as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_INVALID
    except Exception as error:
        print(f"error interno: {type(error).__name__}: {error}", file=sys.stderr)
        return EXIT_INTERNAL

    reassigned = record["reassignments"]
    summary = reassigned["counts"] if reassigned else "no aplicable"
    print(
        f"Cambio en {args.out}: {record['change']['teacher_id']} sin semana "
        f"{record['change']['week_id']}, día {record['change']['day_id']}, bloque "
        f"{record['change']['block_id']}; nueva corrida código {outcome.exit_code}; "
        f"reasignaciones {summary}"
    )
    return outcome.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
