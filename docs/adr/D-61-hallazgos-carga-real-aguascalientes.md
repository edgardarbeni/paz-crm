# D-61 · Hallazgos de la carga real de Aguascalientes

- **Estado:** Aceptada
- **Área:** Fase C — geografía

- `LOCALIDAD.tipo` 2 = URBANO(A), verificado con el catálogo; esto cierra el pendiente de [D-15](D-15-catalogos-codigos.md).
- Del catálogo de colonias del INE:
  - 323 de los 2,189 pares oficiales tienen menos de 5 % de traslape geométrico (el cálculo por umbral los habría descartado);
  - 23 pares relacionan colonias con secciones que geométricamente no tocan (`catalog_pair_without_overlap`).
- En Aguascalientes no hubo geometrías inválidas, manzanas fuera de su sección ni distritos inconsistentes. El importador los detecta igual; los tests lo prueban con la BGD sintética.
