# D-91 · Jerarquía de reclutamiento con `ltree`

- **Estado:** Aceptada (2026-10-29: opción A, `ltree` materializado)
- **Área:** Movimiento de Paz · Modelo de datos

## Contexto

La pirámide de reclutamiento tendrá cientos de miles de nodos (se diseña para 1 millón) y
profundidad desconocida. Se necesita leer subárboles y ancestros sin recursión, y reasignar un
subárbol de 10,000 nodos en menos de 10 s.

La extensión `ltree` viene con PostgreSQL (contrib), está en la imagen propia
([D-43](D-43-imagen-propia-postgresql-18-postgis.md)) y la ofrecen DigitalOcean y RDS, pero no
está instalada: la migración 0001 solo crea `postgis`, `pg_trgm`, `unaccent` y `citext`.

## Opciones

**A. `ltree` materializado (recomendada).**
- `members.path` con la cadena de `tree_id` desde la raíz, índice GiST; `path <@` para
  subárboles y `path @>` para ancestros.
- `tree_id` es un `bigint` de secuencia usado solo como etiqueta. La PK sigue siendo UUIDv7.
  Con UUID como etiqueta una ruta de profundidad 30 mediría ~1 KB; con bigint, ~200 bytes.
  Encaja con el espíritu de [D-03](D-03-pk-hibrida.md).
- Reasignar es un `UPDATE` del subárbol (`subpath`), en una transacción.
- *A favor:* lecturas por índice sin recursión; reasignación en una sentencia.
- *En contra:* extensión nueva (migración con el rol dueño); rutas largas si la profundidad
  crece mucho.

**B. Closure table (`member_ancestors(ancestor_id, descendant_id, depth)`).**
- *A favor:* SQL estándar, sin extensión.
- *En contra:* filas de profundidad × nodos (≈ 30 millones con 1 millón y profundidad media
  30); reasignar borra e inserta todos los pares del subárbol.

**C. Solo `recruited_by_member_id` con CTE recursivo.**
- *A favor:* lo más simple de escribir.
- *En contra:* cada lectura de red recorre el árbol; no cumple p95 < 200 ms en redes grandes.
