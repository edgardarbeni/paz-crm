# D-31 · Cifrado a nivel aplicación

- **Estado:** Aceptada
- **Área:** Persona y datos sensibles

- **Cifrados:** CURP, teléfonos, correos de contacto y domicilio, con AES-256-GCM.
- **Blind index:** la CURP lleva un hash HMAC-SHA256 para la unicidad y la búsqueda exacta; los teléfonos, uno para la búsqueda exacta.
- **En claro:** el nombre, para el autocompletado con trigramas, y la geografía del domicilio (estado, municipio, sección, colonia, localidad) junto con el CP.
