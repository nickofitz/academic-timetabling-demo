"""Interfaz de línea de comandos. En el Hito 0 solo ofrece la ayuda general."""

import argparse
from collections.abc import Sequence

PROGRAM_NAME = "academic_timetabling_demo"
DESCRIPTION = (
    "Demo local de programación académica: asigna cada sección a un patrón semanal "
    "y una sala, usando exclusivamente datos sintéticos."
)
EPILOG = "Estado: base del proyecto. Todavía no hay comandos funcionales."


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(prog=PROGRAM_NAME, description=DESCRIPTION, epilog=EPILOG)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0
