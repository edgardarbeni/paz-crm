# Módulo: Estructura del partido

**Estado:** especificación aprobada para diseño; sin implementar.
**Paquete propuesto:** `backend/app/modules/party_structure` · esquema `party_structure` · API
`/api/v1/structure`.
**Brief:** respuestas de Darío del 2026-10-30 y catálogo estatutario [`cargos_paz.md`](../reference/cargos_paz.md). Lo marcado
como **[SUPUESTO]** debe confirmarse; lo marcado como **[ADR]** requiere proponer una decisión con
alternativas antes de implementarse.

## Propósito y usuarios

Registrar quién ocupa cada cargo de la estructura del partido y, a partir de eso, **dar acceso al
sistema limitado al territorio que le corresponde a cada cargo**. La estructura tiene dos ramas:

1. **Cargos estatutarios:** comités, consejos, comisiones y coordinaciones que establece el
   estatuto, en los niveles nacional, estatal, distrital y municipal.
2. **Coordinaciones territoriales:** estructura operativa creada por agrupación de territorio:
   federales (grupos de distritos federales), locales (grupos de distritos locales) y
   seccionales (grupos de secciones).

Ambas ramas pueden **abrir o enlazar Casas de Paz** que no abrió un Embajador o un Constructor de Paz.

| Usuario | Qué hace |
|---|---|
| `admin` nacional | Configura catálogos e incompatibilidades; administra toda la estructura y las coordinaciones que cruzan estados |
| Cargo con permiso de gestión | Administra nombramientos y coordinaciones **dentro de su alcance y por debajo de su nivel** |
| Titular de un cargo | Opera el sistema con el alcance y el rol de sus cargos vigentes; puede abrir o enlazar Casas de Paz |

## Dependencias

| Módulo | Qué usa |
|---|---|
| `people` | `persons`: todo titular es una persona registrada con CURP (no necesita ser pacificador ni militante) |
| `geography` | Marco activo; circunscripciones y sus estados; distritos federales y locales; municipios; secciones |
| `identity` | Usuarios, roles, permisos, `user_scope_sections` y flujo de 2FA. Se **amplía** (ver abajo) |
| `peace_movement` | Casas de Paz (implementado): crédito a asientos de estructura y bandeja de casas por enlazar. El alcance por rama del MP (D-83) no cambia |
| `core` | `BusinessTable`, auditoría, `paginate`, errores RFC 9457, tareas programadas de la fase 0 del MP |

### Cambios a módulos existentes (requieren propuesta antes de implementar)

1. **`identity` — permisos con alcance por concesión. [ADR] Es la decisión más importante del módulo.**
   Hoy los roles y el alcance de un usuario se combinan por separado. Con cargos acumulables eso
   filtra permisos: si una persona es Directora Jurídica en Baja California y coordinadora
   seccional en Sonora, la unión simple le daría permisos jurídicos en Sonora. Cada concesión
   debe ser un par **(rol, alcance)**, y una acción se autoriza solo dentro del alcance de las
   concesiones que incluyen ese permiso. Las concesiones manuales actuales migran como pares.
2. **`identity` — origen de las concesiones.** Cada concesión registra su origen (`manual` o
   `appointment` con `appointment_id`) para revocarla automáticamente al terminar el nombramiento.
3. **`identity` — `users.person_id`.** La cuenta se liga a la persona, no al cargo.
4. **`identity` — alta por invitación.** Se reutiliza el flujo existente (D-35, D-55: invitación
   por correo, `invited` → `active`). TOTP obligatorio para toda cuenta originada en un cargo: los
   roles por defecto de la estructura se siembran con `requires_mfa`. **[SUPUESTO]** si un admin
   ajusta el rol de un nombramiento a uno sin `requires_mfa`, la cuenta conserva la exigencia.
5. **`peace_movement`** — sustituye los coordinadores de zona de D-92 (ver «Cambios al Movimiento de Paz»).

## Entidades y relaciones

### Catálogos (editables por admin; sembrados desde el estatuto)

