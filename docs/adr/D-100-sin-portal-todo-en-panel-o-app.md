# D-100 · Sin portal de pacificadores: la App y el panel (reemplaza D-87)

- **Estado:** Aceptada (2026-10-29)
- **Área:** Movimiento de Paz

Decisión de Darío del 2026-10-29: **no habrá un portal de pacificadores**.

- Lo que la ficha asignaba al portal pasa a la **App** (Flutter): que el pacificador vea a sus
  reclutas y su avance, inscriba reclutas y comparta su enlace y QR. La App también cubre la
  captura en campo sin conexión. La App no se construye todavía; cuando se diseñe se decidirá
  cómo se autentican los pacificadores en ella, junto con
  [D-88](D-88-autenticacion-dispositivos-campo.md) (dispositivos y brigadistas).
- [D-87](D-87-cuentas-portal-pacificadores.md) (cuentas del portal) queda **reemplazada**: no hay
  portal ni audiencia de token `portal`.
- **Todo lo demás vive en el panel**, incluido lo que la ficha dejaba como entrega posterior
  fuera de él:
  - el **mapa de Casas de Paz** (antes «mapa público») es una pantalla del panel
    (`/peace-movement/houses/map`) para los usuarios con `peace_movement.house.read`, con puntos
    aproximados ([D-85](D-85-ubicacion-casas-paz.md));
  - el consentimiento de ubicación publicable se sigue registrando, para cuando la App o una
    salida pública muestren la ubicación exacta.
- La página pública de inscripción (`/inscripcion/{código}`, [D-98](D-98-entradas-masivas-publicas.md))
  la sirve la misma aplicación del panel.

Integraciones del panel hechas con esta decisión:
- el mapa de casas, con agrupación por cercanía y clic a la ficha;
- elegir el punto de una casa nueva en el mapa, y un mapa pequeño en la ficha de cada casa;
- la participación en el MP en la ficha de cada persona, con «Inscribir en el Movimiento de Paz»
  (la inscripción llega con la persona ya elegida);
- la pestaña «Lecturas sensibles» en la bitácora (`audit.access_log`, [D-89](D-89-bitacora-lecturas.md));
- en el inicio, los accesos del MP y el aviso de inscripciones pendientes de validar.

*Motivo:* una sola aplicación para el personal (el panel) y otra para quienes están en campo (la
App), sin una tercera superficie que mantener.
