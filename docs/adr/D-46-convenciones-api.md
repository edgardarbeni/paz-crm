# D-46 · Convenciones de API

- **Estado:** Aceptada
- **Área:** Fase A — implementación

- Los errores son RFC 9457 con `type = urn:pazos:problem:<code>` y las extensiones `code` y `request_id`, servidos como `application/problem+json` (también en el OpenAPI, así que el cliente generado los tipa como `Problem`).
- `/health` y `/ready` quedan fuera de `/api/v1`.
- El `X-Request-ID` entrante se respeta si es válido; si no, se genera uno.
- Las variables de entorno del backend llevan el prefijo `PAZ_`.
