# D-32 · Gestión de llaves

- **Estado:** Aceptada
- **Área:** Persona y datos sensibles

Interfaz `KeyProvider` con **cifrado de sobre** (envelope). En desarrollo, llave maestra por variable de entorno; en producción, KMS (AWS KMS como destino probable) sin cambiar código. Cada registro cifrado guarda `key_version` para poder rotar.
