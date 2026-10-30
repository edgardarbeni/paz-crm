# D-99 · Panel del Movimiento de Paz (fase 5)

- **Estado:** Aceptada (2026-10-29)
- **Área:** Movimiento de Paz · Panel

Pantallas del Movimiento de Paz con las convenciones de [D-75](D-75-convenciones-panel.md) y la
identidad de [D-78](D-78-identidad-visual-panel.md).

- **Menú «Movimiento de Paz»**, cada entrada visible con su permiso: Pacificadores
  (`member.read`), Validación (`member.validate`), Casas de Paz (`house.read`), Estadísticas
  (`stats.read`), Importar (`member.import`) y Configuración (`goal.manage`).
- **Pacificadores.** Lista con búsqueda por nombre y filtros de estatus y nivel en la URL. La
  ficha tiene:
  - avance contra la meta vigente, con semáforo (y casas consolidadas para el Embajador);
  - una tarjeta de red (activos por nivel, directos, pendientes y casas acreditadas, con la hora
    del cálculo);
  - pestañas: reclutas directos, red a 3 niveles, datos personales y la comparación de lo enviado
    por el enlace, e historial;
  - el **enlace de inscripción con su QR**, que genera la API (`referral_url` y
    `referral_qr_svg`, con `segno`, sobre `PAZ_PUBLIC_BASE_URL`);
  - las acciones según permiso y estatus: validar o rechazar, inscribir recluta, cambiar nivel,
    cambiar reclutador y registrar la salida.
- **Inscripción.** Reutiliza el formulario de persona (`PersonForm` gana `submitLabel` y
  `beforeSubmit`) o elige a una persona registrada. Agrega nivel, origen, reclutador, casa y el
  canal y la evidencia del consentimiento. Al inscribir se refrescan los contadores y la lista
  del reclutador.
- **Validación:** cola de pendientes con validar o rechazar en la misma fila.
- **Casas.**
  - Lista con filtros de atención (crédito pendiente, sin anfitrión o contacto, publicable).
  - Alta con horario, domicilio, coordenadas (o «Usar mi ubicación») y personas.
  - Ficha con consolidación, integrantes, reuniones con invitados, fotos, crédito, anfitrión y
    contacto, cierre y ubicación publicable.
- **Estadísticas:** activos por nivel geográfico desglosados por nivel de participación,
  crecimiento por día (barras con CSS, sin librería de gráficas) y exportación CSV.
- **Importar:** subida con dry-run, la ayuda de columnas, corridas que se actualizan solas
  mientras haya alguna en cola y errores por fila.
- **Configuración:** metas por nivel y de casas por estado o nacionales (con historial),
  semáforo y alerta de profundidad, coordinadores de zona y avisos de privacidad (avisos de
  ejemplo marcados).
- **Ramas** en la ficha del usuario (Administración → Usuarios), junto a su alcance geográfico.
- **Página pública `/inscripcion/{código}`**, fuera del panel, pensada para el celular:
  - el navegador resuelve la prueba de trabajo en segundo plano (Web Crypto, por lotes) mientras
    la persona llena el formulario;
  - la entidad sale de una lista de los 32 estados en el orden del INE (el mismo de los códigos
    RENAPO de la CURP);
  - cada nivel muestra con cuántas personas se compromete (meta nacional);
  - la CURP se valida al escribir, el aviso completo se puede leer ahí mismo y hay un campo
    trampa oculto.
- **E2E:** la semilla de Playwright agrega un aviso de ejemplo, una pequeña pirámide con una
  inscripción pendiente y el cálculo de agregados. Hay dos escenarios: validar, inscribir desde
  la ficha y verlo en la red; y la página pública completa con su prueba de trabajo.

*Motivo:* cubrir el flujo de captura, validación, seguimiento y configuración del MP sin
librerías nuevas en el panel.
