# Encargo para Claude: Hito 5, exportaciones y demostración reproducible

Preparado por Codex el 16 de noviembre de 2026. Base aprobada y publicada: main en 6c4b0a7. Hitos 0–4 cerrados. Este encargo autoriza implementación en una rama, no push, integración o despliegue.

## 1. Objetivo y comienzo

Completar la versión 0.1: una corrida válida genera CSV de sesiones y una grilla HTML autocontenida filtrable. Entregar una demostración reproducible de cinco minutos con auditoría, comparación y cambio de disponibilidad. Mantener las garantías de estados, integridad y costos de los hitos anteriores.

Leer AGENTS.md y sus documentos de referencia. Confirmar que Codex terminó de editar, revisar Git y remoto y crear `hito/5-presentacion` desde main limpio y actualizado. Preservar archivos ignorados, stash y respaldos. Si existen borradores coincidentes, respaldarlos con hashes antes de editar. No reutilizar demo_run.py como flujo paralelo público: los comandos vigentes son la interfaz canónica.

Copiar este encargo a docs/encargos/hito-5.md y añadir su excepción precisa en .gitignore. Esta ruta está autorizada para conservar el encargo junto con la entrega.

### Rutas permitidas

- Paquete: src/academic_timetabling_demo/report.py, recursos bajo src/academic_timetabling_demo/templates/ y modificaciones de runner.py y metrics.py para la integración y registro de exportaciones.
- compare.py solo para extraer o reutilizar validación pública de evidencia de una corrida, sin cambiar reglas/códigos de compare. cli.py solo para actualizar ayudas y mensajes del flujo run que ahora exporta; no añadir un comando de optimización visual.
- Script reproducible scripts/demo_change.py y, si hace falta, helpers pequeños dentro del paquete para comparar asignaciones entre entradas distintas, sin llamarlos compare de calidad.
- Pruebas tests/test_report.py, tests/test_demo_change.py y ampliaciones de test_runner.py y test_cli.py. Fixtures sintéticos mínimos para estos tests bajo tests/fixtures/hito-5/.
- Documentación .gitignore, README.md, especificacion.md, Guia_MVP_Timetabling_Codex.md, docs/decisiones.md, docs/encargos/hito-5.md, docs/entregas/hito-5.md y docs/demo/ según la selección de la sección 6.

No cambiar modelo, baseline, auditor independiente, candidatos SQL, schema.sql, dominio, generador, datasets originales ni lockfile para producir una demo favorable. Si hace falta un cambio fuera de estas rutas, explicar primero la necesidad a Codex. Usar Jinja2 ya instalada o generación equivalente segura, sin nuevas dependencias ni frontend framework.

Fuera: login, backend web, APIs institucionales, arrastrar sesiones, optimizar desde el navegador, exámenes, ruido, otros solvers y minimizar cambios. No publicar un sitio ni activar GitHub Pages. No editar material local ajeno al alcance.

## 2. Integración con run y puertas de validez

Los comandos run actuales de cp-sat y greedy generan además schedule.csv y schedule.html cuando toda la corrida es válida. No agregar pasos manuales necesarios para obtenerlos. No cambiar las opciones existentes ni los costos.

Antes de preparar cualquier exportación se exige: datos válidos, precheck READY, solución completa (CP-SAT OPTIMAL/FEASIBLE o baseline COMPLETE), auditoría PASSED/audit_valid=true y snapshot verificado. Nunca exportar una grilla presentada como válida para NO_CANDIDATES, INFEASIBLE, UNKNOWN, MODEL_INVALID, greedy INCOMPLETE, auditoría fallida o integridad FAILED/NOT_VERIFIED.

Generar exclusivamente desde el snapshot input/, effective_config.json y asignaciones de la propia corrida, sin consultar de nuevo la carpeta de entrada original, generation.witness ni una corrida previa. Validar o reutilizar comprobaciones de evidencia ya probadas, incluidos tipos enteros de costos y auditoría contra fuentes; no inventar un lector permisivo que salte las correcciones de compare. La reconstrucción para presentación no debe importarse dentro del auditor.

