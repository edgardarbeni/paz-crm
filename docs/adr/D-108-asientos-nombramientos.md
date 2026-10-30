# D-108 · Asientos y nombramientos (fase 2 de la estructura; precisa D-105)

- **Estado:** Aceptada (2026-10-30)
- **Área:** Estructura del partido

Cómo quedó la fase 2 (migración `0020`).

**Asientos**
- `positions` tiene un asiento por cada cargo de cada órgano vigente. Se crean al instalar un
  órgano y al agregar un cargo al catálogo; la migración los creó para los 170 órganos
  sembrados (640 asientos).
- La Secretaría de Circunscripción tiene **cinco asientos** (`region_number` 1 a 5), porque el
  catálogo dice «Cinco Secretarías de Circunscripción». Como la clave de estado, el número de
  circunscripción no cambia entre marcos.
- Un asiento sin nombramiento vigente está vacante, con `vacant_since` desde que terminó el
  último.

**Nombramientos**
- Un asiento tiene a lo más un nombramiento vigente (índice único parcial). Nombrar en un asiento
  ocupado responde 409.
- El titular es una persona de `people` con CURP. Basta con que exista: no se exige que quien
  nombra la vea por su domicilio, porque los cargos cruzan territorios. El panel la busca en
  `/people`, que sí respeta el alcance.
- `ends_on` se propone con el periodo del cargo y se puede editar; la prórroga de una delegación
  también se registra editándolo.
- Terminar un nombramiento guarda la fecha y el motivo (`term_end`, `resignation`, `removal`,
  `death` u `other`). Nunca se borra.
- **Incompatibilidades:** si la persona ocupa un cargo incompatible, responde 409.
- **Periodos consecutivos (D-105):** cuenta los nombramientos inmediatos anteriores del mismo
  asiento con la misma persona (electos o designados). Al llegar al máximo responde 409. Los
  encargos de despacho y las delegaciones no cuentan.
- **Delegación Estatal (D-107):** es el tipo `delegate` y solo se admite donde
  `position_types.delegate_months` tiene valor. Hoy solo la Presidencia del Consejo Directivo
  Estatal, con 6 meses.
- Cada nombramiento guarda el rol por defecto de su cargo. Dar acceso con ese rol es la fase 3
  (D-104).

**Presídium (D-105)**
- Un asiento derivado no acepta nombramientos. Su titular es el titular vigente del asiento
  fuente del mismo estado (o el nacional).
- Si tiene varias fuentes, como la Vicepresidencia nacional, se registra cuál ocupa cada periodo
  en `derived_choices`. Mientras no se elija, el asiento aparece como «elección pendiente».

**Administración delegada (D-105; respuesta de Darío del 2026-10-30)**
- Se administra un asiento a través de una concesión con
  `party_structure.appointment.write` que cumpla dos condiciones: su nivel es **mayor** que el
  del asiento y su alcance contiene todo el territorio del asiento.
- Orden de niveles: nacional > circunscripción > estatal > distrital y municipal >
  coordinaciones territoriales.
- El nivel de una concesión depende de su origen:
  - si viene de un nombramiento, es el nivel de ese cargo;
  - si es manual, es **el de su alcance**: circunscripción, estado, distrito o municipio, y la
    sección cuenta como el nivel de las coordinaciones.
- Una concesión manual con alcance nacional, y el superadmin, administran **todos** los niveles,
  incluidos los cargos nacionales.
- Ejemplo: un admin con alcance estatal nombra en los comités distritales y municipales de su
  estado, pero no en los órganos estatales ni en los nacionales.

**API**
- `GET /bodies/{id}/positions`: asientos con su titular vigente, o el derivado.
- `GET` y `POST /positions/{id}/appointments`: historial y nombrar.
- `PATCH /appointments/{id}` y `POST /appointments/{id}/end`: corregir y terminar.
- `POST /positions/{id}/derived-choice`: elegir la fuente de un asiento derivado.
- `GET /people/{id}/appointments`: los cargos de una persona en órganos visibles.
- Permisos:
  - `party_structure.appointment.read`: admin, coordinator, viewer y los dos roles de la
    estructura;
  - `party_structure.appointment.write`: admin, coordinator y «Dirigente territorial».
