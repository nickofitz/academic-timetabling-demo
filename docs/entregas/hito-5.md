# Entrega del Hito 5: exportaciones y demostración reproducible

Estado: aprobado técnicamente por Codex, con 416 pruebas versionadas y Ruff aprobados. Pendiente de autorización del autor para integrar y publicar. Se conserva abajo la evidencia de implementación y correcciones; el alcance visual y los límites de accesibilidad permanecen explícitos.

## Correcciones tras la revisión de Codex

Codex revisó `8378397` y pidió dos correcciones funcionales y una editorial. Están en `270ee1d`, sobre la misma rama. Solo se tocaron las rutas autorizadas: `.gitattributes`, `runner.py`, `tests/test_runner.py`, un test nuevo del conjunto (`tests/test_demo_set.py`, con su excepción en `.gitignore`), `docs/encargos/hito-5.md` y esta entrega. No cambiaron el modelo, los candidatos, la auditoría, la heurística, los costos ni las fuentes. `docs/demo/` no se regeneró: el formato de exportación no cambió y sus bytes ya eran los que se usaron para calcular los hashes.

### 1. Bytes de `docs/demo/` en los clones

- **Regla:** `.gitattributes` agrega `docs/demo/** -text`. Las reglas de `data/synthetic` siguen igual y no se renormalizó nada.
- **Comprobación:** `git check-attr` da `text: unset` para CSV, JSON, HTML, Markdown y PNG del conjunto, y `text: set, eol: lf` sigue en `data/synthetic`. `git ls-files --eol` muestra los 108 archivos de texto con `i/lf w/lf attr/-text` y el PNG como `-text`. La carpeta no aparece modificada.
- **Conteo:** en la primera entrega conté 104 archivos con CR porque solo miré CSV y JSON. Codex contó 108 porque también incluyó HTML y Markdown.

Clones nuevos de `270ee1d`:

| Comprobación | `core.autocrlf=true` | `core.autocrlf=false` |
|---|---|---|
| Archivos de texto de `docs/demo/` con CR | 0 | 0 |
| `uv sync --locked` (`UV_LINK_MODE=copy`) | 0 | 0 |
| `uv run python -m pytest -p no:cacheprovider` | 0, 416 aprobadas | 0, 416 aprobadas |
| `uv run ruff check src tests scripts` y `format --check` | 0 | 0 |
| `audit` de `cpsat` (17), `greedy` (21) y `changed/changed-run` (17), con `--config` y `--reported-objective` | 0, 0 y 0 | 0, 0 y 0 |
| `compare --runs docs/demo/greedy docs/demo/cpsat` | 0, diferencia 4 | 0, diferencia 4 |
| `compare` de la heurística frente a `changed/changed-run` | 2, entradas distintas | 2, entradas distintas |
| `run` CP-SAT y greedy, `compare` y `scripts/demo_change.py` regenerados en `runs/` | 0 en los cuatro | 0 en los cuatro |

`tests/test_demo_set.py` comprueba en cada clon los atributos, los hashes de `input/`, el hash global, `effective_config.json` y los dos archivos exportados de las tres corridas, además de las dos comparaciones. **Clon anterior:** uno de `2fc6e40`, previo a la regla, sigue fallando con `compare` en código 2. La regla solo protege a los clones posteriores.

### 2. Coherencia de toda la evidencia exportada

- **Antes:** la verificación final solo comprobaba `input/`. Si `assignments.csv` cambiaba durante el render, la corrida terminaba con código 0 y archivos finales que ya no correspondían a las asignaciones guardadas.
- **Ahora, al empezar:** `_export` captura los hashes de `assignments.csv` y `effective_config.json` antes de revalidar.
- **Ahora, después de leer las asignaciones:** vuelve a comprobar esos hashes.
- **Ahora, antes de publicar:** comprueba el snapshot, esos dos hashes, que `assignments.csv` contenga exactamente los triples exportados y que `effective_config.json` sea la configuración usada para presentar.
- **Ante una discrepancia:** código 5, `export=FAILED`, `deliverable=false`, un mensaje que nombra el archivo y el momento, y ningún `schedule.csv` ni `schedule.html` final ni temporal. La evidencia alterada se conserva para diagnóstico. `result_valid` sigue en `true` como hecho histórico de la auditoría que ocurrió; `deliverable` indica la incoherencia del paquete. No se vuelve a llamar al solver.

