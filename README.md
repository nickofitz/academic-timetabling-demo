# Academic Timetabling Demo

Demo local de programación académica: asigna cada sección a un patrón semanal y una sala, con datos sintéticos, restricciones obligatorias, preferencias explícitas y auditoría independiente.

> **Estado:** MVP 0.1 implementado y revisado. Existen la validación de datos, la carga en SQLite, la generación de los casos micro y demo, la preparación de alternativas en SQL, la optimización con CP-SAT, una heurística voraz, una auditoría independiente, la comparación entre métodos, la grilla HTML offline y el cambio de disponibilidad reproducible. El alcance y las limitaciones de la versión 0.1 se documentan en las entregas y en la demo.
>
> Prototipo independiente con **datos sintéticos**. No usa información, registros ni sistemas de ninguna institución.

## Instalación

Requiere [uv](https://docs.astral.sh/uv/), que obtiene Python 3.12 si no está disponible.

```bash
uv sync --locked
uv run python -m academic_timetabling_demo --help
```

## Generar datos sintéticos

```bash
uv run python -m academic_timetabling_demo generate --case demo --seed 42 --out data/generado/demo
```

La salida debe ser una carpeta nueva o vacía. Los casos `micro` y `demo` de semilla 42 ya están en `data/synthetic/`.

## Resolver y auditar

```bash
uv run python -m academic_timetabling_demo run --input data/synthetic/demo --solver cp-sat --time-limit 30 --seed 42 --out runs/demo
uv run python -m academic_timetabling_demo audit --input data/synthetic/demo --assignments runs/demo/assignments.csv --config runs/demo/effective_config.json
```

`run` copia la entrada a `input/` y trabaja solo desde esa copia. Escribe `metrics.json`, `diagnostics.json`, `audit.json`, `effective_config.json` y, si hay asignaciones, `assignments.csv`. Solo si la solución es completa, está auditada y el snapshot se verificó, agrega `schedule.csv` (una fila por sesión y semana) y `schedule.html`. `--time-limit` y `--seed` sustituyen los valores de `config.json` y quedan registrados.

| Código | Significado |
|---|---|
| 0 | Solución completa y auditada, o auditoría válida |
| 2 | Argumentos o datos inválidos |
| 3 | Sin solución completa: `NO_CANDIDATES`, `INFEASIBLE`, `UNKNOWN` o heurística `INCOMPLETE` |
| 4 | Auditoría fallida; las asignaciones se conservan solo como evidencia inválida |
| 5 | `MODEL_INVALID`, fallo de integridad o de exportación, error del entorno o error interno |

`audit` imprime su informe en JSON y no modifica la corrida.

## Heurística y comparación

```bash
uv run python -m academic_timetabling_demo run --input data/synthetic/demo --solver greedy --out runs/demo-greedy
uv run python -m academic_timetabling_demo run --input data/synthetic/demo --solver cp-sat --time-limit 30 --seed 42 --out runs/demo-cpsat
uv run python -m academic_timetabling_demo compare --runs runs/demo-greedy runs/demo-cpsat --out runs/comparison.json
```

La heurística voraz usa las mismas alternativas y pesos que CP-SAT, sin retroceso. Si se atasca, la corrida termina con código 3 y conserva el prefijo elegido, que no es comparable. `compare` acepta las corridas en cualquier orden, recalcula hashes y auditorías, y solo compara soluciones completas de la misma entrada y los mismos `alpha` y `beta`. La diferencia es `z_greedy - z_cpsat`: positiva favorece a CP-SAT. `metrics.json` registra la semilla de datos en `provenance` solo cuando `generation.json` coincide con las fuentes; `--seed` es la semilla de CP-SAT.

## Grilla HTML

`schedule.html` es un archivo único que se abre con doble clic o arrastrándolo a un navegador, sin servidor ni conexión: CSS, JavaScript y datos van incrustados. Muestra los indicadores reales de la corrida (estado, auditoría, integridad, costo con D/E y pesos, tiempo del método y semilla de datos si está verificada) y una grilla por sala. Se elige una semana a la vez y se puede filtrar por sala, docente y grupo; el botón «Restablecer filtros» vuelve a la primera semana. Los filtros solo cambian lo que se muestra: no recalculan la solución.

## Cambio de disponibilidad

```bash
uv run python scripts/demo_change.py --base-run runs/demo-cpsat --out runs/demo-change
```

Revalida una corrida CP-SAT válida, copia sus fuentes a `changed-input/`, retira la disponibilidad del docente en el primer bloque usado por la primera sección asignada y vuelve a resolver con los mismos parámetros efectivos en `changed-run/`. `change.json` registra el cambio exacto y, si la nueva corrida es válida, cuántas secciones mantienen o cambian patrón o sala. No es una comparación de calidad: las entradas difieren y `compare` las rechaza. El código de salida es el de la nueva corrida, o 2 si la base o la salida no son válidas.

## Demostración

`docs/demo/` contiene un conjunto ya generado y auditado (CP-SAT, heurística, comparación y cambio de disponibilidad) con su guion de cinco minutos en [docs/demo/README.md](docs/demo/README.md).

**Requisito comprobado:** SQLite 3.44 o posterior, porque la preparación ordena dentro de `json_group_array`. `run` lo verifica al empezar; el entorno de desarrollo usa SQLite 3.53.1.

## Preparar alternativas

`run` ejecuta esta preparación; también existe como API de Python:

```python
from pathlib import Path
from academic_timetabling_demo.candidates import build_candidates
from academic_timetabling_demo.db import connect, load_instance
from academic_timetabling_demo.domain import read_instance

connection = connect("base.sqlite")
load_instance(connection, read_instance(Path("data/synthetic/demo")))
precheck = build_candidates(connection)  # READY o NO_CANDIDATES, con conteos por sección
```

## Decisiones técnicas de la versión 0.1

| Aspecto | Decisión |
|---|---|
| Tecnología | Python 3.12, uv, SQLite y OR-Tools CP-SAT |
| Tiempo | Semanas, días y bloques explícitos; sin compresión por segmentos inicialmente |
| Disponibilidad | Docentes y salas disponibles solo en los bloques declarados, por semana |
| Secciones | Docente asignado, matrícula positiva, semanas activas y patrones permitidos explícitos |
| Patrones | Sesiones de igual duración dentro de cada sección; una misma sala para todas |
| Grupos | Incompatibilidades explícitas por estudiantes compartidos o regla curricular documentada |
| Preferencias | Penalización docente por bloques semanales y exceso de capacidad en decenas de asientos |
| Objetivo | `α × penalización + β × exceso`; valores iniciales `α=10`, `β=1` |
| Resultados | CSV, JSON y HTML autocontenido; cada corrida conserva entradas, parámetros y versiones |

Reservas y franjas protegidas son restricciones duras. Los costos se cuentan una vez por patrón semanal o sección, sin multiplicarlos por semanas.

**Fuera de esta versión:** ruido, traslados, asignación de docentes, exámenes, integración institucional, minimizar cambios y comparación con otros solvers.

## Plan de trabajo

La documentación técnica preparada para revisión está organizada así:

- [Especificación normativa](especificacion.md): reglas, datos, modelo, costos, estados y aceptación.
- [Guía de trabajo](Guia_MVP_Timetabling_Codex.md): secuencia, entregables y comandos previstos.
- [Esquema SQLite](schema.sql): tablas fuente y derivadas; su validación no acredita una aplicación terminada.
- [Decisiones](docs/decisiones.md) y [colaboración](docs/colaboracion.md).
- Encargos y entregas de cada hito en `docs/encargos/` y `docs/entregas/`.

Los documentos personales y antecedentes se conservan localmente y quedan fuera del repositorio público.

| Hito | Trabajo | Condición para aprobar |
|---|---|---|
| 0. Base del proyecto | Git, entorno, estructura e instrucciones compartidas | Instalación reproducible y documentación coherente |
| 1. Datos | Esquema, carga transaccional, validación e instancias micro y demo | Datos válidos cargan; errores se rechazan con diagnóstico |
| 2. Candidatos | Filtros SQL y registro de motivos de descarte | Caso micro revisado y secciones sin candidatos explicadas |
| 3. Optimización | CP-SAT y auditoría independiente | Solución válida auditada, infactibilidad detectada y salida manipulada rechazada |
| 4. Comparación | Heurística voraz, métricas y comparación | Mismos datos y pesos; costos comparados solo entre soluciones completas y válidas |
| 5. Presentación | Exportaciones, HTML filtrable y cambio de disponibilidad | Demo reproducible, sin resultados antiguos ni métricas inventadas |

La demo usa cuatro semanas y semilla de datos 42. Los casos de 16 semanas y mayor tamaño quedan para después de la versión 0.1.

## Forma de trabajo

- El autor aprueba el alcance y los cambios de reglas.
- Codex prepara los encargos y revisa las entregas.
- Claude implementa cada hito.
- Cada encargo identifica objetivo, archivos permitidos, pruebas y evidencia requerida.
- Se trabaja en una rama por hito y se revisa antes de integrar en `main`.
- Se evitan las ediciones simultáneas de los mismos archivos.
- Las instrucciones de ambos agentes comparten las mismas reglas y remiten a la especificación.

## Evidencia de aceptación

- Verificar el óptimo de una instancia micro por enumeración independiente.
- Probar capacidad, equipamiento, sesiones de varios bloques, disponibilidad, reservas y franjas protegidas.
- Detectar choques de sala, docente y grupo; permitir compartir recursos en semanas disjuntas.
- Distinguir datos inválidos, dominio vacío, infactibilidad global y búsqueda sin conclusión.
- Reconstruir restricciones y costos en el auditor desde datos originales, sin consultar candidatos ni ocupaciones derivados.
- Probar los estados `OPTIMAL`, `FEASIBLE`, `INFEASIBLE`, `UNKNOWN` y `MODEL_INVALID`; extraer soluciones solo en los dos primeros.
- Ejecutar la demo de 12 secciones y 6 salas, comparar con la heurística y repetir tras cambiar una disponibilidad.

El éxito exige todas las secciones asignadas y cero conflictos auditados en los casos factibles. Los tiempos, costos y diferencias medidos están en `docs/entregas/` y `docs/demo/`; son observaciones de estos datos sintéticos, no promesas de rendimiento.
