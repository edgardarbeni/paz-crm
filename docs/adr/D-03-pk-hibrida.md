# D-03 · PK híbrida (excepción a CLAUDE.md)

- **Estado:** Aceptada
- **Área:** Geografía electoral

UUIDv7 en las entidades que otras tablas referencian (circunscripción, estado, municipio, distritos, sección, localidad, colonia). `bigint` en tablas masivas que nadie referencia (manzanas, puntos localidad-sección, partes de sección, errores de importación).
*Motivo:* con 2.5 M de manzanas por marco, un UUID duplica el tamaño de índices y FKs sin ningún beneficio. (Descartado: UUIDv7 en todo.)
