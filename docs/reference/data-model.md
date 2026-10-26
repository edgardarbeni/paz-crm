# Modelo de datos — PAZOS MVP

**Estado:** aprobado el 2026-10-24 (D-41). **Base:** `docs/adr/`, el brief original (`docs/history/BRIEF_MVP.md`) y `docs/reference/DISENO_BD_GEOESPACIAL.md`. Antes se llamaba `docs/MODELO_DATOS.md`.

---

## 0. Convenciones

### Esquemas de PostgreSQL (uno por módulo)

| Esquema | Módulo (`app/modules/…`) | Contenido |
|---|---|---|
| `identity` | identity | usuarios, sesiones, 2FA, roles, permisos, alcances |
| `geography` | geography | marcos, geografía electoral y tradicional, importaciones, catálogos de códigos |
| `people` | **people** (nuevo) | persona y sus datos de contacto; base del futuro padrón |
| `candidacies` | candidacies | procesos, configuración electoral, partidos, postulaciones, fórmulas |
| `audit` | core | bitácora inmutable |

> `people` se propone como módulo propio, y no dentro de `candidacies`, porque la persona es la base del futuro padrón y de otros módulos (D-27, CLAUDE.md §Persona).

### Columnas comunes (se omiten en los diagramas)

| Tipo de tabla | Columnas |
|---|---|
| Tablas de negocio (identity, people, candidacies, `geographic_frameworks`) | `created_at`, `updated_at`, `deleted_at` (timestamptz) |
| Tablas geográficas importadas (D-04) | `created_at`, `updated_at`, `import_run_id → import_runs`, `is_active`, `source_id` / `source_control` cuando existan en la BGD |
| `audit.audit_log` (D-37) | solo `occurred_at` |

### Llaves
- PK `uuid` con `DEFAULT uuidv7()`.
- PK `bigint GENERATED ALWAYS AS IDENTITY` en: `blocks`, `locality_sections`, `section_parts`, `import_errors` (D-03).
- Las tablas puente usan PK compuesta.

### Nombres de constraints e índices

| Tipo | Patrón |
|---|---|
| PK | `pk_<tabla>` |
| FK | `fk_<tabla>_<columna>__<tabla_ref>` |
| Único | `uq_<tabla>_<cols>` |
| Índice | `ix_<tabla>_<cols>` |
| Índice GiST | `gx_<tabla>_<col>` |
| Check | `ck_<tabla>_<regla>` |

Se configura con la `naming_convention` del `MetaData` de SQLAlchemy.

### Enumeraciones
Columnas `text` con `CHECK (col IN (...))`, no `ENUM` de PostgreSQL. Agregar un valor es solo cambiar el check en una migración, sin el problema de `ALTER TYPE` dentro de transacciones. (Alternativa: `ENUM` nativo, más compacto pero más rígido.)

### Geometrías
`geometry(<Tipo>, 4326)` con índice GiST. En los diagramas, `geom_MultiPolygon` significa `geometry(MultiPolygon, 4326)`.

### Unicidad con soft-delete
Los `UNIQUE` de tablas de negocio son índices parciales `WHERE deleted_at IS NULL`.

---

## 1. Geografía (`geography`)

