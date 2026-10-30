# D-110 · Coordinaciones territoriales (fase 4 de la estructura)

- **Estado:** Aceptada (2026-10-30)
- **Área:** Estructura del partido

Cómo quedó la fase 4 (migración `0022`).

**Una coordinación es un órgano.**
- Las coordinaciones federal, local y seccional son tres tipos de órgano fijos (nivel territorial
  `coordination`, con `coordination_kind`). Cada coordinación es un registro de `bodies` con
  nombre.
- Así sus asientos, nombramientos, historial, acceso y revocación son los de siempre (D-108 y
  D-109), sin duplicar código.
- Los cargos del equipo (D-105: siempre la coordinación, más los que se configuren) son cargos
  de esos tipos y se agregan con `POST /position-types`.
- La tabla `coordination_position_types` de la fase 1 se movió a `position_types` y se eliminó:
  los cargos «coordinator» pasaron a `federal_coordinator`, `local_coordinator` y
  `sectional_coordinator`. *Alternativa descartada:* tablas propias de asientos para
  coordinaciones, que duplicaban los nombramientos y el acceso.

**Territorio**
- Está en `coordination_federal_districts`, `coordination_local_districts` y
  `coordination_sections`, con `added_on` y `removed_on`; quitar un nodo le pone `removed_on`.
- **Exclusividad:** un nodo pertenece a lo más a una coordinación vigente de su tipo, con un
  índice único parcial.
- Las coordinaciones locales y seccionales abarcan un solo estado. Si no, responde 422.
- Una federal puede abarcar varios estados; en ese caso `state_code` queda vacío.
- No hay jerarquía entre coordinaciones (D-105): la relación entre ellas la da la geografía.
- **Cerrar** una coordinación exige que no tenga nombramientos vigentes, y libera su territorio.

**Alcance y nivel**
- Una coordinación es visible si alguno de sus nodos vigentes toca el alcance de quien consulta.
- Para crearla o cambiar su territorio se necesita una concesión con
  `party_structure.coordination.write` que cumpla dos condiciones:
  - su nivel es superior al de las coordinaciones (una concesión con alcance de sección no
    alcanza);
  - su alcance contiene el territorio actual y el nuevo.
- Una coordinación federal de varios estados solo la administra el nivel nacional (alcance sin
  restricción). Lo mismo vale para nombrar en sus asientos.

**El acceso sigue al territorio**
- El alcance de la concesión de quien ocupa un asiento de la coordinación son sus nodos vigentes
  (D-109).
- Al cambiar el territorio, las concesiones de sus titulares se ajustan solas con
  `grants.sync_scopes`, que agrega y quita solo lo que cambió.
- `user_grant_sections` inserta todas las secciones en una sola sentencia.
- Medido con 2,000 secciones sintéticas: dar de alta 1,000 secciones a una concesión tarda
  0.57 s y mover 500 tarda 0.39 s, bitácora incluida. La meta de la ficha era menos de 2 s.

**API y permisos**
- Rutas:
  - `POST /coordinations` y `GET /coordinations` (`kind`, `state_code`, `include_closed`);
  - `GET /coordinations/{id}`;
  - `PUT /coordinations/{id}/territory` (lista completa y fecha del cambio);
  - `POST /coordinations/{id}/close`.
- Sus asientos se consultan en `GET /bodies/{id}/positions`.
- Permisos:
  - `party_structure.coordination.read`: admin, coordinator, viewer y los dos roles de la
    estructura;
  - `party_structure.coordination.write`: admin, coordinator y «Dirigente territorial».
