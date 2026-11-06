# Entrega del Hito 0: base reproducible

Estado: terminado por Claude, revisado técnicamente por Codex y aprobado por el autor.

## Rama

Desarrollado en la rama local `hito/0-base` y publicado en `main` como un único commit junto con la documentación técnica.

## Versiones reales

| Componente | Versión |
|---|---|
| Sistema | Windows 11 (x86_64) |
| uv | 0.13.7 |
| Python | 3.12.16 (CPython, administrado por uv) |
| ortools | 9.15.6755 |
| pydantic | 2.14.3 |
| jinja2 | 3.1.6 |
| pytest | 9.2.0 |
| ruff | 0.17.4 |

`uv.lock` fija 23 paquetes y no contiene rutas personales.

## Archivos

Nuevos: `pyproject.toml`, `.python-version`, `uv.lock`, `src/academic_timetabling_demo/__init__.py`, `src/academic_timetabling_demo/__main__.py`, `src/academic_timetabling_demo/cli.py`, `tests/test_cli.py`, `docs/entregas/hito-0.md`.

Modificados: `.gitignore` (excepciones solo para estas rutas y exclusión de `.venv`, cachés y `runs/`) y `README.md` (estado e instalación).

No se modificaron especificación, esquema, instrucciones compartidas ni material local.

## Comandos y resultados

Ejecutados en la carpeta de trabajo:

| Comando | Código | Resultado |
|---|---|---|
| `uv sync --locked` | 0 | 23 paquetes verificados |
| `uv run python -c "import academic_timetabling_demo"` | 0 | Sin salida |
| `uv run python -m academic_timetabling_demo --help` | 0 | Muestra nombre del programa y propósito |
| `uv run pytest` | 0 | 3 pruebas aprobadas |
| `uv run ruff check .` | 0 | Sin hallazgos |
| `uv run ruff format --check .` | 0 | 12 archivos con formato correcto |

Comprobaciones adicionales:

- Clon limpio del código de este hito: `uv sync --locked`, ayuda, `pytest`, `ruff check` y `ruff format --check` con código 0; `git status` sin cambios después de ejecutarlos.
- Terminal de usuario, fuera de la app de Claude: `uv --version` y la ayuda funcionan.
- `import ortools` funciona con Python 3.12.16. No se ejecutó ningún modelo.
- `git check-ignore` confirma que `.venv`, `__pycache__`, `local/` y el material local quedan excluidos.

## Pruebas

`tests/test_cli.py` ejecuta el programa mediante subprocess y comprueba:

1. `--help` termina con código 0 y muestra nombre y propósito.
2. Un argumento desconocido, como `generate`, termina con código 2. Esta prueba no estaba pedida; evita que parezca existir un comando vacío.
3. Importar el paquete, `cli` y `__main__` no escribe salida ni carga `ortools`.

## Bloqueos y limitaciones

- **Instalación de Python desde la app de Claude:** la primera instalación con la ruta por omisión falló, porque la app empaquetada redirige las escrituras en `AppData`. Se instaló con `UV_PYTHON_INSTALL_DIR` apuntando a `.local\share\uv\python` del perfil de usuario. Esa variable no quedó persistente. Si se recrea el entorno desde la app de Claude, hay que volver a definirla; desde una terminal normal no se probó una instalación nueva con la ruta por omisión.
- **`.venv` dentro de OneDrive:** la carpeta del proyecto está sincronizada, por lo que el entorno puede subirse a la nube. No se observó ningún fallo; queda como decisión del autor.
- **Solo Windows:** no se probó en otro sistema operativo. `uv.lock` es multiplataforma, pero eso no se verificó con ejecuciones.
- **Fin de línea:** Git avisa de conversión LF a CRLF en este equipo. No afecta a las verificaciones.

## Observaciones

- El Hito 1 deberá agregar sus rutas a la lista blanca de `.gitignore`.
