# Entrega del Hito 3: CP-SAT y auditoría independiente

Estado: terminado por Claude, pendiente de revisión de Codex y aprobación del autor. Sin push ni integración en `main`.

## Rama, commits y punto de partida

- Rama `hito/3-optimizacion`, creada desde `main` en `0ed2285`, igual a `origin/main` al empezar.
- Código, pruebas y documentación en `7e1b87c`. Esta entrega va en un commit posterior de la misma rama.
- El encargo se copió sin cambios a `docs/encargos/hito-3.md`.
- **Respaldo:** antes de editar se copiaron los cuatro borradores locales (`model.py`, `validate.py`, `demo_run.py`, `tests/test_optimization.py`) a una carpeta local ignorada, con un `SHA256SUMS`. Eran idénticos a los del respaldo previo al Hito 2. No se tocaron el respaldo anterior, el stash ni `candidates.py`.

## Uso de los borradores

| Borrador | Decisión |
|---|---|
| `model.py` | Base de la formulación. Se reemplazó `round(objective_value)` por un objetivo entero reconstruido y contrastado. Se agregaron el adaptador de estados comprobable, la validación de parámetros y de aritmética exacta, el rechazo de secciones sin alternativas, los conteos y los tiempos. Se conservan `build_and_solve`, `ModelError`, `SolveResult`, `Assignment` y `SOLUTION_STATUSES`. |
| `validate.py` | Base del auditor. Se agregaron límites del día y autosolapamiento de patrones manipulados, hallazgos con tipo de recurso y coordenadas, `status` y `audit_valid`, serialización y lectura validada de `assignments.csv`. Se conservan `audit(...)`, `.passed`, `.objective` y `.findings[].rule`. |
| `tests/test_optimization.py` | Sus casos se reescribieron en `test_model.py` y `test_audit.py`. El archivo queda local e ignorado. Sus 6 pruebas pasan con el código nuevo, pero no cuentan como evidencia. |
| `demo_run.py` | Queda local e ignorado. El flujo público es `run`. No se comprobó si sigue funcionando. |

## Archivos

- **Nuevos:** `src/academic_timetabling_demo/runner.py` y `metrics.py`; `tests/test_model.py`, `test_audit.py` y `test_runner.py`; `.gitattributes`; `docs/encargos/hito-3.md` y esta entrega.
- **Versionados por primera vez a partir de borradores:** `src/academic_timetabling_demo/model.py` y `validate.py`.
- **Modificados:**
  - `cli.py`: comandos `run` y `audit`.
  - `tests/test_cli.py`: ver la sección de pruebas.
  - `.gitignore`: solo las rutas de este hito.
  - `README.md`, `docs/decisiones.md`, y la línea de estado de `especificacion.md` y `Guia_MVP_Timetabling_Codex.md`, sin cambiar reglas ni alcance.
- **Sin cambios:** `schema.sql`, `candidates.py`, `domain.py`, datos versionados, `pyproject.toml` y `uv.lock`. No se usó `tests/fixtures/hito-3/`: las variantes se construyen en las pruebas a partir del micro.

## Finales de línea

- `.gitattributes` fija `eol=lf` para `data/synthetic/**/*.csv` y `data/synthetic/**/*.json`. `git check-attr` lo confirma en ambos datasets; los archivos `.py` no quedan afectados.
- El índice ya guardaba los 44 archivos con LF, así que no hubo renormalización ni cambio de contenido en Git.
- **Carpeta de trabajo:** tenía los 44 archivos con CRLF por `core.autocrlf=true`. Se restauraron desde `HEAD`, tras comprobar que sin `\r` eran idénticos. Ahora están con LF en índice y carpeta.
- **Clon limpio:** con `autocrlf` activo, el clon también obtuvo los 44 archivos con LF.
- **Hashes:** `generation.json` conserva su hash normalizado a LF. Las corridas hashean los bytes exactos de `input/` y lo declaran en `hash_policy`. Una prueba compara entradas LF y CRLF: los hashes de corrida difieren y los del manifiesto coinciden. La decisión quedó en `docs/decisiones.md`.

