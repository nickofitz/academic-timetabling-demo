# Entrega del Hito 2: candidatos SQL

Estado: revisado por Codex el 16 de noviembre de 2026; 155 pruebas versionadas y Ruff aprobados. El autor autorizó integrar y publicar el hito. Los comandos y limitaciones de la entrega original se conservan abajo.

## Rama y punto de partida

- Rama `hito/2-candidatos`, creada desde `main` en `49d667c`. Esta entrega va en el mismo commit que el código.
- El encargo se tomó del borrador local preparado por Codex; no se versionó como `docs/encargos/hito-2.md` porque esa ruta no figura entre las permitidas.
- `candidates.py` partió del archivo local ignorado del 15 de noviembre, que ya tenía las seis reglas, los costos y las ocupaciones en SQL. Antes de modificarlo se respaldaron en una carpeta local ignorada, con sus hashes SHA-256, los cinco archivos locales: `candidates.py`, `model.py`, `validate.py`, `demo_run.py` y `tests/test_optimization.py`. Los otros cuatro siguen fuera de Git y sin cambios.

## Cambios sobre el borrador local

1. **Repetición idempotente:** antes rechazaba una base ya preparada; ahora borra y reconstruye las tres tablas derivadas en la misma transacción.
2. **Desglose por sección:** patrones autorizados, pares de partida, alternativas, pares descartados, motivos por regla y, si la sección queda vacía, sus razones. Se distinguen `NO_PATTERNS` y `NO_ROOMS` de los descartes por regla.
3. **Conteos:** `discarded_pairs` cuenta triples distintos; `discards_by_rule` cuenta motivos, y un triple puede tener varios.
4. **Ocupaciones:** `INSERT OR IGNORE` se reemplazó por `UNION`, que elimina repetidos sin ocultar otros errores de restricción.
5. **Evidencia determinista:** el orden de bloques y equipamiento se fija dentro del agregado (`ORDER BY`, SQLite ≥ 3.44). La versión observada es 3.53.1.
6. **Seguridad transaccional:** rechaza una conexión con transacción abierta, comprueba `foreign_key_check` antes de confirmar y deja intactas las tablas derivadas anteriores si algo falla.

Se conservaron los nombres de la API (`build_candidates`, `Precheck.status`, `pairs_before`, `alternatives_after`, `discards_by_rule`, `empty_sections`), porque los archivos locales los usan.

## Archivos

- Nuevos: `src/academic_timetabling_demo/candidates.py`, `tests/test_candidates.py`, `docs/entregas/hito-2.md`.
- Modificados: `.gitignore` (solo esas tres rutas) y `README.md` (estado y uso de la API).
- Sin cambios: especificación, `schema.sql`, `uv.lock`, generador y datos versionados. Las consultas SQL están en `candidates.py`, sin recurso separado.

## Comandos y resultados

`uv run` no pudo ejecutarse: Windows bloquea `.venv\Scripts\python.exe` por una directiva de Control de aplicaciones (error 4551). Es el mismo bloqueo que registró Codex. No se modificó ninguna política. Se usó el intérprete base de Python 3.12.16 que instaló uv, con `PYTHONPATH` apuntando a `src` y a `.venv\Lib\site-packages`:

| Comando | Código | Resultado |
|---|---|---|
| `python -m pytest -p no:cacheprovider tests/test_cli.py tests/test_db.py tests/test_domain.py tests/test_synthetic.py tests/test_candidates.py` | 0 | 155 pruebas aprobadas: 124 anteriores y 31 nuevas |
| `python -m ruff check src tests` | 0 | Sin hallazgos |
| `python -m ruff format --check src tests` | 0 | 12 archivos con formato correcto |

Ruff respeta `.gitignore`, así que los 12 archivos son exactamente los versionados. Antes de agregar las excepciones a la lista blanca, Ruff omitía `candidates.py` y `test_candidates.py`; el resultado de la tabla es posterior a ese cambio.

`tests/test_optimization.py` es local e ignorado, y por eso se excluyó explícitamente de la evidencia. Corrido aparte con el `candidates.py` nuevo, sus 6 pruebas pasan; no se revisó su contenido ni el de los archivos que usa.

No se repitió la verificación desde un clon limpio: `uv sync` necesita ejecutar el intérprete del entorno, que está bloqueado.

