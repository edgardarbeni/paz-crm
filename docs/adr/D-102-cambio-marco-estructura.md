# D-102 · Cambio de marco geográfico en la estructura del partido (amplía D-41, punto 7)

- **Estado:** Aceptada (2026-10-30: opción A, remapeo automático y bandeja)
- **Área:** Estructura del partido · Geografía electoral

## Contexto

Las coordinaciones territoriales (distritos o secciones) y los comités distritales y municipales
se ligan a nodos de un marco geográfico. Hoy, al activar un marco, `paz geo activate`
(`geography/frameworks.py`) remapea `identity.user_scopes` **automáticamente** por llave natural
y **borra** los alcances sin equivalente. La ficha propone que el sistema sugiera la migración de
cada coordinación y que un admin la confirme. Si conviven los dos mecanismos, el alcance que
deriva de un nombramiento queda desfasado o vacío mientras nadie confirma.

## Opciones

**A. Remapeo automático y bandeja solo para lo que no tiene equivalente (recomendada).**
- En la misma transacción de `activate`, los distritos, secciones, municipios y comités con
  equivalente por llave natural se remapean, igual que los alcances.
- Lo que no tiene equivalente no se borra: la parte del territorio se retira (`removed_on`), y la
  coordinación o el comité aparece en una bandeja de **territorio por resolver**. Un admin elige
  entre asignar el territorio equivalente, cerrar la coordinación o disolver el comité.
- El informe de activación lista cada caso, y las concesiones se recalculan al terminar.
- *A favor:* sin ventana de alcance desfasado; el admin solo revisa las excepciones.
- *En contra:* un cambio de territorio sin equivalente reduce el alcance antes de que alguien lo
  revise (queda reportado).

**B. Todo por confirmación (lo que propone la ficha).**
- La activación genera una propuesta por coordinación y comité, y nada cambia hasta que un admin
  la confirma.
- *A favor:* control total.
- *En contra:* mientras tanto, los nodos apuntan al marco anterior y el alcance no coincide con la
  geografía activa. Además contradice el remapeo automático vigente de los alcances.

## Reglas comunes

- Se conserva el historial: un territorio retirado queda con `removed_on`, nunca se borra.
- Los comités distritales instalados sobre un distrito que desaparece no se disuelven solos (es
  la pregunta abierta 5 de la ficha). Quedan en la bandeja hasta que se responda.

*Motivo:* mantener una sola regla para todo el alcance derivado de la geografía.
