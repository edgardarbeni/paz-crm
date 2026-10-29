from app.core.modules import ModuleSpec

MODULE = ModuleSpec(
    name="identity",
    order=10,
    schema="identity",
    models="app.modules.identity.models",
    routers=(
        "app.modules.identity.routers.auth:router",
        "app.modules.identity.routers.admin:users_router",
        "app.modules.identity.routers.admin:roles_router",
    ),
    permissions="app.modules.identity.permissions:Perm",
)