## Resultados de la preparación

| Caso | Estado | Pares | Alternativas | Pares descartados | Ocupaciones | Tiempo |
|---|---|---|---|---|---|---|
| micro | READY | 12 | 5 | 7 | 36 | 2 ms |
| demo | READY | 432 | 125 | 307 | 3370 | 21 ms |

Los tiempos son de una sola ejecución en memoria, en este equipo.

Motivos de la demo: `CAPACITY` 210, `FEATURES` 30, `TEACHER_UNAVAILABLE` 84, `ROOM_UNAVAILABLE` 64, `ROOM_RESERVED` 13 y `PROTECTED_SLOT` 12. Suman 413 motivos sobre 307 pares. Cada sección de la demo parte de 36 pares y conserva entre 4 y 24 alternativas, incluida la del horario testigo.

### Caso micro revisado a mano

| Triple | Resultado | Motivo o costo |
|---|---|---|
| S1, P1, R1 | Alternativa | `cost_d=2` (T1 penaliza día 1, bloque 1), `cost_e=1` (5 asientos) |
| S1, P2, R1 | Alternativa | `cost_d=0`, `cost_e=1` |
| S1, P1/P2, R2 | Descartado | `FEATURES`: falta F1 |
| S2, P3, R2 | Alternativa | `cost_d=0`, `cost_e=1` (10 asientos) |
| S2, P3/P4, R1 | Descartado | `CAPACITY`: 30 < 40 |
| S2, P4, R2 | Descartado | `ROOM_RESERVED` en semana 2, día 2, bloque 3: segundo bloque de la sesión |
| S3, P5, R1 | Alternativa | `cost_d=0`, `cost_e=1` (10 asientos) |
| S3, P5, R2 | Alternativa | `cost_d=0`, `cost_e=3` (30 asientos) |
| S3, P6, R1/R2 | Descartado | `PROTECTED_SLOT` en semana 1, día 1, bloque 1 |

Coincide con lo anticipado en la entrega del Hito 1: S1=2, S2=1, S3=2. La prueba compara triples, costos y evidencia JSON exactos.

## Cobertura de las pruebas nuevas

- **Micro:** alternativas, costos, descartes con evidencia, conteos y ocupaciones de S2 fila por fila.
- **Reglas:** capacidad exacta e insuficiente, exceso de 0, 1, 10 y 11 asientos (costos 0, 1, 1 y 2), equipamiento faltante, docente no disponible en una sola semana, sala no disponible, disponibilidad totalmente ausente, reserva y franja protegida en el segundo bloque, y un triple con dos motivos contado una vez sin motivos duplicados.
- **Ocupaciones:** semanas disjuntas sin coincidencias y semanas compartidas con coincidencias, todos los grupos declarados sin deducir otros, y ausencia de duplicados.
- **Costos:** penalización de los dos bloques de una sesión doble, contada una vez y no por semana.
- **Diagnóstico:** dominio vacío por capacidad (`NO_CANDIDATES` con sus motivos), cero salas (`NO_ROOMS`) y sección sin patrones (`NO_PATTERNS`, alterando la base porque el cargador rechaza esa entrada). Otra prueba confirma que el módulo no importa OR-Tools.
- **Transacciones:** repetición idempotente con fuentes intactas, rollback efectivo con un fallo real durante la inserción de ocupaciones y rechazo de una transacción abierta.
- **Demo:** estado `READY` y conservación de la alternativa testigo de cada sección, lo que todavía no certifica el solver.

## Limitaciones y observaciones

- **Entorno bloqueado:** sin `uv run` ni clon limpio en esta sesión. Conviene repetir los comandos del encargo con `uv` en un entorno donde el lanzador no esté bloqueado.
- **Sin solver:** `READY` solo indica que cada sección tiene al menos una alternativa; no prueba factibilidad global.
- **Sin comando de preparación:** se usa como API, y el comando `run` queda para el Hito 3.
- **Archivos locales dependientes:** `model.py` y `demo_run.py` dependen de esta API. Siguen fuera del alcance y de Git.
- **Política de hashes:** sigue pendiente para el Hito 3 la decisión sobre finales de línea en los datos versionados (`.gitattributes`).
