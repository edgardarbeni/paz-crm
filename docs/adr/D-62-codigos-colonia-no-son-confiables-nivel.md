# D-62 · Los códigos de colonia no son confiables a nivel nacional (corrige [D-59](D-59-mapeos-codigos-verificados.md))

- **Estado:** Aceptada
- **Área:** Fase C — geografía

- **El error:** [D-59](D-59-mapeos-codigos-verificados.md) generalizó a partir de Aguascalientes, donde `CLASIFICAC` corresponde 1:1 al tipo de colonia. La carga nacional lo desmiente. En la Ciudad de México el código 3 aparece con 11 textos distintos en el catálogo del INE (UNIDAD HABITACIONAL 533, COLONIA 35, RESIDENCIAL 11…), y estados distintos asignan textos distintos al mismo código. Además, el importador sobrescribía la descripción con la de cada estado, y eso dejaba descripciones incorrectas.
- **Descripciones de código:** solo se aceptan mientras toda la evidencia coincide, a nivel nacional. Si un estado se contradice a sí mismo, o contradice lo que fijó otro estado, el código queda con `description_conflict = true` y sin descripción, y no se vuelve a llenar en automático. Esta regla aplica a todos los catálogos de códigos.
- **Tipo de colonia:** se guarda el **texto oficial del catálogo por colonia** en `neighborhoods.type_label`. Es la fuente correcta registro por registro, independiente del código.
- **Lección:** los mapeos de códigos se validan contra el país completo antes de darlos por buenos (se agrega a riesgos).
