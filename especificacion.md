# Especificación normativa del MVP 0.1

Versión documental 0.2 · 5 de noviembre de 2026 · Academic Timetabling Demo.

## 1. Objetivo, autoridad y estado

Demo local independiente de asignación de secciones a patrones semanales y salas, exclusivamente con datos sintéticos. Esta especificación es la fuente de verdad funcional. `schema.sql` materializa el contrato de datos; `Guia_MVP_Timetabling_Codex.md` organiza la ejecución. Si discrepan, detener el cambio afectado y corregir los documentos antes de implementarlo. Los antecedentes en `local/historico/` no son normativos.

Estado: preparación documental; no hay todavía aplicación, corridas ni métricas verificadas. El esquema se valida por separado, lo que no acredita el funcionamiento del futuro programa.

## 2. Alcance y modelo temporal

Python 3.12, uv, SQLite, OR-Tools CP-SAT; un campus. Tiempo discreto `t=(week_id,day_id,block_id)`, con semanas positivas, días 1..7 y bloques consecutivos 1..B de igual duración dentro del día. Las horas de bloque usan `HH:MM`; inicio anterior al fin y bloques ordenados sin superposición. El cargador exige semanas consecutivas 1..W y bloques consecutivos 1..B. La demo inicial usa 4 semanas, 5 días, 7 bloques, 12 secciones, 6 salas y semilla 42. El caso micro usa 2 o 3 secciones y 2 salas, con dominio suficientemente pequeño para enumerarlo.

Cada sección tiene un docente ya asignado, matrícula positiva, al menos un grupo, semanas activas explícitas y al menos un patrón autorizado. Un patrón enumera todas sus sesiones semanales; cada sesión ocupa bloques consecutivos sin salir del día. Las sesiones de una sección tienen igual duración y no se solapan. La sección mantiene una sala y un patrón en todas sus semanas activas. No hay compresión por segmentos ni intervalos implícitos de calendario.

Fuera de 0.1: ruido, traslados, exámenes, asignar docentes o estudiantes, integraciones, login, edición por arrastre, minimizar cambios, otras familias de solver y operación institucional. Casos de 16 semanas y mayor tamaño se incorporan tras verificar el núcleo.

## 3. Contrato de entrada y esquema

Entradas: un CSV UTF-8 por tabla fuente de `schema.sql`, con encabezados iguales a sus columnas, y `config.json`. Tablas sin registros se representan mediante CSV con encabezado. Los campos de texto se leen como texto, incluidos identificadores. No se aceptan referencias rotas ni duplicados. SQLite usa `PRAGMA foreign_keys=ON` en cada conexión; carga transaccional. La base es derivada y reconstruible desde entradas conservadas.

| Tabla fuente | Significado |
|---|---|
| `weeks`, `days`, `blocks` | Horizonte y bloques horarios |
| `teachers`, `rooms`, `features` | Docentes, salas con capacidad y catálogo de equipamiento |
| `room_features` | Equipamiento de cada sala |
| `groups` | Grupos explícitos; `basis` es `estudiantes_compartidos` o `regla_curricular` |
| `sections` | Docente, matrícula, sesiones por semana y bloques por sesión |
| `section_groups`, `section_features` | Grupos y equipamiento requerido por sección |
| `section_weeks` | Semanas activas de cada sección |
| `patterns`, `pattern_sessions`, `section_patterns` | Sesiones y patrones autorizados por sección |
| `teacher_available`, `room_available` | Triples temporales disponibles de cada recurso |
| `room_reservations` | Reserva externa de sala por triple temporal |
| `section_blocked` | Franja protegida o bloqueo de sección por triple temporal |
| `teacher_penalties` | Costo no negativo por docente, día y bloque; ausencia significa cero |

Disponibilidad ausente significa NO disponible. Una reserva prevalece sobre disponibilidad. Una franja protegida se expande explícitamente a las secciones afectadas en `section_blocked`; no reserva salas por sí misma. Si además se reserva una sala, debe existir `room_reservations`. Compartir nivel de malla no crea incompatibilidad automática. Los grupos requieren origen declarado; no se deducen de nombres o niveles.

