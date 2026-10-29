from app.core.modules import ModuleSpec

MODULE = ModuleSpec(
    name="geography",
    order=30,
    schema="geography",
    models="app.modules.geography.models",
    routers=("app.modules.geography.router:router",),
)
