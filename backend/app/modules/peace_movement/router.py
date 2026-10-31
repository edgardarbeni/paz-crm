"""/peace-movement — members, goals, settings and branch scopes
(docs/modules/peace-movement.md). Everything is limited by the member scope (D-83)."""

import uuid
from datetime import date
from typing import Annotated

import segno
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Path,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import SessionDep
from app.core.errors import BadRequestError
from app.core.pagination import CursorPage, PageParams, page_params
from app.core.storage import ObjectStorage, StorageDep
from app.modules.identity.dependencies import CurrentUser, permission
from app.modules.identity.permissions import Perm
from app.modules.party_structure import access as structure
from app.modules.peace_movement import catalog, houses, intake, members, scope, stats
from app.modules.peace_movement.models import (
    Member,
    PeaceHouse,
    PeaceHouseMeeting,
    PeaceHousePhoto,
)
from app.modules.peace_movement.permissions import PeacePerm
from app.modules.peace_movement.schemas import (
    AttendeeOut,
    BatchIn,
    BatchOut,
    BranchesIn,
    BranchOut,
    ChildrenPage,
    CreditIn,
    DirectCounts,
    EnrollmentIn,
    GeoStatOut,
    GrowthPoint,
    HouseAddressOut,
    HouseGoalIn,
    HouseGoalOut,
    HouseIn,
    HouseMapOut,
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
    LinkIn,
    LocationConsentIn,
    MeetingIn,
    MeetingOut,
    MeetingSummary,
    MemberHistory,
    MemberImportErrorOut,
    MemberImportRunOut,
    MemberSummary,
    NetworkNode,
    NetworkOut,
    NetworkPage,
    PeaceMemberOut,
    PhotoOut,
    ReasonIn,
    ReassignIn,
    RecruiterChangeOut,
    ScheduleSlot,
    SettingsIn,
    SettingsOut,
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


PUBLIC_ENROLLMENT_PATH = "/inscripcion/"


def public_base(request: Request) -> str:
    """Panel URL for links meant for people outside it (PAZ_PUBLIC_BASE_URL)."""
    return str(request.app.state.settings.public_base_url).rstrip("/")


PublicBase = Annotated[str, Depends(public_base)]


def referral_url(base: str, code: str) -> str:
    return f"{base}{PUBLIC_ENROLLMENT_PATH}{code}"


def referral_qr(url: str) -> str:
    return str(segno.make(url, error="m").svg_data_uri(scale=4, border=2))


async def _actor(db: AsyncSession, user: CurrentUser) -> members.Actor:
    return members.Actor(
        user_id=user.id,
        geo=user.geo,
        can_accept_curp_incoherence=await user.holds_within(db, Perm.PERSON_READ_SENSITIVE),
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
    db: AsyncSession, crypto: CryptoDep, user: CurrentUser, base: str, member_id: uuid.UUID
) -> PeaceMemberOut:
    sensitive = await user.holds_within(db, Perm.PERSON_READ_SENSITIVE)
    member, view = await members.read_member(db, user.geo, member_id, unmasked=sensitive)
    counts = await members.direct_counts(db, user.geo, member)
    goal, pct, light = await members.progress(db, member, counts["active"])
    network = await stats.network_stats(db, member)
    house_goal, houses_pct = await members.houses_progress(
        db, member, network.houses_consolidated if network else 0
    )
    recruiter = None
    if member.recruited_by_member_id is not None:
        parent = await db.get(Member, member.recruited_by_member_id)
        if parent is not None:
            recruiter = (await _summaries(db, crypto, [parent], sensitive))[0]
    return PeaceMemberOut(
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
        referral_url=referral_url(base, member.referral_code),
        referral_qr_svg=referral_qr(referral_url(base, member.referral_code)),
        depth=member.depth,
        state_id=member.state_id,
        section_id=member.section_id,
        validated_at=member.validated_at,
        direct=DirectCounts(**counts),
        recruit_goal=goal,
        progress_pct=pct,
        traffic_light=light,
        network=NetworkOut.model_validate(network) if network else None,
        requested_house_id=member.requested_house_id,
        intake=intake.decoded_intake(crypto, member) if sensitive else None,
        house_goal=house_goal,
        houses_progress_pct=houses_pct,
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
    person_id: uuid.UUID | None = None,
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
        person_id=person_id,
        q=q,
    )
    items = await _summaries(
        db, crypto, page.items, await user.holds_within(db, Perm.PERSON_READ_SENSITIVE)
    )
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
    db: SessionDep, crypto: CryptoDep, base: PublicBase, user: Writer, body: EnrollmentIn
) -> PeaceMemberOut:
    member = await members.enroll(db, crypto, await _actor(db, user), body)
    return await _member_out(db, crypto, user, base, member.id)  # type: ignore[arg-type]