| Tabla | Campos clave | Notas |
|---|---|---|
| `body_types` | `code`, `name`, `territorial_level` (`national`, `state`, `district`, `municipal`), `requires_installation`, `statutory_basis` | Órganos: Consejo Directivo Nacional, Comité Directivo Estatal, Comisión Política, Comité Nacional de Vigilancia, Comisión Nacional de Honor y Justicia, Comisión Nacional Electoral, Presídium, Coordinaciones Especiales, Coordinaciones de Causas, Comité Directivo Distrital, Comité Directivo Municipal o de Alcaldía, etc. |
| `position_types` | `body_type_id`, `code`, `name`, `scope_rule`, `electing_body`, `term_years`, `statutory_basis`, `default_role_id`, `derived_from_position_type_id`, `sort_order` | `scope_rule`: `body_territory` (por defecto), `circumscription` o `national` |
| `position_incompatibilities` | `position_type_a_id`, `position_type_b_id` | Pares que una misma persona no puede ocupar a la vez |
| `coordination_position_types` | `kind` (`federal`, `local`, `sectional`), `code`, `name`, `default_role_id` | Cargos del equipo de una coordinación territorial: siempre `coordinator`, más los que se configuren (por ejemplo, enlace u operador) |

Reglas de siembra:
- Se siembran todos los órganos y cargos de `cargos_paz.md`, con su artículo como `statutory_basis`.
- Los cinco cargos de **Secretaría de Circunscripción** usan `scope_rule = circumscription`.
- Los tres cargos del **Presídium** (nacional y estatal) son **derivados**: apuntan a su cargo de
  origen y heredan a su titular; no se capturan.
- Los 22 cargos de **Causas y Movimientos Sociales** y demás cargos temáticos nacionales tienen
  alcance nacional; lo que pueden hacer lo limita su rol.
- «Demás cargos que se creen» se agregan al catálogo sin migraciones.

### Órganos instalados y asientos

`bodies`: un órgano concreto en un territorio.

| Campo | Descripción |
|---|---|
| `body_type_id` | Tipo de órgano |
| `framework_id` | Marco geográfico (para órganos distritales y municipales) |
| `state_id`, `municipality_id`, `federal_district_id`, `local_district_id` | Territorio según el nivel. Un comité distrital elige al instalarse si es de distrito **federal o local** |
| `installed_on`, `installation_agreement` | Fecha y acuerdo del CDN que lo instala |
| `dissolved_on` | Fecha de disolución |

Los órganos nacionales y los 32 estatales se siembran instalados. Los distritales y municipales
**existen solo si se registra su instalación**; sus cargos no pueden nombrarse antes.

`positions`: el asiento concreto que se ocupa (por ejemplo, «Presidencia del Comité Directivo
Estatal de Baja California»). Pertenece a un `body_id` **o** a una `territorial_coordination_id`,
nunca a ambos; para Secretarías de Circunscripción guarda además `circumscription_id`.

### Nombramientos

`appointments`:

| Campo | Descripción |
|---|---|
| `position_id`, `person_id` | Asiento y titular |
| `kind` | `elected` · `designated` · `acting` (encargado de despacho) · `delegate` (Delegación Estatal en funciones de Presidencia) |
| `appointed_by`, `agreement_ref` | Órgano que elige o nombra y referencia del acuerdo |
| `starts_on`, `ends_on` | Periodo; `ends_on` se propone con `term_years` del cargo y es editable |
| `ended_on`, `end_reason` | Terminación real: `term_end`, `resignation`, `removal`, `death`, `other` |
| `grants_access` | Si el nombramiento da acceso al sistema (se decide en cada nombramiento) |
| `role_id` | Rol del acceso; por defecto el `default_role_id` del cargo, ajustable por un admin |
| `user_id` | Cuenta de la persona (se crea o reutiliza al dar acceso) |

- Un asiento sin nombramiento vigente está **vacante**; se registra desde cuándo.
- Sin suplencias: las ausencias se cubren con nombramientos `acting` o `delegate`.
- Historial completo: los nombramientos terminados no se borran.

### Coordinaciones territoriales

