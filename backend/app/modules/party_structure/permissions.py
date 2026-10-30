"""Permission codes of the party structure (docs/modules/party-structure.md)."""

from enum import StrEnum


class StructurePerm(StrEnum):
    CATALOG_MANAGE = "party_structure.catalog.manage"
    BODY_READ = "party_structure.body.read"
    BODY_WRITE = "party_structure.body.write"
    APPOINTMENT_READ = "party_structure.appointment.read"
    APPOINTMENT_WRITE = "party_structure.appointment.write"
