"""Catalogs, electoral processes and their configuration (D-21..D-28)."""

import uuid
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.db.base import pk
from app.core.errors import BadRequestError, ConflictError, NotFoundError
from app.modules.candidacies.models import (
    Coalition,
    CoalitionParty,
    ElectionLevel,
    ElectoralProcess,
    MunicipalitySetting,
    NominationKind,
    OfficeType,
    Party,
    Principle,
    ProcessOffice,
    ProcessStatus,
    ProcessValidationRule,
    Severity,
    ValidationRule,
)
from app.modules.candidacies.schemas import (
    CoalitionIn,
    MunicipalitySettingIn,
    OfficeTypeIn,
    PartyIn,
    ProcessIn,
    ProcessOfficeIn,
    ProcessRuleIn,
    ProcessUpdate,
)

DEFAULT_ENABLED_RULES = {"unique_person_in_process"}  # D-28


async def _get(db: AsyncSession, model: type[Any], item_id: uuid.UUID, label: str) -> Any:
    item = await db.get(model, item_id)
    if item is None or getattr(item, "deleted_at", None) is not None:
        raise NotFoundError(f"{label} no encontrado.")
    return item


# --- parties and office types ---------------------------------------------------------------


async def list_parties(db: AsyncSession) -> list[Party]:
    rows = await db.execute(
        select(Party).where(col(Party.deleted_at).is_(None)).order_by(col(Party.acronym))
    )
    return list(rows.scalars())


async def create_party(db: AsyncSession, body: PartyIn) -> Party:
    if (
        await db.execute(
            select(Party).where(col(Party.acronym) == body.acronym, col(Party.deleted_at).is_(None))
        )
    ).first():
        raise ConflictError("Ya existe un partido con esas siglas.")
    party = Party(**body.model_dump())
    db.add(party)
    await db.commit()
    return party


async def update_party(db: AsyncSession, party_id: uuid.UUID, body: PartyIn) -> Party:
    party: Party = await _get(db, Party, party_id, "Partido")
    for key, value in body.model_dump().items():
        setattr(party, key, value)
    await db.commit()
    return party


async def list_office_types(db: AsyncSession) -> list[OfficeType]:
    rows = await db.execute(
        select(OfficeType)
        .where(col(OfficeType.deleted_at).is_(None))
        .order_by(col(OfficeType.sort_order))
    )
    return list(rows.scalars())


async def create_office_type(db: AsyncSession, body: OfficeTypeIn) -> OfficeType:
    """New offices are data, not migrations (CLAUDE.md §Candidaturas)."""
    if (
        await db.execute(
            select(OfficeType).where(
                col(OfficeType.code) == body.code, col(OfficeType.deleted_at).is_(None)
            )
        )
    ).first():
        raise ConflictError("Ya existe un cargo con ese código.")
    office = OfficeType(**body.model_dump())
    db.add(office)
    await db.commit()
    return office


async def list_rules(db: AsyncSession) -> list[ValidationRule]:
    rows = await db.execute(
        select(ValidationRule)
        .where(col(ValidationRule.deleted_at).is_(None))
        .order_by(col(ValidationRule.code))
    )
    return list(rows.scalars())


# --- processes ------------------------------------------------------------------------------


async def get_process(db: AsyncSession, process_id: uuid.UUID) -> ElectoralProcess:
    process: ElectoralProcess = await _get(db, ElectoralProcess, process_id, "Proceso electoral")
    return process


async def list_processes(db: AsyncSession) -> list[ElectoralProcess]:
    rows = await db.execute(
        select(ElectoralProcess)
        .where(col(ElectoralProcess.deleted_at).is_(None))
        .order_by(col(ElectoralProcess.election_year).desc(), col(ElectoralProcess.name))
    )
    return list(rows.scalars())