`territorial_coordinations`: `kind` (`federal`, `local`, `sectional`), `name`, `framework_id`,
`state_id` (obligatorio para `local`; derivado si todo su territorio está en un estado), `created_on`, `closed_on`.

| Tabla de territorio | Para | Regla |
|---|---|---|
| `coordination_federal_districts` | `federal` | Cualquier combinación de distritos federales, **aun de varios estados** |
| `coordination_local_districts` | `local` | Distritos locales de **un solo estado** |
| `coordination_sections` | `sectional` | Secciones de **un solo estado**, de cualquier municipio |

- Cada tabla lleva `added_on` y `removed_on`. **Exclusividad:** un distrito o sección pertenece a lo
  más a una coordinación vigente de su tipo (índice único parcial donde `removed_on` es nulo).
- Las coordinaciones son **independientes entre sí**: no hay jerarquía federal > local > seccional;
  la relación entre ellas la da la geografía.
- Se ligan al **marco geográfico**. Con un marco nuevo, el sistema propone la migración de cada
  coordinación (distritos o secciones equivalentes) y un admin la confirma. **[ADR]**
- Sus asientos son un `coordinator` más los cargos configurados del equipo, con nombramientos
  idénticos a los estatutarios (periodo, historial, acceso opcional).

## Reglas de negocio

### Nombramientos
- El titular debe ser persona registrada con CURP.
- Una persona puede ocupar varios cargos, salvo los pares de `position_incompatibilities`.
- Un asiento tiene a lo más un nombramiento vigente; nombrar a alguien en un asiento ocupado exige terminar primero el vigente.
- Los cargos derivados (Presídium) no aceptan nombramientos.
- **[SUPUESTO]** los cargos adicionales que el estatuto dice que aprueba el Comité Directivo Estatal se registran sin flujo de aprobación; el acuerdo va en `agreement_ref`.

### Acceso al sistema
- La cuenta es **una por persona**. Su acceso es la suma de las concesiones `(rol, alcance)` de sus nombramientos vigentes con `grants_access`, más las concesiones manuales.
- **Alcance de cada nombramiento** según `scope_rule` y el territorio del asiento:

  | Asiento | Alcance |
  |---|---|
  | Órgano nacional, cargos temáticos | Nacional |
  | Secretaría de Circunscripción | Su circunscripción (`scope_level = electoral_region`), resuelta a los estados del marco activo |
  | Órgano estatal o Delegación Estatal | Su estado |
  | Comité distrital | Su distrito federal o local |
  | Comité municipal o de alcaldía | Su municipio |
  | Coordinación federal o local | Sus distritos |
  | Coordinación seccional | Sus secciones |

- El alcance se recalcula al cambiar el territorio de una coordinación o el marco activo.
- **Revocación automática:** al registrar la terminación, o al llegar `ends_on` (proceso diario),
  se retiran las concesiones del nombramiento y se revocan las sesiones activas de la cuenta.
- Al dar acceso, se envía invitación por correo; **TOTP obligatorio** en el primer ingreso.

### Administración delegada
- `admin` nacional administra todo.
- Un usuario con permiso de gestión administra órganos, nombramientos y coordinaciones **solo dentro
  de su alcance** y **solo de nivel inferior** al de su cargo de mayor nivel. Orden de niveles:
  nacional > circunscripción > estatal > distrital y municipal > coordinaciones territoriales. **[SUPUESTO]**
- Las coordinaciones federales que cruzan estados solo las administra el nivel nacional.
- **Antiescalamiento:** nadie puede conceder un rol con permisos que no tiene, ni un alcance mayor al suyo.

### Casas de Paz (ver también «Cambios al Movimiento de Paz»)
- Cualquier asiento de estructura con nombramiento vigente (estatutario o de coordinación) puede
  **abrir** una casa o **enlazar** una de la bandeja de casas por enlazar, **sin importar la geografía**.
- El crédito queda en el **asiento** (`positions`), no en la persona: si cambia el titular, el nuevo lo hereda.
- Si la persona tiene varios cargos, elige con cuál asiento abre o enlaza.
- Una casa tiene **un solo crédito**: no se enlaza a estructura una casa acreditada a un Embajador o Constructor.