La secuencia del runner debe respetar la comprobación final de integridad. Si se generan archivos antes de esa comprobación, mantenerlos en staging y no publicarlos con los nombres finales hasta pasar la puerta. Comprobar que lo exportado corresponde a los mismos datos y asignaciones auditados; un snapshot cambiado durante la presentación tampoco debe dejar una corrida exitosa con archivos aparentemente válidos.

Preparar ambos contenidos y escribir mediante temporales de la propia corrida, evitando un schedule.html válido a medias. Si falla renderizado/escritura/verificación, devolver código 5, marcar que la corrida no está lista para entregar y conservar los diagnósticos/assignments necesarios. No reescribir OPTIMAL o PASSED como si el solver/auditor hubieran fallado. No dejar schedule.csv/schedule.html de éxito tras un fallo; limpiar solo los temporales y archivos recién creados por ese intento, nunca fuentes o resultados ajenos.

Registrar fase y tiempo de exportación, archivos generados y sus hashes en metrics.json, con run_id coherente. El tiempo total definitivo debe incluir exportación. El HTML incrusta solo la proyección necesaria de datos/indicadores, no su propio hash ni una copia recursiva de metrics.json; así no hay dependencias circulares al calcular el hash del HTML. Las corridas antiguas y compare siguen siendo legibles sin exigir campos de exportación nuevos; no reescribir corridas ya guardadas para actualizarlas. No se exige un comando nuevo para renderizar corridas antiguas.

## 3. Contrato de schedule.csv

UTF-8, finales LF, encabezado y orden deterministas. Una fila por sesión y semana ACTIVA; una sesión doble genera una fila con duración 2, no dos filas ni una fila por grupo. El archivo completo contiene solo sesiones de las asignaciones válidas de la corrida.

Columnas, en este orden:

```text
run_id,section_id,section_name,pattern_id,session_id,week_id,day_id,start_block_id,duration_blocks,start_time,end_time,room_id,room_name,teacher_id,teacher_name,group_ids,enrollment,room_capacity
```

- session_id es el identificador original de pattern_sessions dentro del patrón.
- start_time es el inicio del primer bloque; end_time es el fin del último bloque ocupado. No inferir fechas de calendario ni semanas no declaradas.
- group_ids se serializa como un array JSON de IDs ordenados dentro de una única celda CSV, usando csv.writer para comillas. No duplicar la sesión por pertenecer a varios grupos.
- Orden de filas: week_id, day_id, start_block_id, room_id, section_id y session_id. Los números temporales se ordenan como números.
- Conservar nombres e IDs originales. No truncar sesiones o duraciones para que quepan en la vista. D/E y objetivo siguen siendo costos del horario; no multiplicarlos por las filas o semanas del CSV.

Prueba de referencia: reconstruir la cantidad y coordenadas esperadas desde asignaciones y fuentes, sin usar el propio exportador como oráculo.

## 4. schedule.html: vista offline y comportamiento

Archivo único que funciona abierto directamente por file:// y al copiarlo solo a otra carpeta: CSS, JS y datos necesarios incrustados. Sin CDN, fuentes remotas, fetch/XHR, imports de red, servidor o acceso a Python. No añadir botones ficticios de optimización. Las únicas acciones del navegador son filtros y, opcionalmente, descarga local del CSV/JSON incrustado si se implementa de verdad.

### Contenido y diseño

