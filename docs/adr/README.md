# Decisiones de arquitectura (ADR)

Una decisión por archivo, numeradas `D-NN`. El código y los documentos las citan por número.

- **Precedencia:** cuando una decisión contradice a `CLAUDE.md`, a una ficha de módulo o a
  `reference/`, manda la decisión.
- **Inmutables:** una decisión no se reescribe. Se reemplaza, corrige o amplía con una nueva que
  la cite en su título (por ejemplo «reemplaza D-09»); la anterior conserva su texto.
- **Nueva decisión:** crea `D-NN-tema-corto.md` con el siguiente número y agrégala a este índice
  y, si cambia una suposición o un riesgo, a las listas del final.

Formato de un archivo nuevo:

```markdown
# D-NN · Tema

- **Estado:** Aceptada
- **Área:** <área>

Decisión. *Motivo.* (Alternativas descartadas.)
```

Las decisiones D-01 a D-79 vienen del registro único `DECISIONES.md` (2026-10-24 a 2026-10-25),
separado en archivos sin cambiar su texto; solo se actualizaron las rutas de los documentos movidos.

## Geografía electoral

| D | Tema | Estado |
|---|---|---|
| [D-01](D-01-marco-geografico.md) | Marco geográfico | Aceptada |
| [D-02](D-02-recarga.md) | Recarga | Aceptada |
| [D-03](D-03-pk-hibrida.md) | PK híbrida (excepción a CLAUDE.md) | Aceptada |
| [D-04](D-04-geografia-solo-lectura.md) | Geografía de solo lectura (excepción a CLAUDE.md) | Aceptada |
| [D-05](D-05-postgresql-18-postgis-3-5.md) | PostgreSQL 18 + PostGIS 3.5+ | Aceptada |
| [D-06](D-06-modelo-conceptual.md) | Modelo conceptual | Aceptada |
| [D-07](D-07-circunscripcion.md) | Circunscripción | Aceptada |
| [D-08](D-08-diputaciones-locales-rp.md) | Diputaciones locales de RP | Aceptada |
| [D-09](D-09-relacion-colonia-seccion.md) | Relación colonia ↔ sección | Reemplazada |
| [D-10](D-10-llave-natural-colonia.md) | Llave natural de colonia | Aceptada (actualizada por D-58) |
| [D-11](D-11-localidades.md) | Localidades | Aceptada |
| [D-12](D-12-registros-sin-geometria.md) | Registros sin geometría | Aceptada |
| [D-13](D-13-capas-no-electorales-fuera-mvp.md) | Capas no electorales fuera del MVP | Aceptada |
| [D-14](D-14-particionado.md) | Particionado | Aceptada |
| [D-15](D-15-catalogos-codigos.md) | Catálogos de códigos | Aceptada (ampliada por D-59) |
| [D-16](D-16-fuente-datos-primer-marco.md) | Fuente de datos del primer marco | Aceptada |
| [D-17](D-17-kml-fuera-mvp.md) | KML fuera del MVP | Aceptada |
| [D-18](D-18-importador.md) | Importador | Aceptada |
| [D-19](D-19-api-geografica.md) | API geográfica | Aceptada |
| [D-20](D-20-datos-desarrollo-ci.md) | Datos de desarrollo y CI | Aceptada |

## Candidaturas

| D | Tema | Estado |
|---|---|---|
| [D-21](D-21-rp-local-configurable.md) | RP local configurable | Aceptada |
| [D-22](D-22-senado-presidencia.md) | Senado y Presidencia | Aceptada |
| [D-23](D-23-modulo-configuracion-electoral.md) | Módulo de configuración electoral | Aceptada |
| [D-24](D-24-regidurias.md) | Regidurías | Aceptada |
| [D-25](D-25-sindicatura.md) | Sindicatura | Aceptada |
| [D-26](D-26-regimen-municipal.md) | Régimen municipal | Aceptada |
| [D-27](D-27-partidos-alianzas.md) | Partidos y alianzas | Aceptada |
| [D-28](D-28-motor-validaciones.md) | Motor de validaciones | Aceptada |
| [D-29](D-29-sustitucion.md) | Sustitución | Aceptada |

## Persona y datos sensibles

