# D-05 · PostgreSQL 18 + PostGIS 3.5+

- **Estado:** Aceptada
- **Área:** Geografía electoral

Se usa `uuidv7()` nativo.
*Riesgo:* hay que verificar que el Postgres administrado de DigitalOcean y el de AWS ofrezcan PG18 con PostGIS. *Alternativa:* PG17 con UUIDv7 generado en la aplicación, sin otro impacto.