async def create_process(db: AsyncSession, body: ProcessIn) -> ElectoralProcess:
    framework = (
        await db.execute(
            text(
                "SELECT id FROM geography.geographic_frameworks WHERE is_active AND deleted_at IS "
                "NULL"
            )
        )
    ).scalar_one_or_none()
    if framework is None:
        raise BadRequestError("No hay un marco geográfico activo.")
    if body.election_level == ElectionLevel.LOCAL:
        if body.state_id is None:
            raise BadRequestError("Un proceso local requiere el estado.")
        valid = (
            await db.execute(
                text("SELECT 1 FROM geography.states WHERE id = :s AND framework_id = :f"),
                {"s": body.state_id, "f": framework},
            )
        ).first()
        if valid is None:
            raise BadRequestError("El estado no pertenece al marco geográfico activo.")
    elif body.state_id is not None:
        raise BadRequestError("Un proceso federal no lleva estado.")

    process = ElectoralProcess(
        **body.model_dump(), framework_id=framework, status=ProcessStatus.DRAFT
    )
    db.add(process)
    await db.flush()
    process_id = pk(process)
    # One (disabled) configuration row per office of the process level: the user enables what
    # is up for election (D-23).
    for office in await list_office_types(db):
        if office.election_level == body.election_level:
            db.add(
                ProcessOffice(process_id=process_id, office_type_id=pk(office), is_enabled=False)
            )
    for rule in await list_rules(db):
        db.add(
            ProcessValidationRule(
                process_id=process_id,
                validation_rule_id=pk(rule),
                is_enabled=rule.code in DEFAULT_ENABLED_RULES,
                severity=Severity.BLOCKING,
            )
        )
    await db.commit()
    return process


