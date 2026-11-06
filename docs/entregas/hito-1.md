# Entrega del Hito 1: datos y validación

Estado: terminado por Claude, pendiente de revisión de Codex y aprobación del autor. Sin push ni integración en `main`.

## Rama

`hito/1-datos`, creada desde `main` en `b1d7f0b`. Código y datos en `dd81425`; esta entrega va en un commit posterior de la misma rama.

## Archivos

- Nuevos: `src/academic_timetabling_demo/domain.py`, `db.py`, `synthetic.py`; `tests/test_domain.py`, `test_db.py`, `test_synthetic.py`; `data/synthetic/micro/` y `data/synthetic/demo/` (22 archivos cada uno); `docs/entregas/hito-1.md`.
- Modificados: `src/academic_timetabling_demo/cli.py`, `tests/test_cli.py`, `.gitignore`, `README.md`.
- Sin cambios: `schema.sql`, especificación, instrucciones compartidas y `uv.lock`. No se usaron fixtures en `tests/fixtures/`: las pruebas parten del caso micro generado y lo alteran.

## API y comandos

```bash
uv run python -m academic_timetabling_demo generate --case micro --seed 42 --out RUTA
uv run python -m academic_timetabling_demo generate --case demo --seed 42 --out RUTA
```

```python
from pathlib import Path
from academic_timetabling_demo.db import load_database
from academic_timetabling_demo.domain import read_instance

load_database("base.sqlite", read_instance(Path("data/synthetic/demo")))
```

No existe comando de carga: el encargo pide funciones, y `run` queda para hitos posteriores. `run`, `audit` y `compare` terminan con código 2.

## Resultados

Ejecutados en la carpeta de trabajo con uv 0.13.7 y Python 3.12.16 en Windows 11:

| Comando | Código | Resultado |
|---|---|---|
| `uv sync --locked` | 0 | 23 paquetes verificados |
| `uv run python -m academic_timetabling_demo --help` | 0 | Muestra `generate` |
| `uv run python -m academic_timetabling_demo generate --help` | 0 | Muestra `--case`, `--seed`, `--out` |
| `uv run pytest` | 0 | 124 pruebas aprobadas |
| `uv run ruff check src tests` | 0 | Sin hallazgos |
| `uv run ruff format --check src tests` | 0 | 10 archivos con formato correcto |

Clon limpio de `dd81425`, con `UV_LINK_MODE=copy` (ver limitaciones): los mismos `uv sync --locked`, `pytest` y Ruff con código 0 y 124 pruebas aprobadas. `generate` de micro y demo en carpetas nuevas: los 44 archivos coinciden con los versionados, sin contar finales de línea. `git status` quedó sin cambios.

Además, `generate_case("demo", semilla)` terminó sin error para las semillas 0 a 499. La compatibilidad del testigo se comprobó solo para las semillas 0 a 19 y 42, en las pruebas.

## Casos generados (semilla 42)

| Caso | Secciones | Salas | Semanas | Días | Bloques | Patrones | Filas fuente | Hash de `sections.csv` | Hash de `config.json` |
|---|---|---|---|---|---|---|---|---|---|
| micro | 3 | 2 | 2 | 2 | 3 | 6 | 99 | `98f2e89af24f6a22…` | `5499e259e488a10e…` |
| demo | 12 | 6 | 4 | 5 | 7 | 38 | 1909 | `8c3bb7039eba6278…` | `5499e259e488a10e…` |

Ambos se cargaron en SQLite con `load_database`: `foreign_key_check` sin hallazgos y las tres tablas derivadas con 0 filas. Los hashes completos de las 21 fuentes están en cada `generation.json`.

### Dominio del caso micro

Es un diseño fijo para revisarlo a mano. Tiene 12 pares sección-patrón-sala antes de filtrar. Lo siguiente es lo esperado por razonamiento, no un resultado calculado, porque los filtros son del Hito 2:

| Sección | Patrones | Sala posible | Motivo | Alternativas esperadas |
|---|---|---|---|---|
| S1 | P1, P2 | R1 | R2 no tiene el equipamiento F1 | 2 |
| S2 | P3 (P4 descartado) | R2 | 40 inscritos superan la capacidad de R1; P4 choca con la reserva de R2 | 1 |
| S3 | P5 (P6 descartado) | R1, R2 | P6 usa la franja protegida del día 1, bloque 1 | 2 |

## Cobertura de las pruebas

- **Lectura:** carga válida, tablas opcionales vacías, ID con ceros iniciales, archivo ausente, encabezado incorrecto, fila mal formada, codificación, enteros inválidos (decimales, booleanos, vacíos) y rangos.
- **Reglas:** duplicados, referencias rotas, horizonte vacío, semanas y bloques no consecutivos, bloques de distinta duración o superpuestos, sesiones fuera del día o solapadas, frecuencia y duración incompatibles, sección sin grupo, semana o patrón, y bloqueo fuera de semanas activas.
- **Datos válidos que no se rechazan:** ausencia de disponibilidad, reserva sobre sala disponible y demanda superior a todas las salas.
- **Carga:** columnas iguales a `schema.sql`, claves foráneas por conexión, rollback con un fallo real provocado por un trigger durante la inserción, rechazo previo de datos inválidos, base no vacía intacta y tablas derivadas vacías.
- **Generador:** bytes idénticos por semilla, características de la demo, salida no vacía intacta y casos versionados iguales a la regeneración.
- **Testigo:** un verificador propio de las pruebas lee los CSV crudos sin usar el código del generador, y una prueba confirma que detecta un testigo alterado. No es el auditor del Hito 3.

## Decisiones para revisar

1. **Finales de línea:** los archivos se generan con LF, pero `core.autocrlf=true` los convierte a CRLF al clonar en Windows. Por eso los hashes de `generation.json` se calculan normalizando a LF, lo que queda declarado en el manifiesto. Dos generaciones sí son idénticas byte por byte. Un `.gitattributes` con `data/synthetic/** -text` sería más limpio, pero esa ruta no está permitida en este encargo. Se recomienda evaluarlo antes de que el Hito 3 calcule hashes de entrada.
2. **Cardinalidades mínimas:** solo se exige horizonte no vacío y lo que la especificación pide a cada sección. Una entrada sin secciones o sin salas es estructuralmente válida. No se agregó una regla que la especificación no declara.
3. **Micro no depende de la semilla:** es fijo para que siga siendo revisable a mano. La semilla se registra igual en el manifiesto. `config.json` conserva `random_seed=42` aunque cambie la semilla de datos, porque son parámetros separados.
4. **Patrones no autorizados:** se les comprueba límites del día y solapamiento. Frecuencia y duración solo se comprueban contra las secciones que los autorizan.
5. **Numeración de filas:** los diagnósticos cuentan registros CSV, con el encabezado como fila 1.

## Limitaciones

- No hay candidatos, solver, auditor ni HTML. La compatibilidad del testigo no certifica factibilidad del solver.
- Los casos `no-candidates`, `infeasible` y `calendar` no se prepararon; el encargo los deja para cuando se necesiten.
- **Clon con hardlinks:** en este equipo `uv sync` falló en el clon limpio con el error 396 de Windows al crear hardlinks desde la caché de uv, probablemente porque esa caché comparte vínculos con un `.venv` dentro de OneDrive. Con `UV_LINK_MODE=copy` funciona. No es un fallo del proyecto, pero afecta a quien clone en este equipo.
- La carga necesita `schema.sql` en la raíz del repositorio; no funciona como paquete instalado aparte.
- Solo se probó en Windows.
