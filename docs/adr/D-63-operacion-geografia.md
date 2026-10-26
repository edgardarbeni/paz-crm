# D-63 · Operación de la geografía

- **Estado:** Aceptada
- **Área:** Fase C — geografía

- Cada corrida de importación registra tiempos por etapa (`counts.timings_s`).
- Después de reconstruir los alcances en bloque se ejecuta `ANALYZE identity.user_scope_sections` (visto en el benchmark nacional: sin estadísticas, una tesela acotada tardó 207 ms en lugar de 5.6 ms).
- `scripts/import-national.sh` carga los 32 estados desde una carpeta local.
- `scripts/benchmark_geo.py` mide la API de punta a punta.