| D | Tema | Estado |
|---|---|---|
| [D-30](D-30-validacion-curp.md) | Validación de CURP | Aceptada |
| [D-31](D-31-cifrado-nivel-aplicacion.md) | Cifrado a nivel aplicación | Aceptada |
| [D-32](D-32-gestion-llaves.md) | Gestión de llaves | Aceptada |

## Identidad, acceso y auditoría

| D | Tema | Estado |
|---|---|---|
| [D-33](D-33-roles-iniciales.md) | Roles iniciales | Aceptada |
| [D-34](D-34-alcance-geografico.md) | Alcance geográfico | Aceptada |
| [D-35](D-35-alta-usuarios-correo.md) | Alta de usuarios y correo | Aceptada |
| [D-36](D-36-auditoria-importaciones.md) | Auditoría de importaciones | Aceptada |
| [D-37](D-37-bitacora-inmutable.md) | Bitácora inmutable | Aceptada (detallada por D-45) |

## Infraestructura y repositorio

| D | Tema | Estado |
|---|---|---|
| [D-38](D-38-despliegue.md) | Despliegue | Aceptada |
| [D-39](D-39-monorepo.md) | Monorepo | Aceptada |
| [D-40](D-40-cliente-api.md) | Cliente de API | Aceptada |

## Modelo de datos

| D | Tema | Estado |
|---|---|---|
| [D-41](D-41-modelo-datos-aprobado.md) | Modelo de datos aprobado | Aceptada |
| [D-42](D-42-plan-fases-aprobado.md) | Plan por fases aprobado | Aceptada |

## Fase A — implementación

| D | Tema | Estado |
|---|---|---|
| [D-43](D-43-imagen-propia-postgresql-18-postgis.md) | Imagen propia de PostgreSQL 18 + PostGIS | Aceptada |
| [D-44](D-44-separacion-roles-base-datos.md) | Separación de roles de base de datos | Aceptada |
| [D-45](D-45-implementacion-bitacora.md) | Implementación de la bitácora | Aceptada (detallada por D-53) |
| [D-46](D-46-convenciones-api.md) | Convenciones de API | Aceptada |
| [D-47](D-47-typescript-6-frontend.md) | TypeScript 6 en el frontend | Aceptada |

## Fase B — identidad

| D | Tema | Estado |
|---|---|---|
| [D-48](D-48-tokens-sesiones.md) | Tokens y sesiones | Aceptada |
| [D-49](D-49-defensa-login.md) | Defensa del login | Aceptada |
| [D-50](D-50-contrasenas.md) | Contraseñas | Aceptada |
| [D-51](D-51-segundo-factor.md) | Segundo factor | Aceptada |
| [D-52](D-52-reglas-rbac.md) | Reglas de RBAC | Aceptada |
| [D-53](D-53-ajustes-auditoria-automatica.md) | Ajustes a la auditoría automática | Aceptada |
| [D-54](D-54-ajustes-modelo-identidad.md) | Ajustes al modelo de identidad (sobre `data-model.md` §2) | Aceptada |
| [D-55](D-55-correo-arranque.md) | Correo y arranque | Aceptada |
| [D-56](D-56-fase-b-aprobada.md) | Fase B aprobada | Aceptada |

## Fase C — geografía

