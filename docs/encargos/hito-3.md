# Encargo para Claude: Hito 3, CP-SAT y auditoría independiente

Preparado por Codex el 16 de noviembre de 2026. Hitos 0, 1 y 2 integrados y publicados. Base revisada: main en 0ed2285. Este encargo autoriza preparar la implementación en una rama, no integrarla ni publicarla.

## 1. Objetivo y preparación

Obtener una solución calculada y auditada desde entradas sintéticas, con estados exactos y evidencia reproducible. Leer AGENTS.md y los cuatro documentos que referencia; especificacion.md es normativa para reglas, costos, estados y códigos de salida.

- Confirmar que Codex ya no está editando. Comprobar estado Git y remoto; preservar cambios ajenos. Desde main limpio y actualizado crear `hito/3-optimizacion`.
- Copiar este encargo a `docs/encargos/hito-3.md` y añadir su excepción concreta a .gitignore. Esta ruta está permitida para evitar perder la trazabilidad del encargo.
- Hay cuatro archivos locales ignorados: model.py, validate.py, demo_run.py y tests/test_optimization.py. Respaldarlos con hashes antes de editar y conservar el respaldo previo y el stash. Revisarlos como borradores, sin considerarlos entregas aprobadas. No restaurar encima de candidates.py: el Hito 2 publicado es canónico.
- Conservar nombres model.py y validate.py y las APIs públicas existentes cuando resulte viable; sus nombres no eximen de cumplir el contrato. Si hace falta ajustar consumidores, hacerlo dentro de las rutas permitidas y registrar el cambio.

### Rutas permitidas

Dentro de src/academic_timetabling_demo/: model.py, validate.py, runner.py, metrics.py, cli.py y domain.py únicamente para validación de configuración efectiva si es necesaria. No reescribir los modelos fuente por conveniencia.

Pruebas: tests/test_model.py, tests/test_audit.py, tests/test_runner.py, tests/test_cli.py y tests/test_optimization.py si se reutiliza y amplía; fixtures sintéticos bajo tests/fixtures/hito-3/. Se pueden ajustar pruebas previas solo por extensiones intencionales de CLI o configuración; no eliminar cobertura de los hitos anteriores.

Documentación/configuración: .gitignore, .gitattributes, README.md, docs/decisiones.md, docs/encargos/hito-3.md y docs/entregas/hito-3.md. Las notas de estado en especificacion.md y Guia_MVP_Timetabling_Codex.md se pueden actualizar para quitar el estado antiguo, sin cambiar reglas ni alcance. No regenerar documentos privados o PDF.

Los resultados de ejecución van a runs/ y siguen ignorados. No cambiar schema.sql, candidates.py, datos versionados, pyproject.toml o uv.lock sin un problema concreto que se informe primero a Codex. Añadir excepciones precisas a Git solo para las rutas utilizadas. demo_run.py queda local e ignorado: el flujo público será la CLI principal.

Fuera: heurística voraz, compare, HTML, schedule.csv expandido, drag-and-drop, integraciones, otros solvers y minimizar cambios. Las exportaciones de sesiones y la presentación quedan para Hito 5; no generar archivos vacíos ni afirmar que existen. El Hito 3 sí entrega assignments.csv y los JSON de diagnóstico, auditoría y métricas.

## 2. Solver CP-SAT

Usar las tablas alternative y occupancy del Hito 2. Una variable booleana por alternativa, exactamente una por sección y a lo sumo una por ocupación recurso-semana-día-bloque. No imponer choques entre semanas disjuntas ni inventar incompatibilidades de grupos.

Minimizar alpha*D + beta*E con costos y configuración efectivos. No pasar al solver el testigo del generador como respuesta ni usarlo como hint: solo evidencia del dataset y de pruebas. No truncar candidatos ni relajar restricciones duras.

Configurar límite de tiempo, semilla y trabajadores desde RunConfig; los overrides de CLI sustituyen su valor efectivo y se registran. Validar antes de resolver valores finitos, rangos del solver y aritmética entera admitida por CP-SAT. Ante parámetros incompatibles, informar la causa, sin recortar, redondear o sustituir silenciosamente. Si los costos no se pueden representar correctamente, detener con explicación.