## Cambios al Movimiento de Paz

El MP ya está implementado (fases 0 a 5, D-82 a D-99). Este módulo cambia sus reglas de crédito
de casas; **supera la parte de D-92 sobre coordinadores de zona** y requiere una ADR nueva que
lo registre. `peace-movement.md` se actualiza al implementar, no antes.

| Hoy (D-92) | Cambia a |
|---|---|
| Cualquier pacificador abre una casa y el crédito se busca hacia arriba hasta el primer Embajador | Si la abre un **Embajador o un Constructor**, el crédito es suyo. Si la abre un Pacificador, Promotor o Mensajero, queda con **crédito pendiente** en la bandeja de casas por enlazar; ya no se busca en la cadena |
| Sin Embajador, el crédito va al coordinador de la zona que cubre la sección | Se eliminan `zone_coordinators`, `zone_coordinator_nodes` y `zone_coordinator_sections`. Las casas pendientes las abre o enlaza **cualquier asiento** de estructura |
| `credited_member_id` / `credited_user_id` | `credited_member_id` / `credited_position_id` (FK a `party_structure.positions`); a lo más uno |
| Solo el Embajador tiene meta de casas | El **Constructor** tiene meta de casas: semilla nacional de **1**, ajustable por estado en `level_goals.house_goal`, medida con casas consolidadas |
| Lista de casas con crédito pendiente para asignar a mano | Se conserva como **bandeja de casas por enlazar**, visible para quien tenga `peace_movement.house.link` |

Reglas que se mantienen: el crédito se fija al abrir o enlazar; `house.reassign_credit` sigue
reasignándolo con motivo e historial (`peace_house_credit_changes`), ahora también hacia asientos.

**Migración de datos existentes [SUPUESTO]:** las casas acreditadas a un usuario coordinador de
zona pasan al asiento vigente de esa persona si tiene exactamente uno; si no, quedan en la
bandeja. Las casas acreditadas a un Promotor o Mensajero por la regla anterior conservan su
crédito (no se recalcula, por la regla de D-92).

## Permisos y alcance

| Permiso | Uso | Roles base |
|---|---|---|
| `party_structure.catalog.manage` | Órganos, cargos, incompatibilidades, cargos de coordinación y roles por defecto | admin |
| `party_structure.body.read` | Consultar órganos y asientos | admin, coordinator, viewer |
| `party_structure.body.write` | Registrar instalación y disolución de comités | admin, coordinator |
| `party_structure.appointment.read` | Consultar nombramientos e historial | admin, coordinator, viewer |
| `party_structure.appointment.write` | Nombrar y terminar nombramientos | admin, coordinator |
| `party_structure.appointment.grant_access` | Dar acceso, invitar y ajustar el rol de un nombramiento | admin |
| `party_structure.coordination.read` | Consultar coordinaciones territoriales | admin, coordinator, viewer |
| `party_structure.coordination.write` | Crear coordinaciones y cambiar su territorio | admin, coordinator |
| `peace_movement.house.link` | Abrir o enlazar una casa con crédito a un asiento propio | Roles por defecto de los cargos |

Cada `position_type` y `coordination_position_type` define su rol por defecto. **[SUPUESTO]** se
crean roles base para la estructura (por ejemplo, dirigente territorial y coordinador territorial)
y los temáticos se agregan cuando existan sus módulos (jurídico, causas, etc.).

**Alcance de la gestión:** un órgano, asiento o coordinación es visible si su territorio se cruza
con el alcance del usuario. Los nombramientos nacionales son visibles para todos los que tengan
permiso de lectura.

## Datos sensibles

- La titularidad de un cargo partidista es información pública del partido, pero liga a la persona
  con una afiliación política: los datos de la persona siguen las reglas de `people`.
- Los cambios de concesiones y de alcance son operaciones de seguridad: quedan en la bitácora con
  el nombramiento que los originó.
- La invitación usa un token de un solo uso con expiración corta; no revela si el correo ya tenía cuenta.

## Volumen y rendimiento

