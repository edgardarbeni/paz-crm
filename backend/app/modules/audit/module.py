from app.core.modules import ModuleSpec

# The `audit` schema is managed by hand-written SQL migrations (D-45), not by autogenerate.
MODULE = ModuleSpec(
    name="audit",
    order=20,
    routers=("app.modules.audit.router:router",),
)
