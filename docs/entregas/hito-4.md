# Entrega del Hito 4: heurística voraz y comparación

Estado: aprobado técnicamente por Codex el 16 de noviembre de 2026, con 361 pruebas versionadas y Ruff aprobados. Las dos correcciones están verificadas; el autor autorizó integrar y publicar el hito. Se conserva abajo la evidencia de las entregas y revisiones anteriores.

## Correcciones tras la revisión de Codex

Codex revisó `611e572` y pidió dos correcciones en `compare`. Están en `5a46ac1`, sobre la misma rama. Solo cambiaron `compare.py`, `tests/test_compare.py` y `tests/test_cli.py`, además de esta entrega. No se tocaron la heurística, el runner, el modelo, el auditor, las reglas, los pesos ni los datasets.

### 1. El objetivo comparado ya no elude la auditoría

- **Antes:** si `costs.objective` no era entero, se le pasaba `None` al auditor (sin contraste), y la diferencia se calculaba con el valor guardado. Con `0.0` en greedy, la comparación declaraba una falsa victoria de la heurística.
- **Ahora:** `validate_costs` revisa la estructura antes de usar los costos.
  - En una corrida completa, `cost_d`, `cost_e` y `objective` deben ser enteros no negativos, sin aceptar `bool`. Cualquier otro valor (ausente, `null`, flotante, texto, negativo o `costs` que no sea un objeto) da código 2.
  - En una corrida sin solución completa, los tres deben ser `null`; si no, es corrupción (código 2), no `NOT_COMPARABLE`.
- **Contraste obligatorio:** el auditor siempre recibe el objetivo registrado. Un entero bien formado pero falso sigue dando código 4.
- **Diferencia:** se calcula con el objetivo confirmado por la nueva auditoría y los pesos efectivos. Ningún informe con error incluye `difference`.

### 2. Los estados se validan antes de declarar NOT_COMPARABLE

- **Antes:** cualquier estado fuera de los completos se clasificaba como `NOT_COMPARABLE`. Por ejemplo, `ESTADO_INEXISTENTE` daba código 3.
- **Ahora:** `validate_status` corre antes que cualquier clasificación y exige:
  - `status.precheck` igual a `READY` o `NO_CANDIDATES`.
  - Greedy: `status.solver` en `null` y `status.baseline` igual a `COMPLETE` o `INCOMPLETE`.
  - CP-SAT: `status.baseline` en `null` o ausente (corridas del Hito 3), y `status.solver` entre los cinco estados reales.
  - Con precheck `NO_CANDIDATES`, el estado del método debe ser `null`; con `READY` no puede faltar.
- **Resultado:** las etiquetas desconocidas, ausentes o contradictorias dan código 2 `INVALID`. `MODEL_INVALID` también da 2, con un mensaje que lo presenta como error de la corrida y no como búsqueda inconclusa.
- **Lo que no cambia:** `INCOMPLETE`, `NO_CANDIDATES`, `INFEASIBLE` y `UNKNOWN` legítimos siguen dando código 3, sin fórmulas. Las corridas del Hito 3 sin `baseline` ni `provenance` siguen siendo comparables.

### Regresiones nuevas

24 pruebas nuevas: 23 en `test_compare.py` y 1 en `test_cli.py`. Contra el código de `ab78715`, 21 fallan y 3 pasan. Las 3 que pasan son guardas que deben aprobarse con ambas versiones: entero falso sigue en código 4, la diferencia usa objetivos auditados, y los estados legítimos sin solución siguen dando 3.

