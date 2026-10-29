"""Registers the Peace Movement's reactions to `people` events (ModuleSpec.setup)."""

from app.modules.peace_movement.members import follow_address, withdraw_person
from app.modules.people import hooks

hooks.on_person_deleted(withdraw_person)
hooks.on_address_changed(follow_address)