## Entorno y comandos

`uv run` sigue bloqueado: Windows impide ejecutar `.venv\Scripts\python.exe` por una directiva de Control de aplicaciones (error 4551), en la carpeta de trabajo y en el clon. No se modificó ninguna política. Se usó la alternativa documentada:

```text
C:\Users\<usuario>\.local\share\uv\python\cpython-3.12-windows-x86_64-none\python.exe
PYTHONPATH=<repo>\src;<repo>\.venv\Lib\site-packages
```

Versiones observadas: Python 3.12.16, OR-Tools 9.15.6755, SQLite 3.53.1, paquete 0.1.0, Windows 11 x86_64, 16 CPU lógicas.

| Comando | Dónde | Código | Resultado |
|---|---|---|---|
| `uv sync --locked` (`UV_LINK_MODE=copy`) | Clon limpio | 0 | Entorno instalado desde el lock |
| `uv run ...` | Carpeta y clon | 2 | Bloqueado por Control de aplicaciones |
| `python -m academic_timetabling_demo --help`, `run --help`, `audit --help` | Clon | 0 | Ayuda de los tres |
| `python -m pytest -p no:cacheprovider` | Clon (solo archivos versionados) | 0 | 255 aprobadas |
| `python -m pytest` con los 8 archivos versionados | Carpeta | 0 | 255 aprobadas |
| `python -m ruff check src tests` | Clon | 0 | Sin hallazgos |
| `python -m ruff format --check src tests` | Clon | 0 | 19 archivos con formato correcto |

En el clon, el `site-packages` es el que instaló `uv sync --locked` desde `uv.lock`, y no existen los borradores ignorados. Por eso esa ejecución prueba lo que se enviaría a GitHub. Lo que no se pudo probar es el lanzador `uv run`.

pytest informa 2 advertencias `DeprecationWarning` sobre `~` aplicado a un booleano. Se originan al importar una dependencia (`<frozen importlib>`), no en el código del proyecto.

## Pruebas

| Archivo | En `main` | En la rama |
|---|---|---|
| `test_cli.py` | 14 | 31 |
| `test_db.py` | 10 | 10 |
| `test_domain.py` | 66 | 66 |
| `test_synthetic.py` | 34 | 34 |
| `test_candidates.py` | 31 | 31 |
| `test_model.py` | — | 28 |
| `test_audit.py` | — | 31 |
| `test_runner.py` | — | 24 |
| **Total** | **155** | **255** |

En `test_cli.py`, la prueba que rechazaba `run`, `audit` y `compare` como comandos futuros ahora rechaza solo `compare`. Sus otros dos casos pasaron a una prueba que exige `--input` en `run` y `audit`, así que se conserva el conteo de casos.

Cobertura respecto de la sección 5 del encargo:

