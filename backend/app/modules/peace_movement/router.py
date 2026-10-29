"""/peace-movement — members, goals, settings, zone coordinators and branch scopes
(docs/modules/peace-movement.md). Everything is limited by the member scope (D-83)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Path, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import SessionDep
from app.core.pagination import CursorPage, PageParams, page_params
from app.core.storage import ObjectStorage, StorageDep
from app.modules.identity.dependencies import CurrentUser, permission
from app.modules.identity.permissions import Perm
from app.modules.peace_movement import catalog, houses, members, scope
from app.modules.peace_movement.models import (
    Member,
    PeaceHouse,
    PeaceHouseMeeting,
    PeaceHousePhoto,
    ZoneCoordinator,
)
from app.modules.peace_movement.permissions import PeacePerm
from app.modules.peace_movement.schemas import (
    AttendeeOut,
    BranchesIn,
    BranchOut,
    ChildrenPage,
    CreditIn,
    DirectCounts,
    EnrollmentIn,
    HouseAddressOut,
    HouseGoalIn,
    HouseGoalOut,
    HouseIn,
    HouseMemberIn,
    HouseMemberOut,
    HouseOut,
    HouseSummary,
    HouseUpdate,
    LevelChangeIn,
    LevelChangeOut,
    LevelGoalIn,
    LevelGoalOut,
    LevelOut,
    LocationConsentIn,
    MeetingIn,
    MeetingOut,
    MeetingSummary,
    MemberHistory,
    MemberOut,
    MemberSummary,
    PhotoOut,
    ReasonIn,
    ReassignIn,
    RecruiterChangeOut,
    ScheduleSlot,
    SettingsIn,
    SettingsOut,
    ZoneCoordinatorIn,
    ZoneCoordinatorOut,
    ZoneNodeOut,
)
from app.modules.people.models import Person
from app.modules.people.views import CryptoDep, person_out, person_summary

router = APIRouter(prefix="/peace-movement", tags=["peace-movement"])

Reader = Annotated[CurrentUser, permission(PeacePerm.MEMBER_READ)]
Writer = Annotated[CurrentUser, permission(PeacePerm.MEMBER_WRITE)]
Validator = Annotated[CurrentUser, permission(PeacePerm.MEMBER_VALIDATE)]
Reassigner = Annotated[CurrentUser, permission(PeacePerm.MEMBER_REASSIGN)]
GoalManager = Annotated[CurrentUser, permission(PeacePerm.GOAL_MANAGE)]
UserReader = Annotated[CurrentUser, permission(Perm.USER_READ)]
ScopeAssigner = Annotated[CurrentUser, permission(Perm.USER_ASSIGN_SCOPES)]
MemberId = Annotated[uuid.UUID, Path(description="Id del pacificador.")]
StateFilter = Annotated[uuid.UUID | None, Query(description="Estado (incluye la meta nacional).")]
History = Annotated[bool, Query(description="Incluir metas o vigencias ya cerradas.")]


def _actor(user: CurrentUser) -> members.Actor:
    return members.Actor(
        user_id=user.id,
        geo=user.geo,
        can_accept_curp_incoherence=user.has(Perm.PERSON_READ_SENSITIVE),
    )


# --- catalogs ---------------------------------------------------------------------------------


@router.get("/levels", operation_id="listParticipationLevels", summary="Niveles de participación")
async def list_levels(db: SessionDep, _: Reader) -> list[LevelOut]:
    return [LevelOut.model_validate(level) for level in await catalog.list_levels(db)]


@router.get("/level-goals", operation_id="listLevelGoals", summary="Metas de reclutamiento")
async def list_level_goals(
    db: SessionDep, _: Reader, state_id: StateFilter = None, history: History = False
) -> list[LevelGoalOut]:
    goals = await catalog.list_level_goals(db, state_id=state_id, history=history)
    return [LevelGoalOut.model_validate(goal) for goal in goals]


@router.post(
    "/level-goals",
    operation_id="setLevelGoal",
    summary="Fijar la meta de un nivel (nacional o por estado)",
    status_code=status.HTTP_201_CREATED,
)
async def set_level_goal(db: SessionDep, _: GoalManager, body: LevelGoalIn) -> LevelGoalOut:
    return LevelGoalOut.model_validate(await catalog.set_level_goal(db, body))


@router.get("/house-goals", operation_id="listHouseGoals", summary="Metas de integrantes por casa")
async def list_house_goals(
    db: SessionDep, _: Reader, state_id: StateFilter = None, history: History = False
) -> list[HouseGoalOut]:
    goals = await catalog.list_house_goals(db, state_id=state_id, history=history)
    return [HouseGoalOut.model_validate(goal) for goal in goals]


@router.post(
    "/house-goals",
    operation_id="setHouseGoal",
    summary="Fijar la meta de integrantes por casa",
    status_code=status.HTTP_201_CREATED,
)
async def set_house_goal(db: SessionDep, _: GoalManager, body: HouseGoalIn) -> HouseGoalOut:
    return HouseGoalOut.model_validate(await catalog.set_house_goal(db, body))


@router.get("/settings", operation_id="getPeaceSettings", summary="Configuración del módulo")
async def get_settings(db: SessionDep, _: Reader) -> SettingsOut:
    settings = await catalog.get_settings(db)
    await db.commit()
    return SettingsOut.model_validate(settings)


@router.put("/settings", operation_id="updatePeaceSettings", summary="Cambiar la configuración")
async def update_settings(db: SessionDep, _: GoalManager, body: SettingsIn) -> SettingsOut:
    return SettingsOut.model_validate(await catalog.update_settings(db, body))


async def _zone_out(db: AsyncSession, zone: ZoneCoordinator) -> ZoneCoordinatorOut:
    nodes, count = await catalog.zone_details(db, zone.id)  # type: ignore[arg-type]
    return ZoneCoordinatorOut(
        id=zone.id,
        user_id=zone.user_id,
        state_id=zone.state_id,
        valid_from=zone.valid_from,
        valid_to=zone.valid_to,
        nodes=[
            ZoneNodeOut.model_validate(
                {"level": node.level, "node_id": getattr(node, f"{node.level}_id")}
            )
            for node in nodes
        ],
        section_count=count,
    )


@router.get(
    "/zone-coordinators",
    operation_id="listZoneCoordinators",
    summary="Coordinadores de zona (crédito de casas sin Embajador)",
)
async def list_zone_coordinators(
    db: SessionDep, _: Reader, state_id: StateFilter = None, history: History = False
) -> list[ZoneCoordinatorOut]:
    zones = await catalog.list_zone_coordinators(db, state_id=state_id, history=history)
    return [await _zone_out(db, zone) for zone in zones]


@router.post(
    "/zone-coordinators",
    operation_id="createZoneCoordinator",
    summary="Asignar un coordinador de zona",
    status_code=status.HTTP_201_CREATED,
)
async def create_zone_coordinator(
    db: SessionDep, _: GoalManager, body: ZoneCoordinatorIn
) -> ZoneCoordinatorOut:
    return await _zone_out(db, await catalog.create_zone_coordinator(db, body))


@router.post(
    "/zone-coordinators/{zone_id}/end",
    operation_id="endZoneCoordinator",
    summary="Terminar la vigencia de un coordinador de zona",
)
async def end_zone_coordinator(
    db: SessionDep, _: GoalManager, zone_id: uuid.UUID
) -> ZoneCoordinatorOut:
    return await _zone_out(db, await catalog.end_zone_coordinator(db, zone_id))


# --- members ----------------------------------------------------------------------------------


def _summary(crypto: CryptoDep, member: Member, person: Person, sensitive: bool) -> MemberSummary:
    return MemberSummary(
        id=member.id,
        person=person_summary(crypto, person, sensitive),
        level_id=member.level_id,
        status=member.status,
        depth=member.depth,
        state_id=member.state_id,
        section_id=member.section_id,
        recruited_by_member_id=member.recruited_by_member_id,
        enrolled_on=member.enrolled_on,
    )


async def _summaries(
    db: AsyncSession, crypto: CryptoDep, items: list[Member], sensitive: bool
) -> list[MemberSummary]:
    persons = await members.people_of(db, items)
    return [_summary(crypto, m, persons[m.person_id], sensitive) for m in items]


async def _member_out(
    db: AsyncSession, crypto: CryptoDep, user: CurrentUser, member_id: uuid.UUID
) -> MemberOut:
    sensitive = user.has(Perm.PERSON_READ_SENSITIVE)
    member, view = await members.read_member(db, user.geo, member_id, unmasked=sensitive)
    counts = await members.direct_counts(db, user.geo, member)
    goal, pct, light = await members.progress(db, member, counts["active"])
    recruiter = None
    if member.recruited_by_member_id is not None:
        parent = await db.get(Member, member.recruited_by_member_id)
        if parent is not None:
            recruiter = (await _summaries(db, crypto, [parent], sensitive))[0]
    return MemberOut(
        id=member.id,
        person=person_out(crypto, view, sensitive),
        level_id=member.level_id,
        status=member.status,
        status_reason=member.status_reason,
        origin=member.origin,
        origin_detail=member.origin_detail,
        channel=member.channel,
        enrolled_on=member.enrolled_on,
        left_on=member.left_on,
        recruited_by=recruiter,
        referral_code=member.referral_code,
        depth=member.depth,
        state_id=member.state_id,
        section_id=member.section_id,
        validated_at=member.validated_at,
        direct=DirectCounts(**counts),
        recruit_goal=goal,
        progress_pct=pct,
        traffic_light=light,
    )


@router.get("/members", operation_id="searchMembers", summary="Buscar pacificadores")
async def search_members(
    db: SessionDep,
    crypto: CryptoDep,
    user: Reader,
    params: Annotated[PageParams, Depends(page_params)],
    status_: Annotated[
        str | None,
        Query(alias="status", pattern="^(pending_validation|active|rejected|left|withdrawn)$"),
    ] = None,
    level_id: uuid.UUID | None = None,
    state_id: uuid.UUID | None = None,
    recruiter_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
) -> CursorPage[MemberSummary]:
    page = await members.search_members(
        db,
        user.geo,
        params,
        status=status_,
        level_id=level_id,
        state_id=state_id,
        recruiter_id=recruiter_id,
        q=q,
    )
    items = await _summaries(db, crypto, page.items, user.has(Perm.PERSON_READ_SENSITIVE))
    return CursorPage[MemberSummary](
        items=items, next_cursor=page.next_cursor, has_more=page.has_more
    )


@router.post(
    "/members",
    operation_id="enrollMember",
    summary="Inscribir pacificador",
    status_code=status.HTTP_201_CREATED,
)
async def enroll_member(
    db: SessionDep, crypto: CryptoDep, user: Writer, body: EnrollmentIn
) -> MemberOut:
    member = await members.enroll(db, crypto, _actor(user), body)
    return await _member_out(db, crypto, user, member.id)  # type: ignore[arg-type]


@router.get("/members/{member_id}", operation_id="getMember", summary="Detalle de pacificador")
async def get_member(
    db: SessionDep, crypto: CryptoDep, user: Reader, member_id: MemberId
) -> MemberOut:
    return await _member_out(db, crypto, user, member_id)


@router.get(
    "/members/{member_id}/children",
    operation_id="listMemberChildren",
    summary="Reclutas directos (los de fuera del alcance, solo en total)",
)
async def list_children(
    db: SessionDep,
    crypto: CryptoDep,
    user: Reader,
    member_id: MemberId,
    params: Annotated[PageParams, Depends(page_params)],
) -> ChildrenPage:
    page, hidden = await members.children(db, user.geo, member_id, params)
    items = await _summaries(db, crypto, page.items, user.has(Perm.PERSON_READ_SENSITIVE))
    return ChildrenPage(
        items=items, next_cursor=page.next_cursor, has_more=page.has_more, hidden=hidden
    )


@router.get(
    "/members/{member_id}/history",
    operation_id="getMemberHistory",
    summary="Historial de niveles y reclutadores",
)
async def get_history(db: SessionDep, user: Reader, member_id: MemberId) -> MemberHistory:
    levels, recruiters = await members.history(db, user.geo, member_id)
    return MemberHistory(
        levels=[LevelChangeOut.model_validate(item) for item in levels],
        recruiters=[RecruiterChangeOut.model_validate(item) for item in recruiters],
    )


@router.post(
    "/members/{member_id}/validate",
    operation_id="validateMember",
    summary="Validar inscripción pendiente",
)
async def validate_member(
    db: SessionDep, crypto: CryptoDep, user: Validator, member_id: MemberId
) -> MemberOut:
    await members.validate(db, _actor(user), member_id)
    return await _member_out(db, crypto, user, member_id)


@router.post(
    "/members/{member_id}/reject",
    operation_id="rejectMember",
    summary="Rechazar inscripción pendiente",
)
async def reject_member(
    db: SessionDep, crypto: CryptoDep, user: Validator, member_id: MemberId, body: ReasonIn
) -> MemberOut:
    await members.reject(db, _actor(user), member_id, body.reason)
    return await _member_out(db, crypto, user, member_id)


@router.post(
    "/members/{member_id}/leave",
    operation_id="memberLeaves",
    summary="Registrar que el pacificador deja el movimiento",
)
async def leave(
    db: SessionDep, crypto: CryptoDep, user: Validator, member_id: MemberId, body: ReasonIn
) -> MemberOut:
    await members.leave(db, _actor(user), member_id, body.reason)
    return await _member_out(db, crypto, user, member_id)


@router.post(
    "/members/{member_id}/level",
    operation_id="changeMemberLevel",
    summary="Cambiar el nivel de participación",
)
async def change_level(
    db: SessionDep, crypto: CryptoDep, user: Writer, member_id: MemberId, body: LevelChangeIn
) -> MemberOut:
    await members.change_level(db, _actor(user), member_id, body.level_id, body.reason)
    return await _member_out(db, crypto, user, member_id)


@router.post(
    "/members/{member_id}/reassign",
    operation_id="reassignMember",
    summary="Cambiar el reclutador (mueve toda su red)",
)
async def reassign(
    db: SessionDep, crypto: CryptoDep, user: Reassigner, member_id: MemberId, body: ReassignIn
) -> MemberOut:
    await members.reassign(db, _actor(user), member_id, body.recruiter_member_id, body.reason)
    return await _member_out(db, crypto, user, member_id)


# --- branch scopes ----------------------------------------------------------------------------


async def _branches_out(
    db: AsyncSession, crypto: CryptoDep, user_id: uuid.UUID, sensitive: bool
) -> list[BranchOut]:
    branches = await scope.branches_of(db, user_id)
    nodes = [await db.get(Member, branch.member_id) for branch in branches]
    persons = await members.people_of(db, [n for n in nodes if n is not None])
    return [
        BranchOut(
            member_id=node.id,
            person=person_summary(crypto, persons[node.person_id], sensitive),
            depth=node.depth,
        )
        for node in nodes
        if node is not None
    ]


@router.get(
    "/users/{user_id}/branches",
    operation_id="listUserBranches",
    summary="Ramas asignadas a un usuario (alcance por rama)",
)
async def list_branches(
    db: SessionDep, crypto: CryptoDep, user: UserReader, user_id: uuid.UUID
) -> list[BranchOut]:
    return await _branches_out(db, crypto, user_id, user.has(Perm.PERSON_READ_SENSITIVE))


@router.put(
    "/users/{user_id}/branches",
    operation_id="setUserBranches",
    summary="Reemplazar las ramas de un usuario",
)
async def set_branches(
    db: SessionDep, crypto: CryptoDep, user: ScopeAssigner, user_id: uuid.UUID, body: BranchesIn
) -> list[BranchOut]:
    await scope.set_branches(db, user.geo, user_id, body.member_ids)
    await db.commit()
    return await _branches_out(db, crypto, user_id, user.has(Perm.PERSON_READ_SENSITIVE))


# --- Peace Houses -----------------------------------------------------------------------------

HouseReader = Annotated[CurrentUser, permission(PeacePerm.HOUSE_READ)]
HouseWriter = Annotated[CurrentUser, permission(PeacePerm.HOUSE_WRITE)]
CreditManager = Annotated[CurrentUser, permission(PeacePerm.HOUSE_REASSIGN_CREDIT)]
HouseId = Annotated[uuid.UUID, Path(description="Id de la Casa de Paz.")]


async def _house_summaries(db: AsyncSession, items: list[PeaceHouse]) -> list[HouseSummary]:
    counts = await houses.member_counts(db, [h.id for h in items if h.id is not None])
    result = []
    for house in items:
        lon, lat = houses.approx_point(house)
        result.append(
            HouseSummary(
                id=house.id,
                name=house.name,
                status=house.status,
                state_id=house.state_id,
                municipality_id=house.municipality_id,
                section_id=house.section_id,
                approx_longitude=lon,
                approx_latitude=lat,
                member_count=counts.get(house.id, 0),  # type: ignore[arg-type]
                credited_member_id=house.credited_member_id,
                credited_user_id=house.credited_user_id,
                credit_pending=house.credited_member_id is None and house.credited_user_id is None,
                needs_reassignment=house.needs_reassignment,
                publishable=house.public_location_consent_id is not None,
                opened_on=house.opened_on,
            )
        )
    return result


async def _house_out(
    db: AsyncSession, crypto: CryptoDep, user: CurrentUser, house_id: uuid.UUID
) -> HouseOut:
    sensitive = user.has(Perm.PERSON_READ_SENSITIVE)
    house = await houses.read_house(db, user.geo, house_id, unmasked=sensitive)
    summary = (await _house_summaries(db, [house]))[0]
    roles: dict[str, MemberSummary | None] = {"host": None, "contact": None}
    for key, member_id in (("host", house.host_member_id), ("contact", house.contact_member_id)):
        if member_id is not None:
            member = await db.get(Member, member_id)
            if member is not None:
                roles[key] = (await _summaries(db, crypto, [member], sensitive))[0]
    address = houses.decoded_address(crypto, house)
    goal, pct = await houses.progress(db, house, summary.member_count)
    return HouseOut(
        **summary.model_dump(),
        schedule=[ScheduleSlot.model_validate(slot) for slot in house.schedule],
        capacity=house.capacity,
        address=HouseAddressOut(**address)
        if sensitive
        else HouseAddressOut(postal_code=address.get("postal_code")),
        host=roles["host"],
        contact=roles["contact"],
        opened_by_member_id=house.opened_by_member_id,
        member_goal=goal,
        progress_pct=pct,
        consolidated_on=house.consolidated_on,
        first_consolidated_on=house.first_consolidated_on,
        closed_on=house.closed_on,
        status_reason=house.status_reason,
    )


@router.get("/houses", operation_id="searchPeaceHouses", summary="Buscar Casas de Paz")
async def search_houses(
    db: SessionDep,
    user: HouseReader,
    params: Annotated[PageParams, Depends(page_params)],
    status_: Annotated[
        str | None, Query(alias="status", pattern="^(open|consolidated|closed)$")
    ] = None,
    state_id: uuid.UUID | None = None,
    credited_member_id: uuid.UUID | None = None,
    credit_pending: bool | None = None,
    needs_reassignment: bool | None = None,
    publishable: bool | None = None,
) -> CursorPage[HouseSummary]:
    page = await houses.search_houses(
        db,
        user.geo,
        params,
        status=status_,
        state_id=state_id,
        credited_member_id=credited_member_id,
        credit_pending=credit_pending,
        needs_reassignment=needs_reassignment,
        publishable=publishable,
    )
    return CursorPage[HouseSummary](
        items=await _house_summaries(db, page.items),
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


@router.post(
    "/houses",
    operation_id="openPeaceHouse",
    summary="Abrir una Casa de Paz",
    status_code=status.HTTP_201_CREATED,
)
async def open_house(
    db: SessionDep, crypto: CryptoDep, user: HouseWriter, body: HouseIn
) -> HouseOut:
    house = await houses.open_house(db, crypto, _actor(user), body)
    return await _house_out(db, crypto, user, house.id)  # type: ignore[arg-type]


@router.get("/houses/{house_id}", operation_id="getPeaceHouse", summary="Detalle de Casa de Paz")
async def get_house(
    db: SessionDep, crypto: CryptoDep, user: HouseReader, house_id: HouseId
) -> HouseOut:
    return await _house_out(db, crypto, user, house_id)


@router.patch("/houses/{house_id}", operation_id="updatePeaceHouse", summary="Editar Casa de Paz")
async def update_house(
    db: SessionDep, crypto: CryptoDep, user: HouseWriter, house_id: HouseId, body: HouseUpdate
) -> HouseOut:
    await houses.update_house(db, _actor(user), house_id, body)
    return await _house_out(db, crypto, user, house_id)


@router.post(
    "/houses/{house_id}/close", operation_id="closePeaceHouse", summary="Cerrar Casa de Paz"
)
async def close_house(
    db: SessionDep, crypto: CryptoDep, user: HouseWriter, house_id: HouseId, body: ReasonIn
) -> HouseOut:
    await houses.close_house(db, _actor(user), house_id, body.reason)
    return await _house_out(db, crypto, user, house_id)


@router.post(
    "/houses/{house_id}/credit",
    operation_id="reassignHouseCredit",
    summary="Reasignar el crédito de una Casa de Paz",
)
async def reassign_credit(
    db: SessionDep, crypto: CryptoDep, user: CreditManager, house_id: HouseId, body: CreditIn
) -> HouseOut:
    await houses.reassign_credit(db, _actor(user), house_id, body)
    return await _house_out(db, crypto, user, house_id)


@router.get(
    "/houses/{house_id}/members", operation_id="listHouseMembers", summary="Integrantes vigentes"
)
async def list_house_members(
    db: SessionDep, crypto: CryptoDep, user: HouseReader, house_id: HouseId
) -> list[HouseMemberOut]:
    house = await houses.visible_house(db, user.geo, house_id)
    rows = await houses.current_members(db, house.id)  # type: ignore[arg-type]
    nodes = {row.member_id: await db.get(Member, row.member_id) for row in rows}
    summaries = await _summaries(
        db,
        crypto,
        [n for n in nodes.values() if n is not None],
        user.has(Perm.PERSON_READ_SENSITIVE),
    )
    by_id = {s.id: s for s in summaries}
    return [
        HouseMemberOut(member=by_id[row.member_id], joined_on=row.joined_on, source=row.source)
        for row in rows
        if row.member_id in by_id
    ]


@router.post(
    "/houses/{house_id}/members",
    operation_id="addHouseMember",
    summary="Asignar un integrante",
    status_code=status.HTTP_201_CREATED,
)
async def add_house_member(
    db: SessionDep, crypto: CryptoDep, user: HouseWriter, house_id: HouseId, body: HouseMemberIn
) -> list[HouseMemberOut]:
    await houses.add_member(db, _actor(user), house_id, body.member_id)
    return await list_house_members(db, crypto, user, house_id)


@router.delete(
    "/houses/{house_id}/members/{member_id}",
    operation_id="removeHouseMember",
    summary="Registrar que un integrante deja la casa",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_house_member(
    db: SessionDep, user: HouseWriter, house_id: HouseId, member_id: MemberId
) -> None:
    await houses.remove_member(db, _actor(user), house_id, member_id)


@router.post(
    "/houses/{house_id}/public-location-consent",
    operation_id="recordHouseLocationConsent",
    summary="Registrar el consentimiento del anfitrión para publicar la ubicación",
)
async def record_location_consent(
    db: SessionDep, crypto: CryptoDep, user: HouseWriter, house_id: HouseId, body: LocationConsentIn
) -> HouseOut:
    await houses.record_location_consent(
        db, _actor(user), house_id, channel=body.channel, evidence_uri=body.evidence_uri
    )
    return await _house_out(db, crypto, user, house_id)


@router.delete(
    "/houses/{house_id}/public-location-consent",
    operation_id="revokeHouseLocationConsent",
    summary="Retirar la ubicación publicable",
)
async def revoke_location_consent(
    db: SessionDep, crypto: CryptoDep, user: HouseWriter, house_id: HouseId
) -> HouseOut:
    await houses.revoke_location_consent(db, _actor(user), house_id)
    return await _house_out(db, crypto, user, house_id)


def _attendees(
    attendance: list[tuple[Person, uuid.UUID | None]], crypto: CryptoDep, sensitive: bool
) -> list[AttendeeOut]:
    return [
        AttendeeOut(person=person_summary(crypto, person, sensitive), member_id=member_id)
        for person, member_id in attendance
    ]


def _meeting_summary(
    meeting: PeaceHouseMeeting, attendance: list[tuple[Person, uuid.UUID | None]]
) -> MeetingSummary:
    return MeetingSummary(
        id=meeting.id,
        held_at=meeting.held_at,
        topic=meeting.topic,
        attendee_count=len(attendance),
        guest_count=sum(1 for _, member_id in attendance if member_id is None),
    )


@router.get(
    "/houses/{house_id}/meetings", operation_id="listHouseMeetings", summary="Reuniones de la casa"
)
async def list_meetings(
    db: SessionDep,
    user: HouseReader,
    house_id: HouseId,
    params: Annotated[PageParams, Depends(page_params)],
) -> CursorPage[MeetingSummary]:
    page = await houses.list_meetings(db, user.geo, house_id, params)
    attendance = await houses.attendance(db, [m.id for m in page.items if m.id is not None])
    return CursorPage[MeetingSummary](
        items=[_meeting_summary(m, attendance[m.id]) for m in page.items],  # type: ignore[index]
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


@router.post(
    "/houses/{house_id}/meetings",
    operation_id="addHouseMeeting",
    summary="Registrar una reunión con su asistencia",
    status_code=status.HTTP_201_CREATED,
)
async def add_meeting(
    db: SessionDep, crypto: CryptoDep, user: HouseWriter, house_id: HouseId, body: MeetingIn
) -> MeetingOut:
    meeting = await houses.add_meeting(db, crypto, _actor(user), house_id, body)
    return await get_meeting(db, crypto, user, house_id, meeting.id)  # type: ignore[arg-type]


@router.get(
    "/houses/{house_id}/meetings/{meeting_id}",
    operation_id="getHouseMeeting",
    summary="Detalle de una reunión",
)
async def get_meeting(
    db: SessionDep, crypto: CryptoDep, user: HouseReader, house_id: HouseId, meeting_id: uuid.UUID
) -> MeetingOut:
    meeting = await houses.get_meeting(db, user.geo, house_id, meeting_id)
    attendance = (await houses.attendance(db, [meeting_id]))[meeting_id]
    return MeetingOut(
        **_meeting_summary(meeting, attendance).model_dump(),
        notes=meeting.notes,
        attendees=_attendees(attendance, crypto, user.has(Perm.PERSON_READ_SENSITIVE)),
    )


async def _photo_out(storage: ObjectStorage, photo: PeaceHousePhoto) -> PhotoOut:
    return PhotoOut(
        id=photo.id,
        caption=photo.caption,
        content_type=photo.content_type,
        size_bytes=photo.size_bytes,
        url=await storage.url(photo.storage_key),
        created_at=photo.created_at,
    )


@router.get("/houses/{house_id}/photos", operation_id="listHousePhotos", summary="Fotos de la casa")
async def list_photos(
    db: SessionDep, storage: StorageDep, user: HouseReader, house_id: HouseId
) -> list[PhotoOut]:
    return [await _photo_out(storage, p) for p in await houses.list_photos(db, user.geo, house_id)]


@router.post(
    "/houses/{house_id}/photos",
    operation_id="uploadHousePhoto",
    summary="Subir una foto (JPEG, PNG o WebP, hasta 10 MB)",
    status_code=status.HTTP_201_CREATED,
)
async def upload_photo(
    db: SessionDep,
    storage: StorageDep,
    user: HouseWriter,
    house_id: HouseId,
    file: Annotated[UploadFile, File(description="Imagen JPEG, PNG o WebP.")],
    caption: Annotated[str | None, Form(max_length=300)] = None,
) -> PhotoOut:
    data = await file.read(houses.PHOTO_MAX_BYTES + 1)
    photo = await houses.add_photo(
        db,
        storage,
        _actor(user),
        house_id,
        data=data,
        content_type=file.content_type or "",
        caption=caption,
    )
    return await _photo_out(storage, photo)


@router.delete(
    "/houses/{house_id}/photos/{photo_id}",
    operation_id="deleteHousePhoto",
    summary="Eliminar una foto",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_photo(
    db: SessionDep, storage: StorageDep, user: HouseWriter, house_id: HouseId, photo_id: uuid.UUID
) -> None:
    await houses.delete_photo(db, storage, _actor(user), house_id, photo_id)
