# D-94 · Infraestructura: scheduler, S3 de desarrollo y registro de módulos (detalla D-38 y D-84)

- **Estado:** Aceptada (2026-10-29)
- **Área:** Infraestructura y repositorio

Fase 0b del Movimiento de Paz.

- **Tareas programadas** ([D-84](D-84-tareas-periodicas.md)). Contenedor `scheduler` con la imagen
  de la API y supercronic (v0.2.51, verificado por SHA-256 en amd64 y arm64), que lee
  `backend/crontab`. Cada comando programado toma un candado consultivo
  (`app.core.jobs.exclusive_job`): una ejecución que se empalma con otra, manual o de otra
  réplica, termina sin hacer nada. Hoy corre `paz audit ensure-partitions` (03:10 UTC) y
  `paz people purge` (03:30 UTC); la fase 3 agrega los agregados del MP.
- **Almacenamiento S3** ([D-38](D-38-despliegue.md)). `app.core.storage.ObjectStorage` usa el
  SDK de MinIO, que habla S3 genérico (Spaces, S3, MinIO, SeaweedFS). Objetos privados, claves
  no adivinables por módulo y URLs firmadas de 10 minutos, firmadas contra
  `PAZ_STORAGE_PUBLIC_ENDPOINT` cuando la API llega por un host interno. Sin
  `PAZ_STORAGE_ENDPOINT`, las funciones con archivos responden 503 y `/ready` reporta
  `storage: disabled`.
- **Servidor S3 de desarrollo y tests: SeaweedFS 4.51**, no MinIO como decía el plan. Las
  imágenes de MinIO ya no se pueden descargar de Docker Hub ni de Quay. SeaweedFS (Apache 2.0)
  toma las credenciales de variables de entorno, exige firma y no expone objetos sin ella.
  `paz storage ensure-bucket` crea el bucket al migrar en compose.
- **Registro de módulos** (diferencia 2 de `architecture.md` §8). Cada paquete de
  `app/modules/` con un `module.py` declara `MODULE = ModuleSpec(...)` con su orden, esquema,
  modelos, routers y enum de permisos, como referencias en texto que se resuelven bajo demanda
  (sin ciclos de importación). `main.py`, `models.py`, `migrations/env.py` y el catálogo de
  permisos (`permission_codes()`) leen el registro. Un test compara la copia de permisos del
  panel con el backend.

*Motivo:* el MP necesita tareas periódicas (agregados), fotos (casas) y un módulo nuevo sin
tocar el núcleo. (Descartadas: un worker con colas, ver D-84; RustFS y Garage como S3 de
desarrollo, por menor madurez y configuración más compleja, respectivamente; mantener el
registro manual de routers y esquemas.)