Regresiones nuevas en `tests/test_runner.py`. Las cuatro fallan con el runner anterior y pasan ahora:

| Prueba | Qué comprueba |
|---|---|
| `test_assignments_changed_during_render_block_export` (2 casos) | El render real seguido de la escritura de los triples de la revisión (inválidos), o de otro horario válido (S1 en P1): código 5, export `FAILED`, sin archivos finales, `assignments.csv` alterado conservado |
| `test_effective_config_changed_during_render_blocks_export` | `alpha` cambiado en `effective_config.json` durante el render: código 5 |
| `test_assignments_changed_before_validation_reading_is_detected` | Cambio entre la captura y la lectura de las asignaciones: código 5 |

Se mantienen las regresiones anteriores: corrida normal, snapshot alterado durante la presentación, fallo entre ambos archivos y asignaciones manipuladas antes de exportar.

### 3. Redacción neutra

Se reemplazó en `docs/encargos/hito-5.md` la enumeración de documentos personales por «No editar material local ajeno al alcance». La observación correspondiente de esta entrega se reescribió sin repetir los términos originales. No se reescribieron ni borraron commits ni ramas; las versiones anteriores siguen en la historia local de la rama, y Codex preparará la historia publicable al integrar.

### Pruebas tras las correcciones

| Comando | Dónde | Código | Resultado |
|---|---|---|---|
| `uv run python -m pytest` con los 13 archivos versionados | Carpeta | 0 | 416 aprobadas: 406 anteriores, 4 de exportación y 6 del conjunto |
| `uv run ruff check src tests scripts` y `format --check` | Carpeta | 0 | 28 archivos sin hallazgos |
| Clones de `270ee1d` | Ver la tabla anterior | 0 | 416 aprobadas en ambos |

## Rama y commits

- Rama `hito/5-presentacion`, creada desde `main` en `6c4b0a7`, igual a `origin/main` al empezar.
- `5f73a76`: exportaciones, grilla HTML, script de cambio, pruebas y documentación.
- `25fae94`: corrección de tipos en los parámetros del cambio de disponibilidad (ver más abajo).
- `2fc6e40`: conjunto `docs/demo/`, generado desde `25fae94` con el árbol limpio.
- `8378397`: primera entrega.
- `270ee1d`: correcciones de la revisión de Codex. Esta actualización de la entrega va en un commit posterior.
- No había borradores locales coincidentes. Se conservaron el stash, los respaldos y los archivos ignorados.

## Archivos

- **Nuevos:**
  - Paquete: `src/academic_timetabling_demo/report.py` y `src/academic_timetabling_demo/templates/schedule.html`.
  - `scripts/demo_change.py`.
  - Pruebas: `tests/test_report.py` y `tests/test_demo_change.py`.
  - Documentación: `docs/encargos/hito-5.md`, `docs/demo/` y esta entrega.
- **Modificados:**
  - `runner.py`: exportación tras la integridad.
  - `cli.py`: solo la ayuda de `run`.
  - `tests/test_runner.py` y `tests/test_cli.py`.
  - `.gitignore`: solo las rutas del hito.
  - `README.md`, `especificacion.md`, `Guia_MVP_Timetabling_Codex.md` y `docs/decisiones.md`.
- **Sin cambios:** `compare.py` (se reutilizan sus funciones públicas tal cual), `metrics.py`, `model.py`, `baseline.py`, `validate.py`, `candidates.py`, `domain.py`, `schema.sql`, el generador, los datasets, `pyproject.toml` y `uv.lock`. No se agregaron dependencias.
- **Empaquetado:** `uv build --wheel` incluye `report.py` y `templates/schedule.html`, así que la vista también funciona como paquete instalado.

## Implementación

### Integración con `run`

1. Tras la comprobación final de integridad, `run` escribe los tres JSON con `status.export=PENDING`.
2. Revalida su propia carpeta con las funciones públicas de `compare`: `load_run` (hashes del snapshot y configuración efectiva), `validate_status`, `validate_costs` (costos enteros) y `recheck` (nueva auditoría contra el snapshot, con el objetivo registrado como contraste).
3. Genera ambos archivos desde `input/`, `effective_config.json` y `assignments.csv` en temporales `.schedule.*.tmp`.
4. Vuelve a verificar los hashes del snapshot y que los bytes escritos sean los generados.
5. Solo entonces publica los dos nombres finales.

