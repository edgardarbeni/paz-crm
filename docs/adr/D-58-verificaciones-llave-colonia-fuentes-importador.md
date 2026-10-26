# D-58 · Verificaciones sobre la llave de colonia (actualiza [D-10](D-10-llave-natural-colonia.md)) y fuentes del importador

- **Estado:** Aceptada
- **Área:** Fase C — geografía

- **Llave de colonia:** en la BGD dic-2025, `COLONIA.ID` y `CONTROL` son únicos por estado y coinciden con el catálogo. En cambio, `(municipio, nombre, CP)` tiene 18 duplicados en Aguascalientes, así que **no sirve como llave**. Se usa `(estado, ID)`. La estabilidad del `ID` entre cortes sigue sin verificarse, porque solo hay un corte disponible; el importador reporta las colonias cuyo `ID` cambia de nombre o municipio.
- **Carpetas locales:** las de `paz-maps/` son **idénticas byte por byte** a la BGD oficial dic-2025 (verificado en las 9 capas del MVP de Aguascalientes).
- **Fuentes que acepta el importador:** una carpeta de shapefiles o el 7z oficial. Los catálogos tabulares (Secciones, Manzanas, Localidades con Sección, Colonias) se descargan del INE con `paz geo download`.
