# D-06 · Modelo conceptual (corrige la jerarquía de CLAUDE.md)

- **Estado:** Aceptada
- **Área:** Geografía electoral

- La **sección** es la unidad atómica del marco electoral.
- **Distrito federal (DF)**, **distrito local (DL)** y **municipio** son agrupaciones de secciones **independientes entre sí**: se traslapan y ninguna está anidada dentro de otra. Cada sección pertenece a exactamente un DF, un DL y un municipio.
- **Estado** contiene DF, DL y municipios. **Circunscripción** contiene estados.
- **Manzana, colonia y localidad** son geografía **tradicional** (no electoral) y se relacionan con la sección:
  - La manzana se liga a **una** sección por la clave que trae la BGD. Sus distritos se obtienen siempre a través de la sección y **no se guardan en la manzana**. Una manzana que geométricamente cae fuera de su sección solo genera una advertencia en el reporte.
  - La colonia se relaciona **N:M** con las secciones (ver [D-09](D-09-relacion-colonia-seccion.md)).