Resultados:

- **Éxito:** `status.export=WRITTEN`, `status.deliverable=true` y `metrics.export` con los SHA-256 de ambos archivos y el número de sesiones. `timings_seconds.export` se mide aparte, y `total` se vuelve a medir para incluir la exportación.
- **Fallo:** cualquier error de revalidación, renderizado, escritura, verificación o publicación da código 5, `status.export=FAILED`, `deliverable=false` y un mensaje de que la corrida «no está lista para entregar». Se borran solo los temporales y los finales creados en ese intento, y se conservan `assignments.csv` y los JSON. Los estados del método y de la auditoría no se reescriben.
- **Sin solución válida:** `NO_CANDIDATES`, `INFEASIBLE`, `UNKNOWN`, `MODEL_INVALID`, heurística `INCOMPLETE`, auditoría fallida o integridad `FAILED`/`NOT_VERIFIED` dejan `status.export=NOT_APPLICABLE` y no generan ningún archivo de exportación.
- **Hash del HTML:** el HTML lleva solo una proyección de la corrida (identificador, fecha, método, estados, costos, pesos, tiempo del método y semilla verificada), sin su propio hash ni una copia de `metrics.json`.

### `schedule.csv`

- Formato UTF-8 con LF, en el orden de columnas del encargo. Hay una fila por sesión y semana activa; una sesión doble es una sola fila de duración 2.
- `group_ids` es un array JSON ordenado dentro de una celda, sin duplicar filas por grupo. `start_time` es el inicio del primer bloque y `end_time` el fin del último.
- El orden es numérico por semana, día y bloque, y luego por sala, sección y sesión.
- La reconstrucción es propia de `report.py`; el auditor no la importa.

### `schedule.html`

- **Archivo único:** sin CDN, fuentes remotas, `fetch`, XHR ni `import`, con una CSP `default-src 'none'`. Los textos pasan por el autoescape de Jinja2. Los datos van en un bloque JSON con `<`, `>`, `&`, U+2028 y U+2029 escapados, y el JavaScript solo usa `createElement` y `textContent`, sin `innerHTML`, eventos en línea ni `eval`.
- **Indicadores:** encabezado y etiqueta «Datos sintéticos»; identificador de la corrida, fecha UTC, método, estado con una etiqueta precisa, secciones asignadas, auditoría, integridad, costo α·D + β·E, tiempo del método (CP-SAT o heurística, no el total) y semilla de datos solo si la procedencia es `VERIFIED`. FEASIBLE y COMPLETE nunca se presentan como óptimos.
- **Filtros:** una semana a la vez, la primera al inicio, más sala, docente y grupo con la opción «Todos», combinados por intersección. El grupo filtra por membresía.
- **Vista:** una grilla de días por bloques para cada sala con sesiones visibles, donde las sesiones de varios bloques usan `rowspan`. La acompaña una tabla accesible con las mismas filas. El contador de sesiones visibles se actualiza; los indicadores globales no.
- **Estado vacío:** explica que no hay sesiones y ofrece un botón para restablecer.
- **Diseño:** tipografía del sistema, colores con leyenda (azul para un bloque, verde para dos o más), etiquetas asociadas a los controles y foco visible. En pantallas estrechas, la grilla se desplaza dentro de su contenedor.

### `scripts/demo_change.py`

- **Validación:** revalida la base con las mismas funciones de `compare` y exige CP-SAT `OPTIMAL` o `FEASIBLE` con nueva auditoría positiva. Rechaza salidas no vacías o dentro de la base, sin modificarlas.
- **Cambio:** copia las 21 fuentes del snapshot a `changed-input/` y elige primera sección asignada, primera semana activa, primera sesión (día, bloque, `session_id`) y su primer bloque. Quita esa única línea de `teacher_available.csv` sin tocar el resto de bytes; si la fila no existe exactamente una vez, informa una inconsistencia.
- **Parámetros:** solo `time_limit_seconds` y `random_seed` pueden diferir de `config.json`, y se reproducen con los overrides de `run`. Cualquier otra diferencia se rechaza con código 2.
- **Nueva corrida:** resuelve en `changed-run/` y escribe `change.json` con base, cambio exacto, parámetros, nueva corrida y recuento de reasignaciones por sección. Si no hay solución completa, el recuento queda `null`.
- **Códigos:** devuelve el de la nueva corrida, 2 para una base o salida inválida y 5 para errores internos. Los errores esperables se muestran sin traceback.