| Prueba | Qué comprueba |
|---|---|
| `test_reproduction_float_objective_is_not_a_greedy_win` | Reproducción exacta de Codex (`objective=0.0` en greedy): código 2, sin `difference` |
| `test_malformed_objective_is_invalid` (5 casos) | `2.5`, `null`, `"3"`, `true` y `-3`: código 2 |
| `test_missing_objective_or_costs_is_invalid` | Clave ausente y `costs` que no es objeto: código 2 |
| `test_malformed_cost_components_are_invalid` (3 casos) | `cost_d="0"`, `cost_e=3.0` y `cost_e=false`: código 2 |
| `test_well_formed_false_objective_is_still_an_audit_failure` | Objetivo 2 (entero falso): código 4, sin `difference` |
| `test_difference_uses_audited_objectives` | La comparación normal se conserva; objetivo auditado igual al registrado |
| `test_unknown_or_contradictory_states_are_invalid` (9 casos) | CP-SAT desconocido o ausente, greedy desconocido o ausente, greedy con `solver`, CP-SAT con `baseline`, precheck desconocido, estado con precheck vacío y `MODEL_INVALID`: código 2 |
| `test_incomplete_run_with_full_costs_is_invalid` | Prefijo con costos completos registrados: código 2 |
| `test_legitimate_no_solution_states_remain_not_comparable` | `INCOMPLETE` frente a `UNKNOWN` legítimo: código 3 |
| `test_compare_rejects_float_objective_via_cli` (`test_cli.py`) | `compare` por la CLI con `0.0`: código 2, informe `INVALID` sin `difference`, sin traceback |

### Evidencia tras las correcciones

| Comando | Dónde | Código | Resultado |
|---|---|---|---|
| `uv run python -m pytest` con los 10 archivos versionados | Carpeta | 0 | 361 aprobadas (337 anteriores y 24 nuevas) |
| `uv run ruff check src tests` y `format --check` | Carpeta | 0 | 23 archivos sin hallazgos |
| `uv sync --locked` (`UV_LINK_MODE=copy`) | Clon limpio de `5a46ac1` | 0 | Entorno desde el lock |
| `uv run python -m pytest -p no:cacheprovider` | Clon | 0 | 361 aprobadas, solo archivos versionados |
| `uv run ruff check src tests` y `format --check` | Clon | 0 | Sin hallazgos |
| `run` micro y demo con ambos métodos, más `compare` | Clon | 0 | Demo 21 frente a 17, diferencia 4 (19.05 %); micro 3 frente a 3, empate |

Comparaciones repetidas en la carpeta (`runs/hito4c-*`), con los mismos resultados del primer envío: micro empate (código 0) y demo con diferencia 4, con los argumentos en orden inverso (código 0).

Reproducciones de Codex por la CLI:

| Caso | Antes (`ab78715`) | Ahora (`5a46ac1`) |
|---|---|---|
| `objective=0.0` en greedy (`runs/hito4c-repro-objetivo`) | 0, COMPARED, «la heurística obtiene menor costo» | 2, INVALID: «costs.objective debe ser un entero no negativo; hay 0.0», sin `difference` |
| `status.solver="ESTADO_INEXISTENTE"` (`runs/hito4c-repro-estado`) | 3, NOT_COMPARABLE | 2, INVALID: «status.solver desconocido o ausente: 'ESTADO_INEXISTENTE'», sin `difference` |

Al preparar la primera reproducción con `ConvertTo-Json` de PowerShell, `0.0` se guardó como el entero `0`. Ese intento dio código 4 (`OBJECTIVE_MISMATCH`), que es lo correcto para un entero falso. La reproducción exacta con `0.0` se repitió escribiendo el JSON con Python.

## Rama y commits

- Rama `hito/4-heuristica`, creada desde `main` en `96fa513`, igual a `origin/main` al empezar.
- Código, pruebas y documentación en `ab78715`; primera entrega en `611e572`; correcciones en `5a46ac1`. Esta actualización de la entrega va en un commit posterior.
- El encargo se copió sin cambios a `docs/encargos/hito-4.md`.
- No había borradores locales con los nombres de los archivos nuevos, así que no hubo nada que respaldar. Se conservaron el stash, los respaldos anteriores, `demo_run.py` y `tests/test_optimization.py`.

