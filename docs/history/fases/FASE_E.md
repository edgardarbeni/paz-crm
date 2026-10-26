# Cierre de fase E — Panel de administración

**Fecha:** 2026-10-25 · **Rama:** `feat/phase-e-admin-panel` · **Estado:** aprobada el 2026-10-25 · PR [#5](https://github.com/edgardarbeni/paz-crm/pull/5) (D-77).

## Criterios de aceptación (PLAN_FASES.md)

| Criterio | Resultado | Evidencia |
|---|---|---|
| Playwright E2E: login con TOTP | ✅ | `auth.spec.ts`: credenciales y código inválidos, login con TOTP, sesión que sobrevive a la recarga (cookie de refresh), cierre de sesión. Además, enrolamiento TOTP en el primer acceso con QR y códigos de recuperación |
| Playwright E2E: captura de una planilla completa | ✅ | `candidacies.spec.ts`: alta de la postulación y captura de las 5 fórmulas (presidencia, sindicatura, 2 regidurías MR y 1 RP) **solo con teclado**, validación en seco y envío |
| Playwright E2E: sustitución | ✅ | Sustitución desde el menú de la fórmula con motivo; la fórmula nueva queda en la posición y el historial muestra «Aspirante → Sustituida» |
| Playwright E2E: usuario con alcance limitado | ✅ | Coordinador acotado a un municipio: el distrito que cruza municipios aparece solo en lectura, el distrito ajeno no aparece (y da 404) y la geografía se limita a su municipio |
| Vitest en componentes y hooks | ✅ | 36 tests: sesión (refresh único, reintento ante 401, expiración), tabla (teclado, orden, carga), paginador por cursor, atajos, autocompletado, formulario de persona con CURP en línea, diálogo de excepciones a reglas, ayudantes de formularios y CURP |
| Accesibilidad básica de teclado | ✅ | Enlace «Saltar al contenido» como primer elemento enfocable, captura de planilla sin ratón (E2E), filas navegables con flechas y Enter, paleta `Ctrl+K`, etiquetas asociadas a todos los controles (Biome a11y recomendado sin excepciones, salvo un componente de shadcn) |

Todo corre contra el stack real (`scripts/e2e.sh`, D-73): 7 escenarios en unos 20 s.

## Entregables

| Área | Entregado |
|---|---|
| Autenticación | Login con segundo factor (TOTP o código de recuperación), enrolamiento TOTP con QR, aceptar invitación, recuperar y restablecer contraseña |
| Base | Sesión en memoria con renovación automática (D-74), layout con navegación por permisos y menú móvil, paleta `Ctrl+K`, tabla genérica con cursor, orden y teclado, formularios TanStack Form + Zod generado en español, autocompletado asíncrono, diálogos y avisos RFC 9457 |
| Geografía | Explorador por nivel con búsqueda y filtros por padre, detalle con mapa, ancestros y contenido, visor MapLibre con las teselas de la API sobre OpenFreeMap (D-72), ubicación de coordenadas, corridas de importación con sus incidencias |
| Identidad | Usuarios (invitar, editar, deshabilitar, desbloquear, reenviar invitación, restablecer 2FA, roles, alcance geográfico, sesiones), roles con su matriz de permisos, bitácora con filtros y vista antes/después, mi cuenta (contraseña, códigos de recuperación, sesiones) |
| Personas | Búsqueda por nombre, CURP o teléfono; alta y edición con CURP validada en línea, campos derivados de la CURP, avisos de incoherencia, contactos, domicilio con geografía; consentimientos; baja ARCO. Lo sensible sale enmascarado sin permiso y solo se reemplaza a propósito |
| Candidaturas | Partidos y cargos (alta y edición), procesos con pestañas de cargos, integración de ayuntamientos (con pegado desde hoja de cálculo), reglas y coaliciones; postulaciones con filtros; editor de planillas y listas para captura con teclado, alta rápida de personas, avisos de validación, validación en seco, cambios de estatus, sustitución, excepciones a reglas e historial |
| Backend | `PATCH /office-types/{id}` (D-76) |
| E2E | `scripts/e2e.sh`, semilla `backend/tests/e2e/seed.py` y job `e2e` en CI (D-73) |

## Errores encontrados y corregidos durante la fase

1. **Paleta de comandos rota:** el `CommandDialog` de shadcn ya no envuelve a sus hijos en `<Command>`. Al abrir `Ctrl+K` fallaba con «reading 'subscribe'». Lo detectó el E2E.
2. **Mapa en gris:** MapLibre 6 busca su web worker junto a su propio módulo; con Vite no lo encontraba. Ahora el worker se empaqueta y se registra con `setWorkerUrl` (D-72).
3. **Detalle de municipio sin «Pertenece a»:** la API solo calcula ancestros para secciones. Para los demás niveles el panel usa los ids de padre del nodo.
4. **Etiquetas de controles Radix:** un `<label>` que envuelve un checkbox de Radix no queda asociado. Se cambió por `LabeledToggle`, que lo asocia por `id`.

## Suposiciones

1. Solo tema claro y solo español (es-MX); no hay infraestructura de traducción.
2. Personas: sin `people.person.read_sensitive`, una CURP vacía en la edición significa «sin cambio», y contactos y domicilio solo se reemplazan si el usuario lo elige (no se pueden editar valores que no ve).
3. Contraseña nueva: el panel exige 12 caracteres como el backend (`password_min_length`); el backend es la autoridad.

## Deuda técnica

| # | Deuda | Cuándo atenderla |
|---|---|---|
| DT-27 | No hay bajas de partidos, cargos, coaliciones ni procesos (solo alta y edición); falta definir el soft-delete cuando ya tienen postulaciones | Cuando se requiera |
| DT-28 | Accesibilidad: se verifica el teclado y las etiquetas, pero no hay escaneo automático (axe) en CI ni revisión de contraste | Antes de abrir el panel a más usuarios |
| DT-29 | La pestaña Municipios carga en el navegador todos los municipios del estado (máximo 570, Oaxaca) | Si se vuelve lenta |
| DT-30 | El instrumentador OpenTelemetry de SQLAlchemy no soporta la versión 2.1 y avisa en el log al arrancar | Cuando publiquen soporte |
| DT-31 | El panel no tiene vista de alcance «qué ve este usuario» (vista previa del alcance de otro usuario) | Fase posterior |

## Riesgos

| # | Riesgo | Mitigación |
|---|---|---|
| R-11 | OpenFreeMap es un servicio comunitario sin SLA | El mapa base es configurable (D-72); las capas electorales no dependen de él |
| R-12 | Los E2E dependen de Docker y tardan más en CI | Un solo job, base desechable y escenarios independientes; el reporte y las trazas se suben cuando fallan |
