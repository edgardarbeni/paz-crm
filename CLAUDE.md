<contexto>
El sistema es una platforma ERP/CRM denominado “PAZOS” orientada gestionar más 10 áreas distintas de información constante del partido político nacional PAZ, tales como registro y padrones de candidaturas, estructura de defensa del voto, padrones simpatizantes del denominado “movimiento de paz” en conjunto con el padrón de militancia/afiliadoss, registros legales del área jurídica, seguimiento del área de atención social y necesidades comunitarias, monitoreo de encuestas y medición poll of polls, localicación y registro de vallas y bardas publicitarias, y un sistema de captura de resultados electorales preliminares para el día de la jornada y los cómputos distritales.

El sistema debe estar orientado a la facilidad de uso, velocidad de captura, velocidad de recuperación de la información, capacidad de moldear el sistema a futuro, y debe tener una infraestructura de alto rendimiento, se desarrolla porque no existe en el mercado una alternativa que brinde todas estas soluciones en paquete.
</contexto>

<alcance>
MVP incluye: El sistema requiere iniciar por ahora con los siguientes componetes elementales.
- Backend bien estructurado.
- API del backend bien diseñada orientada al rendimiento.
- Sistema de usuarios con control de niveles de acceso robusto, y 2FA propio con integración para apps como Google Auth, Microsoft Auth o 1Password.
- API y Estructura en la Base de Datos del modelo geográfico electoral del país.
  - Modelos (geografía electoral):
    - Secciones electorales (unidad atómica).
    - Municipios (integrados a su vez por secciones electorales).
    - Distritos Locales (integrados a su vez por secciones electorales).
    - Distritos Federales (integrados a su vez por secciones electorales).
    - Estados (integrados a su vez por municipios, distritos locales y distritos federales).
    - Circunscripciones (integradas a su vez por estados).
  - Modelos (geografía tradicional, relacionada con la sección):
    - Manzana (pertenece a una sección).
    - Colonia (N:M con secciones).
    - Localidad (polígono de la localidad + puntos por localidad-sección).
  - Para el diseño de esta estructura de Base de Datos toma como base el siguiente documento: '/Users/dariobenitez/Development/PAZ/paz-crm/docs/DISENO_BD_GEOESPACIAL.md’, pero toma en cuenta que es una referencia de la información que cargaremos de los Shapes y catálogos del INE. Termina de modelar la base de datos conforme las necesidades del proyecto y estándares de naming convention. Las capas no electorales (vialidades, POI, hidrografía, módulos INE, números exteriores) quedan fuera del MVP (ver docs/DECISIONES.md D-13).
- API y Backend del Módulo de gestión de candidaturas.
  - Modelos:
    - Planillas de Presidentes Municipales correspondiente al nivel geográfico de Municipios e integrada por:
      - Presidente Municipal
      - Sindicatura
      - Lista de regidores (variable de acuerdo al municipio)
    - En algunos estadoss se eligen Sindicaturas de manera individualkl en el nivel geográfico de Municipios *
    - Diputados locales correspondiente al nivel geográfico de distritos locales
    - Diputados federales correspondiente al nivel geográfico de distritos federales
    - Gobernaturas correspondiente al nivel geográfico de estados
    - Diputaciones federales plurinominales correspondiente al nivel geográfico de Circunscripciones
        - Se nombran 40 posiciones
    - Diputaciones locales plurinominales correspondiente al nivel geográfico de estados, con método configurable por estado y proceso: lista cerrada, mejor perdedor preponderante o mixto.
    - Senadurías de mayoría relativa por estado: lista de 2 fórmulas con posición (la posición 1 es la que puede entrar por primera minoría).
    - Senadurías plurinominales: lista nacional cerrada de 32 fórmulas.
    - Presidencia de la República (nivel nacional).
    - Módulo de configuración electoral: por proceso se habilita qué cargos van a elección a nivel federal y local.
    - * Nota importante: todas las candidaturas nombradas a su vez deben de llevar una suplencia.
- Implementa una forma de conexión segura con la API del backend utilizando tecnologías adhoc y documentación a través de una tecnología como Swagger o similar.
- Implementa un panel de administración del sistema que conecte con el backend, y por ahora solamente deberá tener todo el CRUD del sistema.

Fuera de alcance: El sistema debe estar abierto a ampliarse, pero en este primer bloque de desarrollo aún no haremos el ressto de implementaciones.
- Módulo conjunto de padrón de personas (movimiento por la paz y afiliación).
- Módulo de información electoral (históricos electorales).
- Módulo de estructura de defensa del voto.
- Módulo de registros legales del área jurídica.
- Módulo de seguimiento de atención ssocial y necesidades comunitarias.
- Módulo de monitoreo de encuestas y medición poll of polls.
- Módulo de locación y registro de vallas y bardas publicitarias.
</alcance>

