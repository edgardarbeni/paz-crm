# D-90 · Auditoría de escrituras masivas (amplía D-36 y D-45)

- **Estado:** Aceptada (2026-10-29: opción B, una entrada por lote)
- **Área:** Identidad, acceso y auditoría

## Contexto

Dos operaciones del MP escriben miles de filas en una transacción:
- **Importación:** 50,000 filas en menos de 5 minutos. Cada fila crea persona, contacto,
  domicilio, consentimiento y pacificador: unas 250,000 entradas en la bitácora, todas
  serializadas por el candado de la cadena ([D-45](D-45-implementacion-bitacora.md)).
- **Reasignación:** reescribir `path` y `depth` de un subárbol de 10,000 nodos en menos de
  10 s, con SQL Core (no pasa por el hook).

[D-36](D-36-auditoria-importaciones.md) resolvió la geografía con una entrada por corrida, pero
la geografía es pública y de solo lectura; aquí son datos personales sujetos a ARCO.

## Opciones

**A. Una entrada por fila.**
- *A favor:* granularidad total.
- *En contra:* probablemente no cumple las metas; hay que medirlo con la semilla de 1 millón.

**B. Una entrada por lote, con IDs (recomendada).**
- La importación audita, por fila, solo la entidad de negocio que importa (el pacificador), y
  una entrada `member_import` por corrida con conteos; el detalle por fila queda en
  `member_import_runs` y `member_import_errors`.
- La reasignación escribe una entrada `member_reassigned` con el nodo, el reclutador anterior y
  el nuevo; las rutas del subárbol son derivadas y no se auditan una por una (como
  `user_scope_sections`).
- *A favor:* cumple D-45 (toda escritura deja rastro) sin cientos de miles de vueltas al
  candado.
- *En contra:* para saber qué persona entró en una corrida hay que cruzar con la corrida.

## Nota

La decisión se confirma con la medición de la fase 1 (semilla de 1 millón, profundidad ≥ 30).