- Asientos: miles (32 estados, hasta 300 distritos federales, 2,469 municipios aproximadamente,
  más coordinaciones). Nombramientos: decenas de miles con historial.
- Coordinaciones seccionales: hasta las ~70,000 secciones del país.
- Recalcular el alcance de una coordinación con 1,000 secciones: < 2 s.
- Revocación diaria por vencimiento: < 1 min para todo el país.

## Integraciones y eventos

- Al cambiar un nombramiento o el territorio de una coordinación se recalculan las concesiones
  y `user_scope_sections` de las cuentas afectadas.
- Al activar un marco geográfico nuevo: propuesta de migración de coordinaciones y comités distritales y municipales. **[ADR]**
- `peace_movement` consulta los asientos vigentes de la persona para abrir o enlazar casas.

## Criterios de aceptación

**Catálogo y órganos**
- La siembra crea todos los órganos y cargos de `cargos_paz.md`, con su fundamento.
- Un admin agrega un cargo nuevo a un órgano sin migraciones.
- No se puede nombrar en un comité distrital o municipal no instalado.
- El Presídium muestra como titulares a los de sus cargos de origen y rechaza nombramientos directos.

**Nombramientos y acceso**
- Nombrar a una persona en dos cargos incompatibles: 409.
- Un nombramiento con acceso crea o reutiliza la cuenta de la persona y envía invitación; el primer ingreso exige configurar TOTP.
- La Directora Jurídica de Baja California que además coordina secciones en Sonora no tiene permisos jurídicos en Sonora.
- La Secretaría de la tercera circunscripción ve exactamente los estados de esa circunscripción en el marco activo.
- Al terminar un nombramiento, la cuenta pierde ese alcance y sus sesiones se revocan; conserva el de sus otros cargos.
- Un nombramiento vencido por fecha se revoca en el proceso diario.

**Administración delegada**
- Un usuario con cargo estatal no puede nombrar en otro estado ni en cargos estatales o nacionales.
- Nadie puede conceder un rol con permisos que no tiene.
- Una coordinación federal con distritos de dos estados solo la crea o edita el nivel nacional.

**Coordinaciones territoriales**
- Agregar a una coordinación local un distrito de otro estado: 422.
- Agregar una sección que ya pertenece a otra coordinación seccional vigente: 409.
- Cambiar el territorio actualiza el alcance de sus titulares.

**Casas de Paz**
- Un titular de cualquier cargo vigente abre una casa en cualquier estado y el crédito queda en su asiento.
- Al cambiar el titular del asiento, el crédito permanece en el asiento.
- No se puede enlazar a estructura una casa acreditada a un Embajador o Constructor.

## Plan sugerido

1. ADR y cambios a `identity`: concesiones `(rol, alcance)`, origen de concesiones, `users.person_id`, invitación con TOTP obligatorio.
2. Catálogos, siembra estatutaria, órganos e instalación.
3. Asientos, nombramientos, incompatibilidades, cargos derivados y concesión automática de acceso.
4. Coordinaciones territoriales, exclusividad y recálculo de alcance.
5. Revocación por vencimiento y migración de marco.
6. Cambios al Movimiento de Paz: crédito a asientos, retiro de coordinadores de zona, meta de casas del Constructor y migración de datos.
7. Panel.

## Preguntas abiertas

1. ¿Qué pares de cargos son incompatibles? Se cargan desde el panel, pero conviene una lista inicial.
2. ¿Es correcta la migración propuesta para las casas acreditadas hoy a coordinadores de zona?
3. ¿El orden de niveles para la administración delegada es el propuesto?
4. ¿Qué roles base debe tener la estructura además de los actuales?
5. Al cambiar de marco, ¿los comités distritales instalados sobre distritos que desaparecen se disuelven o se migran?

## Fuera de alcance

- Metas propias de cargos y coordinaciones (Casas de Paz, pacificadores).
- Tableros de estadísticas por cargo o territorio.
- Flujos de elección o aprobación de órganos (congresos, votaciones); solo se registran sus resultados.
- Jerarquía entre coordinaciones territoriales.
