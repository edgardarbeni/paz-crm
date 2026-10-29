# D-85 · Precisión de la ubicación de las Casas de Paz

- **Estado:** Aceptada (2026-10-29: opción B, punto exacto cifrado y aproximado en claro)
- **Área:** Movimiento de Paz · Persona y datos sensibles

## Contexto

Muchas Casas de Paz funcionan en un domicilio particular. La ficha cifra la dirección
(`address_ciphertext`) pero deja el punto `location` en claro, porque lo usan las consultas
geográficas (sección, cruces, mapa). Un punto exacto en claro equivale a la dirección de quien
la hospeda, ligada al MP (dato sensible). La publicación exige el consentimiento expreso del
anfitrión (`public_location_consent_id`).

## Opciones

**A. Punto exacto en claro, con acceso controlado.**
- *A favor:* lo más simple.
- *En contra:* un respaldo o una lectura con permiso de casas revela domicilios; el cifrado de
  la dirección pierde sentido.

**B. Coordenadas exactas cifradas y punto aproximado en claro (recomendada).**
- Las coordenadas exactas viajan dentro de `address_ciphertext`.
- `location` guarda el punto redondeado a unos 100 m (3 decimales).
- La sección y la geografía se calculan con el punto exacto al escribir, antes de redondear.
- Verlo exacto requiere `people.person.read_sensitive` (mismo criterio que la calle, D-66).
- Con consentimiento de publicación, la salida pública usa el punto exacto descifrado.
- *A favor:* mapas y cruces siguen funcionando; la base no revela domicilios.
- *En contra:* un descifrado para ver o editar el punto exacto; casas cercanas a un límite
  pueden caer del lado contrario en el mapa aproximado (no en la sección, que se calcula
  exacta).

**C. Solo la sección, sin punto.**
- *A favor:* lo más privado.
- *En contra:* sin mapa de casas ni distancia a quien busca una.
