"""API views of a person with the masking of D-66: sensitive values (CURP, contacts, street
address) come out complete only with `people.person.read_sensitive`. Shared with modules that
serve a person's data under their own scope rule (D-83)."""

from typing import Annotated

from fastapi import Depends

from app.modules.identity.container import ServicesDep
from app.modules.people import curp as curp_rules
from app.modules.people import service
from app.modules.people.models import Person
from app.modules.people.schemas import AddressOut, ContactOut, PersonOut, PersonSummary
from app.modules.people.service import CONTACT_CONTEXT, CURP_CONTEXT, Crypto, PersonView


def _curp(crypto: Crypto, person: Person, sensitive: bool) -> str | None:
    if person.curp_ciphertext is None:
        return None
    value = crypto.cipher.decrypt(person.curp_ciphertext, context=CURP_CONTEXT)
    return value if sensitive else curp_rules.mask(value)


def person_summary(crypto: Crypto, person: Person, sensitive: bool) -> PersonSummary:
    return PersonSummary(
        id=person.id,
        full_name=service.full_name(person),
        sex=person.sex,
        birth_date=person.birth_date,
        curp=_curp(crypto, person, sensitive),
    )


def person_out(crypto: Crypto, view: PersonView, sensitive: bool) -> PersonOut:
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
        **person_summary(crypto, person, sensitive).model_dump(),
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


def get_crypto(services: ServicesDep) -> Crypto:
    return Crypto(cipher=services.cipher, indexer=services.indexer)


CryptoDep = Annotated[Crypto, Depends(get_crypto)]