- Encabezado Academic Timetabling Demo y etiqueta visible Datos sintéticos. Interfaz en español.
- Mostrar run_id, fecha UTC explícita, método, estado exacto (OPTIMAL/FEASIBLE o COMPLETE), secciones asignadas/total, auditoría e integridad verificadas, costo total con D/E y pesos, tiempo de resolución (o de la heurística) con etiqueta precisa y semilla de datos solo si la procedencia la acredita. El tiempo total definitivo y las fases están en metrics.json; no presentar un tiempo parcial como total. No llamar óptimo a greedy ni a FEASIBLE; no convertir un costo en porcentaje de ahorro institucional.
- Tipografía del sistema; fondo claro, texto oscuro, acento sobrio azul/verde y leyenda. Usar etiquetas además de colores, contraste legible, controles asociados a sus labels y foco visible de teclado.
- Seleccionar una semana a la vez, inicialmente la primera del horizonte. Filtros opcionales de sala/docente/grupo con opción Todos, combinados por intersección. Un grupo filtra por membresía real, no por texto del nombre.
- Vista por sala: una grilla día/bloque por sala pertinente a los filtros, para que clases simultáneas en distintas salas no se pisen. Días en orden numérico y horas/bloques identificables. Las sesiones de varios bloques ocupan toda su duración con rowspan o representación visual equivalente, sin ocultar el segundo bloque.
- Cada tarjeta identifica sección, horario, sala, docente y grupos de manera consultable. Una tabla/lista accesible de sesiones acompaña a la grilla y responde a los mismos filtros.
- Mantener indicadores globales de la corrida sin recalcularlos como si el filtro fuera una nueva solución. Un contador separado de sesiones visibles sí se actualiza. Mostrar estado vacío explicativo cuando ningún registro cumple los filtros; permitir restablecerlos.
- Evitar desbordes que corten nombres o controles en escritorio; en pantallas estrechas permitir desplazamiento de la grilla dentro de su contenedor. Probar al menos un ancho de escritorio y uno estrecho.

### Seguridad del contenido

Nombres/IDs y metadatos se tratan como texto, también en opciones, atributos y etiquetas. Usar autoescape para HTML y serialización JSON segura frente a </script>, etiquetas y comillas; un bloque application/json sin escape del cierre de script no es suficiente. En JS usar textContent y creación de nodos para valores de datos; no concatenarlos en innerHTML, eventos inline o eval.

Probar nombres sintéticos con comillas, &, etiquetas y un cierre de script. Deben mostrarse como texto sin ejecutar código, romper filtros ni producir solicitudes de red. No modificar los datasets versionados para esas pruebas: usar fixtures temporales.

## 5. Cambio de disponibilidad reproducible

Entregar scripts/demo_change.py, ejecutable con el Python del proyecto:

```bash
uv run python scripts/demo_change.py --base-run runs/demo-cpsat --out runs/demo-change
```

El script recibe una corrida CP-SAT completa, auditada e íntegra, y un directorio NUEVO o vacío de trabajo. Rechazar una salida dentro de la corrida base o de su snapshot y cualquier salida no vacía sin modificarla. No editar la corrida base ni data/synthetic/demo.

1. Revalidar la evidencia de la corrida base contra su snapshot y asignaciones. Copiar sus 21 fuentes a out/changed-input/.
2. Elegir de forma estable la primera sección asignada por section_id, su primera semana activa, su primera sesión por día/bloque/session_id y el primer bloque ocupado de esa sesión. Identificar el docente y eliminar de teacher_available.csv exactamente esa fila semana/día/bloque. Debe existir porque la base fue auditada; si no existe, informar inconsistencia.
3. Guardar en out/change.json el run_id/hash de base, sección/docente, triple temporal y cambio exacto realizado. No copiar generation.json: no atribuir a datos modificados una semilla de generación verificada.
4. Ejecutar una nueva corrida CP-SAT en out/changed-run/ con las mismas preferencias y parámetros efectivos de la base. Copiar config.json original sin cambiar bytes y aplicar por el runner los overrides de tiempo/semilla efectivos; los trabajadores/pesos provienen del config original. Si una base externa declara diferencias no representables con la interfaz actual, rechazarla con explicación en vez de usar otros parámetros silenciosamente.
5. Si la nueva corrida es válida, comparar por section_id el par pattern_id/room_id y guardar en change.json secciones sin cambios y con cambio de patrón, de sala o de ambos, además del total. Mostrar IDs y valores antes/después. La sección afectada ya no puede usar el patrón que ocupa la disponibilidad retirada. No afirmar minimización de cambios.
6. Si la nueva corrida no tiene solución o falla, conservar estado/código/diagnóstico. Los conteos de cambios entre dos horarios completos serán null/no aplicables, no cero ni una comparación con un resultado parcial. No forzar una solución cambiando otra regla.

