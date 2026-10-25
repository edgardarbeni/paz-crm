# Cierre de fase D — Personas y candidaturas

**Fecha:** 2026-10-25 · **Rama:** `feat/phase-d-candidacies` · **Estado:** implementada, pendiente de aprobación.

## Criterios de aceptación (PLAN_FASES.md)

| Criterio | Resultado | Evidencia |
|---|---|---|
| Tests de cada regla de validación con sus parámetros | ✅ | `test_nominations.py`: persona única con su excepción; suplente del mismo sexo; alternancia como advertencia; apagado por cargo; paridad con `min_female_ratio` al enviar y en la validación en seco. `test_processes.py`: parámetros desconocidos rechazados y `default_params \|\| params` efectivo |
| Tests de sustitución e historial | ✅ | `test_submit_parity_transitions_and_substitution`: transiciones y permisos, sustitución ligada con `replaces_formula_id`, historial completo `aspirant → registered → approved → substituted` y fórmula nueva con su estatus |
| Unicidad de CURP y cifrado (nada sensible en claro en la BD ni en la bitácora) | ✅ | `test_people.py`: CURP duplicada (409); la CURP y el teléfono no aparecen en claro en `persons`, `person_contacts` ni en `audit.audit_log`; blind index de 32 bytes; CURP validada contra python-stdnum con 300 casos aleatorios (`test_curp.py`) |
| Tests negativos de alcance para edición y lectura | ✅ | `test_scope_read_vs_edit`: no crea fuera del alcance (distrito que cruza municipios, lista estatal); lee las que se traslapan con `editable: false` y no puede editarlas (403); las ajenas no aparecen en el listado y dan 404. `test_national_nominations_need_national_scope`. Personas: `test_scope_visibility` |
| Cobertura ≥ 85 % en servicios y validaciones | ✅ | Total 96.3 %; `nominations` 95 %, `rules` 94 %, `service` (candidaturas) 96 %, `composition` 94 %, `people/service` 97 % |

## Entregables

| Área | Entregado |
|---|---|
| Modelos y migraciones | `0007`: 4 tablas de `people` y 13 de `candidacies`, con CHECKs de geografía por nivel, un solo postulante e índices únicos parciales (posición vigente, postulación activa, CURP). `0008`: siembra 14 cargos (Senado y Presidencia incluidos, D-22), las 4 reglas, el partido PAZ, 10 permisos y su asignación a roles. `0009`: vista `nomination_sections` |
| CURP (D-30) | Estructura oficial, dígito verificador RENAPO, fecha y entidad, coherencia con los datos capturados, enmascarado |
| Personas | `/api/v1/people`: búsqueda sin acentos por nombre (trigramas), por CURP o por teléfono vía blind index; alta y edición con contactos y domicilio cifrados; consentimientos; baja ARCO; `paz people purge` |
| Catálogos | `/parties`, `/office-types` (cargos nuevos como datos, D-70), `/validation-rules` |
| Configuración electoral (D-23) | `/processes` con `offices` (habilitar, posiciones, planilla, método de RP), `municipalities` (régimen y conteos, carga masiva), `rules` (activar, severidad y parámetros por proceso o cargo) y `coalitions` |
| Postulaciones | `/nominations`: creación validada, slots esperados según la configuración, completitud, `editable`, advertencias, validación en seco, envío, aprobación, cancelación e historial |
| Fórmulas | Alta con propietaria y suplente, edición en `aspirant`, transiciones de estatus, sustitución (D-29), partido de origen en coaliciones |
| Motor de reglas (D-28, D-67) | 4 reglas parametrizables, bloqueantes o advertencia; excepciones auditadas en `rule_overrides`; 409 `rule-violation` con `violations` |
| Remapeo de marcos | `paz geo activate` remapea también la geografía de los domicilios (cierra DT-21) |
| Pruebas | 197 tests (unidad e integración) sobre la BGD sintética; `alembic check` sin deriva |
| Documentación | D-65 a D-70, `MODELO_DATOS.md` actualizado, colección Bruno (`docs/api/people`, `docs/api/candidacies`), README |

## Errores encontrados y corregidos durante la fase

1. **Violaciones de la contraparte.** Al aceptar "persona no duplicada" en la fórmula nueva, la fórmula original seguía reportando la misma violación como pendiente. El motor ahora juzga cada edición por lo que introduce (antes vs. después) y registra la excepción de todas las fórmulas involucradas (D-67).
2. **Postulaciones nacionales editables con alcance estatal.** Con un solo estado cargado, un usuario con alcance estatal cubría todas las secciones y podía editar una postulación nacional que no podía crear. La edición de postulaciones nacionales ahora exige alcance nacional (D-68).
3. **Extensiones de RFC 9457.** El manejador ignoraba `extra` de los errores; ahora se agregan como miembros de extensión (así viaja `violations`).

## Suposiciones (a confirmar)

1. **Visibilidad de personas con alcance limitado:** domicilio en el alcance, postulación visible o sin domicilio aún (D-66).
2. **Forzar una CURP incoherente** usa el permiso `people.person.read_sensitive`; no hay un permiso aparte (D-66).
3. **Paridad:** cuenta como mujer el sexo `M`; `X` no suma a la cuota. Se evalúa sobre las cabezas (posición 1 del cargo principal) de las postulaciones enviadas o aprobadas del mismo cargo (D-67). Hay que confirmar contra la ley de cada estado.
4. **La fórmula sustituta hereda el estatus** de la reemplazada (D-68).
5. **Retención de 30 días** antes de anonimizar a una persona dada de baja (D-69).

## Deuda técnica

| # | Deuda | Cuándo atenderla |
|---|---|---|
| DT-22 | El detalle de una postulación hace varias consultas (slots, fórmulas, integrantes, reglas); con planillas de 30+ fórmulas conviene medirlo | Con datos reales en la fase E |
| DT-23 | `is_editable` sobre postulaciones estatales recorre todas las secciones del estado con `NOT EXISTS`; medir con el país completo cargado | Antes de abrir la captura a coordinadores estatales |
| DT-24 | La paridad solo cuenta cabezas de postulación; las reglas de paridad horizontal y vertical por bloques de competitividad no están modeladas | Cuando se defina la regla por estado |
| DT-25 | No hay importación masiva de personas ni de postulaciones (CSV) | Fase posterior |
| DT-26 | Las solicitudes ARCO no tienen tabla propia; la baja se ejecuta directo | Con el módulo de padrón |

## Riesgos

| # | Riesgo | Mitigación |
|---|---|---|
| R-9 | Reglas electorales mal parametrizadas por estado (paridad, alternancia, suplencias) | Todo es configuración y nada viene activado salvo "persona no duplicada"; la validación en seco muestra el efecto antes de enviar |
| R-10 | Uso del permiso de excepciones sin control | Cada excepción guarda quién, cuándo, la regla, la fórmula y el motivo; queda además en la bitácora |
| R-2 | (Fase A) contención en la cadena de auditoría | Sin cambios |