| D | Tema | Estado |
|---|---|---|
| [D-57](D-57-relacion-colonia-seccion-desde-catalogo-ine.md) | Relación colonia ↔ sección desde el catálogo del INE | Aceptada |
| [D-58](D-58-verificaciones-llave-colonia-fuentes-importador.md) | Verificaciones sobre la llave de colonia y fuentes del importador | Aceptada |
| [D-59](D-59-mapeos-codigos-verificados.md) | Mapeos de códigos verificados | Aceptada (corregida por D-62) |
| [D-60](D-60-ajustes-implementacion-geografia.md) | Ajustes de implementación de la geografía (sobre `data-model.md` §1) | Aceptada |
| [D-61](D-61-hallazgos-carga-real-aguascalientes.md) | Hallazgos de la carga real de Aguascalientes | Aceptada |
| [D-62](D-62-codigos-colonia-no-son-confiables-nivel.md) | Los códigos de colonia no son confiables a nivel nacional | Aceptada |
| [D-63](D-63-operacion-geografia.md) | Operación de la geografía | Aceptada |
| [D-64](D-64-fase-c-aprobada.md) | Fase C aprobada | Aceptada |
| [D-65](D-65-ajustes-implementacion-personas-candidaturas.md) | Ajustes de implementación de personas y candidaturas (sobre `data-model.md` §3 y §4) | Aceptada |
| [D-66](D-66-personas-visibilidad-enmascarado-permisos.md) | Personas: visibilidad, enmascarado y permisos | Aceptada |
| [D-67](D-67-motor-reglas-cuando-bloquea-se-acepta.md) | Motor de reglas: cuándo bloquea y qué se acepta | Aceptada |
| [D-68](D-68-ciclo-vida-postulaciones-formulas.md) | Ciclo de vida de postulaciones y fórmulas | Aceptada |
| [D-69](D-69-baja-personas-suposicion-confirmar.md) | Baja de personas (ARCO) — suposición a confirmar | Aceptada |
| [D-70](D-70-cargos-partidos-como-datos.md) | Cargos y partidos como datos | Aceptada |
| [D-71](D-71-fase-d-aprobada.md) | Fase D aprobada | Aceptada |
| [D-72](D-72-mapa-base-visor-openfreemap-configurable.md) | Mapa base del visor: OpenFreeMap, configurable | Aceptada |
| [D-73](D-73-e2e-panel-contra-stack-real.md) | E2E del panel contra el stack real | Aceptada |
| [D-74](D-74-sesion-panel.md) | Sesión del panel | Aceptada |
| [D-75](D-75-convenciones-panel.md) | Convenciones del panel | Aceptada |
| [D-76](D-76-edicion-cargos.md) | Edición de cargos | Aceptada |
| [D-77](D-77-fase-e-aprobada-mvp-completo.md) | Fase E aprobada; MVP completo | Aceptada |
| [D-78](D-78-identidad-visual-panel.md) | Identidad visual del panel | Aceptada |
| [D-79](D-79-busqueda-geografica-nombre-estado.md) | Búsqueda geográfica por nombre y estado | Aceptada |
| [D-80](D-80-teselas-geometrias-generalizadas.md) | Teselas con geometrías generalizadas por zoom (amplía D-19) | Aceptada |

## Suposiciones vigentes

- El ID de origen de colonia en la BGD es estable entre cortes ([D-10](D-10-llave-natural-colonia.md)/[D-58](D-58-verificaciones-llave-colonia-fuentes-importador.md): único y consistente con el catálogo dentro del corte; la estabilidad entre cortes queda por verificar).
- El umbral por defecto colonia ↔ sección es 5 % del área de la colonia o 500 m² ([D-09](D-09-relacion-colonia-seccion.md)).
- No se precargan reglas electorales por estado (regidurías, sindicatura, régimen municipal, paridad); todo es configuración ([D-24](D-24-regidurias.md) a [D-28](D-28-motor-validaciones.md)).
- La primera minoría del Senado se infiere de la posición 1 de la lista estatal; el cálculo de resultados queda fuera del MVP.
- Personas visibles con alcance limitado: domicilio en el alcance, postulación visible o sin domicilio aún ([D-66](D-66-personas-visibilidad-enmascarado-permisos.md)).
- Forzar una CURP incoherente usa el permiso `people.person.read_sensitive` ([D-66](D-66-personas-visibilidad-enmascarado-permisos.md)).
- Paridad: cuenta como mujer el sexo `M`; `X` no suma a la cuota ([D-67](D-67-motor-reglas-cuando-bloquea-se-acepta.md)).
- Una fórmula sustituta hereda el estatus de la reemplazada ([D-68](D-68-ciclo-vida-postulaciones-formulas.md)).
- Retención de 30 días antes de anonimizar a una persona dada de baja ([D-69](D-69-baja-personas-suposicion-confirmar.md)).

## Riesgos abiertos

- ~~Disponibilidad de PG18 + PostGIS en Postgres administrado ([D-05](D-05-postgresql-18-postgis-3-5.md)).~~ **Resuelto el 2026-10-24:** DigitalOcean administrado ofrece PostGIS en PostgreSQL 18 (Standard Edition, según su lista oficial de extensiones) y AWS RDS ofrece PostgreSQL 18.4 con PostGIS 3.6.3. Se mantiene PG18 sin fallback.
- Cadena de hashes de la bitácora con alta concurrencia: requiere serializar la escritura del eslabón (secuencia o lock ligero) y medir su costo en carga.