El script devuelve el código de la nueva corrida (0/2/3/4/5) y conserva change.json cuando se pudo crear el trabajo; una base/salida inválida es código 2. Errores internos son 5. Mensajes legibles sin traceback para errores esperables de entrada. Las funciones pequeñas de comparación de pares pueden testearse sin resolver; los IDs/run_id deben quedar enlazados a resultados reales.

No usar compare para calcular la mejora de calidad entre base y datos modificados: son entradas distintas y compare debe seguir rechazándolas. El informe de cambios es un recuento de reasignaciones, no un benchmark de costo.

## 6. Demo compartible y documentación

Actualizar README/guía con comandos reales, archivos y códigos, cómo abrir schedule.html localmente, filtros, supuestos/limitaciones y guion de cinco minutos. Quitar frases antiguas que digan que todos los comandos están pendientes. Los resultados cuantitativos siguen sustentados en corridas; no inventar enlaces publicados ni afirmar MVP terminado antes de revisión final.

Preparar un conjunto pequeño y explícito bajo docs/demo/:

- cpsat/: una corrida demo nueva completa, incluyendo snapshot, configuración, métricas/auditoría/diagnóstico, assignments, schedule.csv y schedule.html.
- greedy/: corrida equivalente del mismo dataset/pesos, igualmente completa y auditada.
- changed/: la corrida válida de disponibilidad modificada y change.json como evidencia; si no quedó válida, conservar diagnóstico claramente rotulado en lugar de un horario ficticio.
- comparison.json: comparación real de las dos primeras corridas, con objetivos verificados.
- README.md: contenido del conjunto, comandos para regenerarlo y ejecutar audit/compare desde el clon, límites de tiempo/entorno y explicación del cambio.
- preview.png: captura real de la grilla final que corresponda a la corrida elegida, nunca un mockup.

Conservar runs/ ignorado y abrir en .gitignore solo estos subdirectorios/archivos revisados. No añadir todos los experimentos, .venv, cachés, respaldos o capturas de otros programas. El HTML lleva todo lo necesario para visualizarse solo; el resto del conjunto sirve como evidencia auditable.

Las copias de docs/demo deben conservar íntegros los datos y hashes de las corridas. Revisar rutas y metadatos antes de seleccionarlas para Git: generarlas desde el repo con rutas relativas evita rutas personales. Si aparece información local privada, no editar silenciosamente la evidencia para ocultarla: elegir/regenerar un conjunto limpio o documentar por separado una redacción explícita, sin falsear lo que se ejecutó.

Volver a auditar las copias seleccionadas y ejecutar compare sobre docs/demo/greedy y docs/demo/cpsat antes de considerarlas compartibles. No sobrescribir los ejemplos existentes sin revisar su estado. Para capturar el conjunto final se permite hacer primero un commit de código en la rama y después otro con evidencia generada desde ese commit, como en hitos anteriores. Sin push ni integración.

El guion de cinco minutos debe poder mostrar: datos y supuestos -> ejecución/grilla -> auditoría -> comparación con greedy -> copia de disponibilidad modificada y nueva corrida/informe de cambios. El HTML solo filtra datos ya calculados; las nuevas soluciones se ejecutan en Python.

## 7. Pruebas y comprobaciones de aceptación

Mantener las 361 pruebas versionadas del Hito 4. No contar test_optimization.py local ignorado como evidencia del clon. Ajustar expectativas de archivos de salida solo para los dos nuevos artefactos y metadatos; no debilitar validaciones previas.

### Exportación y puertas