1. **Micro:** OPTIMAL con objetivo 3, igual a la enumeración de las 64 combinaciones de patrones autorizados y salas desde las fuentes, sin usar `alternative` ni `occupancy`. Para evitar circularidad, el auditor tiene pruebas directas de costos calculados a mano: `(S1,P1,R1),(S2,P3,R2),(S3,P5,R2)` da D=2, E=5, objetivo 25.
2. **Demo:** 12 secciones asignadas, auditoría sin hallazgos y costo recalculado igual al del solver. Se acepta OPTIMAL o FEASIBLE.
3. **Dominio vacío:** un stub falla si se invoca el solver. Resultado: `solver_status=null`, código 3, diagnóstico persistido y sin `assignments.csv`.
4. **Infactibilidad global:** micro con S1 en G2 da INFEASIBLE, sin asignaciones y con costos `null`.
5. **Semanas:** para sala, docente y grupo por separado, coincidir en el segundo bloque de una sesión doble da INFEASIBLE; en semanas disjuntas da OPTIMAL y auditado.
6. **Estados:** los cinco se prueban con un lector simulado. Los estados sin solución usan un lector que falla si se consulta, y FEASIBLE se mantiene como FEASIBLE. También se prueban un estado desconocido, un objetivo no entero (2.4, sin redondear), una solución que no cubre cada sección una vez y una cota infinita (`null`).
7. **Auditor:** ID desconocido de sección, patrón o sala; sección omitida o duplicada; lista vacía; patrón no autorizado o de forma incompatible; patrón manipulado fuera del día o autosolapado; capacidad; equipamiento; disponibilidad de docente y de sala con coordenadas; reserva y franja en el segundo bloque; choques de sala, docente y grupo, cada uno aislado y con recurso y coordenadas; objetivo falso; `assignments.csv` mal formado, ausente o no UTF-8.
8. **Costos y pesos:** D una vez por patrón semanal y E en decenas redondeadas. Se prueban pesos `alpha`/`beta` alternativos, `alpha=2**40` resuelto sin pérdida, límite exacto en 2**53 y rechazo explícito de semilla o trabajadores fuera de int32 y de límite infinito o NaN.
9. **Independencia:** un subproceso confirma que importar `validate` no carga OR-Tools, `model`, `candidates` ni `db`. Además, se altera `cost_e` en `alternative`: el solver informa 2 y el auditor recalcula 5 desde las fuentes, con `OBJECTIVE_MISMATCH`.
10. **CLI:** `generate` se conserva. Se prueban `run` y `audit` independiente con `--config` y `--reported-objective`, con códigos 0, 2 y 4; parámetros inválidos (`--time-limit` 0, -1, `inf`, `nan` o texto; `--seed` -1 o 1.5; solver desconocido); `greedy` no implementado; salida no vacía intacta; overrides registrados y usados por el solver (con un spy); y auditoría fallida que bloquea el éxito sin cambiar el estado OPTIMAL.
11. **Evidencia:** snapshot de 21 archivos byte a byte, sin `generation.json`; hashes por archivo y global recomputables; hash de `effective_config.json`; configuración original y efectiva separadas; JSON estricto en casos con y sin solución; salida igual a la entrada o dentro de ella rechazada; `run_id` distinto por corrida; archivo fuente faltante registrado con `complete=false`; SQLite sin soporte tratado como error de entorno (código 5).
12. **Clon limpio:** ver la sección de entorno.

## Corridas reales

Ejecutadas en la carpeta de trabajo con los datos en LF. Las salidas quedan en `runs/`, ignorado. Los tiempos son de una sola ejecución en este equipo.

| Corrida | Código | Datos | Precheck | Solver | Auditoría | Objetivo (D, E) | Cota | Brecha |
|---|---|---|---|---|---|---|---|---|
| `run --input data/synthetic/micro --solver cp-sat --out runs/hito3-micro` | 0 | VALID | READY | OPTIMAL | PASSED | 3 (0, 3) | 3.0 | 0.0 |
| `run --input data/synthetic/demo --solver cp-sat --time-limit 30 --seed 42 --out runs/hito3-demo` | 0 | VALID | READY | OPTIMAL | PASSED | 17 (0, 17) | 17.0 | 0.0 |
| Micro con S2 de 60 inscritos (`runs/hito3-sin-candidatos`) | 3 | VALID | NO_CANDIDATES | `null` | NOT_RUN | `null` | `null` | `null` |
| Micro con S1 también en G2 (`runs/hito3-infactible`) | 3 | VALID | READY | INFEASIBLE | NOT_RUN | `null` | `null` | `null` |

| Corrida | Variables | Restricciones (choques) | Alternativas / pares | Ocupaciones | Tiempo total | Solver |
|---|---|---|---|---|---|---|
| micro | 5 | 7 (4) | 5 / 12 | 36 | 0.046 s | 0.005 s |
| demo | 125 | 848 (836) | 125 / 432 | 3370 | 0.121 s | 0.009 s |
| infactible | 5 | 11 (8) | 5 / 12 | 40 | 0.044 s | 0.003 s |

