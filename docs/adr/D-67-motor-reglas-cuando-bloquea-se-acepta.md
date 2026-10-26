# D-67 · Motor de reglas: cuándo bloquea y qué se acepta

- **Estado:** Aceptada
- **Área:** Fase C — geografía

- **Configuración:** una fila por cargo prevalece sobre la del proceso, incluso para apagar una regla en un solo cargo. Al crear un proceso solo queda activa `unique_person_in_process`, bloqueante ([D-28](D-28-motor-validaciones.md)).
- **Ediciones de fórmulas:** se juzgan por lo que **introducen**. Se compara la evaluación antes y después del cambio, y solo bloquean las violaciones nuevas. Así una regla activada a mitad del proceso no congela la captura, pero sí se exige al enviar.
- **Excepciones:** requieren `candidacies.rule.override`, un motivo y que `override.rules` cubra todas las reglas violadas. Se registra una fila por violación aceptada, por ejemplo las dos fórmulas que comparten persona. Una violación aceptada ya no se reporta como pendiente.
- **Paridad (`gender_parity`):** solo al enviar o aprobar, y en la validación en seco (`GET /nominations/{id}/validation`). Cuenta a las propietarias de la posición 1 del cargo principal entre las postulaciones enviadas o aprobadas del mismo cargo en el proceso, más la evaluada. **Suposición:** cuenta como mujer el sexo `M`; `X` no suma a la cuota. Hay que confirmarlo según la ley de cada estado.
- **Alternancia:** compara el sexo de las propietarias en posiciones consecutivas del mismo cargo.
- **Suplente del mismo sexo:** parámetro `allow_male_owner_female_substitute`, para las legislaciones que permiten propietario hombre con suplente mujer.