## Archivos

- **Nuevos:** `src/academic_timetabling_demo/baseline.py` y `compare.py`; `tests/test_baseline.py` y `test_compare.py`; `docs/encargos/hito-4.md` y esta entrega.
- **Modificados:**
  - `runner.py`: rama voraz y procedencia.
  - `cli.py`: `run --solver greedy` y `compare`.
  - `tests/test_runner.py` y `tests/test_cli.py`.
  - `.gitignore`: solo las rutas del hito.
  - `README.md`, `docs/decisiones.md`, `especificacion.md` y `Guia_MVP_Timetabling_Codex.md`: las precisiones del encargo y el estado, sin cambiar restricciones ni costos.
- **Sin cambios:** `model.py`, `candidates.py`, `domain.py`, `validate.py`, `metrics.py`, `schema.sql`, el generador, los datos versionados y `uv.lock`. No se agregaron dependencias.

## Implementación

### Heurística (`baseline.py`)

- Lee las tablas `alternative` y `occupancy` de la misma corrida y usa los pesos efectivos. No importa OR-Tools ni `model.py`, no usa el testigo y no escribe en la base.
- **Núcleo puro (`choose`):**
  - Ordena las secciones una sola vez por cantidad inicial de alternativas y luego por `section_id`.
  - Ordena cada dominio por `(alpha*D + beta*E, pattern_id, room_id)`; `alt_id` nunca decide.
  - Elige la primera alternativa cuya ocupación no toca ninguna ya elegida.
  - Si no hay ninguna compatible, se detiene: guarda el prefijo, la sección bloqueada y las restantes.
- La aritmética es entera exacta. No hay cota, brecha ni afirmación de optimalidad.

### Corridas voraces (`run --solver greedy`)

- **Estados:** `status.baseline` vale `COMPLETE` o `INCOMPLETE` (`null` en CP-SAT), `status.solver` es `null` y `parameters.solver` identifica el método.
- **Completa:** pasa por la auditoría completa; si la aprueba, código 0. Los costos se publican y `solver_objective`, `best_bound` y `relative_gap` quedan `null`.
- **Incompleta:**
  - Termina con código 3, `result_valid=false` y `assignments.csv` con el prefijo, aunque esté vacío.
  - Los costos completos quedan `null`. El costo del prefijo va en `diagnostics.baseline.partial_costs`, con `comparable=false`.
  - El prefijo también se audita, con su propio costo como contraste. Si solo faltan las secciones restantes, se mantiene el código 3. Cualquier otro hallazgo, o una omisión distinta, da código 4.
- **Precheck vacío:** no se ejecuta ningún método. Código 3, `baseline` y `solver` en `null`, sin `assignments.csv`.
- **Lo que no cambia del Hito 3:** snapshot, hashes, salida no vacía rechazada e integridad final. Con un snapshot alterado da código 5 y conserva `COMPLETE`.
- **Tiempos:** `timings_seconds.baseline`, sin `build`, `solve` ni bloque `model`. `parameters.note` aclara que el límite, la semilla y los trabajadores de CP-SAT no afectan a la heurística.

### Procedencia (`metrics.provenance`)

- **Lectura:** `generation.json` se lee una vez, junto al snapshot, y se coteja con los mismos bytes copiados según su hash histórico normalizado a LF.
- **Estados:**
  - Con un manifiesto coherente queda `VERIFIED`, con `data_seed`, `case`, `format_version` y `manifest_sha256`.
  - Si no hay manifiesto: `ABSENT`. Si es ilegible o tiene la estructura mal: `INVALID`. Si no coincide con las fuentes: `MISMATCH`.
  - En esos tres casos, semilla, caso y versión quedan `null` y se explica el motivo.
- **Efecto:** la procedencia no impide resolver una entrada válida ni decide la comparabilidad. El manifiesto no entra en `input/` ni en el hash de entradas, y su testigo no llega a ningún método.

