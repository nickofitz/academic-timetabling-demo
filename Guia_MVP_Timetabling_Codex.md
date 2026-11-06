# Guía de construcción y entrega

Academic Timetabling Demo · versión documental 0.2 · 5 de noviembre de 2026.

## 1. Documentos y estado

Reglas, datos, costos, estados y aceptación: `especificacion.md` (fuente de verdad). Esquema: `schema.sql`. Decisiones y alternativas: `docs/decisiones.md`. Reparto y Git: `docs/colaboracion.md`. Esta guía organiza la implementación, sin redefinir esas reglas.

Estado: preparación documental terminada cuando el paquete sea revisado; Hito 0 pendiente. No existen aún comandos de optimización ni resultados. Los comandos siguientes son interfaces por implementar, no evidencia de software terminado.

## 2. Secuencia y puertas de salida

| Hito | Entregable | Evidencia requerida |
|---|---|---|
| 0. Base | Python 3.12, uv, paquete, ayuda CLI, dependencias fijadas | Instalación reproducible, importación, prueba CLI y Ruff |
| 1. Datos | Carga SQLite transaccional, validación Pydantic, generador micro/demo | Datos válidos cargados y errores rechazados; semillas y CSV conservados |
| 2. Candidatos | SQL de alternativas, ocupaciones y rechazos | Micro revisado manualmente, conteos y diagnóstico de dominio vacío |
| 3. Optimización | CP-SAT y auditor independiente | Micro óptimo por enumeración, demo auditada, caso infactible y salida manipulada |
| 4. Comparación | Heurística voraz y métricas comparables | Misma entrada/pesos, resultados completos y válidos para comparar costos |
| 5. Presentación | Exportaciones, HTML filtrable, cambio de disponibilidad | Demo reproducible, nueva corrida, auditoría y cambios por sección |

Codex prepara el encargo de cada hito y revisa la entrega; Claude lo implementa; el autor aprueba alcance e integración. El encargo inicial está en `docs/encargos/hito-0.md`. No ejecutar hitos posteriores desde este documento de forma automática.

## 3. Organización prevista

Paquete `src/academic_timetabling_demo/`: dominio, base/carga, generación sintética, candidatos, solver, auditoría, línea base, métricas, reportes y CLI. `tests/` contiene casos independientes y de integración. `data/synthetic/` conserva CSV generados aprobados; `runs/` contiene corridas locales no versionadas. Una corrida pública seleccionada podrá incluirse en `docs/demo/` en Hito 5, tras revisión.

El esquema raíz sigue siendo canónico. Si la distribución del paquete necesita copiar SQL o plantillas como recursos, automatizar la copia y comprobar igualdad; no mantener dos esquemas editados a mano.

## 4. Contrato de ejecución futuro

Estos comandos deben existir al cerrar Hito 5. Hito 0 solo implementa ayuda general.

```bash
uv sync --locked
uv run python -m academic_timetabling_demo generate --case micro --seed 42 --out data/synthetic/micro
uv run python -m academic_timetabling_demo generate --case demo --seed 42 --out data/synthetic/demo
uv run python -m academic_timetabling_demo run --input data/synthetic/demo --solver cp-sat --time-limit 30 --seed 42 --out runs/demo-cpsat
uv run python -m academic_timetabling_demo run --input data/synthetic/demo --solver greedy --out runs/demo-greedy
uv run python -m academic_timetabling_demo audit --input data/synthetic/demo --assignments runs/demo-cpsat/assignments.csv
uv run python -m academic_timetabling_demo compare --runs runs/demo-greedy runs/demo-cpsat --out runs/comparison.json
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

`generate` escribe tablas fuente y config.json en una carpeta nueva. Incorporar además los casos `no-candidates`, `infeasible` y `calendar` para las pruebas. `run` carga, valida, prepara, resuelve, audita y exporta conforme a la especificación. `audit` usa datos originales y configuración de entrada; al auditar una corrida con parámetros distintos, usar su snapshot de configuración efectiva. `compare` exige hashes y pesos iguales y auditorías positivas. No sobrescribir salidas existentes.

## 5. Demostración y revisión

1. Mostrar supuestos y datos sintéticos de la demo.
2. Ejecutar CP-SAT y mostrar estado real, cobertura y auditoría.
3. Comparar con la heurística, o explicar por qué no corresponde comparar costos.
4. Filtrar la grilla por semana, sala, docente y grupo.
5. Copiar las entradas, retirar una disponibilidad utilizada y ejecutar en otra carpeta. Mostrar diagnóstico si no hay solución y medir cambios si la hay.

Cada entrega incluye diff, comandos, resultados y limitaciones. Las pruebas de aceptación están en la especificación. No afirmar rendimiento institucional ni superioridad entre métodos con estos casos.

## 6. Distribución documental

Markdown y SQL son las fuentes editables técnicas. Los PDF se generan después de los cambios; las copias locales deben indicar la misma versión documental. El material local permanece excluido de Git. El repositorio público usa nombre neutro. Publicar documentos requiere revisar el contenido y las rutas añadidas, sin incluir material privado.
