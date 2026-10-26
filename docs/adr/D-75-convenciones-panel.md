# D-75 · Convenciones del panel

- **Estado:** Aceptada
- **Área:** Fase C — geografía

- **Formularios:** TanStack Form (`createFormHook`) validado con los esquemas Zod generados del OpenAPI. Los campos vacíos se convierten en `null` antes de validar y enviar, y los mensajes salen en español (`z.locales.es`).
- **Selects nativos** para catálogos cortos: son accesibles y permiten buscar tecleando.
- **Autocompletado asíncrono** (Radix Popover + cmdk) para personas y geografía: se abre con la primera tecla, Enter elige y Supr limpia.
- **Tablas:** TanStack Table v9 con orden y paginación del lado del servidor. Para que "Anterior" funcione con cursores que solo avanzan, se guarda una pila de cursores.
- **Atajos:** `Ctrl+K`, `/`, `N`, `↑ ↓ Enter` y `Ctrl+Enter`. Las teclas sueltas se ignoran mientras se escribe en un campo.
- **Excepciones a reglas:** un 409 `rule-violation` abre un diálogo para quien tiene `candidacies.rule.override`. Pide el motivo y reintenta con `override`.
- **Lo que se muestra:** el panel oculta lo que el usuario no puede hacer; el backend es quien decide.
- **Tema:** solo tema claro por ahora.
