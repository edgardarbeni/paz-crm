# D-84 · Tareas periódicas y en segundo plano

- **Estado:** Propuesta
- **Área:** Infraestructura y repositorio

## Contexto

El MP necesita recalcular agregados de la red cada pocos minutos desde `network_changes`, con
un recálculo completo nocturno; la meta es reflejar una inscripción en menos de 5 minutos.

Hoy no hay ejecutor de tareas. `paz people purge` y `paz audit ensure-partitions` "se programan
con cron" (README), pero `compose.yaml` no define dónde corre ese cron y el despliegue
([D-38](D-38-despliegue.md)) tampoco.

## Opciones

**A. Cron que invoca la CLI `paz` (recomendada ahora).**
- Contenedor `scheduler` con la imagen de la API y `supercronic`, que ejecuta
  `paz peace-movement aggregate` cada minuto y los trabajos existentes (`purge`,
  `ensure-partitions`).
- Cada tarea toma un candado consultivo (`pg_try_advisory_lock`) y es idempotente, así que
  dos ejecuciones simultáneas no se pisan.
- *A favor:* sigue el patrón actual, sin dependencias nuevas; portátil (un cron job en
  DigitalOcean App Platform o en ECS/EventBridge).
- *En contra:* latencia mínima de un minuto (cumple la meta) y no sirve para tareas disparadas
  por un evento.

**B. Worker sobre Redis (arq o RQ) con planificador.**
- *A favor:* tareas por evento (notificaciones, exportaciones pesadas, reintentos).
- *En contra:* un servicio más que operar, monitorear y escalar; nada de lo que se necesita hoy
  lo exige.

## Nota

Reconsiderar B cuando lleguen las notificaciones a pacificadores (fuera de alcance de la
primera versión del MP).
