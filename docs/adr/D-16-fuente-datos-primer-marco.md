# D-16 · Fuente de datos del primer marco

- **Estado:** Aceptada
- **Área:** Geografía electoral

Se usa la **descarga oficial vigente del INE**, con un mismo corte para los 32 estados:
- BGD: corte del 15 de diciembre de 2025, `https://storage.googleapis.com/mapoteca/BGD_15_diciembre_2025/04 SHAPEFILE_EXTERNOS SIN NUMEXT/NN ESTADO.7z`.
- Catálogos: corte del 19 de enero de 2026, `https://storage.googleapis.com/mapoteca/CORTE_19ENE2026_PRODUCTOSCARTOGRAFICOS/CATALOGOS/...`.
- Índice de archivos: API pública `https://cartografia.ine.mx/sige8/api/bases` y `/api/catalogos`, que alimentan la página `productosCartograficos/bases`.

Esto también resuelve que la carpeta local de Baja California viniera de otra descarga. Las carpetas locales quedan solo como referencia.
