# Colaboración y revisión

Autor: aprueba alcance y cambios de reglas. Codex: prepara encargos, coordina y revisa. Claude: implementa el hito asignado. Especificación raíz: fuente de verdad funcional.

## Ciclo por hito

1. El autor entrega a Claude el encargo preparado. Antes de editar, Claude informa rama y archivos que tocará.
2. Una sola persona o agente escribe en esta carpeta a la vez. Git comparte índice y rama: no cambiar ramas mientras el otro edita. Para concurrencia real, usar worktrees distintos y ramas independientes.
3. Rama por hito desde `main` limpio y actualizado; conservar cambios ajenos. No usar `git add .`, borrados, resets ni force push. Revisar y añadir rutas explícitas.
4. Claude entrega resumen, diff, comandos, resultados reales y pendientes. Codex revisa semántica, independencia del auditor y evidencia; comunica correcciones al autor para que las entregue a Claude.
5. Integrar en `main` después de revisión y aprobación del autor. No avanzar de hito con su puerta de salida pendiente.

No existe comunicación automática entre esta conversación y la terminal de Claude. El autor transmite encargos y avisa cuándo comienza cada revisión.

## Publicación

El repositorio es público. La lista blanca de `.gitignore` admite exclusivamente documentación técnica neutra y el esquema aprobados para revisión. Que una ruta sea visible para Git no equivale a que esté publicada. Los commits locales y la publicación remota son pasos separados.

El material local y las copias de distribución quedan excluidos. Publicar únicamente código, documentación técnica y datos sintéticos revisados. Revisar `git diff --cached` antes de cualquier commit; añadir excepciones de código por hito y rutas explícitas, nunca abrir toda la carpeta.

## Plantilla de encargo y entrega

Cada encargo debe incluir objetivo, rama, rutas permitidas, exclusiones, comandos de validación y condición de cierre. Cada entrega debe incluir estado real, archivos cambiados, comandos y salidas, limitaciones y solicitud de revisión. No presentar pruebas previstas como ejecutadas.
