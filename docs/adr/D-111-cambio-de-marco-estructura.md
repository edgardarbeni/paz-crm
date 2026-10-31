# D-111 · Cambio de marco en la estructura y bandeja de territorio (fase 5; implementa D-102)

- **Estado:** Aceptada (2026-10-30)
- **Área:** Estructura del partido · Geografía electoral

Cómo quedó implementada [D-102](D-102-cambio-marco-estructura.md), con la regla de
[D-105](D-105-reglas-estructura-confirmadas.md) para los comités (migración `0023`).

**Punto de extensión en `geography`.** `frameworks.on_framework_activated(hook)`: los módulos con
datos atados a nodos los remapean dentro de la transacción de `paz geo activate`. Corren después
de las concesiones y los domicilios, y antes de cambiar el marco activo. `geography` no importa a
esos módulos. La estructura se registra en `party_structure/hooks.py` (`ModuleSpec.setup`) y
su conteo sale en el informe de activación (`modules`) y en la bitácora.

**Qué se remapea solo (por llave natural, como los alcances)**
- Los comités distritales y municipales vigentes pasan al nodo equivalente del marco nuevo.
- El territorio vigente de las coordinaciones también pasa a sus nodos equivalentes.
- Los órganos estatales no cambian: guardan la clave INE del estado (D-107).
- Las concesiones de los titulares se remapean en `identity` como cualquier alcance. Lo que no
  tiene equivalente se quita de la concesión.

**Bandeja de territorio por resolver (`territory_issues`)**
- **Comité sin equivalente.**
  - Llega como `committee_without_territory`. No se disuelve ni se mueve: sigue instalado y
    apuntando a su nodo anterior, así que no tiene territorio ni alcance en el marco activo.
  - Sus nombramientos siguen vigentes.
- **Coordinación que pierde nodos.**
  - Llega como `coordination_nodes_removed`, con la lista de lo perdido.
  - Esos nodos quedan retirados (`removed_on`) y la coordinación sigue con el resto.
- La resuelve **el nivel nacional** (`party_structure.catalog.manage` con alcance sin restricción,
  porque los huérfanos no tienen territorio con qué acotarlos):
  - un comité se reasigna a un nodo del marco activo del mismo tipo, y sus titulares con acceso
    lo toman como alcance; o se disuelve;
  - una coordinación se acepta con su territorio actual (se puede ampliar en
    `PUT /coordinations/{id}/territory`) o se cierra;
  - disolver y cerrar terminan los nombramientos vigentes con motivo `other` y retiran su
    acceso (D-109).

**API:** `GET /party-structure/territory-issues` (`include_resolved`) y
`POST /party-structure/territory-issues/{id}/resolve` con `action` reassign, dissolve, accept o
close. Cada resolución queda con quién, cuándo y notas.