**Corrección durante el hito (`25fae94`):** la primera versión comparaba los parámetros solo por valor. Con una base de `--time-limit 30` (guardado como `30.0`) y un `config.json` con `30`, no pasaba el override y la nueva configuración efectiva quedaba con otros bytes y otro hash, aunque los valores fueran iguales. Ahora también compara el tipo. La regresión `test_numerically_equal_override_keeps_identical_effective_config` falla con el script anterior y pasa con la corrección. `docs/demo/` se regeneró completo desde ese commit.

## Comandos y entorno

Versiones observadas: Python 3.12.16, OR-Tools 9.15.6755, SQLite 3.53.1, uv 0.13.7, Microsoft Edge 157.0.4341.60, Windows 11 x86_64.

| Comando | Dónde | Código | Resultado |
|---|---|---|---|
| `uv run python -m pytest` con los 12 archivos versionados | Carpeta | 0 | 405 aprobadas en `5f73a76`; los 15 de `test_demo_change.py` también tras `25fae94` |
| `uv run ruff check src tests scripts` y `format --check` | Carpeta | 0 | 27 archivos sin hallazgos |
| `uv sync --locked` (`UV_LINK_MODE=copy`) | Clon limpio de `2fc6e40` | 0 | Entorno desde el lock |
| `uv run python -m pytest -p no:cacheprovider` | Clon (sin borradores ignorados) | 0 | 406 aprobadas |
| `uv run ruff check src tests scripts` y `format --check` | Clon | 0 | Sin hallazgos |
| `run` CP-SAT y greedy en demo, `compare` y `scripts/demo_change.py` | Clon | 0 | 17 y 21, diferencia 4; cambio con 7, 4, 0 y 1 |
| `uv build --wheel` | Carpeta | 0 | El wheel incluye `report.py` y `templates/schedule.html` |

## Pruebas

| Archivo | En `main` | En la rama |
|---|---|---|
| `test_cli.py` | 42 | 44 |
| `test_db.py` | 10 | 10 |
| `test_domain.py` | 66 | 66 |
| `test_synthetic.py` | 34 | 34 |
| `test_candidates.py` | 31 | 31 |
| `test_model.py` | 28 | 28 |
| `test_audit.py` | 33 | 33 |
| `test_runner.py` | 43 | 62 |
| `test_baseline.py` | 17 | 17 |
| `test_compare.py` | 57 | 57 |
| `test_report.py` | — | 13 |
| `test_demo_change.py` | — | 15 |
| `test_demo_set.py` | — | 6 |
| **Total** | **361** | **416** |

La única prueba anterior ajustada es la de `test_runner.py` sobre la corrida micro: su lista exacta de archivos y su diccionario de estados ahora incluyen los dos archivos nuevos y los campos `export` y `deliverable`.

Cobertura nueva:

- **`schedule.csv`:**
  - Micro calculado a mano: 6 filas, la sesión doble como una fila de 2 bloques y las dos sesiones de S3.
  - Coordenadas de la demo contra un oráculo independiente que no usa el exportador.
  - Membresía múltiple sin duplicar filas, orden numérico, UTF-8 con LF e ida y vuelta con nombres especiales (comillas, `<b>`, `&` y saltos de línea).
- **HTML:**
  - Sin recursos de red ni `innerHTML`, `eval` o `onclick`; indicadores reales.
  - FEASIBLE y COMPLETE nunca se rotulan como óptimos, y la semilla no verificada no se muestra.
  - Nombres hostiles: exactamente 2 bloques `<script>`, ningún `<img>` y JSON recuperable.
  - Escape de `</script>`, `&` y U+2028.
- **Puertas de exportación:**
  - Exportaciones coherentes en micro (ambos métodos) y en demo con heurística: hashes de bytes, `run_id` y conjunto de secciones.
  - Sin exportación para precheck vacío, infactible, `UNKNOWN`, `MODEL_INVALID`, heurística incompleta, auditoría fallida o snapshot alterado.
  - Fallo de renderizado, fallo entre ambos archivos (el primero se elimina), snapshot cambiado durante la presentación y asignaciones manipuladas antes de exportar: todos dan código 5 sin archivos finales ni temporales, con `OPTIMAL` y `PASSED` conservados.
  - La exportación lee el snapshot aunque cambie la fuente original.
