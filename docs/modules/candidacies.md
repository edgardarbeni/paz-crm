# Módulo: Candidaturas

**Estado:** implementado (fase D, [D-71](../adr/D-71-fase-d-aprobada.md); panel en la fase E).
**Código:** `backend/app/modules/candidacies/` · esquema `candidacies` · migraciones `0007` a `0009`.
**Modelo:** [`reference/data-model.md` §4](../reference/data-model.md#4-candidaturas-candidacies).

## Propósito y usuarios

Registra y da seguimiento a las candidaturas del partido en cada proceso electoral, federal o local:
quién se postula, a qué cargo, en qué geografía, por qué partido o alianza y en qué estatus va.

| Usuario (rol sembrado) | Qué hace |
|---|---|
| `admin` | Administra catálogos (partidos, cargos) y configura procesos electorales |
| `coordinator` | Captura, envía y aprueba postulaciones; cambia estatus, sustituye y acepta excepciones a reglas |
| `capturist` | Captura postulaciones y fórmulas (sin aprobar) |
| `viewer` | Consulta |

Todos operan dentro de su alcance geográfico (ver «Permisos y alcance»).

**Pantallas del panel** (`frontend/src/routes/_app/`):
- `parties` y `office-types`: partidos y cargos (alta y edición).
- `processes`: lista y detalle con pestañas de cargos, integración de ayuntamientos (admite pegar
  desde una hoja de cálculo), reglas y coaliciones (`features/candidacies/process/`).
- `nominations`: lista con filtros, alta (`new`) y editor de planillas y listas
  (`$nominationId`). El editor permite capturar solo con teclado, dar de alta personas rápido,
  ver avisos de validación y hacer la validación en seco. También cambia estatus, sustituye,
  acepta excepciones y muestra el historial.

## Dependencias

| Módulo | Qué usa (no se redefine aquí) |
|---|---|
| `people` | `people.persons`: toda persona integrante de una fórmula. Se busca y da de alta desde el editor |
| `geography` | Marco geográfico (`framework_id` del proceso), nodos (estado, circunscripción, DF, DL, municipio) y secciones |
| `identity` | `CurrentUser`, permisos `Perm.*` y `GeoScope` (alcance materializado en `identity.user_scope_sections`) |
| `core` | `BusinessTable`, `AuditedSession`, `paginate`, errores RFC 9457 |

## Entidades y relaciones

**Catálogos (datos, no código):**
- `office_types`: cargos. Cada uno tiene `code`, `election_level` (federal | local) y
  `geographic_level` (national | electoral_region | state | federal_district | local_district |
  municipality). También `principle`: MR (mayoría relativa) o RP (representación proporcional).
  Y `nomination_kind`:
  - `single`: un cargo solo;
  - `slate`: encabeza una planilla;
  - `list`: lista ordenada;
  - `member`: solo existe dentro de una planilla ([D-65](../adr/D-65-ajustes-implementacion-personas-candidaturas.md)).

  Lleva además `default_positions`, `has_substitute` y `sort_order`. Se siembran 14 cargos
  (migración 0008); los nuevos se agregan por API sin migraciones
  ([D-70](../adr/D-70-cargos-partidos-como-datos.md)).
- `parties`: partidos. Se siembra solo PAZ (`is_own_party`).
- `validation_rules`: las 4 reglas del motor, con `default_params`.

**Configuración electoral por proceso** ([D-23](../adr/D-23-modulo-configuracion-electoral.md)):
- `electoral_processes`: nombre, año, `process_type` (ordinario | extraordinario),
  `election_level` (federal | local) y `state_id` (obligatorio si es local). También
  `framework_id`, `election_date` y `status`, que pasa de `draft` a `active` y luego a `closed`.
- `process_offices`: qué cargos van a elección, con:
  - `positions`;
  - `slate_parent_office_type_id`: qué cargo encabeza la planilla de la que forma parte;
  - `rp_method` (`closed_list` | `best_loser` | `mixed`) y `rp_method_params`
    ([D-21](../adr/D-21-rp-local-configurable.md)).
- `municipality_settings`: por municipio y proceso, `election_regime` (`party_based` |
  `normative_system`), `mr_councilor_count`, `rp_councilor_count` y `syndic_count`
  ([D-24](../adr/D-24-regidurias.md) a [D-26](../adr/D-26-regimen-municipal.md)).
- `process_validation_rules`: activa o inactiva, `severity` (`blocking` | `warning`) y `params`
  por proceso o por cargo.
- `coalitions` (`coalition` | `common_candidacy`) + `coalition_parties`
  ([D-27](../adr/D-27-partidos-alianzas.md)).

**Postulaciones** ([D-41](../adr/D-41-modelo-datos-aprobado.md), punto 3: una sola estructura para todos los cargos):
- `nominations`: proceso, cargo principal, geografía y postulante (`party_id` **o**
  `coalition_id`, exactamente uno). La geografía usa una sola FK, la del `geographic_level`;
  en `national` no lleva ninguna. Además tiene `status` y `notes`.
- `formulas`: cada posición de la postulación, con `office_type_id`, `position`, `status`,
  `origin_party_id` (partido de origen en una coalición), `replaces_formula_id` y
  `substitution_reason`.
- `formula_members`: propietario (`owner`) y suplente (`substitute`), ligados a
  `people.persons`, con `process_id` denormalizado para validar duplicados.
- `formula_status_history`: cada transición, con quién, cuándo y motivo.
- `rule_overrides`: excepciones aceptadas, una fila por violación.
- Vista `nomination_sections` (migración 0009): las secciones que cubre cada postulación.

**Cómo se representa cada cargo** (posiciones según la configuración del proceso):

| Cargo (brief) | Postulación: cargo principal · nivel | Fórmulas |
|---|---|---|
| Planilla municipal: presidencia, sindicatura y regidurías | `municipal_president` · municipio | Presidencia (1); sindicatura(s) si van en planilla; regidurías MR 1..n; regidurías RP 1..n. Los conteos vienen de `municipality_settings` |
| Sindicatura electa por separado | `syndic` · municipio | 1..n |
| Alcaldía de CDMX | `mayor` · municipio | Alcaldía (1) + concejalías 1..n |
| Diputación local MR | `local_deputy_mr` · DL (distrito local) | 1 |
| Diputación local RP | `local_deputy_rp` · estado | 1..n; con `best_loser` no se registra lista (0 posiciones) |
| Diputación federal MR | `federal_deputy_mr` · DF (distrito federal) | 1 |
| Diputación federal RP | `federal_deputy_rp` · circunscripción | 1..40 |
| Gubernatura | `governor` · estado | 1 |
| Senaduría MR | `senator_mr` · estado | 2 fórmulas con posición; la 1 es la que puede entrar por primera minoría ([D-22](../adr/D-22-senado-presidencia.md)) |
| Senaduría RP | `senator_rp` · nacional | Lista nacional cerrada de 32 |
| Presidencia de la República | `president` · nacional | 1 |

**Toda candidatura es una fórmula propietario + suplente** (`has_substitute = true` por defecto).

**Ciclos de vida** ([D-68](../adr/D-68-ciclo-vida-postulaciones-formulas.md)):
- **Postulación:** `draft` → `submitted` → `approved`; desde cualquiera, `cancelled`.
- **Fórmula:** `aspirant` → `registered` → `approved`; también `substituted` o `cancelled`.
- Cada cambio de estatus de una fórmula queda en `formula_status_history`.

## Reglas de negocio

**Creación de una postulación** ([D-68](../adr/D-68-ciclo-vida-postulaciones-formulas.md)):
- El cargo debe estar habilitado en el proceso y no ser `member` de una planilla.
- El nodo debe ser del nivel del cargo y del marco del proceso; si el proceso es local, debe
  estar en su estado.
- Un municipio con `normative_system` no admite postulaciones de partido (409).
- Con `best_loser` la lista RP espera 0 posiciones.
- Una sola postulación activa por geografía, cargo y postulante (índice único parcial). Al
  cancelarla, la geografía se libera.

**Fórmulas:**
- Se agregan y editan solo con la postulación en `draft` y la fórmula en `aspirant`. Después
  solo cambian por transición o sustitución.
- Hay una sola fórmula vigente por posición:
  `UNIQUE (nomination_id, office_type_id, position) WHERE status NOT IN ('substituted','cancelled')`.
- En coaliciones, `origin_party_id` debe pertenecer a la coalición.

**Transiciones:**
- `aspirant → registered`: captura.
- `registered → approved`: requiere `candidacies.nomination.approve`.
- `→ cancelled`: requiere motivo, y `nomination.approve` salvo desde `aspirant`.
- **Enviar** exige todas las posiciones esperadas y aplica todas las reglas, incluida la paridad.
- **Aprobar** requiere `nomination.approve`.
- **Cancelar** cancela las fórmulas vigentes.
- Un proceso `closed` deja todo en solo lectura (409).

**Sustitución** ([D-29](../adr/D-29-sustitucion.md)):
- Requiere `nomination.approve` y debe cambiar al menos a una persona: solo al suplente o a
  ambos.
- La fórmula original pasa a `substituted` y se crea una nueva en la misma posición, ligada por
  `replaces_formula_id` y con su motivo.
- **Suposición:** la nueva hereda el estatus de la reemplazada.

**Motor de validaciones** ([D-28](../adr/D-28-motor-validaciones.md), [D-67](../adr/D-67-motor-reglas-cuando-bloquea-se-acepta.md)):

| Regla (`code`) | Qué valida | Parámetros |
|---|---|---|
| `unique_person_in_process` | Una persona no integra más de una fórmula activa en el proceso | — |
| `substitute_same_sex` | El suplente es del mismo sexo que el propietario | `allow_male_owner_female_substitute` |
| `list_alternation` | Las posiciones consecutivas del mismo cargo alternan el sexo del propietario | — |
| `gender_parity` | Proporción mínima de mujeres entre los propietarios de la posición 1 del cargo principal, contando las postulaciones enviadas o aprobadas del mismo cargo en el proceso | `min_female_ratio` (0.5 por defecto) |

- **Por defecto** solo está activa `unique_person_in_process`, y es bloqueante. Todo lo demás se
  activa y parametriza por proceso, o por cargo, que prevalece. Cada regla puede ser bloqueante
  o solo advertencia.
- El parámetro efectivo es `default_params || params`; un parámetro desconocido se rechaza
  con 400.
- Las ediciones se juzgan por lo que **introducen** (antes contra después): una regla activada
  a mitad del proceso no congela la captura, pero sí se exige al enviar.
- La paridad solo se evalúa al enviar, al aprobar y en la validación en seco
  (`GET /nominations/{id}/validation`).
- Una violación bloqueante responde 409 `rule-violation` con `violations`.
- **Excepciones:** requieren `candidacies.rule.override`, un motivo y cubrir todas las reglas
  violadas. Se guarda una fila por violación en `rule_overrides`.

**Cargos y partidos como datos:**
- `PATCH /office-types/{id}` solo cambia nombre, posiciones por defecto, suplencia y orden. El
  código, los niveles, el principio y el tipo quedan fijos
  ([D-76](../adr/D-76-edicion-cargos.md)).
- Un proceso nuevo incluye todos los cargos deshabilitados.

**Lo que no se precarga** (suposiciones vigentes; no se inventan reglas electorales):
- Número de regidurías por municipio, si la sindicatura va en planilla o por separado, el
  régimen municipal y los parámetros de paridad: todo es configuración por estado y proceso
  ([D-24](../adr/D-24-regidurias.md), [D-25](../adr/D-25-sindicatura.md), [D-26](../adr/D-26-regimen-municipal.md), [D-28](../adr/D-28-motor-validaciones.md)).
- Paridad: cuenta como mujer el sexo `M`; `X` no suma a la cuota. Hay que confirmarlo según la
  ley de cada estado.
- Primera minoría del Senado: se infiere de la posición 1 de la lista estatal; el cálculo de
  resultados queda fuera.
- **Pendiente de definir:**
  - la regla de intercalado del método RP `mixed`. Se guarda en `rp_method_params`, pero el
    sistema no la interpreta todavía;
  - la paridad horizontal y vertical por bloques de competitividad (DT-24).

## Permisos y alcance

| Permiso | Uso | Roles sembrados |
|---|---|---|
| `candidacies.read` | Consultar catálogos, procesos y postulaciones | admin, coordinator, capturist, viewer |
| `candidacies.catalog.manage` | Partidos y cargos | admin |
| `candidacies.process.manage` | Procesos: cargos, municipios, reglas y coaliciones | admin |
| `candidacies.nomination.write` | Crear y editar postulaciones y fórmulas | coordinator, capturist |
| `candidacies.nomination.approve` | Aprobar, cancelar, sustituir y cambiar estatus | coordinator |
| `candidacies.rule.override` | Aceptar violaciones de reglas con motivo | coordinator |

El superadmin (`grants_all`) tiene todos.

**Alcance geográfico** ([D-34](../adr/D-34-alcance-geografico.md), `candidacies/scope.py`, vista `nomination_sections`):
- **Lectura:** una postulación es visible si comparte al menos una sección con el alcance
  (`readable_filter`, un `EXISTS` en la consulta del listado). Una ajena no aparece en el
  listado y su detalle responde 404.
- **Edición:** solo si **todas** sus secciones están en el alcance (`is_editable`). Si no, es de
  solo lectura (`editable: false`, 403 al editar).
- **Creación:** el nodo debe quedar completo dentro del alcance (`ensure_node_within_scope`).
- Las postulaciones nacionales solo las crea y edita un usuario con alcance nacional.
- Los catálogos y procesos no se filtran por alcance.

## Datos sensibles

- Este módulo no guarda datos personales propios: referencia a `people.persons`. La CURP, los
  contactos y el domicilio viven cifrados en `people` y salen enmascarados sin
  `people.person.read_sensitive`.
- **Auditoría:** toda escritura del ORM queda en `audit.audit_log`, igual que cada excepción a
  reglas, además de `rule_overrides`.
- **Hueco conocido** ([architecture.md §8](../architecture.md)): en `update_members`
  (`nominations.py:810`), el soft-delete de los integrantes anteriores se hace con una
  sentencia Core y no queda en la bitácora; solo se registra el alta de los nuevos.
- No hay auditoría de lectura.

## Volumen y rendimiento

- **Volumen esperado:** sin medición con datos reales. La planilla municipal más grande depende
  de la integración de cada ayuntamiento (30+ fórmulas, según DT-22).
- **Consultas críticas:**
  - el detalle de una postulación hace varias consultas (DT-22, sin medir);
  - `is_editable` sobre postulaciones estatales recorre todas las secciones del estado con
    `NOT EXISTS` (DT-23). Hay que medirlo con el país completo antes de abrir la captura a
    coordinadores estatales.
- **Apoyos:**
  - `nomination_sections` usa `UNION ALL` por nivel para que cada rama use su índice en
    `geography.sections`;
  - «persona no duplicada» usa el índice `formula_members (process_id, person_id)`.
- Las metas generales (p95 < 200 ms en lecturas y < 500 ms en escrituras) se describen en
  [`architecture.md`](../architecture.md). No hay benchmark específico de candidaturas.

## Integraciones y eventos

- **Consume:**
  - `people`: personas y la búsqueda o alta rápida desde el editor;
  - `geography`: nodos del marco del proceso y secciones, vía la vista `nomination_sections`;
  - `identity`: permisos y alcance.
- **Provee a `people`:** la visibilidad de una persona incluye a quienes integran una postulación
  visible para el usuario ([D-66](../adr/D-66-personas-visibilidad-enmascarado-permisos.md)). No
  se puede dar de baja a quien integra una fórmula vigente
  ([D-69](../adr/D-69-baja-personas-suposicion-confirmar.md)).
- **Cambio de marco:** `paz geo activate` remapea la geografía. Las postulaciones guardan FKs del
  marco de su proceso.
- **Eventos:** no hay bus de eventos. Los cambios quedan en `formula_status_history` y en la
  bitácora.

## Criterios de aceptación

| Escenario | Estado | Evidencia |
|---|---|---|
| Un proceso nuevo inicia con todos los cargos deshabilitados y solo «persona no duplicada» activa | ✅ | `test_process_starts_disabled_with_default_rules` |
| Habilitar cargos, posiciones, composición de planilla y método RP por proceso | ✅ | `test_configure_offices` |
| Régimen e integración de ayuntamientos por municipio (carga masiva), reglas y coaliciones | ✅ | `test_municipalities_rules_and_coalitions` |
| Un cargo nuevo se agrega sin migración | ✅ | `test_office_types_are_data` |
| La composición esperada de la planilla y las validaciones de creación (nivel, marco, estado, `normative_system`) | ✅ | `test_slate_composition_and_creation_checks` |
| Toda fórmula con propietario y suplente; validaciones de integrantes | ✅ | `test_formula_checks` |
| Cada regla con sus parámetros, bloqueante o advertencia, y apagado por cargo | ✅ | `test_unique_person_rule_and_override`, `test_configurable_rules_block_or_warn` |
| Paridad al enviar y en seco; transiciones con permisos; sustitución con historial completo | ✅ | `test_submit_parity_transitions_and_substitution` |
| Un proceso cerrado es de solo lectura | ✅ | `test_closed_process_is_read_only` |
| **Un usuario NO crea, edita ni ve postulaciones fuera de su alcance** | ✅ | `test_scope_read_vs_edit`, `test_national_nominations_need_national_scope` |
| Coalición con partido de origen | ✅ | `test_coalition_nomination_with_origin_party` |
| Captura de una planilla completa solo con teclado en el panel | ✅ | `frontend/e2e/candidacies.spec.ts` |
| Cobertura ≥ 85 % en servicios y validaciones | ✅ | Fase D: `nominations` 95 %, `rules` 94 %, `service` 96 %, `composition` 94 % |
| La edición de integrantes queda completa en la bitácora (bajas incluidas) | ❌ | Hueco de `update_members` |
| Planilla de 30+ fórmulas y edición estatal dentro de p95 < 200 ms | ⏳ | Sin medir (DT-22, DT-23) |

## Fuera de alcance

- Candidaturas de partidos rivales en la UI. El modelo ya soporta cualquier partido, pero el
  MVP opera solo PAZ y sus alianzas ([D-27](../adr/D-27-partidos-alianzas.md)).
- Cálculo de resultados y asignación de RP: mejor perdedor, primera minoría o intercalado
  `mixed`.
- Circunscripciones plurinominales locales ([D-08](../adr/D-08-diputaciones-locales-rp.md)).
- Paridad horizontal y vertical por bloques de competitividad (DT-24).
- Importación masiva de postulaciones por CSV (DT-25).
- Bajas de partidos, cargos, coaliciones y procesos; hoy solo hay alta y edición (DT-27).
- Precarga de reglas electorales por estado sin fuente oficial.
