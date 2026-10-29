# D-81 · «Contiene» en el detalle de nodo

- **Estado:** Aceptada
- **Área:** Geografía electoral

El detalle de un nodo (`/geography/$level/$nodeId`) muestra lo que contiene ahí mismo, junto al mapa, en lugar de enlazar al Explorador.

- **API:** `GET /geography/{level}/{node_id}/children` devuelve, en orden, cada nivel hijo con su `count` dentro del alcance del usuario y el `parent_filter` con el que `GET /geography/{level}` lo lista.
  - La relación padre → hijos vive en el backend (`service.CHILDREN`).
  - Un nodo fuera del alcance da 403 y uno inexistente 404, igual que el detalle.
  - Los conteos no van en `getGeoNode` porque ese endpoint resuelve todas las etiquetas geográficas del panel (`GeoName`).
- **Panel:**
  - Un grupo abatible por nivel con su conteo; los grupos vacíos no se muestran.
  - Los hijos se cargan al abrir el grupo, de 50 en 50, con filtro (número o nombre) desde 13 elementos y un enlace al Explorador filtrado.
  - El primer grupo se abre solo si tiene ≤ 30 elementos.
  - El encabezado del grupo abierto queda fijo dentro de la tarjeta, que se desplaza por dentro y mide lo mismo que el mapa en pantallas anchas.
- **Mapa:**
  - Abrir un grupo agrega su capa sin mover la cámara: el encuadre del nodo se separó del efecto de capas.
  - Señalar un hijo lo resalta (relleno amarillo y contorno oscuro, distinto de todas las capas y del rojo del nodo) cuando su capa tiene teselas a ese zoom.
  - Las capas de resaltado permanecen ocultas mientras no se usan, para no descargar teselas de más.

*Motivo:* el usuario navega la jerarquía sin perder el mapa ni el contexto. Un grupo largo abierto por defecto (p. ej. 1,207 secciones de Tijuana) ocultaría a los demás. (Descartadas: listas con desplazamiento propio por grupo, porque anidan barras de desplazamiento; pestañas por nivel, porque ocultan los conteos de los otros niveles; conteos dentro de `getGeoNode`.)