@router.get("/members/{member_id}", operation_id="getMember", summary="Detalle de pacificador")
async def get_member(
    db: SessionDep, crypto: CryptoDep, base: PublicBase, user: Reader, member_id: MemberId
) -> PeaceMemberOut:
    return await _member_out(db, crypto, user, base, member_id)


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
    items = await _summaries(
        db, crypto, page.items, await user.holds_within(db, Perm.PERSON_READ_SENSITIVE)
    )
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
    db: SessionDep, crypto: CryptoDep, base: PublicBase, user: Validator, member_id: MemberId
) -> PeaceMemberOut:
    await members.validate(db, await _actor(db, user), member_id)
    return await _member_out(db, crypto, user, base, member_id)


@router.post(
    "/members/{member_id}/reject",
    operation_id="rejectMember",
    summary="Rechazar inscripción pendiente",
)
async def reject_member(
    db: SessionDep,
    crypto: CryptoDep,
    base: PublicBase,
    user: Validator,
    member_id: MemberId,
    body: ReasonIn,
) -> PeaceMemberOut:
    await members.reject(db, await _actor(db, user), member_id, body.reason)
    return await _member_out(db, crypto, user, base, member_id)


@router.post(
    "/members/{member_id}/leave",
    operation_id="memberLeaves",
    summary="Registrar que el pacificador deja el movimiento",
)
async def leave(
    db: SessionDep,
    crypto: CryptoDep,
    base: PublicBase,
    user: Validator,
    member_id: MemberId,
    body: ReasonIn,
) -> PeaceMemberOut:
    await members.leave(db, await _actor(db, user), member_id, body.reason)
    return await _member_out(db, crypto, user, base, member_id)


@router.post(
    "/members/{member_id}/level",
    operation_id="changeMemberLevel",
    summary="Cambiar el nivel de participación",
)
async def change_level(
    db: SessionDep,
    crypto: CryptoDep,
    base: PublicBase,
    user: Writer,
    member_id: MemberId,
    body: LevelChangeIn,
) -> PeaceMemberOut:
    await members.change_level(db, await _actor(db, user), member_id, body.level_id, body.reason)
    return await _member_out(db, crypto, user, base, member_id)


@router.post(
    "/members/{member_id}/reassign",
    operation_id="reassignMember",
    summary="Cambiar el reclutador (mueve toda su red)",
)
async def reassign(
    db: SessionDep,
    crypto: CryptoDep,
    base: PublicBase,
    user: Reassigner,
    member_id: MemberId,
    body: ReassignIn,
) -> PeaceMemberOut:
    await members.reassign(
        db, await _actor(db, user), member_id, body.recruiter_member_id, body.reason
    )
    return await _member_out(db, crypto, user, base, member_id)


# --- branch scopes ----------------------------------------------------------------------------


async def _branches_out(
    db: AsyncSession, crypto: CryptoDep, grant_id: uuid.UUID, sensitive: bool
) -> list[BranchOut]:
    branches = await scope.branches_of(db, grant_id)
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
    "/grants/{grant_id}/branches",
    operation_id="listGrantBranches",
    summary="Ramas de una concesión (alcance por rama)",
)
async def list_branches(
    db: SessionDep, crypto: CryptoDep, user: UserReader, grant_id: uuid.UUID
) -> list[BranchOut]:
    await scope.grant_in_scope(db, user.geo, grant_id)
    sensitive = await user.holds_within(db, Perm.PERSON_READ_SENSITIVE)
    return await _branches_out(db, crypto, grant_id, sensitive)


@router.put(
    "/grants/{grant_id}/branches",
    operation_id="setGrantBranches",
    summary="Reemplazar las ramas de una concesión",
    description=(
        "Una rama amplía una concesión: su rol también alcanza la red debajo del pacificador, "
        "aunque cruce estados (D-83, D-101)."
    ),
)
async def set_branches(
    db: SessionDep, crypto: CryptoDep, user: ScopeAssigner, grant_id: uuid.UUID, body: BranchesIn
) -> list[BranchOut]:
    await scope.set_branches(db, user.geo, user.access, grant_id, body.member_ids)
    await db.commit()
    sensitive = await user.holds_within(db, Perm.PERSON_READ_SENSITIVE)
    return await _branches_out(db, crypto, grant_id, sensitive)


