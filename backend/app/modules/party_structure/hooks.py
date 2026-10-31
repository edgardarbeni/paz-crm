"""Registers the party structure's reaction to framework activation (ModuleSpec.setup, D-102)."""

from app.modules.geography.frameworks import on_framework_activated
from app.modules.party_structure.framework_change import remap_structure

on_framework_activated(remap_structure)