### Comparación (`compare`)

- **Independencia:** no importa `runner`, `model` ni `candidates`. Acepta las dos corridas en cualquier orden e identifica el método por `parameters.solver`.
- **Orden de validación:**
  1. Estructura e integridad de cada corrida, código 2. Se recalculan desde `input/` los hashes por archivo y el global y se cotejan con lo registrado. `input/` debe tener exactamente las 21 fuentes, `effective_config.json` debe coincidir con su hash y con la configuración registrada, y no puede haber un fallo de integridad registrado.
  2. Entre corridas, código 2: `run_id` distintos, un método de cada tipo, mismo hash global y mismos `alpha` y `beta`. No se exige el mismo hash de configuración efectiva.
  3. Solución completa, código 3 `NOT_COMPARABLE` si falta: la heurística debe estar `COMPLETE` y CP-SAT en `OPTIMAL` o `FEASIBLE`.
  4. Nueva auditoría, código 4: se vuelve a auditar `assignments.csv` contra el snapshot y la configuración efectiva, con el objetivo registrado como contraste, y se exigen `audit.json` válido y `result_valid=true`.
- **Corridas del Hito 3:** se aceptan aunque no tengan `status.baseline`, `status.integrity` ni `provenance`.
- **Salida:** `--out` debe ser un JSON nuevo, fuera de ambas corridas; si no, código 2 por stderr y sin escribir nada. Los informes `INVALID`, `NOT_COMPARABLE` y `AUDIT_FAILED` no incluyen diferencias. Un error interno da código 5 con un informe `ERROR`.
- **Diferencia:** `z_greedy - z_cpsat`, positiva a favor de CP-SAT. El porcentaje solo se calcula si `z_greedy > 0`; con base cero queda `null` y se explica. Los empates y las diferencias negativas se informan tal cual.

## Comandos y entorno

Versiones observadas: Python 3.12.16, OR-Tools 9.15.6755, SQLite 3.53.1, uv 0.13.7, Windows 11 x86_64.

| Comando | Dónde | Código | Resultado |
|---|---|---|---|
| `uv sync --locked` (`UV_LINK_MODE=copy`) | Clon limpio de `ab78715` | 0 | Entorno desde el lock |
| `uv run python -m academic_timetabling_demo --help`, `run --help`, `compare --help` | Clon | 0 | Ayuda de los tres |
| `uv run python -m pytest -p no:cacheprovider` | Clon (solo archivos versionados) | 0 | 337 aprobadas |
| `uv run ruff check src tests` y `format --check` | Clon | 0 | 23 archivos sin hallazgos |
| `uv run python -m pytest` con los 10 archivos versionados | Carpeta | 0 | 337 aprobadas |
| `uv run ruff check src tests` y `format --check` | Carpeta | 0 | Sin hallazgos |

En la carpeta se pasaron explícitamente los 10 archivos versionados, para no recoger el `test_optimization.py` local. pytest informa las mismas 2 `DeprecationWarning` del Hito 3, originadas en una dependencia.

## Pruebas

| Archivo | En `main` | En la rama |
|---|---|---|
| `test_cli.py` | 36 | 42 |
| `test_db.py` | 10 | 10 |
| `test_domain.py` | 66 | 66 |
| `test_synthetic.py` | 34 | 34 |
| `test_candidates.py` | 31 | 31 |
| `test_model.py` | 28 | 28 |
| `test_audit.py` | 33 | 33 |
| `test_runner.py` | 28 | 43 |
| `test_baseline.py` | — | 17 |
| `test_compare.py` | — | 57 |
| **Total** | **266** | **361** |

Pruebas anteriores ajustadas, sin perder cobertura de errores:

- `test_cli.py`: la prueba que rechazaba `compare` como comando futuro ahora rechaza un comando desconocido (`html`), y otra exige `--runs` en `compare`. La que rechazaba `greedy` ahora verifica una corrida voraz completa.
- `test_runner.py`: el rechazo de un solver desconocido usa `otro` en vez de `greedy`, y la igualdad de estados incluye `baseline: null`.

