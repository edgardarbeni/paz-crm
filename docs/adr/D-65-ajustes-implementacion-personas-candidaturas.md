# D-65 · Ajustes de implementación de personas y candidaturas (sobre [`reference/data-model.md`](../reference/data-model.md) §3 y §4)

- **Estado:** Aceptada
- **Área:** Fase C — geografía

- **Entidad de nacimiento:** `persons.birth_entity` guarda el código de dos letras de la CURP (`AS`…`ZS`, `NE` = nacido en el extranjero) en lugar de `birth_state_code` numérico; así se compara directo con la CURP.
- **Parámetros de reglas:** `validation_rules.default_params` (jsonb con los valores por defecto) reemplaza `params_schema`. El parámetro efectivo es `default_params || params`; un parámetro desconocido se rechaza con 400.
- **`nomination_kind = member`:** distingue los cargos que solo existen dentro de una planilla (regidurías, concejalías) de los que pueden ir solos o en planilla (sindicatura).
- **`rule_overrides`:** lleva `nomination_id` y `formula_id` opcional (la paridad es de la postulación, no de una fórmula), más `details` con el mensaje aceptado.
- **`nominations.notes`:** notas libres.
- **Vista `candidacies.nomination_sections`:** secciones que cubre cada postulación según su nivel (UNION ALL por nivel). Es la base de las reglas de lectura y edición por alcance ([D-34](D-34-alcance-geografico.md)).
- **Conflictos de reglas:** un 409 `urn:pazos:problem:rule-violation` incluye el miembro de extensión `violations` (regla, severidad, mensaje, fórmula), según RFC 9457 §3.2.
