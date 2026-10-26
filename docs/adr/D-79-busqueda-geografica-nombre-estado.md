# D-79 · Búsqueda geográfica por nombre y estado

- **Estado:** Aceptada
- **Área:** Fase C — geografía

Todos los selectores de geografía (domicilio de personas, alcance de usuarios, postulaciones, procesos) buscan por nombre o por número más el estado, no solo por clave INE. Se cubren los formatos pedidos por el usuario:

| Nivel | Búsqueda | Se muestra |
|---|---|---|
| Estado | Nombre | Nombre |
| Municipio | Nombre, con o sin estado | Nombre · Estado |
| Distrito federal o local | Número y estado, o solo el estado | Distrito federal 03 · Estado |
| Sección | Número sin el prefijo del estado (la clave INE es `##-####`), con o sin estado | Sección 0338 · Estado (más municipio y clave) |
| Localidad y colonia | Nombre, con o sin estado | Nombre · Estado (más municipio) |

- **Un solo intérprete en `GET /geography/search`.** Las claves INE de siempre siguen funcionando. Además entiende: número + estado en cualquier orden, con palabras de nivel opcionales (`sección 338 de aguascalientes`, `df 3 jalisco`); nombre + estado (`centro jalisco`); y solo un estado (`jalisco`), que con `level` devuelve lo que contiene. Si el texto que acompaña al número no es un estado, se toma como nombre (`18 de marzo`).
- **El estado se reconoce sin catálogo de abreviaturas**, para no inventar datos: vale su nombre completo o el inicio de una de sus palabras. Si coincide exacto, gana ese estado (`mexico` → Estado de México); si no, valen todos los que coincidan.
- **El municipio se agrega a secciones, localidades y colonias**, porque los nombres se repiten («Centro» existe en casi todos los municipios). La respuesta incluye `state_name` y `municipality_name`, también en el listado y el detalle, así que las tablas ya no piden el estado nodo por nodo.
- **`state_id` opcional:** en el domicilio de una persona, una vez elegido el estado, los demás niveles buscan solo dentro de él.
- **Explorador:** un número busca por clave del nivel; en distritos y secciones, el texto busca por estado.
- **Rendimiento con los 32 estados cargados (local):** p95 de 5 a 24 ms. El peor caso es buscar por nombre en todos los niveles a la vez. La meta es menos de 200 ms (índices trigram existentes y filtro por `state_id`).
- **Captura rápida:** el autocompletado ya no pierde las teclas que llegan antes de que su campo de búsqueda tome el foco.