Crear un adaptador de estados comprobable mediante pruebas deterministas para OPTIMAL, FEASIBLE, INFEASIBLE, UNKNOWN y MODEL_INVALID. Extraer asignaciones solo en los dos primeros. No llamar Value/BooleanValue ni leer un objetivo de solución cuando no hay solución. Mantener el estado recibido sin reinterpretarlo.

El objetivo entero publicado se reconstruye desde las alternativas seleccionadas y sus costos, con comprobación de consistencia frente al objetivo informado por el solver; no usar round(float) para ocultar diferencias. Registrar costos D/E, objetivo, mejor cota cuando sea válida, número de variables/restricciones y tiempo de construcción/resolución. Sin solución, objetivo/costos/brecha son null.

La orquestación no invoca el solver si el precheck devuelve NO_CANDIDATES: solver_status=null y diagnóstico persistido. La API del modelo también protege contra secciones sin alternativas para evitar uso incorrecto directo.

## 3. Auditoría independiente

validate.py recibe entradas originales, configuración efectiva y triples sección-patrón-sala. No importa model.py, candidates.py, OR-Tools ni consultas auxiliares del preprocesamiento; no consulta tablas alternative, discarded_alternative u occupancy. Puede compartir tipos fuente, pero reconstruye sesiones, semanas, recursos y costos con lógica propia.

Comprobar identificadores conocidos, exactamente una asignación por sección, patrón autorizado, frecuencia/duración, sesiones dentro del día y sin autosolapamiento; capacidad/equipamiento; disponibilidad de cada bloque y semana; reservas; franjas protegidas; choques separados de sala, docente y cada grupo; costos desglosados y objetivo reportado cuando se suministre.

Cada hallazgo incluye regla, sección o secciones, recurso y semana/día/bloque cuando proceda. Una entrada de asignaciones desconocida, duplicada o mal formada no provoca éxito por omisión: producir hallazgos o error de datos según el límite de lectura y no una excepción interna sin explicación. En la API no se presupone que el patrón manipulado es compatible porque provenga de un ID conocido.

Una auditoría fallida marca audit_valid=false y bloquea el éxito y la publicación del horario como válido, aunque CP-SAT diga OPTIMAL. Conservar las asignaciones sospechosas y los hallazgos para diagnóstico, identificadas como inválidas. Con solver no ejecutado o sin asignación: estado de auditoría NOT_RUN y audit_valid=null.

Demostrar independencia ejecutando el auditor sin base de candidatos y mediante una prueba que altere un costo derivado: el auditor debe detectar la diferencia contra los datos originales. No compartir el código de reconstrucción de ocupaciones entre solver/preprocesamiento y auditor.

## 4. CLI y corridas reproducibles

Conservar generate. Implementar:

```bash
uv run python -m academic_timetabling_demo run --input data/synthetic/micro --solver cp-sat --out runs/hito3-micro
uv run python -m academic_timetabling_demo run --input data/synthetic/demo --solver cp-sat --time-limit 30 --seed 42 --out runs/hito3-demo
uv run python -m academic_timetabling_demo audit --input data/synthetic/demo --assignments runs/hito3-demo/assignments.csv
```

run solo acepta cp-sat en este hito; greedy y compare siguen rechazándose claramente como no implementados. No simular comandos futuros. --time-limit debe ser positivo y finito; --seed entero no negativo compatible con el solver. No cambiar el significado de generate --seed, que sigue siendo semilla de datos.

Pipeline: validar entrada/configuración -> cargar SQLite -> preparar candidatos -> resolver si corresponde -> auditar si hay asignación -> exportar diagnóstico/métricas. Cerrar conexiones incluso si falla una fase. Comprobar al principio que SQLite admite la consulta de agregación JSON usada por el Hito 2; si no la admite, indicar versión observada y limitación con error de entorno, sin cambiar SQL aprobado silenciosamente.

Cada corrida crea un directorio nuevo o vacío y rechaza salidas no vacías sin modificarlas. Rechazar salida igual a la entrada o anidada dentro de la entrada, para no alterar el dataset original. No reutilizar resultados de una corrida anterior.

### Salidas del Hito 3

