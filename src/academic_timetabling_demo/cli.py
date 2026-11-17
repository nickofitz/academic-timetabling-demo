"""Interfaz de línea de comandos."""

import argparse
import json
import math
import sys
from collections.abc import Sequence
from pathlib import Path

from academic_timetabling_demo.domain import DataValidationError
from academic_timetabling_demo.synthetic import CASES, OutputNotEmptyError, generate_to_directory

PROGRAM_NAME = "academic_timetabling_demo"
DESCRIPTION = (
    "Demo local de programación académica: asigna cada sección a un patrón semanal "
    "y una sala, usando exclusivamente datos sintéticos."
)
EPILOG = (
    "Estado: generación, optimización con CP-SAT, heurística voraz, auditoría y comparación "
    "disponibles. El HTML aún no existe."
)

EXIT_OK = 0
EXIT_INVALID = 2
EXIT_AUDIT_FAILED = 4
EXIT_INTERNAL = 5
SOLVER_CHOICES = ("cp-sat", "greedy")


def _non_negative_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("debe ser un entero no negativo") from None
    if number < 0:
        raise argparse.ArgumentTypeError("debe ser un entero no negativo")
    return number


_seed = _non_negative_int


def _positive_seconds(value: str) -> float:
    try:
        number = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("debe ser un número positivo y finito") from None
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("debe ser un número positivo y finito")
    return number


def _integer(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("debe ser un entero") from None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=PROGRAM_NAME, description=DESCRIPTION, epilog=EPILOG)
    commands = parser.add_subparsers(dest="command", title="comandos")

    generate = commands.add_parser(
        "generate",
        help="genera un caso sintético",
        description="Genera y valida las tablas fuente de un caso sintético en una carpeta nueva.",
    )
    generate.add_argument("--case", required=True, choices=CASES, help="caso a generar")
    generate.add_argument("--seed", type=_seed, default=42, help="semilla de datos (42)")
    generate.add_argument("--out", required=True, type=Path, help="carpeta de salida nueva o vacía")

    run = commands.add_parser(
        "run",
        help="resuelve y audita una entrada",
        description=(
            "Copia la entrada, prepara alternativas, resuelve con CP-SAT o con la heurística "
            "voraz, audita y escribe metrics.json, diagnostics.json, audit.json y, si hay "
            "asignaciones, assignments.csv. Solo si la solución es completa, está auditada y el "
            "snapshot está verificado, agrega schedule.csv y schedule.html (grilla offline "
            "filtrable). Códigos: 0 solución completa auditada y exportada; 2 datos o "
            "argumentos inválidos; 3 sin solución completa (incluida la heurística atascada); "
            "4 auditoría fallida; 5 MODEL_INVALID, integridad, exportación o error interno."
        ),
    )
    run.add_argument("--input", required=True, type=Path, help="carpeta con los CSV y config.json")
    run.add_argument(
        "--solver", default="cp-sat", choices=SOLVER_CHOICES, help="cp-sat o greedy (voraz)"
    )
    run.add_argument(
        "--time-limit", type=_positive_seconds, help="segundos de CP-SAT; sustituye config.json"
    )
    run.add_argument(
        "--seed",
        type=_non_negative_int,
        help="semilla de CP-SAT, no de datos; sustituye config.json",
    )
    run.add_argument("--out", required=True, type=Path, help="carpeta de salida nueva o vacía")

    audit = commands.add_parser(
        "audit",
        help="audita asignaciones contra los datos originales",
        description=(
            "Imprime el informe de auditoría en JSON. Código 0 si pasa, 4 si falla, "
            "2 si la entrada o las asignaciones no se pueden leer."
        ),
    )
    audit.add_argument(
        "--input", required=True, type=Path, help="carpeta con los CSV y config.json"
    )
    audit.add_argument("--assignments", required=True, type=Path, help="assignments.csv a auditar")
    audit.add_argument(
        "--config", type=Path, help="configuración a usar, p. ej. effective_config.json"
    )
    audit.add_argument(
        "--reported-objective", type=_integer, help="objetivo declarado a contrastar"
    )

    compare = commands.add_parser(
        "compare",
        help="compara una corrida greedy con una cp-sat",
        description=(
            "Compara dos corridas de los mismos datos y pesos (una greedy y una cp-sat, en "
            "cualquier orden), volviendo a verificar snapshots y auditorías. Escribe un JSON "
            "nuevo. Códigos: 0 comparación válida; 2 corridas o argumentos inválidos; 3 no "
            "comparable por falta de solución completa; 4 auditoría fallida; 5 error interno."
        ),
    )
    compare.add_argument(
        "--runs", required=True, nargs=2, type=Path, metavar="CORRIDA", help="dos corridas"
    )
    compare.add_argument("--out", required=True, type=Path, help="JSON nuevo para el informe")
    return parser


