# D-86 · Protección contra bots en la inscripción pública

- **Estado:** Aceptada (2026-10-29: opción A más C, defensas propias y prueba de trabajo propia)
- **Área:** Movimiento de Paz · Seguridad

## Contexto

La inscripción por enlace o QR es el primer endpoint público que escribe datos personales.
Queda en `pending_validation` y no cuenta hasta validarse, pero un ataque puede llenar la cola
de validación o probar CURP.

Lo que existe: `RateLimiter` (ventana fija en Redis) y la IP del cliente desde
`X-Forwarded-For`, que uvicorn acepta de cualquier origen (`--forwarded-allow-ips "*"`). Es
seguro mientras la API solo sea alcanzable a través de Caddy, que descarta ese encabezado del
cliente; hay que garantizarlo en el despliegue antes de abrir el endpoint.

## Opciones

**A. Defensas propias (base obligatoria en cualquier caso).**
- Límite por IP y por `referral_code`; campo trampa; tiempo mínimo de llenado.
- Respuesta idéntica exista o no la CURP; alta siempre pendiente.
- *A favor:* ningún dato sale del sistema.
- *En contra:* un atacante paciente y distribuido las pasa.

**B. CAPTCHA externo (Cloudflare Turnstile o hCaptcha).**
- *A favor:* lo más robusto.
- *En contra:* un tercero procesa la visita a un formulario de afiliación política (IP,
  navegador), que es dato sensible; dependencia de un proveedor (D-38).

**C. Prueba de trabajo propia (ALTCHA o similar, de código abierto y alojada aquí).**
- *A favor:* sin terceros ni fricción visible; portátil.
- *En contra:* menos robusta que B frente a granjas con muchos núcleos.

## Recomendación

A más C. A sola alcanza para arrancar, porque nada cuenta hasta validarse; C se agrega si la
cola de validación muestra abuso.