# --- Peace Houses -----------------------------------------------------------------------------

HouseReader = Annotated[CurrentUser, permission(PeacePerm.HOUSE_READ)]
HouseWriter = Annotated[CurrentUser, permission(PeacePerm.HOUSE_WRITE)]
CreditManager = Annotated[CurrentUser, permission(PeacePerm.HOUSE_REASSIGN_CREDIT)]
HouseLinker = Annotated[CurrentUser, permission(PeacePerm.HOUSE_LINK)]
HouseId = Annotated[uuid.UUID, Path(description="Id de la Casa de Paz.")]


async def _house_summaries(db: AsyncSession, items: list[PeaceHouse]) -> list[HouseSummary]:
    counts = await houses.member_counts(db, [h.id for h in items if h.id is not None])
    seats = await structure.seat_labels(
        db, [h.credited_position_id for h in items if h.credited_position_id]
    )
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
                credited_position_id=house.credited_position_id,
                credited_position=seats.get(house.credited_position_id)
                if house.credited_position_id
                else None,
                credit_pending=house.credited_member_id is None
                and house.credited_position_id is None,
                needs_reassignment=house.needs_reassignment,
                publishable=house.public_location_consent_id is not None,
                opened_on=house.opened_on,
            )
        )
    return result


async def _house_out(
    db: AsyncSession, crypto: CryptoDep, user: CurrentUser, house_id: uuid.UUID
) -> HouseOut:
    sensitive = await user.holds_within(db, Perm.PERSON_READ_SENSITIVE)
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
        opened_by_position_id=house.opened_by_position_id,
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
    house = await houses.open_house(
        db, crypto, await _actor(db, user), body, can_link=user.has(PeacePerm.HOUSE_LINK)
    )
    return await _house_out(db, crypto, user, house.id)  # type: ignore[arg-type]


