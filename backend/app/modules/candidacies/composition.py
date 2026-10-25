"""Expected composition of a nomination (D-21..D-25): which offices and how many positions.

- single: the head office, 1 position.
- list: the head office with `process_offices.positions` (or the office default) positions.
- slate: the head plus every enabled office configured as member of that slate
  (`slate_parent_office_type_id`). Member counts come from the municipality settings
  (syndics, MR/RP councilors) or, when absent, from `process_offices.positions`.
- RP by "best loser" (D-21) registers no list: its expected positions are 0.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.modules.candidacies.models import (
    MunicipalitySetting,
    NominationKind,
    OfficeType,
    ProcessOffice,
    RpMethod,
)

# Member office → municipality-settings column providing its count.
_SETTING_COUNTS = {
    "syndic": "syndic_count",
    "councilor_mr": "mr_councilor_count",
    "councilor_rp": "rp_councilor_count",
    "council_member": "mr_councilor_count",
}


@dataclass(frozen=True, slots=True)
class Slot:
    office_type_id: uuid.UUID
    office_code: str
    office_name: str
    positions: int


async def expected_slots(
    db: AsyncSession,
    *,
    process_id: uuid.UUID,
    head: OfficeType,
    municipality_id: uuid.UUID | None,
) -> list[Slot]:
    assert head.id is not None  # noqa: S101
    configs = {
        config.office_type_id: config
        for config in (
            await db.execute(
                select(ProcessOffice).where(
                    col(ProcessOffice.process_id) == process_id,
                    col(ProcessOffice.deleted_at).is_(None),
                )
            )
        ).scalars()
    }
    head_config = configs.get(head.id)
    head_positions = 1
    if head.nomination_kind == NominationKind.LIST:
        head_positions = (
            (head_config.positions if head_config else None) or head.default_positions or 0
        )
        if head_config and head_config.rp_method == RpMethod.BEST_LOSER:
            head_positions = 0
    slots = [Slot(head.id, head.code, head.name, head_positions)]
    if head.nomination_kind != NominationKind.SLATE:
        return slots

    setting = None
    if municipality_id is not None:
        setting = (
            await db.execute(
                select(MunicipalitySetting).where(
                    col(MunicipalitySetting.process_id) == process_id,
                    col(MunicipalitySetting.municipality_id) == municipality_id,
                    col(MunicipalitySetting.deleted_at).is_(None),
                )
            )
        ).scalar_one_or_none()
    members = [
        config
        for config in configs.values()
        if config.is_enabled and config.slate_parent_office_type_id == head.id
    ]
    offices = {
        office.id: office
        for office in (
            await db.execute(
                select(OfficeType).where(
                    col(OfficeType.id).in_([m.office_type_id for m in members])
                )
            )
        ).scalars()
    }
    for config in sorted(members, key=lambda m: offices[m.office_type_id].sort_order):
        office = offices[config.office_type_id]
        column = _SETTING_COUNTS.get(office.code)
        positions = getattr(setting, column) if setting is not None and column else config.positions
        assert office.id is not None  # noqa: S101
        slots.append(Slot(office.id, office.code, office.name, int(positions or 0)))
    return slots
