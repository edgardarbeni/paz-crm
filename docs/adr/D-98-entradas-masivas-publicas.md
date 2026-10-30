# D-98 · Entradas públicas y masivas del Movimiento de Paz (fase 4)

- **Estado:** Aceptada (2026-10-29)
- **Área:** Movimiento de Paz · Seguridad · Rendimiento

Cómo se implementaron la inscripción pública, la carga por lotes y la importación de
[peace-movement.md](../modules/peace-movement.md), con [D-86](D-86-proteccion-bots-inscripcion-publica.md),
[D-90](D-90-auditoria-escrituras-masivas.md) y [D-92](D-92-reglas-negocio-movimiento-paz.md). Precisa
a D-90 en un punto (auditoría de los pacificadores importados).

**Inscripción pública** (`/api/v1/public/peace-movement`, sin sesión)
- `GET /enroll/{código}` devuelve el aviso vigente, los niveles y un reto de prueba de trabajo.
  No dice quién invita.
- **Prueba de trabajo propia** (`app.core.pow`, al estilo ALTCHA, sin terceros):
  - un SHA-256 con número secreto menor a 100,000, firmado con HMAC (`PAZ_POW_SECRET`, o una
    llave derivada del secreto de JWT);
  - la sal lleva emisión y expiración (15 min);
  - Redis quema cada reto resuelto.
- **Defensas:** campo trampa (se acepta y se descarta), tiempo mínimo de llenado (3 s) y límites
  de 20 inscripciones por IP por hora y de 100 por código por día.
- **Sección:** se pide la entidad y la sección de la credencial de elector; el público no conoce
  los IDs.
- **La respuesta es la misma** (202) se haya registrado o no la CURP. Si la persona ya existe,
  no se sobrescribe: lo enviado se guarda cifrado en `members.intake_ciphertext` y quien valida
  lo ve con `read_sensitive`. Si ya era pacificador, no se crea nada.
- Exige aceptar el aviso y que su versión sea la vigente. La inscripción queda pendiente, con el
  canal `referral_link`.

**Carga por lotes** (`POST /peace-movement/members/batch`, hasta 500)
- Es idempotente por el `client_id` que genera el dispositivo (`member_intake_keys`, con hora y
  coordenadas de captura). Reenviar responde `duplicate` con el mismo `member_id`.
- Cada elemento corre en su propio savepoint: un error no tumba el lote y la respuesta trae el
  resultado por elemento.
- Las inscripciones quedan pendientes (`field_app`). Si eligieron casa, la guardan en
  `requested_house_id` y la integran al validarse (cierra lo pendiente de D-96).

**Importación** (`POST /peace-movement/imports`, CSV o .xlsx de hasta 20 MB y 100,000 filas)
- El archivo va a S3 y lo procesa el `scheduler` (`paz peace-movement process-imports`, cada
  minuto). Hay reporte por corrida y errores por fila.
- **Dry-run:** valida todo y no escribe. Los reclutadores que están en el mismo archivo se
  validan como filas.
- **Columnas** (encabezados sin acentos ni mayúsculas): `nombre`, `apellido_paterno`,
  `apellido_materno`, `curp`, `celular`, `correo`, `calle`, `numero_exterior`, `codigo_postal`,
  `entidad`, `seccion`, `nivel` (código o nombre; si no viene, el nivel por defecto de la
  corrida), `codigo_reclutador` o `curp_reclutador`, `origen` y `detalle_origen`.
- **Orden:** por «olas», cada reclutador del archivo antes que sus reclutas. Un ciclo de
  reclutadores (`recruiter-cycle`) o un reclutador con error (`recruiter-row-failed`) se
  reportan por fila.
- **Paralelismo:** dentro de una ola, trozos de 250 filas en paralelo (4 a la vez), cada uno en
  su transacción y cada fila en un savepoint.
- **Estatus:** las filas entran activas (D-92), con el alcance del usuario que subió el archivo.
- **Bitácora (precisa a D-90):** en una importación, las personas, sus contactos, domicilios y
  consentimientos **y también los pacificadores** se auditan con una entrada por trozo
  (`member_import`, con los IDs de pacificadores y personas). Auditar cada pacificador por fila
  hacía que los trozos paralelos esperaran el candado de la cadena hasta el commit (D-45). La
  sesión lo indica con `audit_skip_tables`.
- **Sin bloqueo del reclutador:** el alta por lotes no bloquea su fila con `FOR UPDATE`, porque
  dos trozos con los mismos reclutadores caían en deadlock; la llave foránea mantiene la
  referencia.
- **Por corrida se cachean** el aviso, la configuración, los niveles, el estado de cada sección
  y los reclutadores ya autorizados.

**Medición** (base desechable, PostgreSQL por defecto, portátil): 50,000 filas en **180 s**
(meta: menos de 5 minutos); el dry-run, en 128 s.

*Motivo:* cumplir la meta de importación y la protección pública sin servicios de terceros ni
workers nuevos.
