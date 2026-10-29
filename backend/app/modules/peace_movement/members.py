"""Members of the Peace Movement: enrollment, validation, level and recruiter changes, leaving,
and reads limited by the member scope (docs/modules/peace-movement.md, D-83, D-91, D-92).

Writes go through the ORM (audited) except the subtree path rewrite of a reassignment, a Core
UPDATE recorded with one bulk audit entry (D-90).
"""

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import ColumnElement, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlmodel import col

from app.core.audit import record_access, record_bulk
from app.core.db.base import pk
from app.core.errors import BadRequestError, ConflictError, NotFoundError
from app.core.logging import get_logger
from app.core.pagination import CursorPage, PageParams, paginate, parse_sort
from app.modules.identity.services.scopes import GeoScope
from app.modules.peace_movement import catalog
from app.modules.peace_movement.models import (
    CURRENT_STATUSES,
    EnrollmentChannel,
    HouseMemberSource,
    Member,
    MemberLevelChange,
    MemberOrigin,
    MemberRecruiterChange,
    MemberStatus,
    NetworkChange,
)
from app.modules.peace_movement.schemas import EnrollmentIn
from app.modules.peace_movement.scope import in_branch, member_visibility
from app.modules.people import service as people
from app.modules.people.models import Person, PersonAddress

logger = get_logger(__name__)

NOTICE_CODE = "peace_movement"
TREE_SEQUENCE = "peace_movement.member_tree_ids"


class MemberRequirementsError(BadRequestError):
    code = "member-requirements"
    title = "La persona no cumple los requisitos del Movimiento de Paz"


class NoticeUnavailableError(ConflictError):
    code = "notice-unavailable"
    title = "No hay un aviso de privacidad del Movimiento de Paz vigente"


@dataclass(frozen=True, slots=True)
class Actor:
    user_id: uuid.UUID
    geo: GeoScope
    can_accept_curp_incoherence: bool = False


# --- helpers ----------------------------------------------------------------------------------


def _visible(geo: GeoScope, member: Any = Member) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = [col(member.deleted_at).is_(None)]
    scoped = member_visibility(geo, member)
    if scoped is not None:
        filters.append(scoped)
    return filters


async def visible_member(
    db: AsyncSession, geo: GeoScope, member_id: uuid.UUID, *, for_update: bool = False
) -> Member:
    statement = select(Member).where(col(Member.id) == member_id, *_visible(geo))
    if for_update:
        statement = statement.with_for_update(of=Member)
    member = (await db.execute(statement)).scalar_one_or_none()
    if member is None:
        raise NotFoundError("Pacificador no encontrado.")
    return member


def _change(kind: str, member: Member, *paths: str, **payload: Any) -> NetworkChange:
    return NetworkChange(
        kind=kind,
        member_id=member.id,
        paths=[p for p in paths if p],
        payload=payload or None,
        created_at=datetime.now(UTC),
    )


def _parent_path(path: str) -> str:
    return path.rpartition(".")[0]


async def _primary_address(db: AsyncSession, person_id: uuid.UUID) -> PersonAddress | None:
    return (
        await db.execute(
            select(PersonAddress).where(
                col(PersonAddress.person_id) == person_id,
                col(PersonAddress.is_primary).is_(True),
                col(PersonAddress.deleted_at).is_(None),
            )
        )
    ).scalar_one_or_none()


async def _home(db: AsyncSession, address: PersonAddress | None) -> tuple[uuid.UUID, uuid.UUID]:
    """(state_id, section_id) of the primary address; both are required (D-92)."""
    if address is None or address.section_id is None:
        raise MemberRequirementsError(
            "La persona necesita un domicilio principal con sección electoral."
        )
    state = await db.execute(
        text("SELECT state_id FROM geography.sections WHERE id = :id"), {"id": address.section_id}
    )
    state_id: uuid.UUID = state.scalar_one()
    return state_id, address.section_id


async def _section_in_scope(db: AsyncSession, geo: GeoScope, section_id: uuid.UUID) -> bool:
    if geo.unrestricted:
        return True
    found = await db.execute(
        text("SELECT 1 FROM identity.user_scope_sections WHERE user_id = :u AND section_id = :s"),
        {"u": geo.user_id, "s": section_id},
    )
    return found.first() is not None


