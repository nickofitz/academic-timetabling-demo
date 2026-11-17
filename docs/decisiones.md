# Decisiones de diseño y antecedentes

Acordadas el 5 de noviembre de 2026. La especificación raíz es normativa.

| Tema | Decisión 0.1 | Alternativa aplazada / motivo |
|---|---|---|
| Solver | OR-Tools CP-SAT | SciPy/HiGHS y otros métodos: comparación posterior, sin resultados acreditados actuales |
| Base | SQLite | DuckDB y PostgreSQL: innecesarios para demo local inicial |
| Tiempo | Semanas explícitas | Segmentos: optimización posterior, previa prueba de equivalencia |
| Disponibilidad | Listas positivas por semana de docentes y salas | Indisponibilidades recurrentes: no constituyen el contrato de entrada |
| Patrones | Autorización explícita por sección | Inferir autorización por tipo de patrón deja de usarse |
| Capacidad | Exceso en decenas de asientos, redondeado hacia arriba | Exceso en asientos individuales cambia la escala de pesos |
| Penalizaciones | Por docente, día y bloque | Penalización global podría expandirse a docentes al preparar datos |
| Grupos | Membresía y origen explícitos | Mismo nivel de malla no implica incompatibilidad automática |
| Ruido | Fuera de 0.1 | Requiere interacciones entre secciones/salas y validación de reglas |
| Hitos | 0 a 5 de la guía | La organización anterior queda como antecedente histórico |
| Finales de línea de datos | `.gitattributes` fija LF en `data/synthetic/**/*.csv` y `*.json` (Hito 3) | Normalizar contenido al calcular hashes oculta diferencias de bytes |
| Hashes | Dos categorías separadas: `generation.json` conserva su hash normalizado a LF; las corridas hashean los bytes exactos de su snapshot `input/` | Una sola política obligaría a reescribir el manifiesto histórico o a perder exactitud en las corridas |
| Objetivo publicado | Entero reconstruido desde los costos de las alternativas elegidas y contrastado con CP-SAT; se rechaza un objetivo posible sobre 2**53 | `round(float)` podría ocultar diferencias |
| Asignaciones con auditoría fallida | Se conserva `assignments.csv` como evidencia; `metrics.json` y `audit.json` lo marcan inválido (`result_valid=false`, `audit_valid=false`) | Borrarlo impediría diagnosticar |
| Heurística incompleta (Hito 4) | `status.baseline=INCOMPLETE`, código 3, `assignments.csv` con el prefijo; el costo del prefijo va aparte en `diagnostics.baseline.partial_costs` y los costos completos quedan `null`. Si la auditoría del prefijo encuentra algo más que las omisiones esperadas, código 4 | Publicar el costo del prefijo como costo de solución lo haría parecer comparable |
| Estados por método | `parameters.solver` identifica el método; `status.solver` describe solo a CP-SAT y `status.baseline` solo a la heurística (`COMPLETE`/`INCOMPLETE`) | Reutilizar OPTIMAL/FEASIBLE para el voraz confundiría garantías distintas |
| Igualdad de entradas en `compare` | Hash global de `input/` del Hito 3, recalculado desde cada snapshot; incluye el `config.json` original | Un segundo criterio que ignore campos crearía dos nociones de misma entrada |
| Parámetros entre métodos | Se exigen iguales `alpha` y `beta` efectivos; no se exige igual hash de `effective_config.json`, porque límite, semilla y trabajadores de CP-SAT pueden diferir y se informan | Exigir el mismo hash impediría comparar con otro límite de tiempo |
| Reutilización de candidatos | La heurística usa las mismas `alternative` y `occupancy` de la corrida y los mismos pesos; no reimplementa reglas | Reglas propias podrían divergir del preprocesamiento |
| Exportaciones (Hito 5) | `schedule.csv` y `schedule.html` solo para soluciones completas, auditadas e íntegras; se generan desde el snapshot y se publican desde temporales tras revalidar la evidencia con las funciones públicas de `compare`. Un fallo da código 5 sin archivos finales | Exportar antes de verificar podría dejar una grilla aparentemente válida |
| Grilla HTML | Archivo único sin red, con CSP restrictiva, datos en JSON escapado (`<`, `>`, `&`) y nodos creados con `textContent`; vista por sala y semana | Un framework o recursos externos impedirían abrirla offline |
| Cambio de disponibilidad | Primera sección asignada por `section_id`, primera semana activa, primera sesión y su primer bloque; se retira una sola fila de `teacher_available.csv` y se resuelve con los mismos parámetros efectivos. El informe es un recuento de reasignaciones, no una comparación de calidad | Elegir el cambio a mano haría la demo menos reproducible |
| Procedencia de datos | `metrics.provenance` registra `data_seed`, `case` y `format_version` solo si `generation.json` coincide con las fuentes (estado `VERIFIED`); si falta, es inválido o no coincide: `ABSENT`, `INVALID` o `MISMATCH` con valores `null`. No decide comparabilidad | Deducir la semilla de datos de la del solver o del nombre de carpeta |

No se afirma superioridad de CP-SAT ni ahorro institucional. Los tamaños son objetivos de diseño, no mediciones. Los plazos y repartos del documento inicial son antecedentes históricos.

Los antecedentes se conservan localmente con hashes, fuera del control de versiones. Solo se distribuye documentación técnica vigente y revisada. Las copias anteriores quedan archivadas al regenerar los documentos.
