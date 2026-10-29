from app.core.modules import ModuleSpec

MODULE = ModuleSpec(
    name="people",
    order=40,
    schema="people",
    models="app.modules.people.models",
    routers=("app.modules.people.router:router",),
)
