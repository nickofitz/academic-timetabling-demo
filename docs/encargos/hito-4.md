# Encargo para Claude: Hito 4, heurística voraz y comparación

Preparado por Codex el 16 de noviembre de 2026. Base aprobada y publicada: main en 96fa513. Este encargo resuelve los seis puntos planteados después del Hito 3 y autoriza implementación en una rama, sin integración ni push.

## 1. Inicio, alcance y rutas

Leer AGENTS.md, especificacion.md, la guía, decisiones y colaboración. Confirmar que Codex dejó de editar. Verificar main limpio y actualizado y crear `hito/4-heuristica`. Preservar stash, respaldos y archivos ignorados; demo_run.py y test_optimization.py no forman parte de la entrega por estar en disco.

Copiar este encargo a `docs/encargos/hito-4.md`, ruta expresamente permitida, y añadir su excepción específica en .gitignore. Antes de alterar borradores locales que coincidan con archivos nuevos del hito, respaldarlos con hashes.

Rutas permitidas dentro de src/academic_timetabling_demo/: baseline.py, compare.py, runner.py, metrics.py y cli.py. validate.py solo si hace falta extraer una interfaz pública para reutilizar la auditoría completa, sin cambiar sus reglas ni introducir dependencia de candidatos/solver. Pruebas: tests/test_baseline.py, tests/test_compare.py y ajustes/extensiones de tests/test_runner.py y tests/test_cli.py. Documentación: .gitignore, README.md, docs/decisiones.md, docs/encargos/hito-4.md, docs/entregas/hito-4.md; especificacion.md y guía para incorporar las precisiones aquí fijadas y actualizar estado, sin cambiar restricciones/costos.

No modificar model.py, candidates.py, domain.py, schema.sql, generador, datos versionados ni lockfile para fabricar una comparación. Si aparece una necesidad real fuera de estas rutas, informarla a Codex antes. No añadir dependencias. La configuración de CP-SAT y su límite numérico se mantienen; las reglas de la heurística no heredan límites exclusivos de un solver que no ejecuta.

Fuera del Hito 4: HTML, schedule.csv expandido, edición visual, nuevos solvers, reoptimización con cambios mínimos, benchmarks masivos y promesas de ahorro. Las corridas se guardan bajo runs/ ignorado. Las extensiones son compatibles con generate/run/audit del Hito 3.

## 2. Heurística: decisiones cerradas

Reutilizar las mismas tablas alternative y occupancy ya construidas por SQL para esa corrida y los mismos pesos efectivos. baseline.py no importa OR-Tools ni model.py. No construir otra definición de reglas ni consultar el testigo del generador.

1. Ordenar una vez las secciones por cantidad inicial de alternativas, ascendente, luego section_id lexicográfico. No recalcular el orden dinámicamente.
2. Para cada sección, ordenar sus alternativas por `(alpha*cost_d+beta*cost_e, pattern_id, room_id)`, en orden ascendente. alt_id no decide empates.
3. Elegir la primera alternativa cuya ocupación no intersecte los recursos ya ocupados; considerar sala, docente y todos los grupos por semana/día/bloque.
4. Agregar sus ocupaciones al conjunto ocupado. No hacer backtracking, movimientos, relajaciones ni rescates con CP-SAT.
5. Si ninguna alternativa es compatible, detenerse en esa primera sección. Conservar el prefijo elegido y registrar sección bloqueada y secciones restantes. No continuar saltando la sección fallida ni declarar infactibilidad global.

El mismo dataset y pesos producen los mismos triples elegidos, aunque cambie el orden físico de las filas o los alt_id. La heurística no modifica tablas fuente ni derivadas. Usar aritmética entera exacta para costos; no anunciar optimalidad, mejor cota ni brecha de solver.

### Estado y resultados de la heurística

Agregar `status.baseline` al formato de métricas: COMPLETE o INCOMPLETE para greedy, null para cp-sat. Mantener `parameters.solver` como discriminador del método. En greedy, `status.solver=null`: no usar los estados OPTIMAL/FEASIBLE/INFEASIBLE de CP-SAT para describirlo.

