# D-88 · Autenticación de dispositivos de la app de campo

- **Estado:** Propuesta (entrega posterior; puede decidirse más adelante)
- **Área:** Movimiento de Paz · Identidad, acceso y auditoría

## Contexto

La app Flutter captura sin conexión y sincroniza con la carga por lotes idempotente. El
brigadista y el dispositivo deben poder revocarse.

## Opciones

**A. El brigadista es usuario de `identity` y el dispositivo se registra (recomendada).**
- Tabla de dispositivos (`device_id`, usuario, alta, revocación); el refresh token queda ligado
  al dispositivo y se revoca por dispositivo o por usuario.
- *A favor:* cada registro sabe quién lo capturó (bitácora y estadísticas); reutiliza sesiones.
- *En contra:* exige una sesión inicial con conexión.

**B. Llave de API por dispositivo, sin usuario.**
- *A favor:* lo más simple de operar.
- *En contra:* se pierde quién capturó cada registro, algo que la bitácora necesita; una llave
  extraída del dispositivo da acceso hasta que se revoque.
