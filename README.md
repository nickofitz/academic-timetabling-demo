# Academic Timetabling Demo

Demo local de programación académica: asigna cada sección a un patrón semanal y una sala, con datos sintéticos, restricciones obligatorias, preferencias explícitas y auditoría independiente.

> **Estado:** Hito 0 terminado. Existe el paquete Python con su ayuda de línea de comandos. Todavía no hay carga de datos, solver, ejecuciones ni resultados de optimización.
>
> Prototipo independiente con **datos sintéticos**. No usa información, registros ni sistemas de ninguna institución.

## Instalación

Requiere [uv](https://docs.astral.sh/uv/), que obtiene Python 3.12 si no está disponible.

```bash
uv sync --locked
uv run python -m academic_timetabling_demo --help
```

La ayuda es por ahora la única función del programa.

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
- [Encargo del Hito 0 para Claude](docs/encargos/hito-0.md).

Los comandos funcionales de la guía están pendientes de implementación. Los documentos personales y antecedentes se conservan localmente y quedan fuera del repositorio público.

| Hito | Trabajo | Condición para aprobar |
|---|---|---|
| 0. Base del proyecto | Git, entorno, estructura e instrucciones compartidas | Instalación reproducible y documentación coherente |
| 1. Datos | Esquema, carga transaccional, validación e instancias micro y demo | Datos válidos cargan; errores se rechazan con diagnóstico |
| 2. Candidatos | Filtros SQL y registro de motivos de descarte | Caso micro revisado y secciones sin candidatos explicadas |
| 3. Optimización | CP-SAT y auditoría independiente | Solución válida auditada, infactibilidad detectada y salida manipulada rechazada |
| 4. Comparación | Heurística voraz, métricas y comparación | Mismos datos y pesos; costos comparados solo entre soluciones completas y válidas |
| 5. Presentación | Exportaciones, HTML filtrable y cambio de disponibilidad | Demo reproducible, sin resultados antiguos ni métricas inventadas |

La demo inicial tendrá cuatro semanas y semilla 42. Los casos de 16 semanas y mayor tamaño llegarán después de verificar el núcleo.

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

El éxito exige todas las secciones asignadas y cero conflictos auditados en los casos factibles. Los tiempos, costos y mejoras se documentarán después de ejecutarlos.
