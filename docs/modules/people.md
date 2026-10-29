# Módulo: Personas

Paquete `backend/app/modules/people` · esquema `people` · API `/api/v1/people` · implementado
en la fase D ([D-71](../adr/D-71-fase-d-aprobada.md)).

## Propósito y usuarios
- Registro único y reutilizable de **personas físicas** con CURP validada. Es la base del
  futuro padrón (brief: «Persona: entidad independiente y reutilizable»). El módulo
  `people` está separado de `candidacies` desde el modelo aprobado
  ([D-41](../adr/D-41-modelo-datos-aprobado.md), punto 1).
- Hoy lo usan quienes capturan y revisan candidaturas: capturistas, coordinadores y
  administradores. Registran a propietarias y suplentes, buscan si una persona ya existe y
  gestionan su consentimiento de privacidad y su baja (derechos ARCO, LFPDPPP).
- Pantallas del panel:
  - `/people`: lista paginada con un solo buscador que detecta si el texto es una CURP, un
    teléfono (solo dígitos) o un nombre.
  - `/people/new`: alta.
  - `/people/$personId`: detalle con edición, baja y consentimientos.
  - Alta rápida (`QuickPersonDialog`) y autocompletado de personas (`searchPeopleItems`)
    dentro de la captura de fórmulas.

## Dependencias
- **identity:** `CurrentUser`, `permission(Perm.…)` y `GeoScope` (alcance por secciones,
  [D-34](../adr/D-34-alcance-geografico.md)). Los servicios de cifrado se obtienen de
  `ServicesDep` (`cipher`, `indexer`).
- **core:** `FieldCipher` y `BlindIndexer` (`app/core/crypto`), con cifrado de sobre y
  `KeyProvider` ([D-32](../adr/D-32-gestion-llaves.md)). También la bitácora automática
  (`AuditedSession`) y la paginación por cursor.
- **geography:** el domicilio referencia `states`, `municipalities`, `sections`, `localities`
  y `neighborhoods` del marco activo. Al activar un marco nuevo (`paz geo activate`), esa
  geografía se remapea por llave natural.
- **candidacies:** solo se lee `formula_members`, `formulas` y la vista `nomination_sections`,
  para la visibilidad y para bloquear bajas. No se redefine nada de ese módulo.

