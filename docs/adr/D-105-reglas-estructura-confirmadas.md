# D-105 · Reglas de la estructura del partido confirmadas (precisa D-103 y D-104)

- **Estado:** Aceptada (2026-10-30)
- **Área:** Estructura del partido

Respuestas de Darío a las preguntas abiertas de [party-structure.md](../modules/party-structure.md)
y a los vacíos del catálogo estatutario [`cargos_paz.md`](../reference/cargos_paz.md).

**Catálogo**
- **Vicepresidencia del Presídium nacional:** el catálogo dice «titular de una de las Secretarías
  del Consejo Directivo del CDN» sin decir cuál. Se elige en cada periodo: un admin indica cuál de
  las dos Secretarías Generales la ocupa, y queda en el historial. La estatal es fija (Secretaría
  General de Estrategia Electoral, como dice el catálogo).
- **Periodos consecutivos:** nuevo campo `position_types.max_consecutive_terms`. Vale 2 para las 22
  Coordinaciones Nacionales de Causas y Movimientos Sociales (Arts. 94 a 106) y queda vacío en el
  resto. Nombrar un tercer periodo consecutivo en el mismo asiento responde 409.
- **Primer periodo transitorio** (Séptimo Transitorio, 6 años por única ocasión): sin regla
  especial. `term_years` propone el fin del periodo y quien captura pone la fecha de 6 años,
  citando el transitorio en `agreement_ref`.
- **Incompatibilidades:** se siembra la lista vacía. Un admin las agrega desde el panel cuando
  jurídico las defina.

**Administración delegada** (reemplaza el [SUPUESTO] de la ficha)
- Orden de niveles: nacional > circunscripción > estatal > **distrital federal, distrital local,
  municipal o de alcaldía y sus direcciones o coordinaciones municipales** (todos en el mismo
  nivel) > coordinaciones territoriales.
- Se administra solo lo que está por debajo del nivel propio y dentro del territorio.

**Roles base** (precisa el punto 6 de [D-104](D-104-cuentas-acceso-por-nombramiento.md))
- Ambos roles tienen TOTP obligatorio y son editables desde el panel.
- **Dirigente territorial:**
  - consulta y gestiona órganos, nombramientos y coordinaciones de su territorio;
  - nombra, pero sin dar acceso;
  - abre o enlaza casas.

  Es el rol por defecto de los cargos de órganos estatutarios.
- **Coordinador territorial:** consulta su estructura y abre o enlaza casas. Es el rol por
  defecto de los cargos de coordinaciones territoriales.
- Los cargos temáticos (jurídico, finanzas, causas) usan uno de estos dos hasta que existan sus
  módulos.

**Cambio de marco** (precisa [D-102](D-102-cambio-marco-estructura.md))
- Un comité distrital cuyo distrito no tiene equivalente **no se disuelve**. Sigue instalado, con
  sus nombramientos vigentes pero sin territorio ni alcance, en la bandeja de territorio por
  resolver hasta que un admin lo reasigne o lo disuelva.

**Crédito de casas** (resuelve el pendiente de [D-103](D-103-credito-casas-estructura.md))
- Si el integrante acreditado se da de baja del MP, la casa **pasa a la bandeja** de casas por
  enlazar. El historial de crédito conserva al acreditado anterior.
