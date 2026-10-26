# D-70 · Cargos y partidos como datos

- **Estado:** Aceptada
- **Área:** Fase C — geografía

`POST /office-types` agrega cargos sin migración; los procesos nuevos los incluyen deshabilitados. Partidos y coaliciones se administran por API. Se siembra solo PAZ (`is_own_party`); los rivales llegan después (respuesta 26).