def _generate(args: argparse.Namespace) -> int:
    try:
        generated = generate_to_directory(args.case, args.seed, args.out)
    except (OutputNotEmptyError, DataValidationError) as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_INVALID
    except Exception as error:
        print(f"error interno: {error}", file=sys.stderr)
        return EXIT_INTERNAL
    print(f"Caso {generated.case} (semilla {generated.seed}) generado en {args.out}")
    return EXIT_OK


def _run(args: argparse.Namespace) -> int:
    from academic_timetabling_demo.runner import RunInputError, run

    try:
        outcome = run(
            args.input, args.out, solver=args.solver, time_limit=args.time_limit, seed=args.seed
        )
    except RunInputError as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_INVALID
    status = outcome.metrics["status"]
    costs = outcome.metrics.get("costs") or {}
    print(
        f"Corrida {outcome.metrics['run_id']} en {outcome.out}: datos {status['data']}, "
        f"precheck {status['precheck']}, método {args.solver}, solver {status['solver']}, "
        f"heurística {status['baseline']}, auditoría {status['audit']}, "
        f"objetivo {costs.get('objective')}, código {outcome.exit_code}"
    )
    if outcome.metrics["error"]:
        print(f"detalle: {outcome.metrics['error']}", file=sys.stderr)
    return outcome.exit_code


def _audit(args: argparse.Namespace) -> int:
    from academic_timetabling_demo.domain import Issue, read_config, read_instance
    from academic_timetabling_demo.validate import AssignmentsError, audit, read_assignments

    # Solo la lectura de entradas traduce errores; la auditoría queda fuera de estos bloques.
    option = "--input"
    try:
        instance = read_instance(args.input)
        config = instance.config
        if args.config is not None:
            option = "--config"
            issues: list[Issue] = []
            config = read_config(args.config, issues)
            if config is None:
                raise DataValidationError(issues)
        option = "--assignments"
        assignments = read_assignments(args.assignments)
    except (DataValidationError, AssignmentsError) as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_INVALID
    except OSError as error:
        path = error.filename or getattr(args, option.removeprefix("--"))
        cause = f"{type(error).__name__}: {error.strerror or error}"
        print(f"error: no se pudo leer {option} ({path}): {cause}", file=sys.stderr)
        return EXIT_INVALID
    report = audit(instance, assignments, args.reported_objective, config)
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, allow_nan=False))
    return EXIT_OK if report.passed else EXIT_AUDIT_FAILED


def _compare(args: argparse.Namespace) -> int:
    from academic_timetabling_demo.compare import (
        EXIT_INTERNAL as COMPARE_INTERNAL,
    )
    from academic_timetabling_demo.compare import (
        OutputError,
        check_output,
        compare_runs,
        write_report,
    )

    try:
        check_output(args.out, list(args.runs))
    except OutputError as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_INVALID
    try:
        code, report = compare_runs(list(args.runs))
    except Exception as error:
        # Fallo interno: no se presenta como dato inválido ni se escribe un informe numérico.
        print(f"error interno: {type(error).__name__}: {error}", file=sys.stderr)
        code, report = (
            COMPARE_INTERNAL,
            {
                "status": "ERROR",
                "exit_code": COMPARE_INTERNAL,
                "reason": f"error interno: {type(error).__name__}: {error}",
                "runs_read": [str(path) for path in args.runs],
            },
        )
    try:
        write_report(args.out, report)
    except OSError as error:
        print(f"error: no se pudo escribir {args.out}: {error}", file=sys.stderr)
        return COMPARE_INTERNAL
    difference = report.get("difference") or {}
    print(
        f"Comparación {report['status']} en {args.out}: diferencia {difference.get('absolute')}, "
        f"porcentaje {difference.get('percent')}, código {code}"
    )
    if report.get("reason"):
        print(f"detalle: {report['reason']}", file=sys.stderr)
    return code


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return EXIT_OK
    handlers = {"generate": _generate, "run": _run, "audit": _audit, "compare": _compare}
    return handlers[args.command](args)