<requisitos_funcionales>
1. Geografía electoral
   - Todas las entidades geográficas pertenecen a un marco_geografico versionado
     (ej. "INE 2023"); varios marcos pueden coexistir, pero solo uno nacional está activo.
     Recargar un marco es un upsert por llave natural que conserva los IDs.
   - Jerarquía electoral: circunscripción > estado > (distrito_federal | distrito_local | municipio) > sección.
     La sección es la unidad atómica: pertenece a exactamente un municipio, un distrito local
     y un distrito federal. DF, DL y municipio son agrupaciones independientes de secciones que se
     traslapan; ninguna está anidada en otra.
   - Geografía tradicional: manzana → 1 sección (sus distritos se obtienen por la sección);
     colonia ↔ sección es N:M (calculada por intersección con umbral); localidad.
   - La geografía es de solo lectura: solo cambia por importación.
   - Geometrías en PostGIS (SRID 4326 para almacenamiento; índices GiST).
   - Scripts de importación idempotentes desde Shapefile (BGD del INE) y catálogos INE (txt/xlsx),
     con reporte de errores por registro y modo dry-run. KML queda fuera del MVP.
   - Endpoints: consulta jerárquica (hijos/ancestros), búsqueda por clave INE,
     punto-en-polígono (¿a qué sección pertenece esta coordenada?), y geometrías
     simplificadas por nivel de zoom (vector tiles MVT, con visor de mapa básico en el panel).
   - Criterio de aceptación: dada una coordenada, devolver la sección, municipio, DL, DF,
     estado y circunscripción en < 50 ms p95.

2. Candidaturas
   - proceso_electoral (año, tipo: ordinario/extraordinario, ámbito: federal/local, estado).
   - Catálogo tipo_cargo con: nombre, ámbito geográfico (municipio, DL, DF, estado,
     circunscripción, nacional), principio (MR/RP), número de posiciones y si aplica fórmula
     propietario-suplente. Los cargos del MVP se cargan como seeds; agregar nuevos cargos
     no debe requerir migraciones.
   - Planilla municipal: presidencia, sindicatura(s) y regidurías; el número de regidurías se
     configura por municipio y proceso. Soportar estados con sindicatura electa por separado.
   - Listas plurinominales: 40 posiciones por circunscripción, ordenadas.
   - Toda candidatura es una fórmula: propietario + suplente.
   - Validaciones de negocio configurables por estado/proceso: paridad de género, alternancia
     en listas, suplente del mismo género, persona no duplicada en el mismo proceso.
   - Estatus con historial: aspirante → registrada → aprobada | sustituida | cancelada.
   - Las candidaturas pueden ir por partido, coalición o candidatura común (modelar
     la entidad, aunque la UI sea básica).
   - Persona: entidad independiente y reutilizable (base del futuro padrón), con CURP
     única y validada.

3. Usuarios y acceso
   - Autenticación: email + contraseña (Argon2id), TOTP RFC 6238 obligatorio para roles
     administrativos (compatible con Google Authenticator, Microsoft Authenticator, 1Password),
     códigos de recuperación de un solo uso. Dejar WebAuthn/passkeys preparado como extensión.
   - Sesiones: access token de vida corta + refresh token rotativo en cookie httpOnly/Secure/
     SameSite, con revocación por dispositivo y cierre de todas las sesiones.
   - Autorización: RBAC (roles → permisos por módulo y acción) + alcance geográfico
     (un usuario se asigna a uno o varios nodos geográficos y solo ve/edita lo que está debajo).
     La verificación de alcance debe aplicarse en la capa de consulta, no solo en endpoints.
   - Bloqueo por intentos fallidos, rate limiting por IP y usuario.
   - Bitácora de auditoría inmutable: quién, qué, cuándo, desde dónde, valor anterior y nuevo,
     para toda escritura del sistema.

4. Panel de administración
   - CRUD completo de todas las entidades del MVP, respetando permisos y alcance geográfico.
   - Tablas con paginación del lado del servidor, filtros, ordenamiento y búsqueda.
   - Captura optimizada: navegación completa con teclado, autocompletado de geografía y personas,
     validación en línea con los mismos esquemas del backend.
   - Gestión de usuarios, roles, permisos, alcances y consulta de la bitácora.
</requisitos_funcionales>

<requisitos_no_funcionales>
- Rendimiento: p95 < 200 ms en lecturas de API y < 500 ms en escrituras, con al menos
  70,000 secciones y 2.5 millones de manzanas cargadas. Diseñar pensando en picos de
  concurrencia alta (jornada electoral, módulo futuro).
- Paginación por cursor en colecciones grandes; nada de "SELECT *" sin límite.
- Seguridad: OWASP ASVS nivel 2 como referencia, CORS restrictivo, cabeceras de seguridad,
  secretos solo por variables de entorno o gestor de secretos, cifrado de campos sensibles
  (CURP, teléfonos, direcciones) a nivel aplicación.
- Cumplimiento: LFPDPPP; diseño preparado para aviso de privacidad, derechos ARCO y
  soft-delete con purga programable.
- Extensibilidad: arquitectura modular; cada módulo futuro (padrón, defensa del voto, jurídico,
  etc.) se agrega como un paquete nuevo sin tocar el núcleo.
