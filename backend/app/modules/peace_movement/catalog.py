"""Levels, goals and settings (D-92; zone coordinators retired by D-103).

Goals keep their history: setting a new one closes the current row (`valid_to`) and opens
another. Progress is always measured against the goal in force for the member's (or house's)
state, falling back to the national one.
"""

import uuid
from datetime import date, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.errors import BadRequestError, ConflictError
from app.modules.peace_movement.models import (
    HouseGoal,
    LevelGoal,
    ParticipationLevel,
    Settings,
)
from app.modules.peace_movement.schemas import (
    HouseGoalIn,
    LevelGoalIn,
    SettingsIn,
)


async def list_levels(db: AsyncSession) -> list[ParticipationLevel]:
    rows = await db.execute(
        select(ParticipationLevel)
        .where(col(ParticipationLevel.deleted_at).is_(None))
        .order_by(col(ParticipationLevel.sort_order))
    )
    return list(rows.scalars())


async def get_level(db: AsyncSession, level_id: uuid.UUID) -> ParticipationLevel:
    level = await db.get(ParticipationLevel, level_id)
    if level is None or level.deleted_at is not None:
        raise BadRequestError("El nivel de participación no existe.")
    return level


async def _ensure_state(db: AsyncSession, state_id: uuid.UUID | None) -> None:
    if state_id is None:
        return
    found = await db.execute(
        text("SELECT 1 FROM geography.states WHERE id = :id AND is_active"), {"id": state_id}
    )
    if found.first() is None:
        raise BadRequestError("El estado no existe en el marco activo.")


# --- goals ------------------------------------------------------------------------------------


def _same_state(column: object, state_id: uuid.UUID | None) -> object:
    return col(column).is_(None) if state_id is None else col(column) == state_id


async def list_level_goals(
    db: AsyncSession, *, state_id: uuid.UUID | None = None, history: bool = False
) -> list[LevelGoal]:
    statement = select(LevelGoal).where(col(LevelGoal.deleted_at).is_(None))
    if state_id is not None:
        statement = statement.where(
            col(LevelGoal.state_id).is_(None) | (col(LevelGoal.state_id) == state_id)
        )
    if not history:
        statement = statement.where(col(LevelGoal.valid_to).is_(None))
    rows = await db.execute(
        statement.order_by(col(LevelGoal.level_id), col(LevelGoal.valid_from).desc())
    )
    return list(rows.scalars())


async def set_level_goal(db: AsyncSession, body: LevelGoalIn) -> LevelGoal:
    await get_level(db, body.level_id)
    await _ensure_state(db, body.state_id)
    valid_from = body.valid_from or date.today()
    current = (
        await db.execute(
            select(LevelGoal).where(
                col(LevelGoal.level_id) == body.level_id,
                _same_state(LevelGoal.state_id, body.state_id),  # type: ignore[arg-type]
                col(LevelGoal.valid_to).is_(None),
                col(LevelGoal.deleted_at).is_(None),
            )
        )
    ).scalar_one_or_none()
    if current is not None:
        if valid_from < current.valid_from:
            raise ConflictError("La vigencia no puede empezar antes que la de la meta actual.")
        if valid_from == current.valid_from:
            # Same day: a correction of the goal in force, not a new period.
            current.recruit_goal = body.recruit_goal
            current.house_goal = body.house_goal
            await db.commit()
            return current
        current.valid_to = valid_from - timedelta(days=1)
        await db.flush()
    goal = LevelGoal(
        level_id=body.level_id,
        state_id=body.state_id,
        recruit_goal=body.recruit_goal,
        house_goal=body.house_goal,
        valid_from=valid_from,
    )
    db.add(goal)
    await db.commit()
    return goal


async def level_goal_for(
    db: AsyncSession, level_id: uuid.UUID, state_id: uuid.UUID, on: date | None = None
) -> LevelGoal | None:
    """Goal in force for a level in a state: the state's own, else the national one."""
    on = on or date.today()
    rows = await db.execute(
        select(LevelGoal)
        .where(
            col(LevelGoal.level_id) == level_id,
            col(LevelGoal.state_id).is_(None) | (col(LevelGoal.state_id) == state_id),
            col(LevelGoal.valid_from) <= on,
            col(LevelGoal.valid_to).is_(None) | (col(LevelGoal.valid_to) >= on),
            col(LevelGoal.deleted_at).is_(None),
        )
        .order_by(col(LevelGoal.state_id).is_(None))  # the state's goal first
        .limit(1)
    )
    return rows.scalar_one_or_none()


async def list_house_goals(
    db: AsyncSession, *, state_id: uuid.UUID | None = None, history: bool = False
) -> list[HouseGoal]:
    statement = select(HouseGoal).where(col(HouseGoal.deleted_at).is_(None))
    if state_id is not None:
        statement = statement.where(
            col(HouseGoal.state_id).is_(None) | (col(HouseGoal.state_id) == state_id)
        )
    if not history:
        statement = statement.where(col(HouseGoal.valid_to).is_(None))
    rows = await db.execute(statement.order_by(col(HouseGoal.valid_from).desc()))
    return list(rows.scalars())


async def set_house_goal(db: AsyncSession, body: HouseGoalIn) -> HouseGoal:
    await _ensure_state(db, body.state_id)
    valid_from = body.valid_from or date.today()
    current = (
        await db.execute(
            select(HouseGoal).where(
                _same_state(HouseGoal.state_id, body.state_id),  # type: ignore[arg-type]
                col(HouseGoal.valid_to).is_(None),
                col(HouseGoal.deleted_at).is_(None),
            )
        )
    ).scalar_one_or_none()
    if current is not None:
        if valid_from < current.valid_from:
            raise ConflictError("La vigencia no puede empezar antes que la de la meta actual.")
        if valid_from == current.valid_from:
            current.member_goal = body.member_goal
            await db.commit()
            return current
        current.valid_to = valid_from - timedelta(days=1)
        await db.flush()
    goal = HouseGoal(state_id=body.state_id, member_goal=body.member_goal, valid_from=valid_from)
    db.add(goal)
    await db.commit()
    return goal


async def house_goal_for(
    db: AsyncSession, state_id: uuid.UUID, on: date | None = None
) -> HouseGoal | None:
    on = on or date.today()
    rows = await db.execute(
        select(HouseGoal)
        .where(
            col(HouseGoal.state_id).is_(None) | (col(HouseGoal.state_id) == state_id),
            col(HouseGoal.valid_from) <= on,
            col(HouseGoal.valid_to).is_(None) | (col(HouseGoal.valid_to) >= on),
            col(HouseGoal.deleted_at).is_(None),
        )
        .order_by(col(HouseGoal.state_id).is_(None))
        .limit(1)
    )
    return rows.scalar_one_or_none()


# --- settings ---------------------------------------------------------------------------------


async def get_settings(db: AsyncSession) -> Settings:
    settings = (await db.execute(select(Settings).limit(1))).scalar_one_or_none()
    if settings is None:  # seeded by migration; recreated if someone removed it
        settings = Settings()
        db.add(settings)
        await db.flush()
    return settings


async def update_settings(db: AsyncSession, body: SettingsIn) -> Settings:
    settings = await get_settings(db)
    for key, value in body.model_dump().items():
        setattr(settings, key, value)
    await db.commit()
    return settings


def traffic_light(settings: Settings, progress_pct: int) -> str:
    if progress_pct >= settings.traffic_light_green_pct:
        return "green"
    if progress_pct >= settings.traffic_light_yellow_pct:
        return "yellow"
    return "red"