Cobertura respecto de la sección 5 del encargo:

- **Heurística:**
  - Orden estático y desempates por costo, patrón y sala.
  - Barajar filas y renumerar `alt_id` no cambia la elección.
  - Sala, docente y grupo en semanas coincidentes y disjuntas, cayendo en el segundo bloque de una sesión doble.
  - Costos exactos y los mismos candidatos y pesos que CP-SAT; con pesos alternativos cambia la decisión.
  - Caso completo auditado, sin importar el modelo, y sin invocar CP-SAT cuando el método es greedy.
  - Atasco con solución existente, confirmada por CP-SAT y por enumeración (22), con prefijo, sección bloqueada y código 3.
  - Prefijo vacío conservado; conflicto de la heurística con código 4, tanto completa como incompleta; precheck vacío sin ningún método; tablas sin cambios; integridad también en voraz.
- **Comparación:**
  - Válida en ambos órdenes; con una corrida sin los campos nuevos; con distinto límite y semilla.
  - Entradas distintas y pesos distintos se rechazan por separado.
  - `FEASIBLE` conservado; `INCOMPLETE`, `NO_CANDIDATES`, `INFEASIBLE` y `UNKNOWN` dan `NOT_COMPARABLE`; la corrupción prevalece sobre la incompletitud.
  - Asignaciones manipuladas, costo falso y `audit.json` fallido dan código 4.
  - Snapshot, hash global, configuración efectiva (archivo o registro), fuente extra en `input/` o integridad registrada dan código 2, aunque las banderas digan válido.
  - Diferencias de 10/7, 7/7, 7/10 y 0/0.
  - Mismo directorio, `run_id` duplicado, dos corridas del mismo método, método inesperado y `metrics.json` mal formado, ausente o carpeta se rechazan; también una salida existente (que queda intacta) o dentro de una corrida. El módulo no importa el solver.
- **Procedencia:** semilla de datos 7 con semilla de solver 3; manifiesto ausente, mal formado (tres variantes) y desactualizado; fuentes CRLF con manifiesto LF verificado, con los hashes de la corrida sobre bytes exactos; snapshot sin manifiesto.

## Corridas reales

En la carpeta de trabajo, con salidas en `runs/` (ignorado). Los tiempos son de una sola ejecución.

| Corrida | Código | Estado | Objetivo (D, E) | Cobertura | Procedencia | Tiempo del método |
|---|---|---|---|---|---|---|
| `hito4-micro-greedy` | 0 | COMPLETE, PASSED | 3 (0, 3) | 1.0 | VERIFIED, micro, semilla 42 | 0.0001 s |
| `hito4-micro-cpsat` | 0 | OPTIMAL, PASSED | 3 (0, 3), cota 3 | 1.0 | VERIFIED, micro, semilla 42 | 0.011 s |
| `hito4-demo-greedy` | 0 | COMPLETE, PASSED | 21 (0, 21) | 1.0 | VERIFIED, demo, semilla 42 | 0.004 s |
| `hito4-demo-cpsat` (`--time-limit 30 --seed 42`) | 0 | OPTIMAL, PASSED | 17 (0, 17), cota 17 | 1.0 | VERIFIED, demo, semilla 42 | 0.009 s |
| `hito4-demo-cpsat-s7` (`--time-limit 10 --seed 7`) | 0 | OPTIMAL, PASSED | 17 (0, 17) | 1.0 | VERIFIED, demo, semilla 42 | 0.009 s |
| `hito4-atasco-greedy` | 3 | INCOMPLETE, FAILED (solo `MISSING_ASSIGNMENT` de S2) | `null`; prefijo 1 (0, 1), no comparable | 0.5 | ABSENT | 0.0001 s |
| `hito4-atasco-cpsat` | 0 | OPTIMAL, PASSED | 22 (2, 2), cota 22 | 1.0 | ABSENT | 0.003 s |

