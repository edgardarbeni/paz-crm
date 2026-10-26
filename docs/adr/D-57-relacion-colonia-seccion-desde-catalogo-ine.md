# D-57 · Relación colonia ↔ sección desde el catálogo del INE (reemplaza [D-09](D-09-relacion-colonia-seccion.md))

- **Estado:** Aceptada
- **Área:** Fase C — geografía

- El Catálogo de Colonias del INE (corte ene-2026) publica la relación oficial colonia–sección con el mismo `ID` que la BGD. Verificado en Aguascalientes: 2,189 pares, 1,265 colonias, 100 % de coincidencia por `ID`, nombre y `CONTROL`.
- **Fuente principal:** el catálogo (`source = 'ine_catalog'`).
- **Cálculo espacial:** sirve para tres cosas:
  - el % y el área de traslape de cada par;
  - agregar pares para colonias que el catálogo no cubra (`source = 'computed'`, con el umbral de [D-09](D-09-relacion-colonia-seccion.md));
  - reportar en el importador los pares del catálogo sin intersección geométrica.