El caso sin candidatos informa `S2: CAPACITY, ROOM_RESERVED`; no construyó modelo ni se midió solver.

La asignación óptima de la demo no coincide con el horario testigo del generador, que no se usó como respuesta ni como hint. No se exige que la asignación sea idéntica entre versiones del solver.

### Auditorías independientes

| Comando | Código | Resultado |
|---|---|---|
| `audit --input data/synthetic/demo --assignments runs/hito3-demo/assignments.csv` | 0 | PASSED, objetivo 17, sin objetivo informado |
| Igual, con `--config runs/hito3-demo/effective_config.json --reported-objective 17` | 0 | PASSED, objetivo 17 contra 17 |
| `audit --input data/synthetic/micro` con `S1,P1,R1 / S2,P3,R2 / S3,P6,R1` | 4 | FAILED: `PROTECTED_SLOT` de S3, y `ROOM_CLASH` R1, `TEACHER_CLASH` T1 y `GROUP_CLASH` G1 entre S1 y S3, todos en semana 1, día 1, bloque 1. Objetivo recalculado 43 (D=4, E=3) |

### Snapshots y hashes

| Corrida | Hash global de `input/` | Hash de `effective_config.json` |
|---|---|---|
| micro | `9db85f36798143e17d3f9a5d89bfef2205cd731751732dedeb45cfd83912f36b` | `5499e259e488a10efc6098c2e8a6796885ef9fd4cd90b6fc3c26b645d8e3e1d9` |
| demo | `2fd989b234c13f9fbab50ba18ee18d9a782a0782b676b954c18745721e5d27c2` | `26a3b784429dfae063a801f7a8d8e498518a483add880ef10fdfa33581fe695e` |

- **Reproducibilidad:** las mismas corridas en el clon limpio dieron los mismos hashes globales y los mismos objetivos.
- **Verificación:** en todas, `snapshot_verified=true`, `source_unchanged=true` y `complete=true`.
- **Configuración efectiva:** en micro coincide en bytes con `config.json`. En demo difiere porque `--time-limit 30` se registra como `30.0`; el override queda en `applied_overrides`.
- **Estado de Git:** las corridas de la carpeta registran `git.dirty=true` sobre `0ed2285`, porque se hicieron antes del commit. Las del clon registran `7e1b87c` con `dirty=false`.

## Decisiones de implementación para revisar

1. **Asignaciones inválidas:** con auditoría fallida, el archivo se sigue llamando `assignments.csv`. Lo marcan inválido `metrics.status.result_valid=false`, `audit.json.audit_valid=false` y el mensaje de error. Si Codex prefiere otro nombre, el cambio es pequeño.
2. **Objetivo exacto:** se rechaza una configuración cuyo objetivo posible supere 2**53. Es el límite en que CP-SAT, que informa el objetivo como `double`, deja de ser exacto.
3. **Base de la corrida:** la corrida usa SQLite en memoria. No guarda un `.sqlite` porque la especificación lo trata como derivado y reconstruible desde `input/`.
4. **Semilla de datos:** `metrics.json` no la registra, porque el snapshot excluye `generation.json` a propósito. Sí registra la semilla, los trabajadores y el límite del solver.
5. **Rutas:** `metrics.input.directory` guarda la ruta de entrada tal como se escribió.

## Limitaciones y pruebas no ejecutadas

- No se ejecutó `uv run` en ninguna parte, por el bloqueo de Windows.
- No se forzó un `UNKNOWN` ni un `MODEL_INVALID` reales: se probaron con el adaptador simulado y con stubs en el runner, como pide el encargo.
- No se probó con más de un trabajador, donde CP-SAT no garantiza el mismo recorrido de búsqueda.
- Solo se probó en Windows.
- Los tiempos son observaciones de una ejecución, no promesas.
- La heurística, `compare`, el HTML y `schedule.csv` quedan para los hitos 4 y 5.