- Observabilidad: logs estructurados JSON con request_id, métricas y trazas.
- Idioma: interfaz en español (México); código, tablas y columnas en inglés con snake_case.
</requisitos_no_funcionales>

<stack>
Backend:
- Python 3.12+, FastAPI, SQLModel (SQLAlchemy 2 async + Pydantic v2), asyncpg.
- PostgreSQL 18 con PostGIS 3.5+ (uuidv7() nativo; fallback PG17 + UUIDv7 en la aplicación);
  GeoAlchemy2 para tipos geométricos.
- pyogrio para la importación de shapefiles.
- Alembic para migraciones (nunca crear tablas con create_all fuera de tests).
- Redis para caché, rate limiting y sesiones revocadas.
- uv como gestor de dependencias; pydantic-settings para configuración.
- pyotp (TOTP), argon2-cffi, PyJWT.
- ruff, mypy (strict), pytest + pytest-asyncio + testcontainers (Postgres real en tests).
- structlog + OpenTelemetry.

Frontend (panel):
- React 19 + TypeScript strict, Vite, TanStack Router (SPA), TanStack Query,
  TanStack Form + Zod, TanStack Table.
- Tailwind CSS 4 + shadcn/ui.
- Cliente de API generado desde el OpenAPI del backend con Hey API (@hey-api/openapi-ts,
  plugins de TanStack Query y Zod); prohibido escribir llamadas fetch a mano.
- MapLibre GL para el visor de mapa.
- Biome, Vitest + Testing Library, Playwright.
- pnpm.

Infraestructura:
- Monorepo: backend/ (uv), frontend/ (pnpm), infra/, docs/.
- Docker Compose para desarrollo (api, db, redis, frontend, proxy, mailpit).
- Proxy inverso con TLS: Caddy.
- Despliegue inicial en DigitalOcean con alta probabilidad de migrar a AWS: todo portátil
  (contenedores estándar, almacenamiento compatible con S3, KMS detrás de una abstracción).
- CI en GitHub Actions: lint, type-check, tests, build de imágenes.
</stack>

<arquitectura>
- Monolito modular. Estructura por dominio:
  app/core (config, seguridad, db, auditoría), app/modules/geography,
  app/modules/candidacies, app/modules/identity (usuarios, roles, 2FA),
  cada uno con models, schemas, repository, service, router.
- Separar modelos de tabla de esquemas de entrada/salida (SQLModel table=True vs DTOs).
- Lógica de negocio en services; los routers solo orquestan.
- API versionada (/api/v1), OpenAPI con Swagger UI y ReDoc, deshabilitables en producción.
- Errores con formato uniforme (RFC 9457 Problem Details).
- Convenciones de BD: tablas en plural snake_case, PK UUIDv7, created_at/updated_at/
  deleted_at en todas las tablas, FKs e índices nombrados explícitamente.
  Excepciones (docs/DECISIONES.md D-03, D-04, D-37):
  - Tablas masivas no referenciadas (manzanas, puntos localidad-sección, errores de importación) usan PK bigint.
  - La geografía no lleva deleted_at: usa is_active + import_run_id.
  - La bitácora de auditoría es append-only: solo occurred_at.
- Si una decisión de diseño tiene alternativas relevantes, propón 2 opciones con trade-offs
  antes de implementarla.
</arquitectura>

<calidad>
- Cobertura ≥ 85 % en services y validaciones de negocio; tests de autorización
  que prueben explícitamente que un usuario NO puede acceder fuera de su alcance.
- Seeds de desarrollo realistas (al menos un estado completo cargado).
- Entregables por fase: código, migraciones, tests verdes, README actualizado,
  .env.example documentado, colección de ejemplos de la API.
- Al final de cada fase: lista de suposiciones tomadas, deuda técnica y riesgos.
- Todo el código, naming conventions de la API y demás deben de escribirse en inglés, aunque la aplicación esté en español.
</calidad>

<proceso>
0. docs/DECISIONES.md es el registro de decisiones tomadas y tiene precedencia sobre este archivo
   y sobre DISENO_BD_GEOESPACIAL.md. Consúltalo antes de cualquier diseño o implementación y
   agrega ahí cada decisión nueva.
1. Lee DISENO_BD_GEOESPACIAL.md y señala inconsistencias o vacíos respecto a este prompt.
2. Haz todas las preguntas de clarificación necesarias antes de escribir código.
3. Propón el modelo de datos completo (diagrama ER en Mermaid) y espera aprobación.
4. Propón un plan por fases y espera aprobación. Orden sugerido:
   a) Infraestructura base, core y CI
   b) Identidad: usuarios, roles, alcances, 2FA, auditoría
   c) Geografía: modelos, importadores, endpoints
   d) Candidaturas: modelos, validaciones, endpoints
   e) Panel de administración
5. Implementa una fase a la vez; no avances sin tests verdes y sin mi aprobación.
6. Nunca inventes datos del INE ni reglas electorales: si una regla no está
   especificada, pregúntala o déjala configurable y documéntala como suposición.
</proceso>