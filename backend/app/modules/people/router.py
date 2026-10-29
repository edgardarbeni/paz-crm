"""/people — persons with validated CURP and encrypted sensitive data (D-30, D-31).

Sensitive values (CURP, contacts, street address) are masked unless the caller holds
`people.person.read_sensitive`.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from pydantic import BaseModel

from app.core.db.session import SessionDep
from app.core.pagination import CursorPage, PageParams, page_params
from app.modules.identity.dependencies import CurrentUser, permission
from app.modules.identity.permissions import Perm
from app.modules.people import service
from app.modules.people.schemas import (
    ConsentIn,
    ConsentOut,
    NoticeIn,
    NoticeOut,
    PersonCreate,
    PersonOut,
    PersonSummary,
    PersonUpdate,
)
from app.modules.people.views import CryptoDep, person_out, person_summary

router = APIRouter(prefix="/people", tags=["people"])

Reader = Annotated[CurrentUser, permission(Perm.PERSON_READ)]
Writer = Annotated[CurrentUser, permission(Perm.PERSON_WRITE)]
Deleter = Annotated[CurrentUser, permission(Perm.PERSON_DELETE)]
NoticeManager = Annotated[CurrentUser, permission(Perm.NOTICE_MANAGE)]
PersonId = Annotated[uuid.UUID, Path(description="Id de la persona.")]


class DeletionOut(BaseModel):
    purge_after: str


@router.get(
    "/privacy-notices",
    operation_id="listPrivacyNotices",
    summary="Avisos de privacidad y sus versiones",
)
async def list_privacy_notices(
    db: SessionDep,
    _: Reader,
    code: Annotated[str | None, Query(max_length=50)] = None,
) -> list[NoticeOut]:
    return [NoticeOut.model_validate(n) for n in await service.list_notices(db, code)]


@router.post(
    "/privacy-notices",
    operation_id="publishPrivacyNotice",
    summary="Publicar una versión nueva de un aviso de privacidad",
    status_code=status.HTTP_201_CREATED,
)
async def publish_privacy_notice(db: SessionDep, _: NoticeManager, body: NoticeIn) -> NoticeOut:
    notice = await service.publish_notice(
        db, code=body.code, version=body.version, title=body.title, body=body.body
    )
    return NoticeOut.model_validate(notice)


@router.get("", operation_id="searchPeople", summary="Buscar personas")
async def search_people(
    db: SessionDep,
    crypto: CryptoDep,
    user: Reader,
    params: Annotated[PageParams, Depends(page_params)],
    q: Annotated[
        str | None, Query(min_length=2, max_length=100, description="Nombre o apellidos.")
    ] = None,
    curp: Annotated[str | None, Query(min_length=18, max_length=18)] = None,
    phone: Annotated[str | None, Query(min_length=10, max_length=20)] = None,
) -> CursorPage[PersonSummary]:
    page = await service.search_people(db, crypto, user.geo, params, q=q, curp=curp, phone=phone)
    sensitive = user.has(Perm.PERSON_READ_SENSITIVE)
    return CursorPage[PersonSummary](
        items=[person_summary(crypto, person, sensitive) for person in page.items],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


@router.post(
    "",
    operation_id="createPerson",
    summary="Registrar persona",
    status_code=status.HTTP_201_CREATED,
)
async def create_person(
    db: SessionDep, crypto: CryptoDep, user: Writer, body: PersonCreate
) -> PersonOut:
    view = await service.create_person(
        db, crypto, user.geo, body, can_accept_incoherence=user.has(Perm.PERSON_READ_SENSITIVE)
    )
    return person_out(crypto, view, user.has(Perm.PERSON_READ_SENSITIVE))


@router.get("/{person_id}", operation_id="getPerson", summary="Detalle de persona")
async def get_person(
    db: SessionDep, crypto: CryptoDep, user: Reader, person_id: PersonId
) -> PersonOut:
    sensitive = user.has(Perm.PERSON_READ_SENSITIVE)
    view = await service.read_person(db, user.geo, person_id, unmasked=sensitive)
    return person_out(crypto, view, sensitive)


@router.patch("/{person_id}", operation_id="updatePerson", summary="Actualizar persona")
async def update_person(
    db: SessionDep, crypto: CryptoDep, user: Writer, person_id: PersonId, body: PersonUpdate
) -> PersonOut:
    view = await service.update_person(
        db,
        crypto,
        user.geo,
        person_id,
        body,
        can_accept_incoherence=user.has(Perm.PERSON_READ_SENSITIVE),
    )
    return person_out(crypto, view, user.has(Perm.PERSON_READ_SENSITIVE))


@router.delete(
    "/{person_id}",
    operation_id="deletePerson",
    summary="Cancelación ARCO (baja con purga diferida)",
)
async def delete_person(db: SessionDep, user: Deleter, person_id: PersonId) -> DeletionOut:
    purge_after = await service.delete_person(db, user.geo, person_id)
    return DeletionOut(purge_after=purge_after.isoformat())


@router.get(
    "/{person_id}/consents", operation_id="listConsents", summary="Consentimientos de privacidad"
)
async def list_consents(db: SessionDep, user: Reader, person_id: PersonId) -> list[ConsentOut]:
    return [
        ConsentOut.model_validate(c) for c in await service.list_consents(db, user.geo, person_id)
    ]


@router.post(
    "/{person_id}/consents",
    operation_id="addConsent",
    summary="Registrar aceptación del aviso de privacidad",
    status_code=status.HTTP_201_CREATED,
)
async def add_consent(
    db: SessionDep, user: Writer, person_id: PersonId, body: ConsentIn
) -> ConsentOut:
    return ConsentOut.model_validate(await service.add_consent(db, user.geo, person_id, body))
