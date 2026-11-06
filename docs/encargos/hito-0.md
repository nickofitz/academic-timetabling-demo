# Encargo para Claude: Hito 0, base reproducible

## Objetivo y punto de partida

Preparar el paquete Python y su entorno, sin implementar generación de horarios, carga de datos, solver ni interfaz. El repositorio ya existe y está vinculado a GitHub: no inicializar otro ni crear uno nuevo. Leer AGENTS.md y los documentos que referencia.

Antes de empezar, confirmar con el autor que Codex terminó la revisión documental y no está editando. Inspeccionar estado Git y conservar cambios existentes. Este encargo se ejecuta después de integrar o asegurar la preparación documental; no cambiar de rama con cambios ajenos pendientes. Crear rama `hito/0-base` desde main limpio.

## Rutas permitidas

`pyproject.toml`, `.python-version`, `uv.lock`, `src/academic_timetabling_demo/__init__.py`, `src/academic_timetabling_demo/__main__.py`, `src/academic_timetabling_demo/cli.py`, `tests/test_cli.py`, `.gitignore`, `README.md`, `docs/entregas/hito-0.md`.

No modificar especificación, esquema, instrucciones compartidas ni documentos privados. Si hace falta cambiar el contrato, entregar la observación a Codex y al autor.

## Trabajo

- Verificar Python 3.12 y uv; instalar solo si el entorno lo permite y registrar versiones reales. Informar bloqueos sin fingir éxito.
- Preparar paquete importable `academic_timetabling_demo` con Python >=3.12,<3.13 y entorno administrado por uv.
- Dependencias: ortools, pydantic, jinja2; desarrollo: pytest y ruff. Generar y conservar uv.lock.
- Implementar únicamente CLI de ayuda con argparse: `python -m academic_timetabling_demo --help` describe el propósito. No exponer comandos funcionales vacíos ni fabricar resultados.
- Añadir prueba de integración que ejecute la ayuda mediante subprocess, compruebe código 0 y nombre del programa. Confirmar importación sin efectos secundarios.
- Extender lista blanca de Git solo para rutas del hito; excluir siempre `.venv`, cachés, runs y material privado. Actualizar README con instalación, ayuda y estado real.

## Verificación y entrega

Ejecutar `uv sync --locked`, `uv run python -c "import academic_timetabling_demo"`, `uv run python -m academic_timetabling_demo --help`, `uv run pytest`, `uv run ruff check .` y `uv run ruff format --check .`.

Entregar en `docs/entregas/hito-0.md`: versiones, rama, archivos, comandos, resultados y bloqueos reales. Revisar diff y contenido publicable; no hacer push ni integrar en main sin autorización.

Puerta de salida: instalación reproducible, paquete importable, ayuda funcional, prueba de CLI y comprobaciones aprobadas. Codex revisa antes de empezar Hito 1.