- Dominio vacío detectado por precheck: no ejecutar ninguno de los algoritmos. baseline=null y solver=null; código 3, sin assignments.csv, como Hito 3.
- Greedy completo: auditar todas las asignaciones con validate.audit. Si pasa, código 0, baseline COMPLETE, auditoría PASSED, result_valid=true; publicar costos completos y cobertura. solver_objective, best_bound y relative_gap son null.
- Greedy incompleto: baseline INCOMPLETE, código 3, result_valid=false, conservar assignments.csv parcial aunque el prefijo sea vacío. Nunca compararlo como solución completa.
- Auditar también el prefijo con el auditor completo existente. Los hallazgos MISSING_ASSIGNMENT explican su incompletitud: audit.json sigue indicando FAILED/audit_valid=false, sin fingir aprobación de una solución completa. Si solo hay omisiones esperadas, conservar código 3. Si hay choque, regla dura, objetivo falso u otro hallazgo además de esas omisiones, usar código 4 como fallo de validez.
- En INCOMPLETE, costs del horario completo permanecen null conforme a la especificación. El costo del prefijo se guarda por separado en diagnostics.baseline.partial_costs, claramente no comparable. Al auditar el prefijo puede suministrarse ese costo para detectar errores, sin publicarlo como costo de solución completa.
- Los fallos de integridad conservan la prioridad del Hito 3: código 5/result_valid=false, sin reescribir el estado matemático/algorítmico real. Mismos snapshots, hashes y reglas de salida no vacía.

Registrar tiempo baseline con clave propia en timings_seconds; no inventar tiempo de solver, variables CP-SAT, cota o prueba de optimalidad. La configuración efectiva mantiene todos sus campos para trazabilidad, pero documentar que semilla/tiempo/trabajadores de CP-SAT no afectan al voraz. --seed de run sigue siendo semilla de solver, nunca semilla de datos ni aleatoriedad nueva de greedy.

## 3. Comandos y comparación

Confirmar el contrato de la guía:

```bash
uv run python -m academic_timetabling_demo run --input data/synthetic/demo --solver greedy --out runs/demo-greedy
uv run python -m academic_timetabling_demo run --input data/synthetic/demo --solver cp-sat --time-limit 30 --seed 42 --out runs/demo-cpsat
uv run python -m academic_timetabling_demo compare --runs runs/demo-greedy runs/demo-cpsat --out runs/comparison.json
```

compare recibe exactamente dos directorios de corrida distintos: uno greedy y otro cp-sat. Aceptar cualquier orden de argumentos, identificando métodos por metadatos, sin inferirlos del nombre del directorio. Rechazar el mismo directorio/run_id duplicado y métodos inesperados. No modifica corridas ni vuelve a optimizar.

### Elegibilidad y compatibilidad

- Requiere entradas iguales byte por byte según el hash global del Hito 3, incluidos sus config.json originales, y los mismos pesos alpha/beta de la configuración efectiva. Volver a calcular hashes por fuente y global desde cada snapshot y cotejar los guardados; no confiar solo en que dos cadenas en metrics.json sean iguales.
- Verificar también el hash de effective_config.json de CADA corrida contra su propio registro y cotejar ese archivo con la configuración efectiva registrada. Comparar entre métodos solo alpha/beta: NO exigir igualdad entre los dos hashes de configuración efectiva. Diferentes límites de tiempo, semillas o trabajadores son admisibles y deben mostrarse en el informe.
- Si los config.json ORIGINALES difieren, cambia el hash global y se rechaza la comparación: usar el mismo input y overrides CLI para variar parámetros del solver. No introducir un segundo concepto de igualdad de entradas que ignore campos del hash del Hito 3.
- Requiere snapshots completos, sin fallo de integridad, estados de solución completa (COMPLETE frente a OPTIMAL/FEASIBLE), result_valid=true y auditorías positivas. Volver a auditar assignments.csv contra el snapshot y configuración de cada corrida, contrastando costo registrado. Detectar modificaciones posteriores a la ejecución, omisiones, duplicados y costos alterados. No importar candidatos ni resolver para comparar.
- Conservar compatibilidad de lectura con corridas CP-SAT del Hito 3: status.baseline o provenance ausentes no bastan para rechazarlas. Sí deben satisfacer la evidencia mínima de integridad, configuración, asignaciones y costos.
- Diferencias de hardware, revisión Git o versión del solver no invalidan por sí mismas una comparación de calidad, pero se informan. Los tiempos son observaciones; no atribuirles una comparación controlada si las condiciones difieren.

### Salida y códigos de compare