- **Orden de la heurística en demo:** S05, S06, S10, S09, S02, S07, S08, S04, S03, S12, S11, S01.
- **Atasco:** la entrada se generó en `runs/hito4-entradas/atasco`. La heurística elige S1/P2/R1 y se bloquea en S2. CP-SAT resuelve con S1/P1/R1 y S2/P2/R1.
- **Semillas:** la de datos (42, verificada en el manifiesto) y la de solver (42 o 7) aparecen por separado en `provenance` y en `parameters.effective_config`.

### Comparaciones

| Comando | Código | Resultado |
|---|---|---|
| `compare --runs runs/hito4-demo-greedy runs/hito4-demo-cpsat --out runs/hito4-demo-comparison.json` | 0 | COMPARED: 21 frente a 17, diferencia 4, 19.05 %, «CP-SAT obtiene menor costo» |
| Igual con los argumentos invertidos | 0 | Mismo resultado |
| Demo greedy contra `hito4-demo-cpsat-s7` (otro límite y otra semilla) | 0 | COMPARED, diferencia 4; distinto hash de configuración efectiva, admitido |
| Demo greedy contra `runs/hito3c-demo` (CP-SAT del Hito 3, sin `provenance` ni `baseline`) | 0 | COMPARED, diferencia 4; informa que la revisión de Git difiere |
| `compare` micro | 0 | COMPARED: 3 frente a 3, empate, 0.0 % |
| `compare` del atasco | 3 | NOT_COMPARABLE: «greedy …: INCOMPLETE», sin diferencias |
| Micro greedy contra demo CP-SAT | 2 | INVALID: «las entradas difieren: el hash global de input/ no coincide» |

En todas las comparaciones válidas, la nueva auditoría de ambas corridas dio PASSED.

**Pesos distintos:** con la CLI no se puede producir una corrida legítima con `alpha` o `beta` efectivos distintos y la misma entrada, porque los pesos solo vienen de `config.json`, que forma parte del hash. Por eso la comparación con pesos distintos se probó con una corrida coherente cuya configuración efectiva cambia `alpha` (`test_different_effective_weights_are_rejected`): da código 2, con la razón separada de la de entradas distintas.

### Hashes

| Entrada | Hash global de `input/` |
|---|---|
| micro | `9db85f36798143e17d3f9a5d89bfef2205cd731751732dedeb45cfd83912f36b` |
| demo | `2fd989b234c13f9fbab50ba18ee18d9a782a0782b676b954c18745721e5d27c2` |
| atasco | `d9266de87802b1fc…` (en `metrics.json` de las corridas) |

Son los mismos de micro y demo que en el Hito 3, y el clon limpio reprodujo los mismos objetivos y la misma comparación.

## Limitaciones

- **Alcance de la comparación:** compara dos casos de una sola semilla de datos. No permite afirmar que un método sea superior en general. La diferencia de demo es una observación de este dataset.
- **Tiempos:** son de ejecuciones separadas y no son una medición controlada.
- **Trabajadores:** no se probó CP-SAT con más de uno.
- **Comparaciones `UNKNOWN` y `FEASIBLE`:** se obtuvieron con un stub o alterando la etiqueta guardada, como permite el encargo, no con un timeout real.
- **Coherencia de métricas:** tras las correcciones, `compare` rechaza etiquetas desconocidas o contradictorias y costos mal formados. Sigue sin detectar que alguien reescriba a mano un estado guardado coherente (por ejemplo, cambiar `OPTIMAL` por `FEASIBLE`), porque `metrics.json` no tiene hash propio. Sí detecta snapshot, configuración, asignaciones y costos alterados.
- **Sistema:** solo se probó en Windows.
- **Fuera de alcance:** HTML, `schedule.csv` y la presentación quedan para el Hito 5.
