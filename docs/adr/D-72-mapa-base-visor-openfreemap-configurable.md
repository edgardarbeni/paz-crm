# D-72 · Mapa base del visor: OpenFreeMap, configurable

- **Estado:** Aceptada
- **Área:** Fase C — geografía

El usuario eligió OpenFreeMap: teselas vectoriales de OpenStreetMap, sin llave ni costo.
- Se cambia con `VITE_MAP_STYLE_URL`, que se lee al construir el panel. La CSP de producción admite el origen indicado en `PAZ_MAP_TILES_ORIGIN`.
- **Qué sale a terceros:** el navegador pide a OpenFreeMap la zona que se está viendo. No viaja ningún dato del partido; las capas electorales salen de la API con el token del usuario.
- **Worker de MapLibre:** se empaqueta con Vite (`?worker&url` y `worker.format = "es"`), porque MapLibre busca su worker junto a su propio módulo y el bundler lo mueve.