@router.get(
    "/houses/pending-credit",
    operation_id="listHousesToLink",
    summary="Bandeja de casas por enlazar (sin crédito, de cualquier lugar)",
)
async def list_houses_to_link(
    db: SessionDep, user: HouseLinker, params: Annotated[PageParams, Depends(page_params)]
) -> CursorPage[HouseSummary]:
    del user
    page = await houses.pending_houses(db, params)
    return CursorPage[HouseSummary](
        items=await _house_summaries(db, page.items),
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


@router.post(
    "/houses/{house_id}/link",
    operation_id="linkPeaceHouse",
    summary="Enlazar una casa de la bandeja a un cargo propio",
    description=(
        "El crédito queda en el asiento, no en la persona: si cambia el titular, el nuevo lo "
        "hereda (D-103). Solo con un cargo de la estructura que ocupas, sin importar la geografía."
    ),
)
async def link_house(
    db: SessionDep, user: HouseLinker, house_id: HouseId, body: LinkIn
) -> HouseSummary:
    house = await houses.link_house(
        db, await _actor(db, user), house_id, body.position_id, can_link=True
    )
    [summary] = await _house_summaries(db, [house])
    return summary


@router.get(
    "/houses/map",
    operation_id="getPeaceHousesMap",
    summary="Casas de Paz en el mapa (puntos aproximados, GeoJSON)",
)
async def houses_map(
    db: SessionDep,
    user: HouseReader,
    status_: Annotated[
        str | None, Query(alias="status", pattern="^(open|consolidated|closed)$")
    ] = None,
    state_id: uuid.UUID | None = None,
) -> HouseMapOut:
    features, truncated = await houses.map_points(db, user.geo, status=status_, state_id=state_id)
    return HouseMapOut(features=features, truncated=truncated)


@router.get("/houses/{house_id}", operation_id="getPeaceHouse", summary="Detalle de Casa de Paz")
async def get_house(
    db: SessionDep, crypto: CryptoDep, user: HouseReader, house_id: HouseId
) -> HouseOut:
    return await _house_out(db, crypto, user, house_id)


@router.patch("/houses/{house_id}", operation_id="updatePeaceHouse", summary="Editar Casa de Paz")
async def update_house(
    db: SessionDep, crypto: CryptoDep, user: HouseWriter, house_id: HouseId, body: HouseUpdate
) -> HouseOut:
    await houses.update_house(db, await _actor(db, user), house_id, body)
    return await _house_out(db, crypto, user, house_id)


@router.post(
    "/houses/{house_id}/close", operation_id="closePeaceHouse", summary="Cerrar Casa de Paz"
)
async def close_house(
    db: SessionDep, crypto: CryptoDep, user: HouseWriter, house_id: HouseId, body: ReasonIn
) -> HouseOut:
    await houses.close_house(db, await _actor(db, user), house_id, body.reason)
    return await _house_out(db, crypto, user, house_id)


@router.post(
    "/houses/{house_id}/credit",
    operation_id="reassignHouseCredit",
    summary="Reasignar el crédito de una Casa de Paz",
)
async def reassign_credit(
    db: SessionDep, crypto: CryptoDep, user: CreditManager, house_id: HouseId, body: CreditIn
) -> HouseOut:
    await houses.reassign_credit(db, await _actor(db, user), house_id, body)
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
        await user.holds_within(db, Perm.PERSON_READ_SENSITIVE),
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
    await houses.add_member(db, await _actor(db, user), house_id, body.member_id)
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
    await houses.remove_member(db, await _actor(db, user), house_id, member_id)


@router.post(
    "/houses/{house_id}/public-location-consent",
    operation_id="recordHouseLocationConsent",
    summary="Registrar el consentimiento del anfitrión para publicar la ubicación",
)
async def record_location_consent(
    db: SessionDep, crypto: CryptoDep, user: HouseWriter, house_id: HouseId, body: LocationConsentIn
) -> HouseOut:
    await houses.record_location_consent(
        db, await _actor(db, user), house_id, channel=body.channel, evidence_uri=body.evidence_uri
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
    await houses.revoke_location_consent(db, await _actor(db, user), house_id)
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
    meeting = await houses.add_meeting(db, crypto, await _actor(db, user), house_id, body)
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
        attendees=_attendees(
            attendance, crypto, await user.holds_within(db, Perm.PERSON_READ_SENSITIVE)
        ),
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
        await _actor(db, user),
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
    await houses.delete_photo(db, storage, await _actor(db, user), house_id, photo_id)


# --- statistics -------------------------------------------------------------------------------

StatsReader = Annotated[CurrentUser, permission(PeacePerm.STATS_READ)]
GeoLevel = Annotated[
    str,
    Query(pattern="^(state|municipality|federal_district|local_district|section)$"),
]
MAX_GROWTH_DAYS = 1100


@router.get(
    "/members/{member_id}/network",
    operation_id="getMemberNetwork",
    summary="Red de un pacificador: agregados y niveles inferiores (máximo 3)",
)
async def get_network(
    db: SessionDep,
    crypto: CryptoDep,
    user: Reader,
    member_id: MemberId,
    params: Annotated[PageParams, Depends(page_params)],
    max_depth: Annotated[int, Query(ge=1, le=stats.MAX_NETWORK_DEPTH)] = 1,
) -> NetworkPage:
    root, page, hidden = await stats.descendants(
        db, user.geo, member_id, params, max_depth=max_depth
    )
    sensitive = await user.holds_within(db, Perm.PERSON_READ_SENSITIVE)
    counters = await stats.stats_of(db, [root, *page.items])
    summaries = await _summaries(db, crypto, [root, *page.items], sensitive)

    def node(summary: MemberSummary) -> NetworkNode:
        found = counters.get(summary.id)
        return NetworkNode(
            member=summary, network=NetworkOut.model_validate(found) if found else None
        )

    return NetworkPage(
        root=node(summaries[0]),
        items=[node(s) for s in summaries[1:]],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
        hidden=hidden,
    )


@router.get(
    "/stats/geography",
    operation_id="getPeaceGeographyStats",
    summary="Pacificadores activos por nivel geográfico (dentro del alcance)",
)
async def geography_stats(
    db: SessionDep,
    user: StatsReader,
    level: GeoLevel = "state",
    state_id: uuid.UUID | None = None,
    municipality_id: uuid.UUID | None = None,
) -> list[GeoStatOut]:
    rows = await stats.by_geography(
        db, user.geo, level=level, state_id=state_id, municipality_id=municipality_id
    )
    return [GeoStatOut.model_validate(row, from_attributes=True) for row in rows]


@router.get(
    "/stats/growth",
    operation_id="getPeaceGrowth",
    summary="Inscripciones validadas por día (dentro del alcance)",
)
async def growth(
    db: SessionDep,
    user: StatsReader,
    date_from: Annotated[date, Query(alias="from")],
    date_to: Annotated[date, Query(alias="to")],
    state_id: uuid.UUID | None = None,
    level_id: uuid.UUID | None = None,
) -> list[GrowthPoint]:
    if date_to < date_from or (date_to - date_from).days > MAX_GROWTH_DAYS:
        raise BadRequestError(
            f"El periodo debe ir hacia adelante y durar hasta {MAX_GROWTH_DAYS} días."
        )
    rows = await stats.growth(
        db, user.geo, date_from=date_from, date_to=date_to, state_id=state_id, level_id=level_id
    )
    return [GrowthPoint(day=day, enrollments=count) for day, count in rows]


@router.get(
    "/members-export",
    operation_id="exportMembers",
    summary="Exportar pacificadores a CSV (queda en la bitácora de lecturas)",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}}},
)
async def export_members(
    db: SessionDep,
    crypto: CryptoDep,
    user: StatsReader,
    status_: Annotated[
        str | None,
        Query(alias="status", pattern="^(pending_validation|active|rejected|left|withdrawn)$"),
    ] = None,
    state_id: uuid.UUID | None = None,
    level_id: uuid.UUID | None = None,
) -> Response:
    content = await stats.export_members(
        db,
        crypto,
        user.geo,
        sensitive=await user.holds_within(db, Perm.PERSON_READ_SENSITIVE),
        status=status_,
        state_id=state_id,
        level_id=level_id,
    )
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="pacificadores.csv"'},
    )


