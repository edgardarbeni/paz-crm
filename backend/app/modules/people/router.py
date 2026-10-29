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
from app.modules.identity.container import ServicesDep
from app.modules.identity.dependencies import CurrentUser, permission
from app.modules.identity.permissions import Perm
from app.modules.people import curp as curp_rules
from app.modules.people import service
from app.modules.people.models import Person
from app.modules.people.schemas import (
    AddressOut,
    ConsentIn,
    ConsentOut,
    ContactOut,
    PersonCreate,
    PersonOut,
    PersonSummary,
    PersonUpdate,
)
from app.modules.people.service import CONTACT_CONTEXT, CURP_CONTEXT, Crypto, PersonView

router = APIRouter(prefix="/people", tags=["people"])

Reader = Annotated[CurrentUser, permission(Perm.PERSON_READ)]
Writer = Annotated[CurrentUser, permission(Perm.PERSON_WRITE)]
Deleter = Annotated[CurrentUser, permission(Perm.PERSON_DELETE)]
PersonId = Annotated[uuid.UUID, Path(description="Id de la persona.")]


def get_crypto(services: ServicesDep) -> Crypto:
    return Crypto(cipher=services.cipher, indexer=services.indexer)


CryptoDep = Annotated[Crypto, Depends(get_crypto)]


class DeletionOut(BaseModel):
    purge_after: str


def _curp(crypto: Crypto, person: Person, sensitive: bool) -> str | None:
    if person.curp_ciphertext is None:
        return None
    value = crypto.cipher.decrypt(person.curp_ciphertext, context=CURP_CONTEXT)
    return value if sensitive else curp_rules.mask(value)


def _summary(crypto: Crypto, person: Person, sensitive: bool) -> PersonSummary:
    return PersonSummary(
        id=person.id,
        full_name=service.full_name(person),
        sex=person.sex,
        birth_date=person.birth_date,
        curp=_curp(crypto, person, sensitive),
    )


def _out(crypto: Crypto, view: PersonView, sensitive: bool) -> PersonOut:
    person = view.person
    contacts = []
    for contact in view.contacts:
        value = crypto.cipher.decrypt(contact.value_ciphertext, context=CONTACT_CONTEXT)
        contacts.append(
            ContactOut(
                id=contact.id,
                contact_type=contact.contact_type,
                value=value if sensitive else service.mask_contact(contact.contact_type, value),
                is_primary=contact.is_primary,
            )
        )
    addresses = [
        AddressOut.model_validate(
            {
                **address.model_dump(include=set(AddressOut.model_fields)),
                **(service.decoded_address(crypto, address) if sensitive else {}),
            }
        )
        for address in view.addresses
    ]
    return PersonOut(
        **_summary(crypto, person, sensitive).model_dump(),
        given_names=person.given_names,
        paternal_surname=person.paternal_surname,
        maternal_surname=person.maternal_surname,
        birth_entity=person.birth_entity,
        curp_coherence_overridden=person.curp_coherence_overridden,
        contacts=contacts,
        addresses=addresses,
        created_at=person.created_at,
        warnings=view.warnings,
    )


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
        items=[_summary(crypto, person, sensitive) for person in page.items],
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
    return _out(crypto, view, user.has(Perm.PERSON_READ_SENSITIVE))


@router.get("/{person_id}", operation_id="getPerson", summary="Detalle de persona")
async def get_person(
    db: SessionDep, crypto: CryptoDep, user: Reader, person_id: PersonId
) -> PersonOut:
    sensitive = user.has(Perm.PERSON_READ_SENSITIVE)
    view = await service.read_person(db, user.geo, person_id, unmasked=sensitive)
    return _out(crypto, view, sensitive)


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
    return _out(crypto, view, user.has(Perm.PERSON_READ_SENSITIVE))


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
