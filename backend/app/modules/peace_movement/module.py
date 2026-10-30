from app.core.modules import ModuleSpec

MODULE = ModuleSpec(
    name="peace_movement",
    order=60,
    schema="peace_movement",
    models="app.modules.peace_movement.models",
    routers=(
        "app.modules.peace_movement.router:router",
        "app.modules.peace_movement.public_router:router",
    ),
    permissions="app.modules.peace_movement.permissions:PeacePerm",
    setup="app.modules.peace_movement.hooks",
    cli="app.modules.peace_movement.cli:app",
)