- diagnostics.json: errores de datos y diagnóstico de candidatos con conteos y evidencias útiles.
- metrics.json: run_id, fecha UTC, estados, configuración efectiva, versiones, código y tiempos; cobertura, variables, conteos, costos, cota y brecha cuando correspondan.
- audit.json: PASSED/FAILED/NOT_RUN, audit_valid, costos recalculados cuando haya auditoría y hallazgos.
- assignments.csv: encabezado section_id,pattern_id,room_id y una fila por asignación extraída. No crearlo para UNKNOWN, INFEASIBLE o dominio vacío. Si falla auditoría, conservarlo solo como evidencia identificada inválida, sin salida de éxito.
- input/: copia de los 20 CSV fuente y config.json originales, sin generation.json ni testigo; el solver y auditor no necesitan leer esa evidencia del generador.
- effective_config.json: configuración aplicada, después de overrides. Los originales y los parámetros efectivos quedan separados explícitamente.

Guardar hash SHA-256 de los bytes exactos de cada fuente copiada y un hash global sobre la lista ordenada de nombres relativos y hashes con serialización estable. Guardar por separado el hash de la configuración efectiva. Verificar que lo copiado coincide con lo usado para resolver: trabajar desde el snapshot, no leer de nuevo el directorio original después de copiarlo. No presentar una corrida con entradas que cambiaron durante su preparación como equivalente al dataset inicial sin registrarlo.

Versiones mínimas de evidencia: Python, OR-Tools, SQLite, versión del paquete y revisión Git/estado de cambios cuando haya repositorio; sistema, CPU cuando esté disponible, semillas, trabajadores y límite. Si algún dato no está disponible, usar null, sin inventarlo. Medir carga, candidatos, construcción, solver, auditoría y total con reloj monotónico; no prometer tiempos idénticos.

Calcular brecha con solución y cota finita según la especificación. JSON estricto: sin NaN/Infinity; valores no aplicables null. En error de datos, dominio vacío o ausencia de solución, no atribuir costo de solución. Para datos inválidos escribir diagnóstico si ya se pudo crear salida; no fingir snapshot completo si faltan fuentes.

Códigos: 0 solución completa auditada o auditoría standalone válida; 2 argumentos/datos inválidos; 3 NO_CANDIDATES/INFEASIBLE/UNKNOWN; 4 auditoría fallida; 5 MODEL_INVALID o fallo interno/entorno. Conservar estado exacto separado del código de salida. Un fallo de auditoría no cambia OPTIMAL a otro estado de solver.

El comando audit imprime JSON y código de salida, sin sobrescribir automáticamente audit.json de una corrida. Añadir --config RUTA opcional para auditar con effective_config.json, y --reported-objective ENTERO opcional para contrastar costo declarado; si no se proporcionan, usar configuración original y devolver costo recalculado sin inventar un objetivo reportado. La API de auditoría siempre admite configuración y objetivo explícitos.

### Política de finales de línea

Agregar .gitattributes con reglas específicas `data/synthetic/**/*.csv text eol=lf` y `data/synthetic/**/*.json text eol=lf`. Verificar con git check-attr que cubren ambos datasets. No alterar valores, semillas ni testigos ni hacer un renormalize de todo el repositorio. Si se requiere normalizar físicamente los archivos de datos, informar el diff de solo finales de línea antes de añadirlos; esos cambios requieren revisión adicional de Codex.

El manifiesto generation.json del generador mantiene su política histórica de hash normalizado a LF. Los hashes de corridas son de bytes exactos del snapshot y deben indicar esa política: no confundir ambas categorías. Registrar esta decisión en docs/decisiones.md y probarla con entradas LF/CRLF y snapshots correspondientes.

## 5. Pruebas de aceptación

Mantener las 155 pruebas versionadas anteriores. Reutilizar las 6 pruebas locales de optimización solo tras revisarlas e incorporarlas conscientemente; el conteo agregado no sustituye los casos siguientes.