`config.json` contiene `alpha=10`, `beta=1`, `time_limit_seconds=30`, `random_seed=42`, `num_search_workers=1` como valores iniciales. Pesos y semilla son enteros no negativos, límite temporal positivo y trabajadores entero positivo. El generador registra separadamente su semilla de datos, inicialmente 42. Los parámetros efectivos se guardan con cada corrida. Los límites de CLI sustituyen su parámetro de configuración y también quedan registrados.

Pydantic valida estructura y tipos. El cargador comprueba cardinalidades mínimas, rangos, horas, igualdad de duración, no solapamiento de sesiones y compatibilidad de frecuencia/duración de cada patrón autorizado. Rechaza bloqueos de sección fuera de sus semanas activas. Las tablas fuente y derivadas están separadas por secciones del esquema. Los chequeos que exigen varias tablas pertenecen al cargador, no se consideran cubiertos solo por las claves foráneas.

## 4. Alternativas SQL y diagnóstico

Una alternativa `(section_id,pattern_id,room_id)` combina un patrón autorizado y una sala. Expandir sesiones a todos sus bloques y semanas activas. Descartar el par completo si falla una regla:

| Regla | Motivo |
|---|---|
| `CAPACITY` | Capacidad menor que matrícula |
| `FEATURES` | Falta equipamiento requerido |
| `TEACHER_UNAVAILABLE` | Algún bloque ocupado no está declarado disponible para el docente |
| `ROOM_UNAVAILABLE` | Algún bloque ocupado no está declarado disponible para la sala |
| `ROOM_RESERVED` | Intersección con una reserva |
| `PROTECTED_SLOT` | Intersección con un bloqueo de sección |

Registrar cada motivo aplicable en `discarded_alternative`, con evidencia JSON; una alternativa puede tener varios motivos. Los conteos de candidatos usan triples distintos, no sumas de rechazos. No truncar candidatos silenciosamente. Datos o patrones estructuralmente inválidos se rechazan durante carga y no se convierten en simples descartes.

Guardar alternativas admisibles con `cost_d` y `cost_e`. Expandir `occupancy` por alternativa, tipo de recurso (`room`, `teacher`, `group`), recurso y triple temporal. Deduplicar pertenencias y ocupaciones. Los identificadores de recurso se validan contra la tabla que corresponde a su tipo.

Antes del solver informar errores de datos, conteos antes/después y secciones sin alternativas con razones. Datos inválidos: no resolver. Dominio vacío: `precheck_status=NO_CANDIDATES`, `solver_status=null`. Si todos tienen alternativas, `precheck_status=READY`; esto no prueba factibilidad global. La infactibilidad se refiere únicamente al catálogo de patrones suministrado.

## 5. Modelo y costos

Variable binaria `x_sa` por alternativa admisible. Cada sección elige exactamente una: `sum(a en A_s) x_sa = 1`. Para cada ocupación recurso-semana-día-bloque: `sum((s,a) que usan q) x_sa <= 1`.

Minimizar `sum_s sum_a (alpha*D_sa + beta*E_sa)*x_sa`:

- `D_sa`: suma de penalizaciones del docente en todos los bloques semanales del patrón, una sola vez; no multiplicar por semanas.
- `E_sa = ceil((capacidad(sala)-matricula(seccion))/10)`, una vez por sección. Calcular con enteros `(exceso+9)//10` tras descartar capacidad insuficiente.
- Pesos iniciales `alpha=10`, `beta=1`; no constituyen prioridad lexicográfica. Las preferencias nunca compensan restricciones duras.

Registrar `OPTIMAL`, `FEASIBLE`, `INFEASIBLE`, `UNKNOWN` o `MODEL_INVALID` sin reinterpretarlos. Extraer asignaciones solo con `OPTIMAL` o `FEASIBLE`. `UNKNOWN` no demuestra infactibilidad; `MODEL_INVALID` requiere corregir formulación o parámetros. No relajar reglas automáticamente.

## 6. Auditoría y línea base

El auditor recibe entradas originales, configuración efectiva y asignaciones sección-patrón-sala. No importa el solver ni consulta alternativas, descartes u ocupaciones derivados; puede compartir tipos, pero reconstruye sesiones, ocupaciones y costos por su cuenta, semana a semana.

