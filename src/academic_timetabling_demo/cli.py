"""Interfaz de línea de comandos."""

import argparse
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
EPILOG = "Estado: generación de datos disponible. Todavía no hay optimización."

EXIT_OK = 0
EXIT_INVALID = 2
EXIT_INTERNAL = 5


def _seed(value: str) -> int:
    try:
        seed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("debe ser un entero no negativo") from None
    if seed < 0:
        raise argparse.ArgumentTypeError("debe ser un entero no negativo")
    return seed


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


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return EXIT_OK
    return _generate(args)