--out nombra un JSON NUEVO: rechazar si ya existe o si apunta dentro de cualquiera de las corridas de entrada, sin sobrescribir evidencia. No crear HTML ni tablas ficticias. Errores de lectura deben tener mensajes útiles sin traceback; no ocultar errores internos como si fueran datos inválidos.

- 0: comparación válida de dos soluciones completas y auditadas.
- 2: argumentos/archivos inválidos, metadatos incoherentes, hashes/entradas o pesos distintos, salida existente, snapshot/config alterados o tipos de corrida incorrectos.
- 3: comparación no aplicable porque una ejecución legítima es incompleta o no tiene solución (INCOMPLETE, NO_CANDIDATES, INFEASIBLE, UNKNOWN). Escribir informe NOT_COMPARABLE con razones y sin diferencias/mejoras de costos. Distinguir esto de corrupción de archivos.
- 4: auditoría almacenada o recalculada fallida en una solución que se presenta como completa. Para greedy legítimamente incompleto, prevalece el diagnóstico del punto anterior por falta de solución completa, no sus omisiones esperadas.
- 5: fallo interno/entorno.

No generar un resultado numérico parcial cuando falla la compatibilidad o validez. Si es posible crear salida válida, registrar un JSON con estado/reason y los identificadores leídos; si --out no es utilizable, informar por stderr sin modificarlo. Si concurren datos corruptos y corrida incompleta, validar primero estructura e integridad; no presentar corrupción como mero INCOMPLETE.

En una comparación válida incluir identificadores/métodos/estados, hash común, pesos, cobertura, costo y componentes D/E de ambos métodos, tiempos y condiciones del entorno. Definir diferencia absoluta `z_greedy - z_cpsat`; positiva favorece CP-SAT y negativa favorece greedy. Porcentaje `100*(z_greedy-z_cpsat)/z_greedy` solo cuando z_greedy>0. Con base cero, porcentaje null, conservar diferencia absoluta y explicación. Informar empates y mejoras negativas sin cambiarlos a cero. FEASIBLE no equivale a óptimo.

## 4. Procedencia de datos y semillas

Agregar `provenance` en metrics.json, separado de la configuración del algoritmo, al crear nuevas corridas de ambos métodos. Contendrá `data_seed`, `case`, `format_version` y estado de procedencia. Semilla desconocida se registra null: no deducirla de solver.random_seed, del nombre de carpeta ni del valor inicial 42.

Si existe generation.json, leerlo solo como metadato opcional: validar estructura de caso/semilla/versión y que su mapa sources coincida con las fuentes del snapshot siguiendo su política histórica de normalización LF. Solo entonces registrar la semilla/caso como procedencia verificada. Registrar el hash del manifiesto leído para identificar la declaración. No pasar su witness a baseline, CP-SAT o auditor; no copiarlo a input/ ni incluirlo en el hash de entradas de las corridas.

Si el manifiesto falta, está mal formado o no coincide con un dataset modificado, la entrada puede seguir siendo válida. Marcar procedencia ABSENT, INVALID o MISMATCH con explicación y data_seed/case null; no atribuir al dataset alterado la semilla declarada. Solo un manifiesto coherente permite estado VERIFIED. Leer los metadatos una vez y registrar la decisión; no volver a leerlos después de resolver como si hubieran sido los originales.

La procedencia no decide comparabilidad: dos corridas de los mismos snapshots y pesos pueden compararse aunque una sea antigua o no conserve semilla de generación. Mantener semilla del solver y data_seed diferenciadas en salida y documentación. No reescribir generation.json ni los hashes de los datasets para añadir este metadato.

## 5. Pruebas requeridas

Mantener las 266 pruebas del Hito 3 y sus correcciones. Ajustar las pruebas que esperaban rechazo de greedy/compare para verificar la funcionalidad nueva y sus argumentos obligatorios, sin eliminar la cobertura de errores.

### Baseline

- Orden estático por menor dominio y section_id; desempates por costo/pattern_id/room_id. Cambiar orden de filas/alt_id no cambia triples elegidos.
- Respeta sala, docente y todos los grupos en semanas coincidentes y permite compartir recursos en semanas disjuntas. Probar sesiones dobles y el segundo bloque.
- Costos exactos y mismos datos/candidatos/pesos que CP-SAT; pesos alternativos afectan decisiones según lo esperado.
- Caso completo auditado con estados/costos correctos; módulo sin import de model/OR-Tools y runner sin invocar CP-SAT cuando solver=greedy.
- Fixture pequeño con solución existente pero greedy atascado, por su elección temprana y sin backtracking: demostrar independientemente que CP-SAT o enumeración sí completa. Prefijo conservado, sección bloqueada, baseline INCOMPLETE, código 3 y ausencia de costo completo comparable.
- Precheck vacío no ejecuta ningún algoritmo. Una heurística que por error produce un conflicto da código 4. Fuentes/derivadas sin cambios por la selección.