- **Cambio de disponibilidad:**
  - Micro calculado a mano: retira `T1,1,1,2` y S1 pasa de P2 a P1, con objetivo 23 y recuento 2, 1, 0 y 0.
  - La base queda intacta byte por byte. La nueva corrida tiene la misma configuración efectiva, otro `run_id`, otro hash de entrada y procedencia no verificada.
  - Se conservan los overrides de la base, con y sin cambio de tipo.
  - Camino sin solución (`NO_CANDIDATES`, recuento `null`).
  - Rechazos de salida existente, salida dentro de la base (tres variantes), base greedy, base sin solución, base manipulada y parámetros no representables; CLI sin traceback.
  - Funciones de recuento y de retiro de fila.
- **Regresiones anteriores:** siguen las del Hito 4 de `compare` (objetivo flotante, estados desconocidos) y las del Hito 3 de integridad y lectura.

## Verificación en navegador

Se usaron dos navegadores, con alcances distintos:

1. **Panel de navegador de la app de Claude.** Carga los archivos locales como `data:` y no como `file://`.
   - **Filtros:** con la demo CP-SAT copiada sola en una carpeta aislada, los filtros combinados de grupo G01, docente T04 y sala R06 dieron 7, 2 y 0 sesiones. Coinciden con un cálculo independiente sobre el JSON incrustado.
   - **Membresía múltiple:** S04 (grupos G01 y G04) aparece al filtrar por G01.
   - **Estado vacío y restablecimiento:** el estado vacío muestra su botón, que restablece a la semana 1 con «Todos».
   - **Semanas y simultaneidad:** el cambio a la semana 3 muestra 8 sesiones dobles con `rowspan=2` y una simultaneidad (martes, bloque 5) en R05 y R06, cada una en su grilla.
   - **Ancho estrecho (375 px):** la página no se desborda, la grilla se desplaza dentro de su contenedor y no hay etiquetas cortadas.
   - **Teclado:** Tab enfoca el control con su etiqueta y un contorno de 2,4 px.
   - **Nombres hostiles:** con `</script>`, `<img onerror>`, `<svg onload>`, comillas y `&` en secciones, salas, docentes y grupos, `window.__pwned` no existe, solo están los 2 scripts de la plantilla, no se crea ningún `img`, `svg`, `b` ni `i`, los textos se ven literales en tarjetas, opciones, tabla y título, y el filtro por grupo sigue funcionando.
   - **Red y consola:** no se registró ninguna petición de red ni errores de consola, también en la grilla final de `docs/demo/cpsat`.
2. **Microsoft Edge 157 sin interfaz, por `file://` real.**
   - Con el HTML copiado solo, en la carpeta de trabajo y en el clon limpio, el DOM final tiene el contador poblado («18 sesiones visibles de 70…») y la grilla construida. El de nombres hostiles no tiene `img` ni `svg` inyectados.
   - `docs/demo/preview.png` es una captura real de `docs/demo/cpsat/schedule.html` a 1280 × 1400 px, sin metadatos de texto en el PNG.

**No verificado:**

- Una revisión visual humana en Chrome o Firefox con interfaz.
- La navegación completa solo con teclado y un lector de pantalla.
- La impresión.
- En el panel, el origen fue `data:` y no `file://`; el comportamiento con `file://` se comprobó solo con Edge sin interfaz.

**Revisión de Codex:** inspeccionó la captura `preview.png` y la consideró legible, pero su navegador bloquea `file://` y no pudo repetir los filtros, el teclado, el ancho estrecho ni las pruebas con nombres hostiles. Esas comprobaciones interactivas siguen siendo solo de Claude. No hay una prueba humana interactiva ni una certificación de accesibilidad con lector de pantalla.

## Conjunto `docs/demo/`

Generado con rutas relativas desde `25fae94`, con el árbol limpio: todas las corridas registran `git.dirty=false`. No contiene rutas personales. Son 110 archivos, unos 800 KB.

