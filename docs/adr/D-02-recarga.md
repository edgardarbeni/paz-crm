# D-02 · Recarga

- **Estado:** Aceptada
- **Área:** Geografía electoral

Recargar datos de un marco existente es un **upsert por llave natural que conserva los IDs**. Un marco nuevo solo se crea cuando hay redistritación.
*Motivo:* candidaturas, alcances de usuario y personas referencian nodos geográficos; regenerar IDs rompería esas referencias. (Descartado: un marco nuevo por cada importación.)
