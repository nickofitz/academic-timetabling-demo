import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import pytest

from academic_timetabling_demo.domain import read_instance
from academic_timetabling_demo.synthetic import (
    MANIFEST_FILE,
    OutputNotEmptyError,
    generate_to_directory,
)

REPOSITORY = Path(__file__).resolve().parents[1]


def table(directory: Path, name: str) -> list[dict[str, str]]:
    with (directory / f"{name}.csv").open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def manifest(directory: Path) -> dict:
    return json.loads((directory / MANIFEST_FILE).read_text(encoding="utf-8"))


def witness_conflicts(directory: Path) -> list[str]:
    """Comprueba el testigo leyendo los CSV crudos, sin usar el código del generador."""
    sections = {row["id"]: row for row in table(directory, "sections")}
    rooms = {row["id"]: row for row in table(directory, "rooms")}
    authorized = {(r["section_id"], r["pattern_id"]) for r in table(directory, "section_patterns")}
    room_features = {(r["room_id"], r["feature_id"]) for r in table(directory, "room_features")}
    teacher_ok = {
        (r["teacher_id"], r["week_id"], r["day_id"], r["block_id"])
        for r in table(directory, "teacher_available")
    }
    room_ok = {
        (r["room_id"], r["week_id"], r["day_id"], r["block_id"])
        for r in table(directory, "room_available")
    }
    reserved = {
        (r["room_id"], r["week_id"], r["day_id"], r["block_id"])
        for r in table(directory, "room_reservations")
    }
    blocked = {
        (r["section_id"], r["week_id"], r["day_id"], r["block_id"])
        for r in table(directory, "section_blocked")
    }
    pattern_slots = defaultdict(list)
    for row in table(directory, "pattern_sessions"):
        for offset in range(int(row["duration_blocks"])):
            block = str(int(row["start_block_id"]) + offset)
            pattern_slots[row["pattern_id"]].append((row["day_id"], block))
    weeks = defaultdict(list)
    for row in table(directory, "section_weeks"):
        weeks[row["section_id"]].append(row["week_id"])
    groups = defaultdict(list)
    for row in table(directory, "section_groups"):
        groups[row["section_id"]].append(row["group_id"])
    required = defaultdict(list)
    for row in table(directory, "section_features"):
        required[row["section_id"]].append(row["feature_id"])

    problems = []
    witness = manifest(directory)["witness"]
    if sorted(item["section_id"] for item in witness) != sorted(sections):
        problems.append("el testigo no cubre cada sección una vez")

    used: dict[tuple[str, ...], str] = {}
    for item in witness:
        section_id, pattern, room = item["section_id"], item["pattern_id"], item["room_id"]
        section = sections[section_id]
        if (section_id, pattern) not in authorized:
            problems.append(f"{section_id}: patrón no autorizado")
        if int(rooms[room]["capacity"]) < int(section["enrollment"]):
            problems.append(f"{section_id}: capacidad insuficiente")
        for feature in required[section_id]:
            if (room, feature) not in room_features:
                problems.append(f"{section_id}: falta equipamiento {feature}")
        for week in weeks[section_id]:
            for day, block in pattern_slots[pattern]:
                slot = (week, day, block)
                if (section["teacher_id"], *slot) not in teacher_ok:
                    problems.append(f"{section_id}: docente no disponible {slot}")
                if (room, *slot) not in room_ok:
                    problems.append(f"{section_id}: sala no disponible {slot}")
                if (room, *slot) in reserved:
                    problems.append(f"{section_id}: sala reservada {slot}")
                if (section_id, *slot) in blocked:
                    problems.append(f"{section_id}: franja protegida {slot}")
                resources = [("room", room), ("teacher", section["teacher_id"])]
                resources += [("group", group) for group in groups[section_id]]
                for resource in resources:
                    key = (*resource, *slot)
                    if key in used:
                        problems.append(f"{section_id} choca con {used[key]} en {key}")
                    used[key] = section_id
    return problems


def files(directory: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in directory.iterdir()}


@pytest.mark.parametrize("case", ["micro", "demo"])
def test_same_seed_produces_identical_bytes(tmp_path: Path, case: str) -> None:
    generate_to_directory(case, 42, tmp_path / "first")
    generate_to_directory(case, 42, tmp_path / "second")

    assert files(tmp_path / "first") == files(tmp_path / "second")