## Entidades y relaciones
ER completo en [`reference/data-model.md` §3](../reference/data-model.md#3-personas-people).

| Tabla | Campos clave | Notas |
|---|---|---|
| `persons` | `given_names`, `paternal_surname`, `maternal_surname`, `search_name` (generada), `birth_date`, `sex` (`H`/`M`/`X`), `birth_entity`, `curp_ciphertext`, `curp_hash`, `curp_coherence_overridden`, `key_version`, `purge_after` | `birth_entity` usa el código de dos letras de la CURP (`AS`…`ZS`, `NE` = extranjero, [D-65](../adr/D-65-ajustes-implementacion-personas-candidaturas.md)) |
| `person_contacts` | `contact_type` (`mobile`/`landline`/`email`), `value_ciphertext`, `value_hash`, `is_primary`, `key_version` | N por persona |
| `person_addresses` | `address_type` (`home`/`work`/`other`), `address_ciphertext` (calle, números, referencias), `postal_code`, FKs de geografía, `is_primary`, `key_version` | Solo uno vigente; al reemplazarlo el anterior queda con soft-delete |
| `privacy_consents` | `notice_version`, `channel` (`panel`/`paper`/`web`), `evidence_uri`, `accepted_at` | Historial de aceptaciones del aviso de privacidad |

**Ciclo de vida de una persona:**
1. **Activa.**
2. **Dada de baja:** `deleted_at` y `purge_after = hoy + 30 días`.
3. **Anonimizada** por `paz people purge`:
   - se borran contactos, domicilios y consentimientos;
   - el nombre queda como `[eliminado]`;
   - se borran apellido materno, fecha y entidad de nacimiento, y la CURP con su hash.

   La fila se conserva para no romper el historial de candidaturas
   ([D-69](../adr/D-69-baja-personas-suposicion-confirmar.md)).

## Reglas de negocio
- **CURP** ([D-30](../adr/D-30-validacion-curp.md), `people/curp.py`):
  - Se validan la estructura oficial, el dígito verificador (módulo 10 de RENAPO) y una
    fecha y una entidad válidas.
  - La coherencia con la fecha de nacimiento, el sexo y la entidad capturados se revisa
    aparte. No hay consulta a RENAPO.
  - Si la CURP es incoherente, la API responde 409 (`IncoherentCurpError`). Se puede forzar
    con `accept_curp_incoherence`, pero solo con `people.person.read_sensitive`
    ([D-66](../adr/D-66-personas-visibilidad-enmascarado-permisos.md), suposición). La persona
    queda marcada con `curp_coherence_overridden` y la respuesta incluye las advertencias.
  - El panel valida en línea con la misma regla (`features/people/curp.ts`).
- **Unicidad:** una sola persona vigente por CURP, mediante el índice único parcial sobre
  `curp_hash` donde `deleted_at IS NULL`. Un duplicado responde 409.
- **Contactos:** los teléfonos se normalizan y deben tener 10 dígitos; los correos se
  normalizan antes de cifrarse.
- **Domicilio:**
  - Los nodos geográficos deben existir, y la sección debe pertenecer al municipio indicado.
  - No se puede registrar un domicilio fuera del alcance del usuario.
  - Editar contactos o domicilio los **reemplaza**: los vigentes quedan con soft-delete y se
    insertan los nuevos.
- **Baja ARCO (cancelación):**
  - `DELETE /people/{id}` responde 409 si la persona integra una fórmula `aspirant`,
    `registered` o `approved`.
  - El plazo de 30 días (`PURGE_RETENTION_DAYS`) es una **suposición** pendiente de la
    política de privacidad del partido
    ([D-69](../adr/D-69-baja-personas-suposicion-confirmar.md)).
- **Solicitudes ARCO formales:** no tienen tabla propia; la baja se ejecuta directamente
  (DT-26). Los demás derechos ARCO (acceso, rectificación, oposición) están **pendientes de
  definir**.
- **Persona no duplicada en un proceso:** es una regla del módulo de candidaturas, no de este
  módulo ([D-28](../adr/D-28-motor-validaciones.md)).

## Permisos y alcance
| Permiso | Uso | Roles (migración 0008) |
|---|---|---|
| `people.person.read` | Buscar, ver detalle y consentimientos | admin, coordinator, capturist, viewer |
| `people.person.write` | Alta, edición y registro de consentimiento | admin, coordinator, capturist |
| `people.person.read_sensitive` | Ver datos sin enmascarar y forzar una CURP incoherente | admin, coordinator |
| `people.person.delete` | Baja ARCO | admin |

El superadmin (`grants_all`) tiene todos. Este módulo no agrega roles.

**Alcance** (`service.visible_filter`, [D-66](../adr/D-66-personas-visibilidad-enmascarado-permisos.md),
suposición). Con alcance limitado, una persona es visible si se cumple alguna de estas
condiciones:
1. su domicilio principal vigente está en una sección del alcance;
2. todavía no tiene domicilio, para poder capturarla;
3. integra una postulación que el usuario puede ver.

El filtro se aplica en la consulta de búsqueda y en el detalle. Si la persona no existe, la
API responde 404; si existe pero está fuera del alcance, 403.

## Datos sensibles
| Dato | Almacenamiento | Búsqueda | Sin `read_sensitive` se ve |
|---|---|---|---|
| CURP | `curp_ciphertext`, AES-256-GCM, contexto `people.persons.curp` | `curp_hash` (HMAC-SHA256), exacta | `GOME******MASRRN07` |
| Teléfonos y correos | `value_ciphertext`, contexto `people.person_contacts.value` | `value_hash`, exacta (solo teléfono en la API) | `******4567`, `m***@dominio` |
| Calle, números y referencias | `address_ciphertext` (JSON cifrado), contexto `people.person_addresses.address` | — | Ocultos |
| Nombre y apellidos | En claro ([D-31](../adr/D-31-cifrado-nivel-aplicacion.md)) | Trigramas sobre `f_unaccent(lower(search_name))` | Completo |
| Geografía del domicilio y CP | En claro ([D-31](../adr/D-31-cifrado-nivel-aplicacion.md)) | Por FK | Completo |

- Cada registro cifrado guarda su `key_version` para poder rotar llaves
  ([D-32](../adr/D-32-gestion-llaves.md)). El enmascarado ocurre en `people/router.py`.
- **Bitácora:** los valores `bytes` (cifrados y hashes) siempre se guardan como `***`. El
  test `test_create_encrypts_and_masks` verifica que la CURP y el teléfono no aparecen en
  claro en la base ni en `audit.audit_log`.
- **Lecturas:** el detalle (`GET /people/{id}`) queda en `audit.access_log` con
  `details.unmasked`, que indica si se devolvieron datos sin enmascarar
  ([D-89](../adr/D-89-bitacora-lecturas.md), [D-93](../adr/D-93-bitacora-alcance-y-enmascarado.md)).
  Las búsquedas no se registran.
- **Datos personales enmascarados en la bitácora** ([D-93](../adr/D-93-bitacora-alcance-y-enmascarado.md)):
  `Person` guarda como `***` el nombre, los apellidos, `search_name`, la fecha de nacimiento, el
  sexo y la entidad; `PersonAddress`, el código postal. La bitácora es inmutable
  ([D-37](../adr/D-37-bitacora-inmutable.md)), así que solo registra qué campos cambiaron. La
  geografía del domicilio se conserva.
- **Escrituras auditadas:** el reemplazo de contactos y domicilio en `update_person` y los
  borrados de `purge_due` usan el ORM, así que cada fila retirada o borrada queda en la
  bitácora ([D-93](../adr/D-93-bitacora-alcance-y-enmascarado.md)).

## Volumen y rendimiento
- **Volumen esperado:** pendiente de definir. El MVP solo carga las personas de las
  candidaturas; el padrón futuro cambiaría la escala.
- **Consultas críticas:**
  - búsqueda por nombre (índice GIN de trigramas);
  - búsqueda por CURP o teléfono (índices sobre los hashes);
  - filtro de alcance (`EXISTS` contra `identity.user_scope_sections` y
    `candidacies.nomination_sections`).
- **Paginación:** por cursor, `limit` ≤ 200 (el panel pide 50). Orden permitido:
  `paternal_surname` (por defecto), `given_names` y `created_at`.
- **Mediciones:** sin medición específica del módulo. La meta general es p95 < 200 ms en
  lecturas y < 500 ms en escrituras.
- No hay importación masiva de personas (DT-25).

## Integraciones y eventos
**Consume:**
- la geografía del marco activo, para validar el domicilio;
- `candidacies.formula_members` y `formulas`, para impedir la baja de quien integra una
  fórmula vigente;
- `candidacies.nomination_sections`, para la visibilidad.

**Lo consumen:**
- `candidacies`: las fórmulas referencian `persons.id` y la regla «persona no duplicada» la
  usa.
- `paz geo activate`: remapea la geografía de los domicilios al nuevo marco.

**Eventos:** no hay bus de eventos. El módulo emite las entradas de bitácora de cada
escritura del ORM (`create`, `update`, `soft_delete`).

**Tareas programadas:** `paz people purge` se ejecuta con cron usando el rol dueño de la base.

## Criterios de aceptación
Cubiertos por `tests/integration/candidacies/test_people.py` y `tests/unit/test_curp.py`:
- Alta con CURP, contactos y domicilio: nada sensible aparece en claro en `persons`,
  `person_contacts` ni `audit.audit_log`, y la respuesta enmascara sin `read_sensitive`.
- CURP con estructura o dígito inválidos: 4xx. CURP incoherente: 409, que solo se fuerza con
  `read_sensitive`. CURP duplicada: 409. El dígito verificador se coteja con python-stdnum en
  300 casos aleatorios.
- La búsqueda por nombre sin acentos, por CURP exacta y por teléfono exacto devuelve a la
  persona.
- Un usuario con alcance limitado no ve a personas con domicilio fuera de su alcance y no
  puede registrar un domicilio fuera de él (`test_scope_visibility`).
- El consentimiento queda registrado y listado. La baja fija `purge_after` y responde 409 si
  la persona está en una fórmula vigente. Después de `purge_due`, la persona queda anonimizada
  y sin contactos, domicilios ni consentimientos (`test_consents_and_arco_deletion`).
- Editar contactos o domicilio reemplaza los vigentes
  (`test_update_replaces_contacts_and_address`).
- El reemplazo y la purga quedan en la bitácora sin datos personales, y el detalle queda en
  `audit.access_log` (`test_audit_hardening.py`).

## Fuera de alcance
- **Padrón conjunto de personas** (movimiento por la paz y afiliación o militancia): es un
  módulo futuro del brief, sin definir.
- Tabla y flujo de solicitudes ARCO (DT-26), y los derechos de acceso, rectificación y
  oposición como procesos formales.
- Consulta a RENAPO para validar la CURP.
- Importación masiva de personas (CSV) (DT-25).
- Auditoría de lecturas de datos sensibles.
