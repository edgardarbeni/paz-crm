# D-83 · Alcance por rama del Movimiento de Paz (amplía D-34 y D-66)

- **Estado:** Propuesta
- **Área:** Movimiento de Paz · Identidad, acceso y auditoría

## Contexto

Un coordinador del MP puede necesitar ver la red completa debajo de un pacificador aunque
cruce estados ([peace-movement.md](../modules/peace-movement.md), «Alcance»). El alcance actual
([D-34](D-34-alcance-geografico.md)) solo resuelve secciones.

Tres choques con el código vigente:
1. **Personas.** `people/service.py:visible_filter` solo reconoce domicilio en el alcance,
   postulación visible o falta de domicilio ([D-66](D-66-personas-visibilidad-enmascarado-permisos.md)).
   Con alcance por rama, el pacificador se vería en el MP pero `/people/{id}` daría 404.
2. **Captura.** D-66 prohíbe registrar un domicilio fuera del alcance
   (`_ensure_address_in_scope`), así que no se podría inscribir a un recluta de otro estado.
3. **Antiescalamiento.** La regla de la ficha («solo sobre nodos que el actor ya puede ver»)
   no basta: ver el nodo X por su domicilio no implica ver su subárbol. Un admin estatal podría
   otorgar la rama de X y con ella la red en otros estados.

## Opciones de ubicación

**A. En `identity`: `identity.user_branch_scopes` y `GeoScope.branches` (lo que propone la ficha).**
- *A favor:* disponible en todo el sistema, como el alcance geográfico.
- *En contra:* `identity` (núcleo) referencia `peace_movement.members` y depende de un módulo de
  negocio, lo que empeora la diferencia 2 de `architecture.md` §8. Cada petición, de cualquier
  módulo, cargaría las ramas.

**B. En el módulo: `peace_movement.user_branch_scopes` (recomendada).**
- Una dependencia del MP resuelve las ramas solo en sus rutas y compone el predicado
  `geo.sections_filter(...) OR path <@ ANY(ramas)`.
- *A favor:* el núcleo no cambia; las demás rutas no pagan la consulta.
- *En contra:* otro módulo que quiera usar ramas tendría que importar el del MP.

## Reglas comunes a ambas opciones

- **Antiescalamiento:** solo se otorga la rama del nodo X si el actor no tiene restricción o si
  X está dentro de una rama que ya tiene (`X.path <@ rama_del_actor.path`). Ver X por su
  domicilio no basta.
- **Datos de la persona:** el MP sirve los datos personales del pacificador en sus propios
  endpoints, con su alcance (geográfico o por rama) y el enmascarado de D-66 según
  `people.person.read_sensitive`. `/people` sigue rigiéndose solo por la geografía.
- **Captura fuera del alcance geográfico:** el servicio de inscripción del MP llama a `people`
  con una excepción explícita a `_ensure_address_in_scope`, válida solo si el reclutador está
  dentro de una rama del usuario.
- **Conservación:** asignar o quitar una rama queda en la bitácora con el ORM (no repetir el
  hueco de `set_scopes`, diferencia 1).