async def _person_for_enrollment(
    db: AsyncSession, crypto: people.Crypto, actor: Actor, body: EnrollmentIn, *, branch: bool
) -> Person:
    if body.person_id is not None:
        if branch:
            person = await db.get(Person, body.person_id)
            if person is None or person.deleted_at is not None:
                raise NotFoundError("Persona no encontrada.")
            return person
        return await people.visible_person(db, actor.geo, body.person_id)
    assert body.person is not None  # noqa: S101 - validated by the schema
    if not body.person.curp:
        raise MemberRequirementsError("La CURP es obligatoria para inscribirse.")
    existing = (
        await db.execute(
            select(Person).where(
                col(Person.curp_hash) == crypto.curp_hash(body.person.curp),
                col(Person.deleted_at).is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        # Reuse the person without overwriting the stored data (D-92).
        if branch:
            return existing
        return await people.visible_person(db, actor.geo, pk(existing))
    view = await people.build_person(
        db,
        crypto,
        actor.geo,
        body.person,
        can_accept_incoherence=actor.can_accept_curp_incoherence,
        address_outside_scope=branch,
    )
    return view.person


# --- enrollment -------------------------------------------------------------------------------


async def enroll(
    db: AsyncSession,
    crypto: people.Crypto,
    actor: Actor,
    body: EnrollmentIn,
    *,
    channel: EnrollmentChannel = EnrollmentChannel.PANEL,
    status: MemberStatus = MemberStatus.ACTIVE,
) -> Member:
    """Enrolls a person. From the panel the member is active; other channels (public link,
    field app) pass `pending_validation` and do not count until validated."""
    notice = await people.current_notice(db, NOTICE_CODE)
    if notice is None:
        raise NoticeUnavailableError(
            "Carga el aviso de privacidad del Movimiento de Paz antes de inscribir."
        )
    level = await catalog.get_level(db, body.level_id)

    recruiter: Member | None = None
    branch = False
    if body.recruiter_member_id is not None:
        recruiter = await visible_member(db, actor.geo, body.recruiter_member_id, for_update=True)
        if recruiter.status != MemberStatus.ACTIVE:
            raise ConflictError("El reclutador debe estar activo.")
        branch = not actor.geo.unrestricted and await in_branch(db, actor.geo, recruiter)

    person = await _person_for_enrollment(db, crypto, actor, body, branch=branch)
    if person.curp_ciphertext is None:
        raise MemberRequirementsError("La persona necesita CURP para inscribirse.")
    state_id, section_id = await _home(db, await _primary_address(db, pk(person)))
    if not branch and not await _section_in_scope(db, actor.geo, section_id):
        raise NotFoundError("Persona no encontrada.")

    current = await db.execute(
        select(col(Member.id)).where(
            col(Member.person_id) == person.id,
            col(Member.status).in_(CURRENT_STATUSES),
            col(Member.deleted_at).is_(None),
        )
    )
    if current.first() is not None:
        raise ConflictError("La persona ya está inscrita en el Movimiento de Paz.")

    tree_id = int((await db.execute(text(f"SELECT nextval('{TREE_SEQUENCE}')"))).scalar_one())
    path = f"{recruiter.path}.{tree_id}" if recruiter else str(tree_id)
    consent = await people.record_consent(
        db,
        pk(person),
        notice,
        channel=body.consent.channel if channel == EnrollmentChannel.PANEL else channel.value,
        evidence_uri=body.consent.evidence_uri,
    )
    member = Member(
        person_id=pk(person),
        enrolled_on=date.today(),
        level_id=pk(level),
        recruited_by_member_id=pk(recruiter) if recruiter else None,
        origin=body.origin,
        origin_detail=body.origin_detail,
        registered_by_user_id=actor.user_id,
        channel=channel,
        status=status,
        validated_by_user_id=actor.user_id if status == MemberStatus.ACTIVE else None,
        validated_at=datetime.now(UTC) if status == MemberStatus.ACTIVE else None,
        referral_code=secrets.token_urlsafe(12),
        tree_id=tree_id,
        path=path,
        depth=path.count("."),
        state_id=state_id,
        section_id=section_id,
        consent_id=consent.id,
    )
    db.add(member)
    await db.flush()
    db.add(_change("enrolled", member, path, status=status))
    if body.house_id is not None:
        if status != MemberStatus.ACTIVE:
            raise BadRequestError("Solo una inscripción activa puede integrar una casa.")
        from app.modules.peace_movement import houses  # noqa: PLC0415 - houses imports members

        await houses.add_member(
            db, actor, body.house_id, pk(member), HouseMemberSource.ENROLLMENT, commit=False
        )
    settings = await catalog.get_settings(db)
    if member.depth > settings.depth_alert_threshold:
        logger.warning(
            "peace_movement_depth_alert",
            member_id=str(member.id),
            depth=member.depth,
            threshold=settings.depth_alert_threshold,
        )
    await db.commit()
    return member


# --- lifecycle --------------------------------------------------------------------------------


async def validate(db: AsyncSession, actor: Actor, member_id: uuid.UUID) -> Member:
    member = await visible_member(db, actor.geo, member_id, for_update=True)
    if member.status != MemberStatus.PENDING_VALIDATION:
        raise ConflictError("Solo se validan inscripciones pendientes.")
    member.status = MemberStatus.ACTIVE
    member.validated_by_user_id = actor.user_id
    member.validated_at = datetime.now(UTC)
    db.add(_change("validated", member, member.path))
    await db.commit()
    return member


async def reject(db: AsyncSession, actor: Actor, member_id: uuid.UUID, reason: str) -> Member:
    """The person created by the enrollment stays in `people` (D-92)."""
    member = await visible_member(db, actor.geo, member_id, for_update=True)
    if member.status != MemberStatus.PENDING_VALIDATION:
        raise ConflictError("Solo se rechazan inscripciones pendientes.")
    if await _has_recruits(db, member):
        raise ConflictError("La inscripción ya tiene reclutas; reasígnalos antes de rechazarla.")
    member.status = MemberStatus.REJECTED
    member.status_reason = reason
    member.validated_by_user_id = actor.user_id
    member.validated_at = datetime.now(UTC)
    db.add(_change("rejected", member, member.path))
    await db.commit()
    return member


async def leave(db: AsyncSession, actor: Actor, member_id: uuid.UUID, reason: str) -> Member:
    """The person leaves the movement but stays in `people`; the node is kept, so recruits keep
    their recruiter (D-92)."""
    member = await visible_member(db, actor.geo, member_id, for_update=True)
    if member.status != MemberStatus.ACTIVE:
        raise ConflictError("Solo un pacificador activo puede dejar el movimiento.")
    member.status = MemberStatus.LEFT
    member.status_reason = reason
    member.left_on = date.today()
    db.add(_change("left", member, member.path))
    await _leave_houses(db, member)
    await db.commit()
    return member


async def change_level(
    db: AsyncSession, actor: Actor, member_id: uuid.UUID, level_id: uuid.UUID, reason: str | None
) -> Member:
    member = await visible_member(db, actor.geo, member_id, for_update=True)
    if member.status not in CURRENT_STATUSES:
        raise ConflictError("Solo se cambia el nivel de un pacificador vigente.")
    level = await catalog.get_level(db, level_id)
    if level.id == member.level_id:
        raise ConflictError("El pacificador ya tiene ese nivel.")
    db.add(
        MemberLevelChange(
            member_id=pk(member),
            from_level_id=member.level_id,
            to_level_id=pk(level),
            changed_by_user_id=actor.user_id,
            changed_at=datetime.now(UTC),
            reason=reason,
        )
    )
    member.level_id = pk(level)
    db.add(_change("level_changed", member, member.path, to_level_id=str(level.id)))
    await db.commit()
    return member


async def reassign(
    db: AsyncSession, actor: Actor, member_id: uuid.UUID, recruiter_id: uuid.UUID, reason: str
) -> Member:
    """Moves the member and its whole subtree under another recruiter, in one transaction."""
    member = await visible_member(db, actor.geo, member_id, for_update=True)
    if recruiter_id == member.id:
        raise ConflictError("Un pacificador no puede ser su propio reclutador.")
    if recruiter_id == member.recruited_by_member_id:
        raise ConflictError("Ese ya es su reclutador.")
    recruiter = await visible_member(db, actor.geo, recruiter_id, for_update=True)
    if recruiter.status != MemberStatus.ACTIVE:
        raise ConflictError("El nuevo reclutador debe estar activo.")
    if recruiter.path == member.path or recruiter.path.startswith(f"{member.path}."):
        raise ConflictError("El nuevo reclutador está dentro de la red del pacificador.")

    old_path, old_parent = member.path, _parent_path(member.path)
    db.add(
        MemberRecruiterChange(
            member_id=pk(member),
            from_member_id=member.recruited_by_member_id,
            to_member_id=pk(recruiter),
            changed_by_user_id=actor.user_id,
            changed_at=datetime.now(UTC),
            reason=reason,
            subtree_size=0,
        )
    )
    member.recruited_by_member_id = recruiter.id
    member.origin = MemberOrigin.RECRUITER
    await db.flush()
    # Derived paths of the subtree: one Core statement, one bulk audit entry (D-90).
    moved = await db.execute(
        text(
            """
            UPDATE peace_movement.members
            SET path = CAST(:prefix AS ltree) || subpath(path, nlevel(CAST(:old AS ltree)) - 1),
                depth = nlevel(CAST(:prefix AS ltree)) + nlevel(path)
                        - nlevel(CAST(:old AS ltree)),
                updated_at = now()
            WHERE path <@ CAST(:old AS ltree)
            RETURNING id
            """
        ),
        {"prefix": recruiter.path, "old": old_path},
    )
    ids = list(moved.scalars())
    change = (
        await db.execute(
            select(MemberRecruiterChange)
            .where(col(MemberRecruiterChange.member_id) == member.id)
            .order_by(col(MemberRecruiterChange.changed_at).desc())
            .limit(1)
        )
    ).scalar_one()
    change.subtree_size = len(ids)
    await record_bulk(
        db,
        action="member_subtree_moved",
        entity_table="peace_movement.members",
        entity_ids=ids,
        details={"member_id": str(member.id), "from": old_parent, "to": recruiter.path},
    )
    await db.refresh(member)
    db.add(_change("reassigned", member, old_parent, recruiter.path, subtree_size=len(ids)))
    await db.commit()
    return member


async def _leave_houses(db: AsyncSession, member: Member) -> None:
    from app.modules.peace_movement import houses  # noqa: PLC0415 - houses imports members

    await db.flush()
    await houses.member_left(db, member)


async def _has_recruits(db: AsyncSession, member: Member) -> bool:
    found = await db.execute(
        select(col(Member.id)).where(col(Member.recruited_by_member_id) == member.id).limit(1)
    )
    return found.first() is not None


# --- hooks from people ------------------------------------------------------------------------


async def withdraw_person(db: AsyncSession, person_id: uuid.UUID) -> None:
    """ARCO cancellation of the person: their node becomes `withdrawn` and stays in the pyramid
    (recruits keep their recruiter, statistics keep their counts)."""
    rows = await db.execute(
        select(Member).where(
            col(Member.person_id) == person_id,
            col(Member.status) != MemberStatus.WITHDRAWN,
            col(Member.deleted_at).is_(None),
        )
    )
    for member in rows.scalars():
        member.status = MemberStatus.WITHDRAWN
        member.status_reason = "Cancelación ARCO de la persona"
        db.add(_change("withdrawn", member, member.path))
        await _leave_houses(db, member)
    await db.flush()


async def follow_address(db: AsyncSession, person_id: uuid.UUID, address: PersonAddress) -> None:
    """The member's state and section follow the primary address (goal and geographic scope)."""
    if address.section_id is None:
        return
    rows = await db.execute(
        select(Member).where(
            col(Member.person_id) == person_id,
            col(Member.status).in_(CURRENT_STATUSES),
            col(Member.deleted_at).is_(None),
        )
    )
    members = list(rows.scalars())
    if not members:
        return
    state_id, section_id = await _home(db, address)
    for member in members:
        member.state_id = state_id
        member.section_id = section_id
        db.add(_change("moved_home", member, member.path))
    await db.flush()


# --- reads ------------------------------------------------------------------------------------

_SORTS = {
    "enrolled_on": col(Member.enrolled_on),
    "depth": col(Member.depth),
    "created_at": col(Member.created_at),
}


async def search_members(
    db: AsyncSession,
    geo: GeoScope,
    params: PageParams,
    *,
    status: str | None = None,
    level_id: uuid.UUID | None = None,
    state_id: uuid.UUID | None = None,
    recruiter_id: uuid.UUID | None = None,
    q: str | None = None,
) -> CursorPage[Member]:
    statement = select(Member).where(*_visible(geo))
    if status:
        statement = statement.where(col(Member.status) == status)
    if level_id:
        statement = statement.where(col(Member.level_id) == level_id)
    if state_id:
        statement = statement.where(col(Member.state_id) == state_id)
    if recruiter_id:
        statement = statement.where(col(Member.recruited_by_member_id) == recruiter_id)
    if q:
        term = q.strip().lower()
        statement = statement.join(Person, col(Person.id) == col(Member.person_id)).where(
            func.f_unaccent(func.lower(col(Person.search_name))).ilike(
                func.concat("%", func.f_unaccent(term), "%")
            )
        )
    sort = parse_sort(params.sort, allowed=_SORTS, tiebreaker=col(Member.id), default="-created_at")
    page: CursorPage[Member] = await paginate(
        db, statement, sort=sort, limit=params.limit, cursor=params.cursor
    )
    return page


async def children(
    db: AsyncSession, geo: GeoScope, member_id: uuid.UUID, params: PageParams
) -> tuple[CursorPage[Member], int]:
    """Direct recruits the user can see, paginated, plus how many are hidden (totals only)."""
    parent = await visible_member(db, geo, member_id)
    child = aliased(Member)
    statement = select(child).where(
        col(child.recruited_by_member_id) == parent.id, *_visible(geo, child)
    )
    sort = parse_sort(
        params.sort,
        allowed={"enrolled_on": col(child.enrolled_on), "created_at": col(child.created_at)},
        tiebreaker=col(child.id),
        default="enrolled_on",
    )
    page: CursorPage[Member] = await paginate(
        db, statement, sort=sort, limit=params.limit, cursor=params.cursor
    )
    counts = await direct_counts(db, geo, parent)
    return page, counts["hidden"]


async def direct_counts(db: AsyncSession, geo: GeoScope, member: Member) -> dict[str, int]:
    child = aliased(Member)
    visible = member_visibility(geo, child)
    row = (
        await db.execute(
            select(
                func.count().filter(col(child.status) == MemberStatus.ACTIVE),
                func.count().filter(col(child.status) == MemberStatus.PENDING_VALIDATION),
                func.count(),
                func.count().filter(visible) if visible is not None else func.count(),
            ).where(col(child.recruited_by_member_id) == member.id, col(child.deleted_at).is_(None))
        )
    ).one()
    active, pending, total, seen = (int(value) for value in row)
    return {"active": active, "pending": pending, "total": total, "hidden": total - seen}


async def read_member(
    db: AsyncSession, geo: GeoScope, member_id: uuid.UUID, *, unmasked: bool
) -> tuple[Member, people.PersonView]:
    """Detail read: logged in the sensitive-read log (D-89). The person's data is served here
    under the member scope, not `/people`'s (D-83)."""
    member = await visible_member(db, geo, member_id)
    view = await _person_view(db, member.person_id)
    await record_access(
        db,
        action="read",
        entity_table="peace_movement.members",
        entity_id=str(member.id),
        details={"unmasked": unmasked},
    )
    await db.commit()
    return member, view


async def _person_view(db: AsyncSession, person_id: uuid.UUID) -> people.PersonView:
    # The member scope already authorized the read; a withdrawn node keeps its (deleted and,
    # after the purge, anonymized) person.
    person = await db.get(Person, person_id)
    if person is None:
        raise NotFoundError("Persona no encontrada.")
    return await people.person_view(db, person)


async def people_of(db: AsyncSession, members: list[Member]) -> dict[uuid.UUID, Person]:
    ids = {member.person_id for member in members}
    if not ids:
        return {}
    rows = await db.execute(select(Person).where(col(Person.id).in_(ids)))
    return {pk(person): person for person in rows.scalars()}


async def history(
    db: AsyncSession, geo: GeoScope, member_id: uuid.UUID
) -> tuple[list[MemberLevelChange], list[MemberRecruiterChange]]:
    member = await visible_member(db, geo, member_id)
    levels = await db.execute(
        select(MemberLevelChange)
        .where(col(MemberLevelChange.member_id) == member.id)
        .order_by(col(MemberLevelChange.changed_at).desc())
    )
    recruiters = await db.execute(
        select(MemberRecruiterChange)
        .where(col(MemberRecruiterChange.member_id) == member.id)
        .order_by(col(MemberRecruiterChange.changed_at).desc())
    )
    return list(levels.scalars()), list(recruiters.scalars())


async def progress(
    db: AsyncSession, member: Member, active_recruits: int
) -> tuple[int | None, int | None, str | None]:
    """(goal, progress %, traffic light) against the goal in force in the member's state."""
    goal = await catalog.level_goal_for(db, member.level_id, member.state_id)
    if goal is None:
        return None, None, None
    if goal.recruit_goal == 0:
        return 0, 100, "green"
    pct = active_recruits * 100 // goal.recruit_goal
    settings = await catalog.get_settings(db)
    return goal.recruit_goal, pct, catalog.traffic_light(settings, pct)
