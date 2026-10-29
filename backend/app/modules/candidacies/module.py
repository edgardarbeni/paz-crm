from app.core.modules import ModuleSpec

MODULE = ModuleSpec(
    name="candidacies",
    order=50,
    schema="candidacies",
    models="app.modules.candidacies.models",
    routers=("app.modules.candidacies.router:router",),
)