```mermaid
erDiagram
    geographic_frameworks ||--o{ import_runs : "registra"
    import_runs ||--o{ import_issues : "reporta"
    geographic_frameworks ||--o{ electoral_regions : "contiene"
    electoral_regions ||--o{ states : "agrupa"
    states ||--o{ municipalities : "contiene"
    states ||--o{ federal_districts : "contiene"
    states ||--o{ local_districts : "contiene"
    municipalities ||--o{ sections : "se compone de"
    federal_districts ||--o{ sections : "se compone de"
    local_districts ||--o{ sections : "se compone de"
    states ||--o{ sections : "contiene"
    sections ||--o{ section_parts : "subdividida en"
    municipalities ||--o{ localities : "contiene"
    localities ||--o{ locality_sections : "cae en"
    sections ||--o{ locality_sections : "contiene"
    sections ||--o{ blocks : "contiene"
    localities ||--o{ blocks : "agrupa"
    municipalities ||--o{ neighborhoods : "contiene"
    neighborhoods ||--o{ neighborhood_sections : "traslapa"
    sections ||--o{ neighborhood_sections : "traslapa"
    section_types ||--o{ sections : "tipifica"
    federal_district_types ||--o{ federal_districts : "tipifica"

    geographic_frameworks {
        uuid id PK
        text name UK "INE dic-2025"
        date cutoff_date
        text source_agreement "acuerdo INE"
        boolean is_active "UNIQUE parcial WHERE is_active"
        timestamptz activated_at
        text notes
    }
    import_runs {
        uuid id PK
        uuid framework_id FK
        text source_kind "bgd_shapefile"
        smallint state_code
        text source_uri "carpeta o .7z"
        char64 file_sha256 "huella de las capas"
        int source_srid "32611..32616"
        text_array layers_loaded
        text_array layers_missing
        boolean dry_run
        text status "running | succeeded | failed"
        jsonb counts "por tabla: inserted, updated, unchanged, deactivated (D-60)"
        int warning_count
        int error_count
        text message
        timestamptz started_at
        timestamptz finished_at
        text triggered_by "CLI / usuario (D-60)"
    }
    import_issues {
        bigint id PK
        uuid import_run_id FK
        text layer "SECCION, MANZANA..."
        int source_fid
        jsonb natural_key
        text severity "error | warning"
        text code "missing_parent, geometry_repaired, outside_section..."
        text message
    }
    electoral_regions {
        uuid id PK
        uuid framework_id FK
        smallint region_number "1-5, UK con framework"
        geom_MultiPolygon geom "ST_Union de estados"
    }
    states {
        uuid id PK
        uuid framework_id FK
        uuid electoral_region_id FK
        smallint state_code "ENTIDAD 1-32, UK con framework"
        text name
        geom_MultiPolygon geom
    }
    municipalities {
        uuid id PK
        uuid framework_id FK
        uuid state_id FK
        smallint municipality_code "UK con state_id"
        text name
        geom_MultiPolygon geom
    }
    federal_districts {
        uuid id PK
        uuid framework_id FK
        uuid state_id FK
        smallint district_number "UK con state_id"
        smallint district_type_code FK
        geom_MultiPolygon geom
    }
    local_districts {
        uuid id PK
        uuid framework_id FK
        uuid state_id FK
        smallint district_number "UK con state_id"
        geom_MultiPolygon geom
    }
    sections {
        uuid id PK
        uuid framework_id FK
        uuid state_id FK
        int section_number "UK con state_id"
        uuid municipality_id FK
        uuid federal_district_id FK
        uuid local_district_id FK
        smallint section_type_code FK
        geom_MultiPolygon geom
    }
    section_parts {
        bigint id PK
        uuid section_id FK
        geom_Polygon geom "ST_Subdivide, para punto-en-poligono"
    }
    localities {
        uuid id PK
        uuid framework_id FK
        uuid state_id FK
        uuid municipality_id FK
        int locality_code "UK con municipality_id"
        text name
        smallint locality_type_code FK
        smallint head_type_code FK "cabecera"
        geom_MultiPolygon geom "NULL si solo existe como punto"
    }
    locality_sections {
        bigint id PK
        uuid framework_id FK
        uuid locality_id FK
        uuid section_id FK "UK con locality_id"
        text name
        smallint status_code
        smallint head_type_code FK
        geom_Point geom
    }
    blocks {
        bigint id PK "PK compuesta con framework_id"
        uuid framework_id PK "llave de particion"
        uuid section_id FK
        uuid locality_id FK
        int block_number "UK con framework, section, locality"
        smallint status_code FK
        text dispersed_raw "DISPERSO crudo"
        int capture_case "CASO_CAPTU"
        geom_MultiPolygon geom
    }
    neighborhoods {
        uuid id PK
        uuid framework_id FK
        uuid state_id FK
        uuid municipality_id FK
        text source_key "llave natural, D-10"
        text name
        smallint neighborhood_type_code FK "CLASIFICAC"
        char5 postal_code
        text_array other_postal_codes
        text representation "polygon | point"
        geom_Geometry geom "NULL permitido"
    }
    neighborhood_sections {
        uuid neighborhood_id PK
        uuid section_id PK
        numeric overlap_ratio "0-1 del area de la colonia"
        numeric overlap_area_m2
        text source "ine_catalog | computed (D-57)"
    }
    section_types {
        smallint code PK
        text description "URBANO, MIXTO, RURAL"
        text description_source "catalogo INE + corte"
    }
    federal_district_types {
        smallint code PK
        text description
        text description_source
    }
```

**Catálogos de códigos con la misma forma** (`code`, `description`, `description_source`): `section_types`, `federal_district_types`, `block_statuses`, `locality_types`, `locality_head_types`, `neighborhood_types`. Los catálogos de capas fuera del MVP no se crean.

