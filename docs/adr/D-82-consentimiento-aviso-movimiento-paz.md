# D-82 · Consentimiento del aviso del Movimiento de Paz (amplía D-69)

- **Estado:** Aceptada (2026-10-29: opción A, extender `people.privacy_consents`)
- **Área:** Movimiento de Paz · Persona y datos sensibles

## Contexto

La afiliación al Movimiento de Paz (MP) es un dato personal sensible (LFPDPPP) y requiere un
consentimiento expreso con su propio aviso de privacidad ([peace-movement.md](../modules/peace-movement.md)).

Hoy `people.privacy_consents` guarda `notice_version`, `channel`, `evidence_uri` y
`accepted_at`:
- no distingue a qué aviso se refiere (general o del MP);
- su CHECK de `channel` solo admite `panel`, `paper` y `web`, y el MP necesita también
  `referral_link`, `import` y `field_app`;
- no guarda una huella del texto aceptado, que ayuda a probar un consentimiento expreso.

Además, `paz people purge` ([D-69](D-69-baja-personas-suposicion-confirmar.md)) **borra
físicamente** los consentimientos al anonimizar (`people/service.py`, `purge_due`).

## Opciones

**A. Extender `people.privacy_consents` (recomendada).**
- Columnas nuevas: `notice_code` (`general`, `peace_movement`; las filas existentes quedan en
  `general`) y `notice_text_sha256`.
- El CHECK de `channel` se amplía con `referral_link`, `import` y `field_app`.
- *A favor:* un solo lugar para el cumplimiento; la purga ARCO ya lo cubre.
- *En contra:* una migración en `people`, que otro módulo motiva.

**B. Tabla propia `peace_movement.consents`.**
- *A favor:* no toca `people`.
- *En contra:* la purga de D-69 tendría que conocer una tabla del MP (dependencia invertida) o
  esos consentimientos sobrevivirían a la baja ARCO.

## Consecuencias comunes

- `members.consent_id` es nulable con `ON DELETE SET NULL`: la purga borra el consentimiento y
  el nodo anonimizado se conserva.
- El formato y la forma de recabar el consentimiento expreso siguen pendientes de revisión
  jurídica (pregunta abierta 7 de la ficha). Esta ADR solo define dónde y cómo se guarda.
- **Catálogo de avisos** (al aceptar): `people.privacy_notices` (`code`, `version`, `text`,
  `text_sha256`, `valid_from`, `valid_to`) guarda cada versión del aviso. El consentimiento
  apunta a la versión aceptada y copia `notice_code` y `notice_text_sha256`, así que la prueba
  no depende de que el aviso siga en el catálogo. Ver [D-92](D-92-reglas-negocio-movimiento-paz.md).