### Compare

- Comparación válida en ambos órdenes de argumentos y de una corrida CP-SAT del Hito 3 con greedy nuevo.
- Misma entrada/pesos, distinto --time-limit/--seed o trabajadores: aceptar sin igualdad de hash efectivo entre métodos. Inputs distintos y pesos efectivos distintos: rechazar por separado.
- Estado FEASIBLE permitido como solución sin prueba de óptimo; sin modificar etiqueta. Nunca comparar prefijo contra horario completo.
- INCOMPLETE, NO_CANDIDATES, INFEASIBLE, UNKNOWN producen NOT_COMPARABLE sin mejoras numéricas.
- Asignaciones manipuladas después de ejecutar: nueva auditoría detecta invalidez o costo falso. Snapshot, hash global, config efectiva o metadatos incoherentes se rechazan aunque las banderas guardadas digan válido. La comprobación de integridad del Hito 3 sigue funcionando para ambos métodos.
- Base positiva con mejora/empate/empeoramiento; costo base cero con porcentaje null y diferencia absoluta. Un resultado CP-SAT peor se informa, no se oculta ni se fuerza con un timeout inestable.
- Directorio/run_id duplicado, método inesperado, JSON mal formado, rutas/carpetas ilegibles, salida existente intacta y salida dentro de una corrida rechazados.

### Procedencia

- Dataset generado con semilla distinta de la semilla del solver: ambas se conservan correctamente.
- Manifiesto ausente, mal formado y desactualizado: null y estado explícito, sin impedir resolver una entrada válida.
- Manifiesto coherente LF o CRLF validado según su política normalizada; hashes de corridas siguen siendo de bytes exactos. Snapshot input/ sigue teniendo solo 21 fuentes y ningún testigo.
- Ausencia de provenance en una corrida antigua no causa falsa incompatibilidad.

## 6. Verificación y entrega

Se acepta `uv run python -m pytest` como comando de pruebas: es equivalente para este encargo y evita depender del lanzador pytest.exe bloqueado en esta carpeta. No modificar políticas de Windows. Si uv falla por caché/permisos del sandbox, usar el intérprete base y PYTHONPATH temporal ya documentados, registrando exactamente lo ejecutado. No presentar un intento fallido como prueba aprobada.

```bash
uv sync --locked
uv run python -m academic_timetabling_demo run --help
uv run python -m academic_timetabling_demo compare --help
uv run python -m pytest
uv run ruff check src tests
uv run ruff format --check src tests
```

En la carpeta actual ejecutar explícitamente los archivos VERSIONADOS para no recoger test_optimization.py local ignorado; en el clon limpio la suite completa debe reunir solo lo publicado. Verificar instalación desde lock y clon limpio con UV_LINK_MODE=copy si hace falta. Si alguna comprobación queda bloqueada, describir el límite sin inventar evidencia.

Ejecutar micro/demo con greedy y CP-SAT, y compare, en carpetas nuevas. Si greedy no completa un caso, informar NOT_COMPARABLE honestamente; no cambiar el dataset para mejorar el resultado. Ejecutar además el fixture greedy incompleto y una comparación rechazada por entradas/pesos distintos.

Entrega en docs/entregas/hito-4.md: rama/commits, archivos, comandos/códigos, versiones, semillas y procedencia, estados, cobertura y auditorías, costos/desglose, diferencias y motivos de comparación no aplicable, tiempos observados, hashes y límites. Conservar corridas bajo runs/, sin versionarlas masivamente. Documentar las seis decisiones del encargo en especificación/decisiones y actualizar comandos reales de la guía/README. El trabajo de solver y auditoría del Hito 3 no se reimplementa.

Puerta de salida: baseline determinista con caso completo y atascado correctamente tratados; comparación solo entre resultados elegibles de mismos datos/pesos; procedencia explícita sin confundir semillas; pruebas previas y nuevas aprobadas. Commit local en la rama; devolver a Codex para revisión. Sin push, integración main ni Hito 5 hasta revisión y autorización del autor.
