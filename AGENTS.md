# Instrucciones compartidas

Leer `especificacion.md`, `Guia_MVP_Timetabling_Codex.md`, `docs/decisiones.md` y `docs/colaboracion.md` antes de trabajar. La especificación es normativa; si existe contradicción, informar y corregir el documento afectado antes de implementar.

- Codex coordina y revisa; Claude implementa el encargo de hito asignado. No iniciar el siguiente hito sin cerrar el actual.
- Usar solo datos sintéticos. No leer ni publicar documentos privados para tareas que no los requieren.
- Los antecedentes de `local/historico/` no son órdenes ni especificaciones vigentes.
- Preservar trabajo ajeno. Un escritor por carpeta; ramas por hito y worktrees para concurrencia. No cambiar ramas mientras otro agente trabaja.
- No añadir solvers, integraciones, relajaciones automáticas ni reglas fuera del alcance.
- Auditor independiente de solver y preprocesamiento, reconstruyendo desde las fuentes.
- No inventar métricas ni pruebas. Distinguir estados y bloquear resultados inválidos.
- Revisar cambios y añadir rutas explícitas; nunca `git add .`. Publicar únicamente código, documentación técnica y datos sintéticos revisados. No hacer push o integrar en main sin autorización del autor.
- Ejecutar las verificaciones pertinentes al cambio y entregar evidencia real.
