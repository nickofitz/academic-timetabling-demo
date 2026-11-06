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

No se afirma superioridad de CP-SAT ni ahorro institucional. Los tamaños son objetivos de diseño, no mediciones. Los plazos y repartos del documento inicial son antecedentes históricos.

Los antecedentes se conservan localmente con hashes, fuera del control de versiones. Solo se distribuye documentación técnica vigente y revisada. Las copias anteriores quedan archivadas al regenerar los documentos.
