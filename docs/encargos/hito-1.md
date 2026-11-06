# Encargo para Claude: Hito 1, datos y validación

Preparado el 6 de noviembre de 2026. Estado: listo para revisión; no ejecutar hasta que el autor cierre el Hito 0 y confirme la base Git.

## Objetivo y condiciones de inicio

Implementar datos tipados, carga SQLite transaccional y generación reproducible de casos micro y demo. Leer AGENTS.md y sus referencias. La especificación raíz y el esquema canónico no cambian en este encargo.

Codex ya revisó técnicamente el Hito 0. Antes de implementar, el autor debe confirmar su cierre y la base integrada. Desde main limpio y actualizado, crear `hito/1-datos`. No partir de los commits históricos pendientes de depuración ni integrar/push por cuenta propia. Confirmar que Codex no está editando esta carpeta.

## Rutas permitidas y límites

- Paquete: `domain.py`, `db.py`, `synthetic.py` y modificaciones de `cli.py` dentro de `src/academic_timetabling_demo/`.
- Pruebas: `tests/test_domain.py`, `tests/test_db.py`, `tests/test_synthetic.py`, `tests/test_cli.py` y fixtures sintéticos bajo `tests/fixtures/`.
- Entradas: `data/synthetic/micro/`, `data/synthetic/demo/`; CSV fuente, config.json y manifiesto de generación.
- Documentación: `.gitignore`, `README.md`, `docs/entregas/hito-1.md`.

No modificar `schema.sql`, especificación, instrucciones compartidas ni lockfile sin una necesidad demostrada y revisión de Codex. No implementar candidatos, solver, auditor final, heurística ni HTML. Las tres tablas derivadas quedan vacías tras la carga. No exponer comandos run/audit/compare incompletos.

## 1. Modelos y lectura

Crear modelos Pydantic para las 20 tablas fuente y configuración. Leer un CSV UTF-8 por tabla, incluso tablas vacías con encabezado, más config.json. Conservar identificadores como texto (incluidos ceros iniciales); convertir números de CSV explícitamente y rechazar valores inválidos sin truncar decimales ni interpretar booleanos como enteros. Rechazar archivos fuente ausentes, encabezados incorrectos, filas mal formadas, claves duplicadas y referencias rotas. Los diagnósticos deben identificar archivo y fila/campo cuando proceda.

Validar reglas de la especificación: horizonte no vacío; semanas y bloques consecutivos; días permitidos; horas válidas, bloques de igual duración ordenados y sin superposición; capacidad y matrícula positivas; pesos enteros no negativos y parámetros de corrida válidos. Cada sección requiere docente, grupo, semanas y patrones autorizados. Cada patrón autorizado debe cumplir frecuencia, duración, límites del día y ausencia de solapamientos. Un bloqueo de sección solo puede referirse a sus semanas activas.

No exigir que cada bloque tenga disponibilidad ni convertir ausencias en disponibilidad total. Reservas y bloqueos sobre recursos disponibles son datos válidos: su efecto sobre candidatos corresponde al Hito 2. Tener demanda superior a la capacidad de todas las salas es un caso estructuralmente válido con dominio vacío potencial; no confundirlo con un archivo mal formado.

## 2. Carga SQLite

Usar `schema.sql` raíz como única fuente del esquema. En este hito la carga se ejecuta desde el repositorio; no prometer distribución standalone del esquema todavía. Centralizar apertura de conexiones y activar/comprobar foreign_keys en cada conexión antes de transacciones. Usar consultas parametrizadas y orden referencial.

Validar antes de insertar y efectuar la carga fuente de forma atómica. Un error no puede dejar filas parciales ni borrar datos preexistentes. Para la primera versión, aceptar bases fuente vacías y rechazar las no vacías, sin reconstruirlas destructivamente. Añadir prueba de rollback forzando un fallo durante inserción, además de rechazo previo de datos inválidos. Verificar foreign_key_check tras la carga. No publicar una base SQLite como sustituto de los CSV.

## 3. Generador y comando generate

Implementar `generate --case micro|demo --seed 42 --out RUTA`. La ayuda general debe seguir funcionando. Mantener rechazo con código 2 para subcomandos futuros y actualizar la prueba que actualmente usa generate como argumento desconocido.

- Micro: 2 o 3 secciones, 2 salas y pocos patrones; diseño explicable a mano y apto para enumeración posterior.
- Demo: 12 secciones, 6 salas, 4 semanas, 5 días y 7 bloques. Incluir grupos compartidos, equipamiento requerido, sesiones dobles, reservas, franjas protegidas y preferencias no nulas.
- Generar primero un horario testigo y derivar datos compatibles. Guardar el testigo únicamente como evidencia separada bajo `witness` en el manifiesto, nunca como asignaciones calculadas ni como tabla fuente. Las pruebas de este hito deben comprobar directamente su compatibilidad con las entradas; el auditor independiente del Hito 3 no se considera implementado por esta comprobación.
- Semilla y caso iguales deben producir CSV y configuración idénticos byte por byte, con orden estable. Registrar caso, semilla, versión del formato y hashes de fuentes en `generation.json`, sin introducir fechas variables en archivos que se comparan por reproducibilidad. El manifiesto no es una tabla fuente y no se carga en SQLite.
- Rechazar salida no vacía sin sobrescribirla. Código 0 si se generó y validó; 2 para argumentos/datos inválidos; 5 para fallo interno, con mensaje útil. No inventar métricas de optimización.

Conservar en Git los casos micro y demo de semilla 42 y las pruebas; las regeneraciones de verificación se ejecutan en carpetas temporales. Los casos no-candidates/infeasible/calendar pueden prepararse como fixtures mínimos según se necesiten; su diagnóstico de candidatos y solver pertenece a hitos posteriores.

## 4. Pruebas y evidencia

Cubrir carga válida, tablas vacías opcionales, ID textual con ceros, duplicados, referencias rotas, rangos y configuración incorrectos, bloques de distinta duración o superpuestos, sesiones fuera del día o solapadas, patrón incompatible, sección sin grupo/semanas/patrón y bloqueo fuera de semanas activas. Comprobar que la ausencia de disponibilidad se conserva y no rechaza estructuralmente una entrada.

Probar claves foráneas por conexión, rollback efectivo, rechazo de base no vacía, tablas derivadas vacías, dos generaciones iguales por semilla, salida no vacía intacta, CLI generate y errores. Probar los casos micro/demo mediante carga real; las pruebas no importan OR-Tools.

Ejecutar:

```bash
uv sync --locked
uv run python -m academic_timetabling_demo --help
uv run python -m academic_timetabling_demo generate --help
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
```

Ejecutar generate para micro y demo en directorios temporales nuevos y cargar ambos en SQLite con las funciones implementadas. Registrar los comandos/API exactos, tamaños reales, hashes, resultados y limitaciones en `docs/entregas/hito-1.md`. Verificar que una instalación desde clon limpio reproduce pruebas y casos; no atribuir a Codex resultados que no haya repetido.

Extender `.gitignore` solo para las rutas del hito y verificar el conjunto de archivos antes de añadir rutas explícitas a Git. Entregar diff y evidencia a Codex; no integrar main ni hacer push sin autorización.

## Puerta de salida

Micro y demo reproducibles y cargables; entradas inválidas explicadas; atomicidad comprobada; cero tablas derivadas pobladas; pruebas y Ruff aprobados. No hay aún horario optimizado ni certificado de factibilidad del solver. Codex revisa la entrega antes del Hito 2.