# --- intake (phase 4) -------------------------------------------------------------------------

Importer = Annotated[CurrentUser, permission(PeacePerm.MEMBER_IMPORT)]


@router.post(
    "/members/batch",
    operation_id="submitMemberBatch",
    summary="Carga por lotes de la app de campo (idempotente; quedan pendientes de validar)",
)
async def submit_batch(db: SessionDep, crypto: CryptoDep, user: Writer, body: BatchIn) -> BatchOut:
    items = await intake.submit_batch(db, crypto, await _actor(db, user), body)
    return BatchOut(
        accepted=sum(1 for i in items if i.status == "accepted"),
        duplicates=sum(1 for i in items if i.status == "duplicate"),
        errors=sum(1 for i in items if i.status == "error"),
        items=items,
    )


@router.post(
    "/imports",
    operation_id="queueMemberImport",
    summary="Subir un CSV o Excel de pacificadores (se procesa en segundo plano)",
    status_code=status.HTTP_202_ACCEPTED,
)
async def queue_import(
    db: SessionDep,
    storage: StorageDep,
    user: Importer,
    file: Annotated[UploadFile, File(description="CSV (UTF-8) o Excel .xlsx.")],
    evidence_uri: Annotated[
        str, Form(min_length=3, max_length=500, description="Evidencia de los consentimientos.")
    ],
    dry_run: Annotated[bool, Form(description="Solo validar, sin escribir.")] = True,
    default_level_id: Annotated[uuid.UUID | None, Form()] = None,
) -> MemberImportRunOut:
    data = await file.read(intake.IMPORT_MAX_BYTES + 1)
    run = await intake.queue_import(
        db,
        storage,
        await _actor(db, user),
        filename=file.filename or "importacion.csv",
        data=data,
        dry_run=dry_run,
        evidence_uri=evidence_uri,
        default_level_id=default_level_id,
    )
    return MemberImportRunOut.model_validate(run)


@router.get("/imports", operation_id="listMemberImports", summary="Importaciones")
async def list_imports(
    db: SessionDep, user: Importer, params: Annotated[PageParams, Depends(page_params)]
) -> CursorPage[MemberImportRunOut]:
    page = await intake.list_runs(db, await _actor(db, user), params)
    return CursorPage[MemberImportRunOut](
        items=[MemberImportRunOut.model_validate(run) for run in page.items],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


@router.get("/imports/{run_id}", operation_id="getMemberImport", summary="Detalle de importación")
async def get_import(db: SessionDep, user: Importer, run_id: uuid.UUID) -> MemberImportRunOut:
    return MemberImportRunOut.model_validate(
        await intake.get_run(db, await _actor(db, user), run_id)
    )


@router.get(
    "/imports/{run_id}/errors", operation_id="listMemberImportErrors", summary="Errores por fila"
)
async def list_import_errors(
    db: SessionDep,
    user: Importer,
    run_id: uuid.UUID,
    params: Annotated[PageParams, Depends(page_params)],
) -> CursorPage[MemberImportErrorOut]:
    page = await intake.run_errors(db, await _actor(db, user), run_id, params)
    return CursorPage[MemberImportErrorOut](
        items=[MemberImportErrorOut.model_validate(error) for error in page.items],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )
