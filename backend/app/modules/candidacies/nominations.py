"""Nominations and formulas (D-27..D-29, D-34).

- A nomination is created for an office enabled in the process, on a node of the office's
  geographic level that belongs to the process (framework and, for local processes, state).
- Formulas are always owner + substitute (unless the office has no substitute). They are
  edited while the nomination is a draft; afterwards changes go through status transitions
  and substitutions, which keep the full history.
- Every change evaluates the business rules; blocking violations stop it unless a user with
  `candidacies.rule.override` accepts them with a reason.
- Readable vs editable follows the geographic scope (scope.py).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.db.base import pk
from app.core.errors import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.core.pagination import CursorPage, PageParams, paginate, parse_sort
from app.modules.candidacies import scope
from app.modules.candidacies.composition import Slot, expected_slots
from app.modules.candidacies.models import (
    ACTIVE_FORMULA,
    GEO_COLUMNS,
    Coalition,
    ElectionRegime,
    ElectoralProcess,
    Formula,
    FormulaMember,
    FormulaStatus,
    FormulaStatusHistory,
    GeographicLevel,
    MemberRole,
    MunicipalitySetting,
    Nomination,
    NominationKind,
    NominationStatus,
    OfficeType,
    Party,
    ProcessOffice,
    ProcessStatus,
    RuleOverride,
)
from app.modules.candidacies.rules import Evaluation, RuleConfig, Violation, evaluate
from app.modules.candidacies.schemas import (
    FormulaIn,
    FormulaMembersUpdate,
    FormulaStatusIn,
    NominationAction,
    NominationIn,
    NominationUpdate,
    Override,
    SubstitutionIn,
)
from app.modules.candidacies.service import get_process
from app.modules.identity.services.scopes import GeoScope
from app.modules.people.models import Person
from app.modules.people.service import full_name, visible_person

_NODE_TABLES: dict[GeographicLevel, str] = {
    GeographicLevel.ELECTORAL_REGION: "electoral_regions",
    GeographicLevel.STATE: "states",
    GeographicLevel.FEDERAL_DISTRICT: "federal_districts",
    GeographicLevel.LOCAL_DISTRICT: "local_districts",
    GeographicLevel.MUNICIPALITY: "municipalities",
}

# to_status → statuses it can come from; approving and cancelling past "aspirant" need
# `candidacies.nomination.approve`.
_FORMULA_TRANSITIONS: dict[str, tuple[str, ...]] = {
    FormulaStatus.REGISTERED: (FormulaStatus.ASPIRANT,),
    FormulaStatus.APPROVED: (FormulaStatus.REGISTERED,),
    FormulaStatus.CANCELLED: ACTIVE_FORMULA,
}


class RuleViolationError(ConflictError):
    code = "rule-violation"
    title = "La operación viola reglas de negocio"

    def __init__(self, detail: str, violations: list[Violation]) -> None:
        super().__init__(detail, extra={"violations": [violation_dict(v) for v in violations]})


@dataclass(frozen=True, slots=True)
class Actor:
    user_id: uuid.UUID
    geo: GeoScope
    can_approve: bool
    can_override: bool


def violation_dict(violation: Violation) -> dict[str, Any]:
    return {
        "rule": violation.rule,
        "severity": violation.severity,
        "message": violation.message,
        "formula_id": str(violation.formula_id) if violation.formula_id else None,
    }


def _now() -> datetime:
    return datetime.now(UTC)


# --- loading and checks ---------------------------------------------------------------------


async def _office(db: AsyncSession, office_type_id: uuid.UUID) -> OfficeType:
    office = await db.get(OfficeType, office_type_id)
    if office is None or office.deleted_at is not None:
        raise BadRequestError("Cargo inexistente.")
    return office


async def _open_process(db: AsyncSession, process_id: uuid.UUID) -> ElectoralProcess:
    process = await get_process(db, process_id)
    if process.status == ProcessStatus.CLOSED:
        raise ConflictError("El proceso electoral está cerrado.")
    return process


async def load_nomination(
    db: AsyncSession, actor: Actor, nomination_id: uuid.UUID, *, edit: bool = False
) -> Nomination:
    nomination = await db.get(Nomination, nomination_id)
    if (
        nomination is None
        or nomination.deleted_at is not None
        or not await scope.is_readable(db, actor.geo, nomination_id)
    ):
        raise NotFoundError("Postulación no encontrada.")
    if edit:
        await scope.ensure_editable(db, actor.geo, nomination_id)
        await _open_process(db, nomination.process_id)
    return nomination


async def _load_formula(
    db: AsyncSession, actor: Actor, formula_id: uuid.UUID
) -> tuple[Formula, Nomination]:
    formula = await db.get(Formula, formula_id, with_for_update=True)
    if formula is None or formula.deleted_at is not None:
        raise NotFoundError("Fórmula no encontrada.")
    nomination = await load_nomination(db, actor, formula.nomination_id, edit=True)
    return formula, nomination


def _ensure_draft(nomination: Nomination) -> None:
    if nomination.status != NominationStatus.DRAFT:
        raise ConflictError(
            "La postulación ya fue enviada: usa sustituciones o cambios de estatus."
        )


async def _validate_node(
    db: AsyncSession, process: ElectoralProcess, level: GeographicLevel, node_id: uuid.UUID | None
) -> None:
    if level == GeographicLevel.NATIONAL:
        if node_id is not None:
            raise BadRequestError("Un cargo nacional no lleva nodo geográfico.")
        return
    if node_id is None:
        raise BadRequestError("Indica el nodo geográfico de la postulación.")
    table = _NODE_TABLES[level]
    if process.state_id is None or level == GeographicLevel.ELECTORAL_REGION:
        state_clause = ""
    elif level == GeographicLevel.STATE:
        state_clause = " AND id = :state"
    else:
        state_clause = " AND state_id = :state"
    found = (
        await db.execute(
            text(
                f"SELECT 1 FROM geography.{table} WHERE id = :node "  # noqa: S608
                f"AND framework_id = :f{state_clause}"
            ),
            {"node": node_id, "f": process.framework_id, "state": process.state_id},
        )
    ).first()
    if found is None:
        raise BadRequestError(
            "El nodo geográfico no corresponde al nivel del cargo o no pertenece al proceso."
        )


async def _validate_nominator(db: AsyncSession, process_id: uuid.UUID, body: NominationIn) -> None:
    if (body.party_id is None) == (body.coalition_id is None):
        raise BadRequestError("Indica un partido o una coalición (solo uno).")
    if body.party_id is not None:
        party = await db.get(Party, body.party_id)
        if party is None or party.deleted_at is not None:
            raise BadRequestError("Partido inexistente.")
    else:
        coalition = await db.get(Coalition, body.coalition_id)
        if (
            coalition is None
            or coalition.deleted_at is not None
            or coalition.process_id != process_id
        ):
            raise BadRequestError("La coalición no pertenece al proceso.")


async def _person(db: AsyncSession, actor: Actor, person_id: uuid.UUID) -> Person:
    try:
        return await visible_person(db, actor.geo, person_id)
    except NotFoundError:
        raise BadRequestError(f"La persona {person_id} no existe.") from None


# --- rule enforcement -----------------------------------------------------------------------


async def _overridden(
    db: AsyncSession, nomination_id: uuid.UUID
) -> set[tuple[uuid.UUID, uuid.UUID | None]]:
    rows = await db.execute(
        select(col(RuleOverride.validation_rule_id), col(RuleOverride.formula_id)).where(
            col(RuleOverride.nomination_id) == nomination_id, col(RuleOverride.deleted_at).is_(None)
        )
    )
    return {(rule_id, formula_id) for rule_id, formula_id in rows.all()}


Baseline = set[tuple[str, uuid.UUID | None]]


async def _pending(
    db: AsyncSession, nomination: Nomination, *, final: bool, baseline: Baseline | None = None
) -> tuple[Evaluation, dict[str, RuleConfig]]:
    """Violations not accepted before and, with a `baseline`, not already present before the
    change being made (so an edit is judged by what it introduces)."""
    evaluation, configs = await evaluate(
        db,
        process_id=nomination.process_id,
        nomination_id=pk(nomination),
        office_type_id=nomination.office_type_id,
        final=final,
    )
    accepted = await _overridden(db, pk(nomination))
    evaluation.violations = [
        v
        for v in evaluation.violations
        if (configs[v.rule].rule_id, v.formula_id) not in accepted
        and (baseline is None or (v.rule, v.formula_id) not in baseline)
    ]
    return evaluation, configs


async def _baseline(db: AsyncSession, nomination: Nomination) -> Baseline:
    evaluation, _ = await _pending(db, nomination, final=False)
    return {(v.rule, v.formula_id) for v in evaluation.violations}


async def _enforce(
    db: AsyncSession,
    actor: Actor,
    nomination: Nomination,
    override: Override | None,
    *,
    final: bool = False,
    baseline: Baseline | None = None,
) -> None:
    """Raises on blocking violations not covered by `override`; records accepted ones. Every
    formula involved is recorded (e.g. both formulas sharing a person)."""
    evaluation, configs = await _pending(db, nomination, final=final, baseline=baseline)
    blocking = evaluation.blocking
    if not blocking:
        return
    if override is None:
        await db.rollback()
        raise RuleViolationError("La operación viola reglas bloqueantes.", blocking)
    if not actor.can_override:
        await db.rollback()
        raise ForbiddenError(
            "No tienes el permiso «candidacies.rule.override» para aceptar violaciones."
        )
    uncovered = [v for v in blocking if v.rule not in override.rules]
    if uncovered:
        await db.rollback()
        raise RuleViolationError("La excepción no cubre todas las reglas violadas.", uncovered)
    for violation in blocking:
        db.add(
            RuleOverride(
                nomination_id=pk(nomination),
                formula_id=violation.formula_id,
                validation_rule_id=configs[violation.rule].rule_id,
                overridden_by_user_id=actor.user_id,
                reason=override.reason,
                details={"message": violation.message},
            )
        )


# --- nominations ----------------------------------------------------------------------------


async def create_nomination(db: AsyncSession, actor: Actor, body: NominationIn) -> Nomination:
    process = await _open_process(db, body.process_id)
    office = await _office(db, body.office_type_id)
    if office.nomination_kind == NominationKind.MEMBER:
        raise BadRequestError(f"«{office.name}» solo se postula dentro de una planilla.")
    config = (
        await db.execute(
            select(ProcessOffice).where(
                col(ProcessOffice.process_id) == body.process_id,
                col(ProcessOffice.office_type_id) == body.office_type_id,
                col(ProcessOffice.deleted_at).is_(None),
            )
        )
    ).scalar_one_or_none()
    if config is None or not config.is_enabled:
        raise BadRequestError(f"El cargo «{office.name}» no está habilitado en este proceso.")
    if config.slate_parent_office_type_id is not None:
        raise BadRequestError(f"En este proceso «{office.name}» se postula dentro de una planilla.")
    level = GeographicLevel(office.geographic_level)
    await _validate_node(db, process, level, body.node_id)
    if level == GeographicLevel.MUNICIPALITY:
        regime = (
            await db.execute(
                select(col(MunicipalitySetting.election_regime)).where(
                    col(MunicipalitySetting.process_id) == body.process_id,
                    col(MunicipalitySetting.municipality_id) == body.node_id,
                    col(MunicipalitySetting.deleted_at).is_(None),
                )
            )
        ).scalar_one_or_none()
        if regime == ElectionRegime.NORMATIVE_SYSTEM:
            raise ConflictError(
                "El municipio elige por sistemas normativos internos: no hay postulaciones de "
                "partido."
            )
    await scope.ensure_node_within_scope(db, actor.geo, level, body.node_id or process.framework_id)
    await _validate_nominator(db, body.process_id, body)

    nomination = Nomination(
        process_id=body.process_id,
        office_type_id=body.office_type_id,
        geographic_level=level,
        party_id=body.party_id,
        coalition_id=body.coalition_id,
        notes=body.notes,
        status=NominationStatus.DRAFT,
    )
    if level != GeographicLevel.NATIONAL:
        setattr(nomination, GEO_COLUMNS[level], body.node_id)
    duplicate = select(col(Nomination.id)).where(
        col(Nomination.process_id) == body.process_id,
        col(Nomination.office_type_id) == body.office_type_id,
        col(Nomination.deleted_at).is_(None),
        col(Nomination.status) != NominationStatus.CANCELLED,
        col(Nomination.party_id).is_(None)
        if body.party_id is None
        else col(Nomination.party_id) == body.party_id,
        col(Nomination.coalition_id).is_(None)
        if body.coalition_id is None
        else col(Nomination.coalition_id) == body.coalition_id,
    )
    if level != GeographicLevel.NATIONAL:
        duplicate = duplicate.where(getattr(Nomination, GEO_COLUMNS[level]) == body.node_id)
    if (await db.execute(duplicate)).first() is not None:
        raise ConflictError(
            "Ya existe una postulación activa de ese partido o coalición para ese cargo y "
            "geografía."
        )
    db.add(nomination)
    await db.commit()
    return nomination


async def update_nomination(
    db: AsyncSession, actor: Actor, nomination_id: uuid.UUID, body: NominationUpdate
) -> Nomination:
    nomination = await load_nomination(db, actor, nomination_id, edit=True)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(nomination, key, value)
    await db.commit()
    return nomination


async def list_nominations(
    db: AsyncSession,
    actor: Actor,
    params: PageParams,
    *,
    process_id: uuid.UUID | None,
    office_type_id: uuid.UUID | None,
    status: NominationStatus | None,
    party_id: uuid.UUID | None,
) -> CursorPage[Nomination]:
    statement = select(Nomination).where(col(Nomination.deleted_at).is_(None))
    for column, value in (
        (Nomination.process_id, process_id),
        (Nomination.office_type_id, office_type_id),
        (Nomination.status, status),
        (Nomination.party_id, party_id),
    ):
        if value is not None:
            statement = statement.where(col(column) == value)
    readable = scope.readable_filter(actor.geo)
    if readable is not None:
        statement = statement.where(readable)
    sort = parse_sort(
        params.sort,
        allowed={"created_at": col(Nomination.created_at), "status": col(Nomination.status)},
        tiebreaker=col(Nomination.id),
        default="-created_at",
    )
    page: CursorPage[Nomination] = await paginate(
        db, statement, sort=sort, limit=params.limit, cursor=params.cursor
    )
    return page


async def _slots(db: AsyncSession, nomination: Nomination) -> list[Slot]:
    return await expected_slots(
        db,
        process_id=nomination.process_id,
        head=await _office(db, nomination.office_type_id),
        municipality_id=nomination.municipality_id,
    )


async def _active_formulas(db: AsyncSession, nomination_id: uuid.UUID) -> list[Formula]:
    rows = await db.execute(
        select(Formula)
        .where(
            col(Formula.nomination_id) == nomination_id,
            col(Formula.deleted_at).is_(None),
            col(Formula.status).in_(ACTIVE_FORMULA),
        )
        .order_by(col(Formula.position))
    )
    return list(rows.scalars())


def _slot_report(slots: list[Slot], formulas: list[Formula]) -> list[dict[str, Any]]:
    report = []
    for slot in slots:
        taken = {f.position for f in formulas if f.office_type_id == slot.office_type_id}
        report.append(
            {
                "office_type_id": slot.office_type_id,
                "office_code": slot.office_code,
                "office_name": slot.office_name,
                "expected": slot.positions,
                "filled": len(taken & set(range(1, slot.positions + 1))),
                "missing_positions": [p for p in range(1, slot.positions + 1) if p not in taken],
            }
        )
    return report


async def _members(
    db: AsyncSession, formula_ids: list[uuid.UUID]
) -> dict[tuple[uuid.UUID, str], dict[str, Any]]:
    if not formula_ids:
        return {}
    rows = await db.execute(
        select(FormulaMember, Person)
        .join(Person, col(Person.id) == col(FormulaMember.person_id))
        .where(
            col(FormulaMember.formula_id).in_(formula_ids), col(FormulaMember.deleted_at).is_(None)
        )
    )
    return {
        (member.formula_id, member.member_role): {
            "person_id": member.person_id,
            "full_name": full_name(person),
            "sex": person.sex,
        }
        for member, person in rows.all()
    }


async def _formula_dicts(db: AsyncSession, formulas: list[Formula]) -> list[dict[str, Any]]:
    members = await _members(db, [pk(f) for f in formulas])
    codes = await office_codes(db)
    return [
        {
            "id": f.id,
            "office_type_id": f.office_type_id,
            "office_code": codes[f.office_type_id],
            "position": f.position,
            "status": f.status,
            "origin_party_id": f.origin_party_id,
            "replaces_formula_id": f.replaces_formula_id,
            "substitution_reason": f.substitution_reason,
            "owner": members.get((pk(f), MemberRole.OWNER)),
            "substitute": members.get((pk(f), MemberRole.SUBSTITUTE)),
        }
        for f in formulas
    ]


async def office_codes(db: AsyncSession) -> dict[uuid.UUID, str]:
    rows = await db.execute(select(col(OfficeType.id), col(OfficeType.code)))
    return {pk_: code for pk_, code in rows.all() if pk_ is not None}


def summary_dict(nomination: Nomination, codes: dict[uuid.UUID, str]) -> dict[str, Any]:
    level = GeographicLevel(nomination.geographic_level)
    return {
        "id": nomination.id,
        "process_id": nomination.process_id,
        "office_type_id": nomination.office_type_id,
        "office_code": codes[nomination.office_type_id],
        "geographic_level": level,
        "node_id": None
        if level == GeographicLevel.NATIONAL
        else getattr(nomination, GEO_COLUMNS[level]),
        "party_id": nomination.party_id,
        "coalition_id": nomination.coalition_id,
        "status": nomination.status,
        "created_at": nomination.created_at,
    }


async def nomination_view(db: AsyncSession, actor: Actor, nomination: Nomination) -> dict[str, Any]:
    formulas = await _active_formulas(db, pk(nomination))
    slots = _slot_report(await _slots(db, nomination), formulas)
    evaluation, _ = await _pending(db, nomination, final=False)
    return {
        **summary_dict(nomination, await office_codes(db)),
        "notes": nomination.notes,
        "editable": await scope.is_editable(db, actor.geo, pk(nomination)),
        "complete": bool(slots)
        and all(not s["missing_positions"] for s in slots)
        and any(s["expected"] for s in slots),
        "slots": slots,
        "formulas": await _formula_dicts(db, formulas),
        "warnings": [violation_dict(v) for v in evaluation.violations],
    }


async def _set_nomination_status(
    db: AsyncSession,
    actor: Actor,
    nomination_id: uuid.UUID,
    body: NominationAction,
    *,
    to: NominationStatus,
) -> Nomination:
    nomination = await load_nomination(db, actor, nomination_id, edit=True)
    current = nomination.status
    if to == NominationStatus.SUBMITTED:
        _ensure_draft(nomination)
        slots = _slot_report(
            await _slots(db, nomination), await _active_formulas(db, nomination_id)
        )
        missing = [
            f"{s['office_name']}: {s['missing_positions']}" for s in slots if s["missing_positions"]
        ]
        if missing or not any(s["expected"] for s in slots):
            raise ConflictError(
                "La postulación está incompleta. Faltan posiciones: " + "; ".join(missing)
            )
        await _enforce(db, actor, nomination, body.override, final=True)
    elif to == NominationStatus.APPROVED:
        if not actor.can_approve:
            raise ForbiddenError("No tienes el permiso «candidacies.nomination.approve».")
        if current != NominationStatus.SUBMITTED:
            raise ConflictError("Solo se aprueban postulaciones enviadas.")
        await _enforce(db, actor, nomination, body.override, final=True)
    else:  # cancelled
        if current == NominationStatus.CANCELLED:
            raise ConflictError("La postulación ya está cancelada.")
        if current != NominationStatus.DRAFT and not actor.can_approve:
            raise ForbiddenError(
                "Cancelar una postulación enviada requiere «candidacies.nomination.approve»."
            )
        for formula in await _active_formulas(db, nomination_id):
            _transition(
                db, actor, formula, FormulaStatus.CANCELLED, body.reason or "Postulación cancelada."
            )
    nomination.status = to
    await db.commit()
    return nomination


async def submit_nomination(
    db: AsyncSession, actor: Actor, nomination_id: uuid.UUID, body: NominationAction
) -> Nomination:
    return await _set_nomination_status(
        db, actor, nomination_id, body, to=NominationStatus.SUBMITTED
    )


async def approve_nomination(
    db: AsyncSession, actor: Actor, nomination_id: uuid.UUID, body: NominationAction
) -> Nomination:
    return await _set_nomination_status(
        db, actor, nomination_id, body, to=NominationStatus.APPROVED
    )


async def cancel_nomination(
    db: AsyncSession, actor: Actor, nomination_id: uuid.UUID, body: NominationAction
) -> Nomination:
    return await _set_nomination_status(
        db, actor, nomination_id, body, to=NominationStatus.CANCELLED
    )


async def validate(db: AsyncSession, actor: Actor, nomination_id: uuid.UUID) -> list[Violation]:
    """Dry run of every enabled rule, nomination-wide ones (parity) included."""
    nomination = await load_nomination(db, actor, nomination_id)
    evaluation, _ = await _pending(db, nomination, final=True)
    return evaluation.violations


async def history(db: AsyncSession, actor: Actor, nomination_id: uuid.UUID) -> list[dict[str, Any]]:
    await load_nomination(db, actor, nomination_id)
    rows = await db.execute(
        select(FormulaStatusHistory, Formula, OfficeType.code)  # type: ignore[call-overload]
        .join(Formula, col(Formula.id) == col(FormulaStatusHistory.formula_id))
        .join(OfficeType, col(OfficeType.id) == col(Formula.office_type_id))
        .where(col(Formula.nomination_id) == nomination_id)
        .order_by(col(FormulaStatusHistory.changed_at), col(FormulaStatusHistory.id))
    )
    return [
        {
            "formula_id": entry.formula_id,
            "office_code": code,
            "position": formula.position,
            "from_status": entry.from_status,
            "to_status": entry.to_status,
            "reason": entry.reason,
            "changed_by_user_id": entry.changed_by_user_id,
            "changed_at": entry.changed_at,
        }
        for entry, formula, code in rows.all()
    ]


# --- formulas -------------------------------------------------------------------------------


def _transition(
    db: AsyncSession, actor: Actor, formula: Formula, to: str, reason: str | None
) -> None:
    db.add(
        FormulaStatusHistory(
            formula_id=pk(formula),
            from_status=formula.status,
            to_status=to,
            reason=reason,
            changed_by_user_id=actor.user_id,
            changed_at=_now(),
        )
    )
    formula.status = to


async def _check_members(
    db: AsyncSession,
    actor: Actor,
    office: OfficeType,
    owner_id: uuid.UUID,
    substitute_id: uuid.UUID | None,
) -> None:
    await _person(db, actor, owner_id)
    if substitute_id is None:
        if office.has_substitute:
            raise BadRequestError(f"«{office.name}» requiere persona suplente.")
        return
    if not office.has_substitute:
        raise BadRequestError(f"«{office.name}» no lleva suplente.")
    if substitute_id == owner_id:
        raise BadRequestError("La propietaria y la suplente deben ser personas distintas.")
    await _person(db, actor, substitute_id)


def _add_members(
    db: AsyncSession,
    formula_id: uuid.UUID,
    process_id: uuid.UUID,
    owner_id: uuid.UUID,
    substitute_id: uuid.UUID | None,
) -> None:
    db.add(
        FormulaMember(
            formula_id=formula_id,
            person_id=owner_id,
            process_id=process_id,
            member_role=MemberRole.OWNER,
        )
    )
    if substitute_id is not None:
        db.add(
            FormulaMember(
                formula_id=formula_id,
                person_id=substitute_id,
                process_id=process_id,
                member_role=MemberRole.SUBSTITUTE,
            )
        )


async def _current_members(db: AsyncSession, formula_id: uuid.UUID) -> dict[str, uuid.UUID]:
    rows = await db.execute(
        select(col(FormulaMember.member_role), col(FormulaMember.person_id)).where(
            col(FormulaMember.formula_id) == formula_id, col(FormulaMember.deleted_at).is_(None)
        )
    )
    return dict(rows.all())


async def _validate_origin_party(
    db: AsyncSession, nomination: Nomination, party_id: uuid.UUID | None
) -> None:
    """Coalition formulas may record the party of origin; it must belong to the coalition."""
    if party_id is None:
        return
    if nomination.coalition_id is None:
        raise BadRequestError("El partido de origen solo aplica a postulaciones de coalición.")
    member = (
        await db.execute(
            text(
                "SELECT 1 FROM candidacies.coalition_parties WHERE coalition_id = :c AND party_id "
                "= :p "
                "AND deleted_at IS NULL"
            ),
            {"c": nomination.coalition_id, "p": party_id},
        )
    ).first()
    if member is None:
        raise BadRequestError("El partido de origen no integra la coalición.")


async def create_formula(
    db: AsyncSession, actor: Actor, nomination_id: uuid.UUID, body: FormulaIn
) -> Nomination:
    nomination = await load_nomination(db, actor, nomination_id, edit=True)
    _ensure_draft(nomination)
    baseline = await _baseline(db, nomination)
    slot = next(
        (s for s in await _slots(db, nomination) if s.office_type_id == body.office_type_id), None
    )
    if slot is None:
        raise BadRequestError("El cargo no forma parte de esta postulación.")
    if body.position > slot.positions:
        raise BadRequestError(
            f"«{slot.office_name}» tiene {slot.positions} posiciones en esta postulación."
        )
    office = await _office(db, body.office_type_id)
    await _check_members(db, actor, office, body.owner_person_id, body.substitute_person_id)
    await _validate_origin_party(db, nomination, body.origin_party_id)
    taken = (
        await db.execute(
            select(col(Formula.id)).where(
                col(Formula.nomination_id) == nomination_id,
                col(Formula.office_type_id) == body.office_type_id,
                col(Formula.position) == body.position,
                col(Formula.deleted_at).is_(None),
                col(Formula.status).in_(ACTIVE_FORMULA),
            )
        )
    ).first()
    if taken is not None:
        raise ConflictError(f"La posición {body.position} de «{slot.office_name}» ya está ocupada.")

    formula = Formula(
        nomination_id=nomination_id,
        office_type_id=body.office_type_id,
        position=body.position,
        status=FormulaStatus.ASPIRANT,
        origin_party_id=body.origin_party_id,
    )
    db.add(formula)
    await db.flush()
    formula_id = pk(formula)
    _add_members(
        db, formula_id, nomination.process_id, body.owner_person_id, body.substitute_person_id
    )
    db.add(
        FormulaStatusHistory(
            formula_id=formula_id,
            to_status=FormulaStatus.ASPIRANT,
            changed_by_user_id=actor.user_id,
            changed_at=_now(),
        )
    )
    await db.flush()
    await _enforce(db, actor, nomination, body.override, baseline=baseline)
    await db.commit()
    return nomination


async def update_members(
    db: AsyncSession, actor: Actor, formula_id: uuid.UUID, body: FormulaMembersUpdate
) -> Nomination:
    formula, nomination = await _load_formula(db, actor, formula_id)
    _ensure_draft(nomination)
    baseline = await _baseline(db, nomination)
    if formula.status != FormulaStatus.ASPIRANT:
        raise ConflictError("Solo se editan fórmulas en estatus «aspirante»; usa una sustitución.")
    current = await _current_members(db, formula_id)
    owner = body.owner_person_id or current[MemberRole.OWNER]
    substitute = body.substitute_person_id or current.get(MemberRole.SUBSTITUTE)
    await _check_members(db, actor, await _office(db, formula.office_type_id), owner, substitute)
    if "origin_party_id" in body.model_fields_set:
        await _validate_origin_party(db, nomination, body.origin_party_id)
        formula.origin_party_id = body.origin_party_id
    await db.execute(
        update(FormulaMember)
        .where(col(FormulaMember.formula_id) == formula_id, col(FormulaMember.deleted_at).is_(None))
        .values(deleted_at=_now())
    )
    _add_members(db, formula_id, nomination.process_id, owner, substitute)
    await db.flush()
    await _enforce(db, actor, nomination, body.override, baseline=baseline)
    await db.commit()
    return nomination


async def change_formula_status(
    db: AsyncSession, actor: Actor, formula_id: uuid.UUID, body: FormulaStatusIn
) -> Nomination:
    formula, nomination = await _load_formula(db, actor, formula_id)
    to = FormulaStatus(body.to_status)
    if formula.status not in _FORMULA_TRANSITIONS[to]:
        raise ConflictError(f"No se puede pasar de «{formula.status}» a «{to}».")
    needs_approve = to == FormulaStatus.APPROVED or (
        to == FormulaStatus.CANCELLED and formula.status != FormulaStatus.ASPIRANT
    )
    if needs_approve and not actor.can_approve:
        raise ForbiddenError("Este cambio de estatus requiere «candidacies.nomination.approve».")
    if to == FormulaStatus.CANCELLED and not body.reason:
        raise BadRequestError("Indica el motivo de la cancelación.")
    _transition(db, actor, formula, to, body.reason)
    await db.commit()
    return nomination


async def substitute_formula(
    db: AsyncSession, actor: Actor, formula_id: uuid.UUID, body: SubstitutionIn
) -> Nomination:
    """A new formula takes the same position; the replaced one stays as history (D-29)."""
    if not actor.can_approve:
        raise ForbiddenError("Las sustituciones requieren «candidacies.nomination.approve».")
    old, nomination = await _load_formula(db, actor, formula_id)
    if old.status not in ACTIVE_FORMULA:
        raise ConflictError("Solo se sustituyen fórmulas vigentes.")
    baseline = await _baseline(db, nomination)
    current = await _current_members(db, formula_id)
    owner = body.owner_person_id or current[MemberRole.OWNER]
    substitute = body.substitute_person_id or current.get(MemberRole.SUBSTITUTE)
    if owner == current.get(MemberRole.OWNER) and substitute == current.get(MemberRole.SUBSTITUTE):
        raise BadRequestError("La sustitución debe cambiar al menos a una persona.")
    await _check_members(db, actor, await _office(db, old.office_type_id), owner, substitute)
    status = old.status
    _transition(db, actor, old, FormulaStatus.SUBSTITUTED, body.reason)
    await db.flush()  # frees the position in the partial unique index
    new = Formula(
        nomination_id=old.nomination_id,
        office_type_id=old.office_type_id,
        position=old.position,
        status=status,
        origin_party_id=old.origin_party_id,
        replaces_formula_id=old.id,
        substitution_reason=body.reason,
    )
    db.add(new)
    await db.flush()
    new_id = pk(new)
    _add_members(db, new_id, nomination.process_id, owner, substitute)
    db.add(
        FormulaStatusHistory(
            formula_id=new_id,
            to_status=status,
            reason=body.reason,
            changed_by_user_id=actor.user_id,
            changed_at=_now(),
        )
    )
    await db.flush()
    await _enforce(db, actor, nomination, body.override, baseline=baseline)
    await db.commit()
    return nomination
