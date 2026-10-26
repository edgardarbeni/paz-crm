# D-52 · Reglas de RBAC

- **Estado:** Aceptada
- **Área:** Fase B — identidad

- **Superadmin:** `roles.grants_all` concede todos los permisos y lo exime del alcance geográfico.
- **Sin escalamiento:** solo se pueden asignar roles y otorgar permisos que uno mismo tiene.
- **Cuentas superadmin:** solo otro superadmin puede gestionarlas, y no se puede desactivar ni degradar al último.
- **Roles protegidos:** los de sistema no se eliminan, el de superadmin es inmutable y un rol con usuarios no se puede eliminar.
- **Permisos:** se registran en código (`Perm`) y se siembran por migración; un test detecta si código y base divergen.