**Notas de geografía**
- **Llaves naturales de upsert (D-02):**

  | Tabla | Llave natural |
  |---|---|
  | `states` | `(framework_id, state_code)` |
  | `municipalities` | `(state_id, municipality_code)` |
  | `sections` | `(state_id, section_number)` |
  | `blocks` | `(framework_id, section_id, locality_id, block_number)` |
  | `neighborhoods` | `(municipality_id, source_key)` |

  Las tablas de nivel inferior se resuelven por la llave natural de su padre.
- **Consistencia de marco:** cada tabla lleva `framework_id` para filtrar el marco activo sin joins. La coherencia hijo-padre se garantiza con FKs compuestas `(framework_id, parent_id) → parent(framework_id, id)`.
- **Punto-en-polígono (< 50 ms p95):** índice GiST sobre `section_parts.geom` → `sections` → municipio, DL y DF por FK → estado → circunscripción. Son 5 joins por PK y un solo lookup espacial.
- **Búsqueda por nombre:** índices GIN `gin_trgm_ops` sobre `unaccent(lower(name))` en municipios, localidades y colonias.
- **Vector tiles:** `ST_AsMVT` sobre `geom` con `ST_SimplifyPreserveTopology` según el zoom. Si las métricas lo piden, se agregan columnas `geom_low` precalculadas en estados, municipios y distritos.
- **Particionado (D-14):** `blocks PARTITION BY LIST (framework_id)`. Por eso la PK es `(framework_id, id)`.

---

## 2. Identidad (`identity`)

```mermaid
erDiagram
    users ||--o| user_invitations : "invitado con"
    users ||--o{ password_reset_tokens : "solicita"
    users ||--o| totp_credentials : "enrola"
    users ||--o{ recovery_codes : "posee"
    users ||--o{ user_sessions : "abre"
    user_sessions ||--o{ refresh_tokens : "rota"
    refresh_tokens ||--o| refresh_tokens : "reemplaza a"
    users ||--o{ user_roles : "tiene"
    roles ||--o{ user_roles : "asignado"
    roles ||--o{ role_permissions : "otorga"
    permissions ||--o{ role_permissions : "incluido"
    users ||--o{ user_scopes : "limitado a"
    users ||--o{ user_scope_sections : "resuelto en"

    users {
        uuid id PK
        citext email UK
        text password_hash "Argon2id"
        text full_name
        text status "invited | active | locked | disabled"
        smallint failed_login_count
        timestamptz locked_until
        timestamptz last_login_at
        timestamptz password_changed_at
    }
    user_invitations {
        uuid id PK
        uuid user_id FK
        bytea token_hash UK
        uuid invited_by_user_id FK
        timestamptz expires_at
        timestamptz accepted_at
        timestamptz revoked_at "D-54"
    }
    password_reset_tokens {
        uuid id PK
        uuid user_id FK
        bytea token_hash UK
        inet requested_ip
        timestamptz expires_at
        timestamptz used_at
    }
    totp_credentials {
        uuid id PK
        uuid user_id FK "UK"
        bytea secret_ciphertext
        smallint key_version
        bigint last_used_step "anti-replay"
        timestamptz confirmed_at
    }
    recovery_codes {
        uuid id PK
        uuid user_id FK
        bytea code_hash
        timestamptz used_at
    }
    user_sessions {
        uuid id PK
        uuid user_id FK
        text device_label
        text user_agent
        inet ip_address
        text_array auth_methods "RFC 8176: pwd, otp (D-54)"
        timestamptz last_seen_at
        timestamptz expires_at
        timestamptz revoked_at
        text revoke_reason
    }
    refresh_tokens {
        uuid id PK
        uuid session_id FK
        bytea token_hash UK
        uuid parent_token_id FK "deteccion de reuso"
        timestamptz expires_at
        timestamptz used_at
        timestamptz revoked_at
    }
    roles {
        uuid id PK
        text code UK "superadmin, admin, coordinator, capturist, viewer"
        text name
        text description
        boolean requires_mfa
        boolean is_system
        boolean grants_all "superadmin (D-54)"
    }
    permissions {
        uuid id PK
        text code UK "candidacies.formula.update"
        text module
        text action "read | create | update | delete | approve | import..."
        text description
    }
    role_permissions {
        uuid role_id PK
        uuid permission_id PK
    }
    user_roles {
        uuid user_id PK
        uuid role_id PK
    }
    user_scopes {
        uuid id PK
        uuid user_id FK
        text scope_level "national | electoral_region | state | federal_district | local_district | municipality | section"
        uuid electoral_region_id FK
        uuid state_id FK
        uuid federal_district_id FK
        uuid local_district_id FK
        uuid municipality_id FK
        uuid section_id FK
    }
    user_scope_sections {
        uuid user_id PK
        uuid section_id PK "derivada, se recalcula"
    }
```

**Notas de identidad**
- **`user_scopes`:** una FK nullable por nivel, con `CHECK` de que solo esté llena la que corresponde a `scope_level`; para `national` todas van vacías. Así hay integridad referencial real, sin FK polimórfica.
- **`user_scope_sections` (D-34):** es una tabla derivada. Se recalcula al cambiar alcances o al activar un marco. Los repositorios filtran con `EXISTS (… user_scope_sections …)`, y "contenida por completo" se evalúa comparando el conjunto de secciones de la postulación contra el del usuario.
- **Nuevo marco geográfico:** los alcances se remapean por llave natural (estado + clave) al nuevo marco dentro del mismo proceso de activación.
- **TOTP:** `requires_mfa` en el rol hace el TOTP obligatorio si cualquiera de los roles del usuario lo exige.
- **WebAuthn:** queda preparado como extensión. Una tabla `webauthn_credentials` se agrega en una fase futura sin tocar las existentes.
- **Rate limiting y revocación:** viven en Redis, no en tablas.

---

## 3. Personas (`people`)

```mermaid
erDiagram
    persons ||--o{ person_contacts : "tiene"
    persons ||--o{ person_addresses : "reside en"
    persons ||--o{ privacy_consents : "acepta"

    persons {
        uuid id PK
        text given_names
        text paternal_surname
        text maternal_surname
        text search_name "generada: unaccent lower, GIN trgm"
        date birth_date
        text sex "H | M | X"
        text birth_entity "codigo CURP: AS..ZS, NE extranjero (D-65)"
        bytea curp_ciphertext
        bytea curp_hash UK "HMAC blind index"
        boolean curp_coherence_overridden
        smallint key_version
        date purge_after "LFPDPPP, purga programable"
    }
    person_contacts {
        uuid id PK
        uuid person_id FK
        text contact_type "mobile | landline | email"
        bytea value_ciphertext
        bytea value_hash "busqueda exacta"
        boolean is_primary
        smallint key_version
    }
    person_addresses {
        uuid id PK
        uuid person_id FK
        text address_type "home | work | other"
        bytea address_ciphertext "calle, numeros, referencias"
        char5 postal_code
        uuid state_id FK "geography"
        uuid municipality_id FK
        uuid section_id FK
        uuid locality_id FK
        uuid neighborhood_id FK
        boolean is_primary
        smallint key_version
    }
    privacy_consents {
        uuid id PK
        uuid person_id FK
        text notice_version
        text channel "panel | papel | web"
        text evidence_uri
        timestamptz accepted_at
    }
```

**Notas de personas**
- **Unicidad de CURP:** `uq_persons_curp_hash WHERE deleted_at IS NULL`.
- **Derechos ARCO:** la tabla de solicitudes llega con el módulo de padrón; el diseño ya soporta soft-delete y `purge_after`.
- **Geografía del domicilio:** se guarda en claro (D-31) y se remapea por llave natural al activar un nuevo marco.

---

## 4. Candidaturas (`candidacies`)