def test_different_seed_changes_demo(tmp_path: Path) -> None:
    generate_to_directory("demo", 42, tmp_path / "first")
    generate_to_directory("demo", 43, tmp_path / "second")

    assert files(tmp_path / "first") != files(tmp_path / "second")


def test_micro_size(tmp_path: Path) -> None:
    generate_to_directory("micro", 42, tmp_path / "micro")
    instance = read_instance(tmp_path / "micro")

    assert len(instance.sections) in (2, 3)
    assert len(instance.rooms) == 2
    assert len(instance.patterns) <= 6


def test_demo_has_required_characteristics(tmp_path: Path) -> None:
    generate_to_directory("demo", 42, tmp_path / "demo")
    instance = read_instance(tmp_path / "demo")

    assert len(instance.sections) == 12
    assert len(instance.rooms) == 6
    assert len(instance.weeks) == 4
    assert len(instance.days) == 5
    assert len(instance.blocks) == 7
    members = defaultdict(set)
    for membership in instance.section_groups:
        members[membership.group_id].add(membership.section_id)
    assert any(len(sections) > 1 for sections in members.values())
    assert instance.section_features
    assert any(section.blocks_per_session == 2 for section in instance.sections)
    assert instance.room_reservations
    assert instance.section_blocked
    assert any(penalty.penalty > 0 for penalty in instance.teacher_penalties)
    assert {group.basis for group in instance.groups} == {
        "estudiantes_compartidos",
        "regla_curricular",
    }


@pytest.mark.parametrize("seed", [42, *range(20)])
def test_demo_witness_is_compatible(tmp_path: Path, seed: int) -> None:
    generate_to_directory("demo", seed, tmp_path / "demo")

    assert witness_conflicts(tmp_path / "demo") == []


def test_micro_witness_is_compatible(tmp_path: Path) -> None:
    generate_to_directory("micro", 42, tmp_path / "micro")

    assert witness_conflicts(tmp_path / "micro") == []


def test_witness_checker_detects_a_conflict(tmp_path: Path) -> None:
    out = tmp_path / "micro"
    generate_to_directory("micro", 42, out)
    path = out / MANIFEST_FILE
    data = manifest(out)
    data["witness"][2]["pattern_id"] = "P6"
    path.write_text(json.dumps(data), encoding="utf-8")

    assert any("franja protegida" in problem for problem in witness_conflicts(out))


def test_manifest_is_separate_from_source_tables(tmp_path: Path) -> None:
    out = tmp_path / "micro"
    generate_to_directory("micro", 42, out)
    data = manifest(out)

    assert (data["case"], data["seed"], data["format_version"]) == ("micro", 42, 1)
    assert set(data["sources"]) == {p.name for p in out.iterdir()} - {MANIFEST_FILE}
    for name, expected in data["sources"].items():
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == expected
    assert not (out / "witness.csv").exists()


def test_data_seed_does_not_change_solver_seed(tmp_path: Path) -> None:
    generate_to_directory("demo", 7, tmp_path / "demo")

    assert read_instance(tmp_path / "demo").config.random_seed == 42
    assert manifest(tmp_path / "demo")["seed"] == 7


def test_non_empty_output_is_left_intact(tmp_path: Path) -> None:
    out = tmp_path / "salida"
    out.mkdir()
    (out / "nota.txt").write_text("conservar", encoding="utf-8")

    with pytest.raises(OutputNotEmptyError):
        generate_to_directory("micro", 42, out)

    assert files(out) == {"nota.txt": b"conservar"}


def test_empty_output_directory_is_accepted(tmp_path: Path) -> None:
    out = tmp_path / "salida"
    out.mkdir()

    generate_to_directory("micro", 42, out)

    assert (out / MANIFEST_FILE).exists()
    assert [path.name for path in tmp_path.iterdir()] == ["salida"]


@pytest.mark.parametrize("case", ["micro", "demo"])
def test_versioned_case_matches_regeneration(tmp_path: Path, case: str) -> None:
    generate_to_directory(case, 42, tmp_path / case)
    versioned = REPOSITORY / "data" / "synthetic" / case

    # Git puede convertir los finales de línea al clonar en Windows.
    expected = {k: v.replace(b"\r\n", b"\n") for k, v in files(tmp_path / case).items()}
    actual = {k: v.replace(b"\r\n", b"\n") for k, v in files(versioned).items()}
    assert actual == expected
    read_instance(versioned)