- Micro/demo de ambos métodos completos producen las dos exportaciones; filas correctas por semana/sesión, sin duplicación por grupos y sin pérdida de sesiones dobles. Revisar valores esperados por mano/fixture y roundtrip CSV con nombres especiales.
- Salidas JSON/CSV/HTML identifican el mismo run_id y conjuntos de secciones; los costos/estados que se muestran son los reales; los hashes de archivos corresponden a los bytes escritos.
- Ninguna exportación de éxito para precheck vacío, infactible, UNKNOWN/MODEL_INVALID, greedy incompleto, auditoría fallida o snapshot no verificable. Mantener las regresiones de snapshot alterado y errores de lectura del Hito 3.
- Un error de renderizado o escritura no deja archivos finales a medias ni una corrida con código 0. Probar fallo simulado entre los dos archivos y conservar evidencia de diagnóstico. No borrar archivos ajenos.
- El reporte usa el snapshot aunque cambien las fuentes originales. Una asignación/costo manipulado no pasa por ser dato de presentación. Compare mantiene sus regresiones de costo flotante/estado desconocido y sus códigos.

### HTML real

- Abrir schedule.html en un navegador y comprobar filtros combinados de semana/sala/docente/grupo, restablecimiento, vacío y sesiones de varios bloques. Probar membresía múltiple de grupo y simultaneidad en distintas salas.
- Copiar solo el HTML a una carpeta aislada y abrirlo offline: debe seguir funcionando y no efectuar peticiones de red.
- Comprobar escritorio/ancho estrecho, teclado/etiquetas y ausencia de texto cortado o solapado. Guardar captura real y registrar qué herramienta/navegador y acciones se verificaron.
- Probar cadenas con etiquetas/cierre de script/comillas. No basta buscar texto en el archivo: confirmar que el navegador no ejecuta el contenido ni rompe la página.
- Usar herramientas de navegador disponibles; si no se puede hacer una verificación visual/interactiva, describir el bloqueo y no presentarla como aprobada. Codex debe completar la revisión visual antes de cerrar el hito.

### Cambio y reproducción

- Base intacta byte por byte; solo una disponibilidad retirada en changed-input, con docente/semana/día/bloque realmente usados.
- Configuración efectiva y preferencias iguales a las de la base, nuevos run_id y hash de entrada distinto; procedencia del dataset modificado no aparece falsamente VERIFIED.
- Si hay nueva solución: auditoría positiva, disponibilidad retirada no ocupada, recuento exacto por patrón/sala y categorías que suman el total de secciones. Si no hay solución: diagnóstico y conteos null. Probar ambos caminos con fixtures/stubs estables, sin depender de un timeout minúsculo.
- Rechazar salida existente, base manipulada o parcial, rutas dentro de la base y parámetros de base que no se puedan conservar; mensajes/códigos coherentes.
- Desde clon limpio: instalación con lock, suite completa, generar ambos métodos, compare, script de cambio y apertura offline de HTML. No depender de scripts locales ignorados ni del directorio de trabajo original.

## 8. Entorno y entrega

Se acepta uv run python -m pytest para evitar el lanzador pytest.exe. Si el entorno falla por caché/sandbox/control de aplicaciones, registrar el intento y usar la alternativa conocida de intérprete base/PYTHONPATH temporal si está disponible. No modificar políticas de Windows ni atribuir pruebas no ejecutadas a una ejecución exitosa. UV_LINK_MODE=copy se permite para el clon limpio.

```bash
uv sync --locked
uv run python -m pytest
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
```

En la carpeta actual pasar rutas de pruebas versionadas para no recoger el test local ignorado; en clon limpio usar suite completa. Comprobar que Ruff incluye los archivos nuevos tras extender la lista blanca. Registrar hashes y estado Git reales de las corridas; no sustituir su origen por un commit posterior.

Entregar docs/entregas/hito-5.md con rama/commits, rutas, versiones, comandos/códigos, prueba visual y capturas, corridas elegidas, auditorías, comparación y cambio, tiempos observados, casos no aplicables y verificaciones no ejecutadas. Mantener la documentación técnica neutra y datos sintéticos. Hacer commits locales con rutas explícitas, sin push ni integración main.

Puerta de salida: 361 pruebas previas y nuevas pertinentes aprobadas; exports fieles que solo se publican para corridas válidas; HTML offline filtrable realmente inspeccionado; caso de cambio reproducible y auditable; docs/demo revisado y reproducción desde clon limpio. Codex revisa antes de declarar finalizada la versión 0.1 y pedir autorización para publicar el hito.
