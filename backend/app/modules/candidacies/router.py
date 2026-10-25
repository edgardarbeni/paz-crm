"""Candidacies API: catalogs, electoral processes and their configuration, nominations and
formulas (D-21..D-29). Reading needs `candidacies.read` and follows the geographic scope."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, status

from app.core.db.session import SessionDep
from app.core.pagination import CursorPage, PageParams, page_params
from app.modules.candidacies import nominations, service
from app.modules.candidacies.models import NominationStatus, Party
from app.modules.candidacies.nominations import Actor
from app.modules.candidacies.schemas import (
    CoalitionIn,
    CoalitionOut,
    FormulaIn,
    FormulaMembersUpdate,
    FormulaStatusIn,
    MunicipalitySettingIn,
    MunicipalitySettingOut,
    NominationAction,
    NominationIn,
    NominationOut,
    NominationSummary,
    NominationUpdate,
    OfficeTypeIn,
    OfficeTypeOut,
    PartyIn,
    PartyOut,
    ProcessIn,
    ProcessOfficeIn,
    ProcessOfficeOut,
    ProcessOut,
    ProcessRuleIn,
    ProcessRuleOut,
    ProcessUpdate,
    StatusHistoryOut,
    SubstitutionIn,
    ValidationRuleOut,
    ViolationOut,
)
from app.modules.identity.dependencies import CurrentUser, permission
from app.modules.identity.permissions import Perm

router = APIRouter(tags=["candidacies"])

Reader = Annotated[CurrentUser, permission(Perm.CANDIDACIES_READ)]
CatalogManager = Annotated[CurrentUser, permission(Perm.CATALOG_MANAGE)]
ProcessManager = Annotated[CurrentUser, permission(Perm.PROCESS_MANAGE)]
Writer = Annotated[CurrentUser, permission(Perm.NOMINATION_WRITE)]
ProcessId = Annotated[uuid.UUID, Path(description="Id del proceso electoral.")]
NominationId = Annotated[uuid.UUID, Path(description="Id de la postulación.")]
FormulaId = Annotated[uuid.UUID, Path(description="Id de la fórmula.")]


def actor(user: CurrentUser) -> Actor:
    return Actor(
        user_id=user.id,
        geo=user.geo,
        can_approve=user.has(Perm.NOMINATION_APPROVE),
        can_override=user.has(Perm.RULE_OVERRIDE),
    )


# --- catalogs -------------------------------------------------------------------------------


@router.get("/parties", operation_id="listParties", summary="Partidos políticos")
async def list_parties(db: SessionDep, _: Reader) -> list[PartyOut]:
    return [PartyOut.model_validate(p) for p in await service.list_parties(db)]


@router.post(
    "/parties",
    operation_id="createParty",
    summary="Registrar partido",
    status_code=status.HTTP_201_CREATED,
)
async def create_party(db: SessionDep, _: CatalogManager, body: PartyIn) -> PartyOut:
    return PartyOut.model_validate(await service.create_party(db, body))


@router.put("/parties/{party_id}", operation_id="updateParty", summary="Editar partido")
async def update_party(
    db: SessionDep, _: CatalogManager, party_id: uuid.UUID, body: PartyIn
) -> PartyOut:
    party: Party = await service.update_party(db, party_id, body)
    return PartyOut.model_validate(party)


@router.get("/office-types", operation_id="listOfficeTypes", summary="Tipos de cargo")
async def list_office_types(db: SessionDep, _: Reader) -> list[OfficeTypeOut]:
    return [OfficeTypeOut.model_validate(o) for o in await service.list_office_types(db)]


@router.post(
    "/office-types",
    operation_id="createOfficeType",
    summary="Agregar tipo de cargo",
    status_code=status.HTTP_201_CREATED,
)
async def create_office_type(
    db: SessionDep, _: CatalogManager, body: OfficeTypeIn
) -> OfficeTypeOut:
    return OfficeTypeOut.model_validate(await service.create_office_type(db, body))


@router.get(
    "/validation-rules",
    operation_id="listValidationRules",
    summary="Catálogo de reglas de validación",
)
async def list_validation_rules(db: SessionDep, _: Reader) -> list[ValidationRuleOut]:
    return [ValidationRuleOut.model_validate(r) for r in await service.list_rules(db)]


# --- processes ------------------------------------------------------------------------------


@router.get("/processes", operation_id="listProcesses", summary="Procesos electorales")
async def list_processes(db: SessionDep, _: Reader) -> list[ProcessOut]:
    return [ProcessOut.model_validate(p) for p in await service.list_processes(db)]


@router.post(
    "/processes",
    operation_id="createProcess",
    summary="Crear proceso electoral",
    status_code=status.HTTP_201_CREATED,
)
async def create_process(db: SessionDep, _: ProcessManager, body: ProcessIn) -> ProcessOut:
    return ProcessOut.model_validate(await service.create_process(db, body))


@router.get("/processes/{process_id}", operation_id="getProcess", summary="Detalle de proceso")
async def get_process(db: SessionDep, _: Reader, process_id: ProcessId) -> ProcessOut:
    return ProcessOut.model_validate(await service.get_process(db, process_id))


@router.patch("/processes/{process_id}", operation_id="updateProcess", summary="Editar proceso")
async def update_process(
    db: SessionDep, _: ProcessManager, process_id: ProcessId, body: ProcessUpdate
) -> ProcessOut:
    return ProcessOut.model_validate(await service.update_process(db, process_id, body))


def _offices_out(rows: list[Any]) -> list[ProcessOfficeOut]:
    return [
        ProcessOfficeOut(
            office_type_id=config.office_type_id,
            is_enabled=config.is_enabled,
            positions=config.positions,
            slate_parent_office_type_id=config.slate_parent_office_type_id,
            rp_method=config.rp_method,
            rp_method_params=config.rp_method_params,
            office_code=office.code,
            office_name=office.name,
        )
        for config, office in rows
    ]


@router.get(
    "/processes/{process_id}/offices",
    operation_id="listProcessOffices",
    summary="Cargos en elección",
)
async def list_process_offices(
    db: SessionDep, _: Reader, process_id: ProcessId
) -> list[ProcessOfficeOut]:
    return _offices_out(await service.process_offices(db, process_id))


@router.put(
    "/processes/{process_id}/offices",
    operation_id="configureProcessOffices",
    summary="Habilitar cargos y su composición",
)
async def configure_process_offices(
    db: SessionDep, _: ProcessManager, process_id: ProcessId, body: list[ProcessOfficeIn]
) -> list[ProcessOfficeOut]:
    return _offices_out(await service.configure_offices(db, process_id, body))


@router.get(
    "/processes/{process_id}/municipalities",
    operation_id="listMunicipalitySettings",
    summary="Integración de ayuntamientos y régimen por municipio",
)
async def list_municipality_settings(
    db: SessionDep, _: Reader, process_id: ProcessId
) -> list[MunicipalitySettingOut]:
    return [
        MunicipalitySettingOut.model_validate(s)
        for s in await service.municipality_settings(db, process_id)
    ]


@router.put(
    "/processes/{process_id}/municipalities",
    operation_id="configureMunicipalities",
    summary="Capturar integración de ayuntamientos (carga masiva)",
)
async def configure_municipalities(
    db: SessionDep, _: ProcessManager, process_id: ProcessId, body: list[MunicipalitySettingIn]
) -> list[MunicipalitySettingOut]:
    rows = await service.configure_municipalities(db, process_id, body)
    return [MunicipalitySettingOut.model_validate(s) for s in rows]


@router.get(
    "/processes/{process_id}/rules", operation_id="listProcessRules", summary="Reglas del proceso"
)
async def list_process_rules(
    db: SessionDep, _: Reader, process_id: ProcessId
) -> list[ProcessRuleOut]:
    return [ProcessRuleOut.model_validate(r) for r in await service.process_rules(db, process_id)]


@router.put(
    "/processes/{process_id}/rules",
    operation_id="configureProcessRules",
    summary="Activar y parametrizar reglas",
)
async def configure_process_rules(
    db: SessionDep, _: ProcessManager, process_id: ProcessId, body: list[ProcessRuleIn]
) -> list[ProcessRuleOut]:
    return [
        ProcessRuleOut.model_validate(r)
        for r in await service.configure_rules(db, process_id, body)
    ]


@router.get(
    "/processes/{process_id}/coalitions",
    operation_id="listCoalitions",
    summary="Coaliciones del proceso",
)
async def list_coalitions(db: SessionDep, _: Reader, process_id: ProcessId) -> list[CoalitionOut]:
    return [
        CoalitionOut(id=c.id, name=c.name, coalition_kind=c.coalition_kind, party_ids=parties)
        for c, parties in await service.list_coalitions(db, process_id)
    ]


@router.post(
    "/processes/{process_id}/coalitions",
    operation_id="createCoalition",
    summary="Registrar coalición o candidatura común",
    status_code=status.HTTP_201_CREATED,
)
async def create_coalition(
    db: SessionDep, _: ProcessManager, process_id: ProcessId, body: CoalitionIn
) -> CoalitionOut:
    coalition, parties = await service.create_coalition(db, process_id, body)
    return CoalitionOut(
        id=coalition.id,
        name=coalition.name,
        coalition_kind=coalition.coalition_kind,
        party_ids=parties,
    )


# --- nominations ----------------------------------------------------------------------------


async def _view(db: SessionDep, user: CurrentUser, nomination: Any) -> NominationOut:
    return NominationOut.model_validate(
        await nominations.nomination_view(db, actor(user), nomination)
    )


@router.get(
    "/nominations", operation_id="listNominations", summary="Postulaciones visibles para el usuario"
)
async def list_nominations(
    db: SessionDep,
    user: Reader,
    params: Annotated[PageParams, Depends(page_params)],
    process_id: uuid.UUID | None = None,
    office_type_id: uuid.UUID | None = None,
    status_: Annotated[NominationStatus | None, Query(alias="status")] = None,
    party_id: uuid.UUID | None = None,
) -> CursorPage[NominationSummary]:
    page = await nominations.list_nominations(
        db,
        actor(user),
        params,
        process_id=process_id,
        office_type_id=office_type_id,
        status=status_,
        party_id=party_id,
    )
    codes = await nominations.office_codes(db)
    return CursorPage[NominationSummary](
        items=[
            NominationSummary.model_validate(nominations.summary_dict(n, codes)) for n in page.items
        ],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


@router.post(
    "/nominations",
    operation_id="createNomination",
    summary="Crear postulación",
    status_code=status.HTTP_201_CREATED,
)
async def create_nomination(db: SessionDep, user: Writer, body: NominationIn) -> NominationOut:
    return await _view(db, user, await nominations.create_nomination(db, actor(user), body))


@router.get(
    "/nominations/{nomination_id}", operation_id="getNomination", summary="Detalle de postulación"
)
async def get_nomination(
    db: SessionDep, user: Reader, nomination_id: NominationId
) -> NominationOut:
    return await _view(db, user, await nominations.load_nomination(db, actor(user), nomination_id))


@router.patch(
    "/nominations/{nomination_id}", operation_id="updateNomination", summary="Editar notas"
)
async def update_nomination(
    db: SessionDep, user: Writer, nomination_id: NominationId, body: NominationUpdate
) -> NominationOut:
    return await _view(
        db, user, await nominations.update_nomination(db, actor(user), nomination_id, body)
    )


@router.post(
    "/nominations/{nomination_id}/submit",
    operation_id="submitNomination",
    summary="Enviar postulación",
)
async def submit_nomination(
    db: SessionDep, user: Writer, nomination_id: NominationId, body: NominationAction
) -> NominationOut:
    return await _view(
        db, user, await nominations.submit_nomination(db, actor(user), nomination_id, body)
    )


@router.post(
    "/nominations/{nomination_id}/approve",
    operation_id="approveNomination",
    summary="Aprobar postulación",
)
async def approve_nomination(
    db: SessionDep, user: Writer, nomination_id: NominationId, body: NominationAction
) -> NominationOut:
    return await _view(
        db, user, await nominations.approve_nomination(db, actor(user), nomination_id, body)
    )


@router.post(
    "/nominations/{nomination_id}/cancel",
    operation_id="cancelNomination",
    summary="Cancelar postulación",
)
async def cancel_nomination(
    db: SessionDep, user: Writer, nomination_id: NominationId, body: NominationAction
) -> NominationOut:
    return await _view(
        db, user, await nominations.cancel_nomination(db, actor(user), nomination_id, body)
    )


@router.get(
    "/nominations/{nomination_id}/validation",
    operation_id="validateNomination",
    summary="Validar postulación (todas las reglas, paridad incluida, sin guardar)",
)
async def validate_nomination(
    db: SessionDep, user: Reader, nomination_id: NominationId
) -> list[ViolationOut]:
    violations = await nominations.validate(db, actor(user), nomination_id)
    return [ViolationOut.model_validate(nominations.violation_dict(v)) for v in violations]


@router.get(
    "/nominations/{nomination_id}/history",
    operation_id="getNominationHistory",
    summary="Historial de estatus de las fórmulas",
)
async def get_nomination_history(
    db: SessionDep, user: Reader, nomination_id: NominationId
) -> list[StatusHistoryOut]:
    return [
        StatusHistoryOut.model_validate(h)
        for h in await nominations.history(db, actor(user), nomination_id)
    ]


@router.post(
    "/nominations/{nomination_id}/formulas",
    operation_id="createFormula",
    summary="Registrar fórmula (propietaria y suplente)",
    status_code=status.HTTP_201_CREATED,
)
async def create_formula(
    db: SessionDep, user: Writer, nomination_id: NominationId, body: FormulaIn
) -> NominationOut:
    return await _view(
        db, user, await nominations.create_formula(db, actor(user), nomination_id, body)
    )


@router.patch(
    "/formulas/{formula_id}",
    operation_id="updateFormulaMembers",
    summary="Cambiar integrantes (aspirante)",
)
async def update_formula_members(
    db: SessionDep, user: Writer, formula_id: FormulaId, body: FormulaMembersUpdate
) -> NominationOut:
    return await _view(
        db, user, await nominations.update_members(db, actor(user), formula_id, body)
    )


@router.post(
    "/formulas/{formula_id}/status",
    operation_id="changeFormulaStatus",
    summary="Cambiar estatus de fórmula",
)
async def change_formula_status(
    db: SessionDep, user: Writer, formula_id: FormulaId, body: FormulaStatusIn
) -> NominationOut:
    return await _view(
        db, user, await nominations.change_formula_status(db, actor(user), formula_id, body)
    )


@router.post(
    "/formulas/{formula_id}/substitute",
    operation_id="substituteFormula",
    summary="Sustituir fórmula",
)
async def substitute_formula(
    db: SessionDep, user: Writer, formula_id: FormulaId, body: SubstitutionIn
) -> NominationOut:
    return await _view(
        db, user, await nominations.substitute_formula(db, actor(user), formula_id, body)
    )
