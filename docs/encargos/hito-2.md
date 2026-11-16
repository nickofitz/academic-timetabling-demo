# Encargo del Hito 2: candidatos SQL

Estado: implementado por Claude y revisado por Codex el 16 de noviembre de 2026; cierre y publicación autorizados por el autor. Este documento conserva el encargo que guio la entrega, no ordena volver a ejecutarlo. Codex coordina y revisa; Claude implementa.

## Objetivo

Construir alternativas patrón-sala, motivos de descarte, ocupaciones semanales y diagnóstico previo desde una base cargada conforme a especificacion.md. No implementar ni integrar solver, auditoría final, heurística o HTML.

## Inicio y preservación

Leer AGENTS.md y documentos referidos. Desde main aprobado y limpio crear hito/2-candidatos. Confirmar un solo escritor. Hay archivos ignorados de trabajo posterior: candidates.py, model.py, validate.py, demo_run.py y test_optimization.py. Preservarlos. Respaldarlos antes de cualquier operación que pueda sustituirlos y no publicar el conjunto automáticamente. Revisar candidates.py como posible punto de partida; mantener los otros fuera del encargo. No limpiar el stash existente.

## Rutas

Propuestas: src/academic_timetabling_demo/candidates.py, tests/test_candidates.py, consultas SQL si se separan en un recurso con ubicación documentada, .gitignore, README.md y docs/entregas/hito-2.md. Especificación y esquema permanecen canónicos; informar si hace falta modificarlos. No cambiar lockfile ni patrones para fabricar resultados.

## Comportamiento

- Cargar instancias con la API existente. Combinar solo patrones autorizados por sección y todas las salas.
- Expandir sesiones a cada bloque de todas sus semanas activas.
- Filtrar mediante SQL las seis reglas normativas: CAPACITY, FEATURES, TEACHER_UNAVAILABLE, ROOM_UNAVAILABLE, ROOM_RESERVED y PROTECTED_SLOT. Un fallo en un segundo bloque invalida la alternativa completa.
- Registrar todos los motivos aplicables por triple, con evidencia JSON útil y coordenadas temporales cuando proceda. Contar triples distintos, no razones.
- Guardar cost_d y cost_e exactos según la especificación. No multiplicar por semanas ni usar float para exceso de asientos.
- Construir occupancy para sala, docente y todos los grupos, sin duplicados, por semana/día/bloque. No comprimir segmentos ni inferir grupos.
- Devolver estado READY o NO_CANDIDATES, conteos antes/después y desglose por sección, incluida una sección con cero pares de partida. NO_CANDIDATES no es un estado de solver; no invocar OR-Tools.
- Poder repetir la preparación en la misma base sin duplicar datos; reemplazar solo tablas derivadas de forma transaccional. Mantener fuentes intactas y revertir la preparación si falla.

## Pruebas

- Micro: 12 triples antes de filtros; S1=2, S2=1, S3=2 después; inspección manual de triples, razones y costos.
- Capacidad exacta/insuficiente, equipamiento faltante, disponibilidad ausente de sala y docente, reserva/franja en segundo bloque, razón múltiple y ausencia de razones duplicadas.
- Semanas disjuntas no generan ocupaciones coincidentes; las coincidentes sí. Cada grupo y docente aparece en occupancy con su identidad, sin deducir incompatibilidades nuevas.
- Costos con exceso 0, 1, 10 y 11 asientos y penalización semanal contada una vez.
- Dominio vacío, cero salas y diagnóstico con ausencia de patrones cuando corresponda; datos estructuralmente inválidos siguen siendo responsabilidad del cargador.
- Repetición idempotente, fuentes inalteradas y rollback efectivo con fallo durante preparación.
- Demo conserva al menos la alternativa testigo para cada sección; esto no certifica todavía el solver.

Ejecutar las 124 pruebas anteriores más las nuevas del hito y Ruff sobre los archivos versionados. Separar los tests locales ignorados de solver: no contarlos como evidencia de este hito. Registrar comandos, tamaños, resultados, razones y limitaciones reales; sin push ni integración main hasta autorización del autor.

## Cierre

Alternativas micro y costos revisados a mano; diagnóstico de dominio vacío; demo y fuentes intactas; pruebas aprobadas. Codex revisa antes del Hito 3.
