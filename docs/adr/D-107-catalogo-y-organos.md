# D-107 · Catálogo estatutario y órganos instalados (fase 1 de la estructura)

- **Estado:** Aceptada (2026-10-30)
- **Área:** Estructura del partido

Cómo quedó la fase 1 (migración `0019`, módulo `party_structure`, API `/api/v1/party-structure`).

**Catálogo sembrado de [`cargos_paz.md`](../reference/cargos_paz.md)**
- **Órganos.** Cada encabezado del catálogo es un tipo de órgano: 10 nacionales, 5 estatales, el
  Comité Directivo Distrital y el Municipal o de Alcaldía (17 en total).
- **[SUPUESTO] Dónde quedan algunas coordinaciones.** Las que el catálogo describe como
  integrantes de un órgano quedan como cargos de ese órgano:
  - Capacitación y Unidad de Transparencia, en el Comité Directivo Nacional;
  - Unidad de Transparencia Estatal, en el Comité Directivo Estatal;
  - Diputaciones Federales en la Entidad, en la Comisión Política Estatal.

  Las demás quedan en «Coordinaciones Nacionales» o «Coordinaciones Estatales». Los
  Grupos Parlamentarios Federales son dos cargos: Senado y Cámara de Diputados.
- **Cargos.** Hay 88, cada uno con su fundamento, el órgano que lo elige y su periodo tal como
  los da el catálogo.
  - Donde el catálogo dice «según designación», el periodo queda vacío.
  - Donde no dice quién elige, el órgano que elige queda vacío.
  - Las 22 de Causas y Movimientos Sociales tienen `max_consecutive_terms = 2` (D-105).
- **Presídium.** Sus cargos son derivados y no se nombran (`position_derivations`).
  - La Vicepresidencia nacional tiene dos fuentes posibles y se elige en cada periodo (D-105).
  - Las del Presídium estatal tienen una fuente fija.
- **No se siembran** las «demás direcciones, delegaciones o coordinaciones que se creen»: se
  agregan desde la API sin migraciones.
- **La Delegación Estatal en funciones de Presidencia** no es un cargo. Será un tipo de
  nombramiento (`delegate`) sobre la Presidencia del Consejo Directivo Estatal (fase 2), con
  6 meses propuestos.
- **Incompatibilidades:** la lista empieza vacía (D-105).

**Órganos y territorio**
- Los 10 órganos nacionales y los 5 estatales de cada uno de los 32 estados se siembran
  instalados (170).
- **Los órganos estatales guardan la clave INE del estado (1 a 32), no una FK al marco.** La
  clave no cambia entre marcos, así que no hay que remapearlos.
- Los comités distritales y municipales:
  - existen solo desde que se registra su instalación (fecha y acuerdo);
  - apuntan al nodo del marco activo (distrito federal o local, o municipio) y guardan además
    la clave de su estado;
  - al cambiar de marco se remapean como dice D-102.
- Solo puede haber un órgano vigente de cada tipo por territorio. Uno disuelto se puede volver a
  instalar, y el disuelto queda en el historial. Los órganos nacionales y estatales no se
  disuelven.

**Alcance (D-34, D-101)**
- Los órganos nacionales los ve cualquiera con `party_structure.body.read`.
- Los estatales se ven si su estado toca el alcance; los distritales y municipales, si su nodo
  lo toca.
- Para instalar o disolver, el nodo debe quedar completo dentro del alcance de
  `party_structure.body.write`. La regla de «solo niveles inferiores» (D-105) entra con los
  nombramientos (fase 2).

**Permisos y roles**
- Permisos: `party_structure.catalog.manage` (admin), `party_structure.body.read` (admin,
  coordinator y viewer) y `party_structure.body.write` (admin y coordinator), como en la ficha.
- Roles base de D-105: «Dirigente territorial» (lectura y escritura de órganos) y «Coordinador
  territorial» (lectura). Ambos tienen TOTP.
  - Son roles de sistema porque el catálogo los usa como rol por defecto: no se borran, pero
    sus permisos sí se editan.
  - Recibirán más permisos en las fases siguientes (nombramientos, casas).
- El rol por defecto de un cargo solo lo fija quien podría conceder ese rol (D-52). Si el rol
  se borra, el cargo se queda sin rol por defecto.
