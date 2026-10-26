# D-66 · Personas: visibilidad, enmascarado y permisos

- **Estado:** Aceptada
- **Área:** Fase C — geografía

- **Visibilidad con alcance limitado (suposición):** una persona es visible si su domicilio principal está en el alcance, si integra una postulación visible para el usuario, o si aún no tiene domicilio (para poder capturarla). No se puede registrar un domicilio fuera del alcance.
- **Enmascarado:** CURP (`GOME******MASRRN07`), contactos (`******4567`, `m***@dominio`) y calle/números solo se ven completos con `people.person.read_sensitive`. La geografía del domicilio siempre se ve ([D-31](D-31-cifrado-nivel-aplicacion.md)).
- **CURP incoherente:** forzar el registro con `accept_curp_incoherence` requiere `people.person.read_sensitive` (suposición: no se creó un permiso aparte). La persona queda marcada con `curp_coherence_overridden` y la respuesta trae las advertencias.
- **Permisos por rol** (migración 0008):
  - admin: personas completo, más candidaturas: lectura, catálogos y procesos;
  - coordinador: personas (sin borrar), lectura, captura, aprobación y excepciones de reglas;
  - capturista: personas (leer y escribir), lectura y captura de candidaturas;
  - consulta: lectura de personas y candidaturas.
- **Búsqueda:** por nombre sin acentos (índice de trigramas sobre `f_unaccent(lower(search_name))`), por CURP o por teléfono exactos vía blind index.