Comprueba identificadores, exactamente una asignación por sección, autorización/frecuencia/duración del patrón, capacidad, equipamiento, disponibilidad, reservas, franjas protegidas y ausencia de choques de sala/docente/grupo. Recalcula ambos costos y contrasta el objetivo informado. Cada hallazgo incluye regla, sección o par, recurso y coordenadas temporales cuando corresponda. Una auditoría fallida impide publicar el horario como válido.

La heurística voraz ordena por menor cantidad de alternativas y luego `section_id`; elige la alternativa compatible de menor costo, con desempate por `pattern_id,room_id`. No retrocede. Si se atasca, `baseline_status=INCOMPLETE`; conservar resultado parcial identificado, sin afirmar infactibilidad. Comparar costos únicamente para asignaciones completas y auditadas de los mismos datos y pesos.

## 7. Corridas, interfaz y métricas

Comandos previstos: `generate`, `run`, `audit`, `compare` del paquete `academic_timetabling_demo`. La guía fija sus invocaciones. Son contratos pendientes de implementación.

Cada corrida usa un directorio nuevo y un `run_id` único; rechazar un directorio de salida no vacío. Conservar snapshot de entradas y configuración efectiva, hashes SHA-256, fecha UTC, revisión Git y estado de cambios si existen, versiones Python/OR-Tools/código, sistema, CPU, semillas, trabajadores y límite temporal.

Salidas: `diagnostics.json`, `metrics.json`, `audit.json`; con asignaciones, también `assignments.csv`. Solo una solución completa auditada produce `schedule.csv` y `schedule.html` válidos. Las salidas parciales se identifican expresamente. Con error de datos, dominio vacío o sin solución, costo y brecha son `null`; no reutilizar horarios previos. `audit.json` indica `NOT_RUN` si no hubo asignaciones que auditar.

Medir carga, preprocesamiento, solver, auditoría y total; cobertura, alternativas antes/después, variables, estados, costos desglosados y mejor cota. Brecha relativa con solución y cota finita: `max(0,z-L)/max(1,abs(z))`. Mejora porcentual: `100*(z_base-z)/z_base` solo si ambas soluciones son válidas y `z_base>0`; si base cero, usar diferencia absoluta. `compare` rechaza hashes de entradas o pesos distintos.

Códigos CLI: 0 éxito completo auditado (o generación/comparación válida); 2 argumentos/datos inválidos; 3 sin solución completa (`NO_CANDIDATES`, `INFEASIBLE`, `UNKNOWN`, heurística incompleta); 4 auditoría fallida; 5 error interno o `MODEL_INVALID`. Los detalles quedan en JSON cuando se haya podido crear el directorio de corrida.

HTML autocontenido sin CDN ni red, con etiqueta Datos sintéticos, estado, fecha, métricas y filtros por semana, sala, docente y grupo. Sesiones de varios bloques muestran toda su duración. Escapar texto y serializar de forma segura. El navegador filtra resultados; Python reoptimiza.

## 8. Pruebas y aceptación

1. Micro: óptimo y costo coinciden con enumeración independiente.
2. Capacidad igual aceptada, inferior rechazada; equipamiento faltante rechazado.
3. Bloqueo en segundo bloque de sesión detectado; patrones fuera del día, solapados o de frecuencia/duración incorrecta rechazados.
4. Conflictos separados de sala, docente y grupo detectados; grupos distintos y semanas disjuntas permitidos si no comparten otro recurso.
5. Disponibilidad ausente, reservas y franjas protegidas descartan lo afectado.
6. Dominio vacío no invoca solver; caso globalmente infactible con dominios no vacíos informa `INFEASIBLE`.
7. Adaptador probado para los cinco estados con simulación estable, más integración real con CP-SAT.
8. Auditor rechaza sección omitida/duplicada, patrón alterado y costo falso.
9. Demo: 12 secciones, 6 salas, 4 semanas, semilla 42; cobertura completa y cero conflictos auditados. Generar primero un horario testigo para asegurar factibilidad del caso, sin entregarlo como respuesta al solver.
10. Comparación con heurística y cambio de disponibilidad usada en una copia de datos; nueva corrida y auditoría, incluso si el cambio vuelve infactible el caso. Medir cambios por sección, sin prometer minimizarlos.
11. Reproducción desde clon limpio con dependencias fijadas; resultados cuantitativos solo tras ejecución.