async def update_process(
    db: AsyncSession, process_id: uuid.UUID, body: ProcessUpdate
) -> ElectoralProcess:
    process = await get_process(db, process_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(process, key, value)
    await db.commit()
    return process


# --- configuration --------------------------------------------------------------------------


async def process_offices(
    db: AsyncSession, process_id: uuid.UUID
) -> list[tuple[ProcessOffice, OfficeType]]:
    await get_process(db, process_id)
    rows = await db.execute(
        select(ProcessOffice, OfficeType)
        .join(OfficeType, col(OfficeType.id) == col(ProcessOffice.office_type_id))
        .where(col(ProcessOffice.process_id) == process_id, col(ProcessOffice.deleted_at).is_(None))
        .order_by(col(OfficeType.sort_order))
    )
    return [(config, office) for config, office in rows.all()]


async def configure_offices(
    db: AsyncSession, process_id: uuid.UUID, items: list[ProcessOfficeIn]
) -> list[tuple[ProcessOffice, OfficeType]]:
    process = await get_process(db, process_id)
    current = {
        config.office_type_id: (config, office)
        for config, office in await process_offices(db, process_id)
    }
    offices = {pk(office): office for office in await list_office_types(db)}
    for item in items:
        office = offices.get(item.office_type_id)
        if office is None:
            raise BadRequestError(f"Cargo inexistente: {item.office_type_id}.")
        if office.election_level != process.election_level:
            raise BadRequestError(
                f"El cargo «{office.name}» no corresponde a un proceso {process.election_level}."
            )
        if item.slate_parent_office_type_id is not None:
            parent = offices.get(item.slate_parent_office_type_id)
            if parent is None or parent.nomination_kind != NominationKind.SLATE:
                raise BadRequestError(
                    f"«{office.name}» solo puede integrarse a un cargo de tipo planilla."
                )
        elif office.nomination_kind == NominationKind.MEMBER and item.is_enabled:
            raise BadRequestError(
                f"«{office.name}» solo existe dentro de una planilla: indica su cargo principal."
            )
        if item.rp_method is not None and office.principle != Principle.RP:
            raise BadRequestError(
                "El método de RP solo aplica a cargos de representación proporcional "
                f"(«{office.name}»)."
            )
        config = current.get(item.office_type_id, (None, None))[0]
        if config is None:
            config = ProcessOffice(process_id=process_id, office_type_id=item.office_type_id)
            db.add(config)
        for key, value in item.model_dump(exclude={"office_type_id"}).items():
            setattr(config, key, value)
    await db.commit()
    return await process_offices(db, process_id)


async def municipality_settings(
    db: AsyncSession, process_id: uuid.UUID
) -> list[MunicipalitySetting]:
    await get_process(db, process_id)
    rows = await db.execute(
        select(MunicipalitySetting).where(
            col(MunicipalitySetting.process_id) == process_id,
            col(MunicipalitySetting.deleted_at).is_(None),
        )
    )
    return list(rows.scalars())


async def configure_municipalities(
    db: AsyncSession, process_id: uuid.UUID, items: list[MunicipalitySettingIn]
) -> list[MunicipalitySetting]:
    """Bulk upsert (D-24..D-26). Numbers are captured or imported by the user, never assumed."""
    process = await get_process(db, process_id)
    current = {
        setting.municipality_id: setting for setting in await municipality_settings(db, process_id)
    }
    for item in items:
        valid = (
            await db.execute(
                text(
                    "SELECT 1 FROM geography.municipalities m WHERE m.id = :m AND m.framework_id "
                    "= :f "
                    "AND (CAST(:s AS uuid) IS NULL OR m.state_id = CAST(:s AS uuid))"
                ),
                {"m": item.municipality_id, "f": process.framework_id, "s": process.state_id},
            )
        ).first()
        if valid is None:
            raise BadRequestError(f"El municipio {item.municipality_id} no pertenece al proceso.")
        setting = current.get(item.municipality_id)
        if setting is None:
            setting = MunicipalitySetting(
                process_id=process_id, municipality_id=item.municipality_id
            )
            db.add(setting)
            current[item.municipality_id] = setting
        for key, value in item.model_dump(exclude={"municipality_id"}).items():
            setattr(setting, key, value)
    await db.commit()
    return await municipality_settings(db, process_id)


async def process_rules(db: AsyncSession, process_id: uuid.UUID) -> list[dict[str, Any]]:
    await get_process(db, process_id)
    rows = await db.execute(
        text(
            "SELECT pvr.id, vr.code AS rule_code, pvr.office_type_id, pvr.is_enabled, "
            "pvr.severity, "
            "pvr.params, vr.default_params || pvr.params AS effective_params "
            "FROM candidacies.process_validation_rules pvr "
            "JOIN candidacies.validation_rules vr ON vr.id = pvr.validation_rule_id "
            "WHERE pvr.process_id = :p AND pvr.deleted_at IS NULL ORDER BY vr.code, "
            "pvr.office_type_id NULLS FIRST"
        ),
        {"p": process_id},
    )
    return [dict(row) for row in rows.mappings()]


async def configure_rules(
    db: AsyncSession, process_id: uuid.UUID, items: list[ProcessRuleIn]
) -> list[dict[str, Any]]:
    await get_process(db, process_id)
    rules = {rule.code: rule for rule in await list_rules(db)}
    for item in items:
        rule = rules.get(item.rule_code)
        if rule is None:
            raise BadRequestError(f"Regla inexistente: {item.rule_code}.")
        unknown = set(item.params) - set(rule.default_params)
        if unknown:
            raise BadRequestError(
                f"Parámetros desconocidos para {rule.code}: {', '.join(sorted(unknown))}."
            )
        statement = select(ProcessValidationRule).where(
            col(ProcessValidationRule.process_id) == process_id,
            col(ProcessValidationRule.validation_rule_id) == pk(rule),
            col(ProcessValidationRule.deleted_at).is_(None),
        )
        statement = statement.where(
            col(ProcessValidationRule.office_type_id).is_(None)
            if item.office_type_id is None
            else col(ProcessValidationRule.office_type_id) == item.office_type_id
        )
        config = (await db.execute(statement)).scalar_one_or_none()
        if config is None:
            config = ProcessValidationRule(
                process_id=process_id,
                validation_rule_id=pk(rule),
                office_type_id=item.office_type_id,
            )
            db.add(config)
        config.is_enabled = item.is_enabled
        config.severity = item.severity
        config.params = item.params
    await db.commit()
    return await process_rules(db, process_id)


# --- coalitions -----------------------------------------------------------------------------


async def list_coalitions(
    db: AsyncSession, process_id: uuid.UUID
) -> list[tuple[Coalition, list[uuid.UUID]]]:
    await get_process(db, process_id)
    coalitions = (
        (
            await db.execute(
                select(Coalition).where(
                    col(Coalition.process_id) == process_id, col(Coalition.deleted_at).is_(None)
                )
            )
        )
        .scalars()
        .all()
    )
    result = []
    for coalition in coalitions:
        parties = (
            (
                await db.execute(
                    select(col(CoalitionParty.party_id)).where(
                        col(CoalitionParty.coalition_id) == coalition.id,
                        col(CoalitionParty.deleted_at).is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        result.append((coalition, list(parties)))
    return result


async def create_coalition(
    db: AsyncSession, process_id: uuid.UUID, body: CoalitionIn
) -> tuple[Coalition, list[uuid.UUID]]:
    await get_process(db, process_id)
    parties = (
        (
            await db.execute(
                select(Party).where(
                    col(Party.id).in_(body.party_ids), col(Party.deleted_at).is_(None)
                )
            )
        )
        .scalars()
        .all()
    )
    if len(parties) != len(set(body.party_ids)):
        raise BadRequestError("Uno o más partidos no existen.")
    coalition = Coalition(process_id=process_id, name=body.name, coalition_kind=body.coalition_kind)
    db.add(coalition)
    await db.flush()
    for party_id in dict.fromkeys(body.party_ids):
        db.add(CoalitionParty(coalition_id=pk(coalition), party_id=party_id))
    await db.commit()
    return coalition, list(dict.fromkeys(body.party_ids))