```mermaid
erDiagram
    electoral_processes ||--o{ process_offices : "habilita"
    office_types ||--o{ process_offices : "configurado en"
    office_types ||--o{ process_offices : "forma parte de planilla de"
    electoral_processes ||--o{ municipality_settings : "configura"
    electoral_processes ||--o{ process_validation_rules : "aplica"
    validation_rules ||--o{ process_validation_rules : "parametrizada en"
    electoral_processes ||--o{ coalitions : "registra"
    coalitions ||--o{ coalition_parties : "integra"
    parties ||--o{ coalition_parties : "participa"
    electoral_processes ||--o{ nominations : "contiene"
    office_types ||--o{ nominations : "cargo principal"
    parties ||--o{ nominations : "postula"
    coalitions ||--o{ nominations : "postula"
    nominations ||--o{ formulas : "posiciones"
    office_types ||--o{ formulas : "cargo"
    formulas ||--o| formulas : "sustituye a"
    parties ||--o{ formulas : "origen partidario"
    formulas ||--|{ formula_members : "propietario y suplente"
    formulas ||--o{ formula_status_history : "historial"
    nominations ||--o{ rule_overrides : "excepciones"
    formulas ||--o{ rule_overrides : "excepciones por formula"
    validation_rules ||--o{ rule_overrides : "forzada"

    electoral_processes {
        uuid id PK
        text name
        smallint election_year
        text process_type "ordinary | extraordinary"
        text election_level "federal | local"
        uuid state_id FK "obligatorio si es local"
        uuid framework_id FK "marco geografico usado"
        date election_date
        text status "draft | active | closed"
    }
    office_types {
        uuid id PK
        text code UK "municipal_president, syndic, councilor_mr, councilor_rp..."
        text name
        text election_level "federal | local"
        text geographic_level "municipality | local_district | federal_district | state | electoral_region | national"
        text principle "mr | rp"
        text nomination_kind "single | slate | list | member"
        smallint default_positions
        boolean has_substitute "default true"
        smallint sort_order
    }
    process_offices {
        uuid id PK
        uuid process_id FK
        uuid office_type_id FK "UK con process_id"
        boolean is_enabled
        smallint positions "40, 32, 2, RP local..."
        uuid slate_parent_office_type_id FK "sindicatura en planilla"
        text rp_method "closed_list | best_loser | mixed"
        jsonb rp_method_params "regla de intercalado"
    }
    municipality_settings {
        uuid id PK
        uuid process_id FK
        uuid municipality_id FK "UK con process_id"
        text election_regime "party_based | normative_system"
        smallint mr_councilor_count
        smallint rp_councilor_count
        smallint syndic_count
    }
    validation_rules {
        uuid id PK
        text code UK "gender_parity, list_alternation, substitute_same_sex, unique_person_in_process"
        text name
        text description
        jsonb default_params "D-65"
    }
    process_validation_rules {
        uuid id PK
        uuid process_id FK
        uuid validation_rule_id FK
        uuid office_type_id FK "NULL = todos los cargos"
        boolean is_enabled
        text severity "blocking | warning"
        jsonb params
    }
    parties {
        uuid id PK
        text acronym UK
        text name
        boolean is_own_party "PAZ"
        text color_hex
        text logo_uri
    }
    coalitions {
        uuid id PK
        uuid process_id FK
        text name
        text coalition_kind "coalition | common_candidacy"
    }
    coalition_parties {
        uuid coalition_id PK
        uuid party_id PK
    }
    nominations {
        uuid id PK
        uuid process_id FK
        uuid office_type_id FK "cargo principal de la postulacion"
        text geographic_level
        uuid electoral_region_id FK
        uuid state_id FK
        uuid federal_district_id FK
        uuid local_district_id FK
        uuid municipality_id FK
        uuid party_id FK "uno de party o coalition"
        uuid coalition_id FK
        text status "draft | submitted | approved | cancelled"
        text notes
    }
    formulas {
        uuid id PK
        uuid nomination_id FK
        uuid office_type_id FK
        smallint position
        text status "aspirant | registered | approved | substituted | cancelled"
        uuid origin_party_id FK "en coalicion"
        uuid replaces_formula_id FK
        text substitution_reason
    }
    formula_members {
        uuid id PK
        uuid formula_id FK
        uuid person_id FK "people.persons"
        uuid process_id FK "denormalizado para validar duplicados"
        text member_role "owner | substitute, UK con formula_id"
    }
    formula_status_history {
        uuid id PK
        uuid formula_id FK
        text from_status
        text to_status
        text reason
        uuid changed_by_user_id FK
        timestamptz changed_at
    }
    rule_overrides {
        uuid id PK
        uuid nomination_id FK
        uuid formula_id FK "NULL en reglas de la postulacion (paridad)"
        uuid validation_rule_id FK
        uuid overridden_by_user_id FK
        text reason
        jsonb details
    }
```

### Cómo se representa cada cargo

Cada **postulación** (`nominations`) tiene una geografía y un postulante (partido o coalición). Cada **fórmula** (`formulas`) es una posición dentro de la postulación con su cargo, y **siempre tiene propietario y suplente** (`formula_members`).