| Elemento | Identificador | Resultado |
|---|---|---|
| `cpsat/` | `20261117T023351Z-f8af3ea1` | Código 0, OPTIMAL, 17 (D=0, E=17), cota 17, auditoría PASSED, integridad VERIFIED, export WRITTEN (70 sesiones), procedencia VERIFIED (semilla 42) |
| `greedy/` | `20261117T023353Z-633a5e33` | Código 0, COMPLETE, 21 (D=0, E=21), PASSED, VERIFIED, WRITTEN (70 sesiones) |
| `comparison.json` | — | COMPARED, diferencia 4, 19.05 %, «CP-SAT obtiene menor costo»; ambas nuevas auditorías PASSED |
| `changed/change.json` | base `…f8af3ea1`, nueva `20261117T023355Z-f38c38d9` | Retirado `T01,1,2,7` (S01, semana 1, día 2, bloque 7). Nueva corrida OPTIMAL, 17, PASSED, export WRITTEN, procedencia ABSENT, configuración efectiva igual a la base (`26a3b784…`). Reasignaciones: 7 sin cambio, 4 de patrón (S04, S07, S09, S10), 0 de sala, 1 de ambos (S01: P2X1-D24-B7/R04 → P2X1-D13-B7/R02) |
| `preview.png` | — | Captura real de `cpsat/schedule.html` |

- **Hashes de entrada:** demo `2fd989b234c13f9fbab50ba18ee18d9a782a0782b676b954c18745721e5d27c2`; entrada modificada `70cc13f51fae64dc4542e8e27a94f0d509a6efedfe156d17540f3373c744c258`.
- **Revalidación de las copias:** `audit` con `--config` y `--reported-objective` dio código 0 en `cpsat` (17), `greedy` (21) y `changed/changed-run` (17). `compare` sobre `docs/demo/greedy` y `docs/demo/cpsat` dio código 0. `compare` entre la heurística y la corrida modificada dio código 2 («las entradas difieren»), como corresponde.
- **Tiempos observados:** CP-SAT resolvió en 0.011 s; la heurística en 0.003 s; la exportación tomó entre 0.05 y 0.06 s; el total de cada corrida, entre 0.32 y 0.42 s.

## Decisiones y observaciones para Codex

1. **`.gitattributes` para `docs/demo/` (resuelto en `270ee1d`, ver «Correcciones»).** Los hashes de las corridas son de bytes exactos. Al clonar `2fc6e40` con `core.autocrlf=true` (lo habitual en Windows), 104 CSV y JSON de `docs/demo/` llegan con CRLF. `audit` sigue pasando, pero `compare docs/demo/greedy docs/demo/cpsat` termina con código 2. Con los bytes conservados (`core.autocrlf=false`) da código 0. `.gitattributes` no está entre las rutas permitidas de este encargo, así que no se modificó. Se propone `docs/demo/** -text` (o `text eol=lf` para CSV, JSON, HTML y MD, y `binary` para el PNG), sin renormalizar nada más.
2. **Redacción del encargo publicado (resuelto en `270ee1d`):** la copia del encargo enumeraba tipos de documentos personales ajenos al proyecto. Se reemplazó por una prohibición neutra de editar material local ajeno al alcance.
3. **Esquema de `metrics.json`:** se agregaron `status.export` (`PENDING`, `WRITTEN`, `FAILED`, `NOT_APPLICABLE`), `status.deliverable` y el bloque `export`. Una corrida con exportación fallida mantiene `result_valid=true` (la solución y su auditoría siguen siendo válidas), pero termina con código 5 y `deliverable=false`. `compare` no exige campos de exportación, así que podría comparar esa corrida; si Codex prefiere bloquearlo, el cambio es pequeño.
4. **Salas visibles:** la grilla muestra solo las salas con sesiones visibles en la semana elegida, salvo que se filtre una sala concreta.
5. **Recuento de reasignaciones:** CP-SAT no minimiza cambios. En la demo cambiaron 5 secciones, aunque solo S01 usaba el bloque retirado; el informe lo dice explícitamente.

## Limitaciones

- La revisión visual humana y la accesibilidad completa siguen pendientes, como se describe arriba.
- Los clones hechos antes de `270ee1d` con conversión CRLF siguen sin poder comparar `docs/demo/`; los posteriores sí.
- Un solo dataset sintético pequeño, solo en Windows y con un trabajador de CP-SAT. Los tiempos son de una ejecución.
- No hay despliegue web, GitHub Pages, backend, edición en el navegador ni reoptimización desde la vista, como pide el encargo.