1. Micro: solver OPTIMAL y costo 3 confirmado mediante enumeración exhaustiva de todos los pares autorizados y salas desde las fuentes, sin usar alternative/occupancy como dominio. La enumeración puede usar el auditor para filtrar, acompañado de pruebas directas de reglas y costos esperados del auditor para evitar validación circular.
2. Demo: 12 secciones asignadas, OPTIMAL o FEASIBLE sin exigir óptimo, cero hallazgos y costo recalculado coincidente. No exigir una asignación idéntica entre versiones del solver.
3. Dominio vacío: solver no invocado (spy o stub que falle si se llama), solver_status=null, código 3, diagnóstico y sin assignments.csv.
4. Infactibilidad global con dominios no vacíos: estado real INFEASIBLE y ninguna asignación publicada. La modificación del micro para compartir un grupo sirve de fixture.
5. Semanas disjuntas permiten compartir recursos; coincidentes impiden choques. Probar sala, docente y grupo por separado, incluyendo sesiones de varios bloques y segundo bloque ocupado.
6. Los cinco estados se prueban con un adaptador simulado estable. No forzar timeouts reales de milisegundos. Verificar que UNKNOWN/MODEL_INVALID no leen valores de solución y que FEASIBLE nunca se anuncia como óptimo.
7. Auditor rechaza ID desconocido, sección omitida/duplicada, patrón cambiado o de forma incompatible, capacidad insuficiente, equipamiento faltante, disponibilidad ausente, reserva/franja en segundo bloque, conflictos de cada recurso y costo falso. Verifica límites y autosolapamiento si recibe una fuente manipulada.
8. Costos: D una vez por semana patrón, E en decenas redondeadas; pesos configurables y extremos de parámetros controlados sin pérdida numérica silenciosa.
9. Independencia del auditor sin candidatos ni imports de solver/preprocesamiento; costo derivado alterado detectado.
10. CLI: generación anterior conservada, ejecución y audit standalone; códigos correctos, parámetros inválidos, overrides registrados y usados por solver/auditor, salida no vacía intacta, fallo de auditoría que bloquea éxito, sin asignaciones antiguas reutilizadas.
11. Evidencia: snapshot exacto sin testigo; hashes corresponden a bytes conservados; configuración original/efectiva diferenciadas; JSON válido en casos sin solución y fallidos. Directorios input/out peligrosamente coincidentes rechazados.
12. Clon limpio: instalar con lock y probar los archivos realmente versionados. No dar por probado lo que se ejecutó usando archivos locales ignorados.

## 6. Entorno, validación y entrega

Intentar los comandos contractuales si el entorno lo permite. No reinstalar Python ni modificar políticas de Windows para resolver el bloqueo de .venv. Si persiste, usar la alternativa documentada: intérprete base Python 3.12.16 con PYTHONPATH temporal a src y .venv/Lib/site-packages. Registrar el comando exacto y distinguir esta ejecución de uv run.

```bash
uv sync --locked
uv run python -m academic_timetabling_demo --help
uv run python -m academic_timetabling_demo run --help
uv run python -m academic_timetabling_demo audit --help
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
```

Para un clon limpio con problemas de hardlinks se permite UV_LINK_MODE=copy. Si no se puede verificar clon limpio, informar el bloqueo y conservar evidencia parcial sin llamarlo reproducido. No contar archivos ignorados como pruebas de lo que se enviará a GitHub. Comprobar además imports sin ejecutar un solver ni escribir archivos por importación.

Ejecutar micro, demo, caso sin candidatos, caso globalmente infactible y auditoría manipulada. Documentar en docs/entregas/hito-3.md: rama/commits, rutas, versiones, comandos/códigos, resultados reales, costo y cota/desglose, conteos, auditorías, snapshots/hashes, límites del entorno y pruebas no ejecutadas. Los números son resultados observados, no promesas.

Actualizar README con comandos disponibles, requisitos de SQLite comprobados, limitaciones y estado real. Añadir este encargo a Git junto con las rutas implementadas, usando nombres explícitos y diff revisado. Commit en la rama, sin push ni integración main hasta revisión de Codex y autorización del autor.

Puerta de salida: micro óptimo comprobado por enumeración; demo completa auditada; dominio vacío, infactibilidad, cinco estados y salida manipulada correctamente tratados; corridas identificables con inputs/configuración y evidencia real; 155 pruebas previas y nuevas pertinentes aprobadas. Solo entonces preparar Hito 4.
