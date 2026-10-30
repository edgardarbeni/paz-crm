from app.core.modules import ModuleSpec

MODULE = ModuleSpec(
    name="party_structure",
    order=70,
    schema="party_structure",
    models="app.modules.party_structure.models",
    routers=("app.modules.party_structure.router:router",),
    permissions="app.modules.party_structure.permissions:StructurePerm",
    cli="app.modules.party_structure.cli:app",
)