| Cargo | Postulación (`office_type` principal, nivel) | Fórmulas |
|---|---|---|
| Planilla municipal | `municipal_president` · municipio | presidencia (1), sindicatura(s) si van en planilla, regidurías MR 1..n, regidurías RP 1..n (los conteos vienen de `municipality_settings`) |
| Sindicatura por separado | `syndic` · municipio | 1..n |
| Alcaldía CDMX | `mayor` · municipio (alcaldía) | alcaldía (1) + concejalías 1..n |
| Diputación local MR | `local_deputy_mr` · DL | 1 |
| Diputación local RP | `local_deputy_rp` · estado | 1..n según `process_offices.positions`; con `best_loser` no se registra lista (D-21) |
| Diputación federal MR | `federal_deputy_mr` · DF | 1 |
| Diputación federal RP | `federal_deputy_rp` · circunscripción | 1..40 |
| Gubernatura | `governor` · estado | 1 |
| Senaduría MR | `senator_mr` · estado | 1..2 (la 1 es la de primera minoría) |
| Senaduría RP | `senator_rp` · nacional | 1..32 |
| Presidencia | `president` · nacional | 1 |

- **Composición de la planilla:** `process_offices.slate_parent_office_type_id` dice qué cargos forman parte de la planilla de otro. Por ejemplo, `syndic → municipal_president` cuando la sindicatura va en planilla, o `NULL` cuando se elige por separado. Agregar un cargo nuevo sigue siendo solo datos, sin migraciones.
- **Geografía de la postulación:** el `CHECK` exige que esté llena exactamente la FK que corresponde a `geographic_level` (ninguna en `national`), y que se cumpla una sola de `party_id` / `coalition_id`.
- **Posición única:** `UNIQUE (nomination_id, office_type_id, position) WHERE status NOT IN ('substituted','cancelled') AND deleted_at IS NULL`. Así, la sustitución (D-29) crea una fórmula nueva en la misma posición sin violar la unicidad.
- **Validaciones:** las reglas del motor (D-28) se evalúan en el servicio. "Persona no duplicada en el proceso" se apoya en el índice `formula_members (process_id, person_id)`, no en un `UNIQUE`, porque la regla es configurable.
- **Marco geográfico:** las FKs geográficas de la postulación pertenecen al `framework_id` del proceso; el servicio lo valida.
- **Vista `nomination_sections`:** `(nomination_id, section_id)` con las secciones que cubre cada postulación; con ella se decide lectura (traslape) y edición (contención) por alcance (D-34, D-65).

---

## 5. Auditoría (`audit`)

```mermaid
erDiagram
    audit_log {
        timestamptz occurred_at PK "particion mensual"
        uuid id PK
        bigint chain_seq UK "orden de la cadena"
        uuid actor_user_id "sin FK: la bitacora sobrevive al usuario"
        inet actor_ip
        text user_agent
        text request_id
        text action "create | update | delete | login | logout | mfa_enroll | import | ..."
        text entity_table "schema.tabla"
        text entity_id
        jsonb before "sensibles enmascarados"
        jsonb after
        bytea prev_hash
        bytea entry_hash "sha256 de prev_hash + contenido"
    }
```

- Escribe un rol de BD con solo `INSERT`, con un trigger que rechaza `UPDATE` y `DELETE` (D-37).
- La escritura se hace en la misma transacción que el cambio auditado, desde el servicio, con un hook de unidad de trabajo.
- Las importaciones no escriben por fila: quedan en `geography.import_runs` (D-36), que a su vez genera una entrada `import` en la bitácora.

---

## 6. Vista general entre módulos

```mermaid
erDiagram
    users ||--o{ user_scopes : ""
    user_scopes }o--|| states : "nodo asignado (o region, DF, DL, municipio, seccion)"
    user_scope_sections }o--|| sections : ""
    electoral_processes }o--|| geographic_frameworks : "usa"
    electoral_processes }o--o| states : "si es local"
    nominations }o--o| municipalities : "geografia segun nivel"
    formula_members }o--|| persons : "persona"
    person_addresses }o--o| sections : "domicilio"
    person_addresses }o--o| neighborhoods : ""
    import_runs }o--|| users : "ejecutado por"
    formula_status_history }o--|| users : "cambiado por"
```

---

## 7. Puntos a aprobar

1. **Módulo `people` separado** de `candidacies`.
2. **Enumeraciones como `text + CHECK`** en lugar de `ENUM` nativo.
3. **Postulación + fórmula** como estructura única para todos los cargos (planilla, lista o cargo único), con la composición de planillas configurable mediante `slate_parent_office_type_id`.
4. **`section_parts`** (secciones subdivididas) para cumplir < 50 ms p95 en punto-en-polígono.
5. **`user_scope_sections`** como conjunto derivado para filtrar por alcance en la capa de consulta.
6. **`framework_id` en todas las tablas geográficas** con FKs compuestas para garantizar la coherencia de marco.
7. **Remapeo por llave natural** de alcances y domicilios al activar un nuevo marco.
