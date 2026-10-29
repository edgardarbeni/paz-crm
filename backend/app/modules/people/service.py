"""People service (D-30, D-31): validated CURP, encrypted sensitive fields with blind indexes,
scope-aware visibility and ARCO-ready deletion.

Visibility for users with a limited geographic scope: a person is visible when their primary
address falls in the scope, when they belong to a nomination the user can see, or when no
address has been captured yet (so capture is possible). Documented as an assumption.
"""

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import ColumnElement, exists, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.audit import record_access
from app.core.crypto import BlindIndexer, FieldCipher
from app.core.db.base import pk
from app.core.errors import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.core.pagination import CursorPage, PageParams, paginate, parse_sort
from app.modules.identity.services.scopes import GeoScope
from app.modules.people import curp as curp_rules
from app.modules.people import hooks
from app.modules.people.models import (
    Person,
    PersonAddress,
    PersonContact,
    PrivacyConsent,
    PrivacyNotice,
)
from app.modules.people.schemas import AddressIn, ConsentIn, ContactIn, PersonCreate, PersonUpdate

CURP_CONTEXT = "people.persons.curp"
CONTACT_CONTEXT = "people.person_contacts.value"
ADDRESS_CONTEXT = "people.person_addresses.address"
PURGE_RETENTION_DAYS = 30


class InvalidCurpError(BadRequestError):
    code = "invalid-curp"
    title = "CURP inválida"


class IncoherentCurpError(ConflictError):
    code = "curp-incoherent"
    title = "La CURP no coincide con los datos capturados"


@dataclass(frozen=True)
class Crypto:
    cipher: FieldCipher
    indexer: BlindIndexer

    def curp_hash(self, value: str) -> bytes:
        return self.indexer.compute(curp_rules.normalize(value), domain=CURP_CONTEXT)

    def contact_hash(self, contact_type: str, value: str) -> bytes:
        return self.indexer.compute(normalize_contact(contact_type, value), domain=CONTACT_CONTEXT)


@dataclass
class PersonView:
    person: Person
    contacts: list[PersonContact] = field(default_factory=list)
    addresses: list[PersonAddress] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def normalize_contact(contact_type: str, value: str) -> str:
    if contact_type == "email":
        return value.strip().lower()
    digits = re.sub(r"\D", "", value)
    return digits[-10:] if len(digits) > 10 else digits  # national 10-digit number


def full_name(person: Person) -> str:
    return " ".join(
        part
        for part in (person.given_names, person.paternal_surname, person.maternal_surname)
        if part
    )


def mask_contact(contact_type: str, value: str) -> str:
    if contact_type == "email":
        user, _, domain = value.partition("@")
        return f"{user[:1]}***@{domain}"
    return "*" * max(len(value) - 4, 0) + value[-4:]


# --- visibility --------------------------------------------------------------------------


def visible_filter(geo: GeoScope) -> ColumnElement[bool] | None:
    if geo.unrestricted:
        return None
    in_scope_address = exists().where(
        col(PersonAddress.person_id) == col(Person.id),
        col(PersonAddress.is_primary).is_(True),
        col(PersonAddress.deleted_at).is_(None),
        geo.sections_filter(col(PersonAddress.section_id)),  # type: ignore[arg-type]
    )
    no_address = ~exists().where(
        col(PersonAddress.person_id) == col(Person.id), col(PersonAddress.deleted_at).is_(None)
    )
    in_visible_nomination = text(
        "EXISTS (SELECT 1 FROM candidacies.formula_members fm "
        "JOIN candidacies.formulas f ON f.id = fm.formula_id "
        "JOIN candidacies.nomination_sections ns ON ns.nomination_id = f.nomination_id "
        "JOIN identity.user_scope_sections u ON u.section_id = ns.section_id "
        "WHERE fm.person_id = people.persons.id AND fm.deleted_at IS NULL AND u.user_id = "
        ":scope_user)"
    ).bindparams(scope_user=geo.user_id)
    return or_(in_scope_address, no_address, in_visible_nomination)


async def visible_person(
    db: AsyncSession, geo: GeoScope, person_id: uuid.UUID, *, for_update: bool = False
) -> Person:
    statement = select(Person).where(col(Person.id) == person_id, col(Person.deleted_at).is_(None))
    if for_update:
        statement = statement.with_for_update()
    person = (await db.execute(statement)).scalar_one_or_none()
    if person is None:
        raise NotFoundError("Persona no encontrada.")
    visible = visible_filter(geo)
    if visible is not None:
        allowed = (
            await db.execute(
                select(func.count()).select_from(Person).where(col(Person.id) == person_id, visible)
            )
        ).scalar_one()
        if not allowed:
            raise ForbiddenError("La persona está fuera de tu alcance geográfico.")
    return person


# --- validation ----------------------------------------------------------------------------


def _apply_curp(
    person: Person,
    crypto: Crypto,
    raw_curp: str | None,
    *,
    accept_incoherence: bool,
    can_accept: bool,
) -> list[str]:
    if raw_curp is None:
        return []
    try:
        data = curp_rules.parse(raw_curp)
    except curp_rules.CurpError as exc:
        raise InvalidCurpError(str(exc)) from None
    person.birth_date = person.birth_date or data.birth_date
    person.sex = person.sex or data.sex
    person.birth_entity = person.birth_entity or data.birth_entity
    problems = curp_rules.coherence(
        data, birth_date=person.birth_date, sex=person.sex, birth_entity=person.birth_entity
    )
    if problems and not (accept_incoherence and can_accept):
        raise IncoherentCurpError(
            " ".join(problems)
            + (" Un usuario con permiso puede forzar el registro." if not can_accept else "")
        )
    blob = crypto.cipher.encrypt(data.curp, context=CURP_CONTEXT)
    person.curp_ciphertext = blob
    person.curp_hash = crypto.curp_hash(data.curp)
    person.key_version = crypto.cipher.key_version(blob)
    person.curp_coherence_overridden = bool(problems)
    return problems


async def _ensure_curp_unique(db: AsyncSession, person: Person) -> None:
    if person.curp_hash is None:
        return
    statement = select(col(Person.id)).where(
        col(Person.curp_hash) == person.curp_hash, col(Person.deleted_at).is_(None)
    )
    if person.id is not None:
        statement = statement.where(col(Person.id) != person.id)
    if (await db.execute(statement)).first() is not None:
        raise ConflictError("Ya existe una persona registrada con esa CURP.")


async def _validate_geography(db: AsyncSession, address: AddressIn) -> None:
    """The captured nodes must exist and be consistent (section inside municipality, etc.)."""
    checks = {
        "states": address.state_id,
        "municipalities": address.municipality_id,
        "sections": address.section_id,
        "localities": address.locality_id,
        "neighborhoods": address.neighborhood_id,
    }
    for table, node in checks.items():
        if node is None:
            continue
        found = (
            await db.execute(text(f"SELECT 1 FROM geography.{table} WHERE id = :id"), {"id": node})  # noqa: S608
        ).first()
        if found is None:
            raise BadRequestError(f"El nodo geográfico {node} no existe ({table}).")
    if address.section_id and address.municipality_id:
        same = (
            await db.execute(
                text("SELECT 1 FROM geography.sections WHERE id = :s AND municipality_id = :m"),
                {"s": address.section_id, "m": address.municipality_id},
            )
        ).first()
        if same is None:
            raise BadRequestError("La sección no pertenece al municipio indicado.")


def _contact_rows(
    person_id: uuid.UUID, crypto: Crypto, contacts: list[ContactIn]
) -> list[PersonContact]:
    rows = []
    for item in contacts:
        normalized = normalize_contact(item.contact_type, item.value)
        if item.contact_type != "email" and len(normalized) != 10:
            raise BadRequestError(f"El teléfono {item.value!r} debe tener 10 dígitos.")
        blob = crypto.cipher.encrypt(normalized, context=CONTACT_CONTEXT)
        rows.append(
            PersonContact(
                person_id=person_id,
                contact_type=item.contact_type,
                value_ciphertext=blob,
                value_hash=crypto.contact_hash(item.contact_type, normalized),
                is_primary=item.is_primary,
                key_version=crypto.cipher.key_version(blob),
            )
        )
    return rows


def _address_row(person_id: uuid.UUID, crypto: Crypto, address: AddressIn) -> PersonAddress:
    private = {
        key: getattr(address, key)
        for key in ("street", "exterior_number", "interior_number", "references")
        if getattr(address, key)
    }
    blob = (
        crypto.cipher.encrypt(json.dumps(private, ensure_ascii=False), context=ADDRESS_CONTEXT)
        if private
        else None
    )
    return PersonAddress(
        person_id=person_id,
        address_type=address.address_type,
        address_ciphertext=blob,
        postal_code=address.postal_code,
        state_id=address.state_id,
        municipality_id=address.municipality_id,
        section_id=address.section_id,
        locality_id=address.locality_id,
        neighborhood_id=address.neighborhood_id,
        is_primary=True,
        key_version=crypto.cipher.key_version(blob) if blob else None,
    )


async def _ensure_address_in_scope(
    db: AsyncSession, geo: GeoScope, address: AddressIn | None
) -> None:
    if geo.unrestricted or address is None or address.section_id is None:
        return
    inside = (
        await db.execute(
            text(
                "SELECT 1 FROM identity.user_scope_sections WHERE user_id = :u AND section_id = :s"
            ),
            {"u": geo.user_id, "s": address.section_id},
        )
    ).first()
    if inside is None:
        raise ForbiddenError("No puedes registrar un domicilio fuera de tu alcance geográfico.")


# --- commands --------------------------------------------------------------------------------


async def create_person(
    db: AsyncSession,
    crypto: Crypto,
    geo: GeoScope,
    body: PersonCreate,
    *,
    can_accept_incoherence: bool,
) -> PersonView:
    view = await build_person(db, crypto, geo, body, can_accept_incoherence=can_accept_incoherence)
    await db.commit()
    await db.refresh(view.person)
    return view


async def build_person(
    db: AsyncSession,
    crypto: Crypto,
    geo: GeoScope,
    body: PersonCreate,
    *,
    can_accept_incoherence: bool,
    address_outside_scope: bool = False,
) -> PersonView:
    """Creates the person and flushes without committing, so another module can write in the
    same transaction. `address_outside_scope` skips the D-66 address rule; only a module with
    its own scope rule may pass it (D-83: enrollment inside a branch)."""
    person = Person(
        given_names=body.given_names,
        paternal_surname=body.paternal_surname,
        maternal_surname=body.maternal_surname,
        birth_date=body.birth_date,
        sex=body.sex,
        birth_entity=body.birth_entity,
    )
    warnings = _apply_curp(
        person,
        crypto,
        body.curp,
        accept_incoherence=body.accept_curp_incoherence,
        can_accept=can_accept_incoherence,
    )
    await _ensure_curp_unique(db, person)
    if body.address:
        await _validate_geography(db, body.address)
        if not address_outside_scope:
            await _ensure_address_in_scope(db, geo, body.address)
    db.add(person)
    await db.flush()
    person_id = pk(person)
    contacts = _contact_rows(person_id, crypto, body.contacts)
    db.add_all(contacts)
    addresses = [_address_row(person_id, crypto, body.address)] if body.address else []
    db.add_all(addresses)
    await db.flush()
    return PersonView(person=person, contacts=contacts, addresses=addresses, warnings=warnings)


async def _live[T: (PersonContact, PersonAddress)](
    db: AsyncSession, model: type[T], person_id: uuid.UUID
) -> list[T]:
    rows = await db.execute(
        select(model).where(col(model.person_id) == person_id, col(model.deleted_at).is_(None))
    )
    return list(rows.scalars())


async def update_person(
    db: AsyncSession,
    crypto: Crypto,
    geo: GeoScope,
    person_id: uuid.UUID,
    body: PersonUpdate,
    *,
    can_accept_incoherence: bool,
) -> PersonView:
    person = await visible_person(db, geo, person_id, for_update=True)
    changes = body.model_dump(
        exclude_unset=True, exclude={"curp", "accept_curp_incoherence", "contacts", "address"}
    )
    for key, value in changes.items():
        setattr(person, key, value)
    warnings: list[str] = []
    if body.curp is not None:
        warnings = _apply_curp(
            person,
            crypto,
            body.curp,
            accept_incoherence=body.accept_curp_incoherence,
            can_accept=can_accept_incoherence,
        )
        await _ensure_curp_unique(db, person)
    elif person.curp_ciphertext and {"birth_date", "sex", "birth_entity"} & set(changes):
        stored = crypto.cipher.decrypt(person.curp_ciphertext, context=CURP_CONTEXT)
        warnings = _apply_curp(
            person,
            crypto,
            stored,
            accept_incoherence=body.accept_curp_incoherence,
            can_accept=can_accept_incoherence,
        )
    now = datetime.now(UTC)
    # Previous rows are retired through the ORM so each soft delete is audited (D-45).
    if body.contacts is not None:
        for contact in await _live(db, PersonContact, person_id):
            contact.deleted_at = now
        db.add_all(_contact_rows(person_id, crypto, body.contacts))
    if body.address is not None:
        await _validate_geography(db, body.address)
        await _ensure_address_in_scope(db, geo, body.address)
        for address in await _live(db, PersonAddress, person_id):
            address.deleted_at = now
            address.is_primary = False
        replacement = _address_row(person_id, crypto, body.address)
        db.add(replacement)
        await db.flush()
        await hooks.address_changed(db, person_id, replacement)
    await db.commit()
    view = await get_person(db, geo, person_id)
    view.warnings = warnings
    return view


async def get_person(db: AsyncSession, geo: GeoScope, person_id: uuid.UUID) -> PersonView:
    return await person_view(db, await visible_person(db, geo, person_id))


async def person_view(db: AsyncSession, person: Person) -> PersonView:
    """Live contacts and addresses of an already authorized person (also a deleted one, for
    modules that keep records of it under their own scope rule)."""
    person_id = pk(person)
    contacts = (
        (
            await db.execute(
                select(PersonContact)
                .where(
                    col(PersonContact.person_id) == person_id,
                    col(PersonContact.deleted_at).is_(None),
                )
                .order_by(col(PersonContact.is_primary).desc(), col(PersonContact.created_at))
            )
        )
        .scalars()
        .all()
    )
    addresses = (
        (
            await db.execute(
                select(PersonAddress)
                .where(
                    col(PersonAddress.person_id) == person_id,
                    col(PersonAddress.deleted_at).is_(None),
                )
                .order_by(col(PersonAddress.is_primary).desc())
            )
        )
        .scalars()
        .all()
    )
    return PersonView(person=person, contacts=list(contacts), addresses=list(addresses))


async def read_person(
    db: AsyncSession, geo: GeoScope, person_id: uuid.UUID, *, unmasked: bool
) -> PersonView:
    """Detail read for the API: logged in the sensitive-read log (D-89)."""
    view = await get_person(db, geo, person_id)
    await record_access(
        db,
        action="read",
        entity_table="people.persons",
        entity_id=str(person_id),
        details={"unmasked": unmasked},
    )
    await db.commit()
    return view


async def search_people(
    db: AsyncSession,
    crypto: Crypto,
    geo: GeoScope,
    params: PageParams,
    *,
    q: str | None,
    curp: str | None,
    phone: str | None,
) -> CursorPage[Person]:
    statement = select(Person).where(col(Person.deleted_at).is_(None))
    if q:
        term = q.strip().lower()
        statement = statement.where(
            func.f_unaccent(func.lower(col(Person.search_name))).ilike(
                func.concat("%", func.f_unaccent(term), "%")
            )
        )
    if curp:
        statement = statement.where(col(Person.curp_hash) == crypto.curp_hash(curp))
    if phone:
        digest = crypto.contact_hash("mobile", phone)
        statement = statement.where(
            exists().where(
                col(PersonContact.person_id) == col(Person.id),
                col(PersonContact.value_hash) == digest,
                col(PersonContact.deleted_at).is_(None),
            )
        )
    visible = visible_filter(geo)
    if visible is not None:
        statement = statement.where(visible)
    sort = parse_sort(
        params.sort,
        allowed={
            "paternal_surname": col(Person.paternal_surname),
            "given_names": col(Person.given_names),
            "created_at": col(Person.created_at),
        },
        tiebreaker=col(Person.id),
        default="paternal_surname",
    )
    page: CursorPage[Person] = await paginate(
        db, statement, sort=sort, limit=params.limit, cursor=params.cursor
    )
    return page


async def delete_person(db: AsyncSession, geo: GeoScope, person_id: uuid.UUID) -> date:
    """Soft delete (ARCO cancellation); the record is anonymized after the retention period."""
    person = await visible_person(db, geo, person_id, for_update=True)
    active = (
        await db.execute(
            text(
                "SELECT 1 FROM candidacies.formula_members fm JOIN candidacies.formulas f ON f.id "
                "= fm.formula_id "
                "WHERE fm.person_id = :p AND fm.deleted_at IS NULL "
                "AND f.status IN ('aspirant', 'registered', 'approved') LIMIT 1"
            ),
            {"p": person_id},
        )
    ).first()
    if active is not None:
        raise ConflictError(
            "La persona integra una candidatura activa; sustitúyela o cancélala primero."
        )
    person.deleted_at = datetime.now(UTC)
    person.purge_after = date.today() + timedelta(days=PURGE_RETENTION_DAYS)
    await hooks.person_deleted(db, person_id)
    await db.commit()
    return person.purge_after


async def add_consent(
    db: AsyncSession, geo: GeoScope, person_id: uuid.UUID, body: ConsentIn
) -> PrivacyConsent:
    await visible_person(db, geo, person_id)
    consent = PrivacyConsent(
        person_id=person_id,
        notice_version=body.notice_version,
        channel=body.channel,
        evidence_uri=body.evidence_uri,
        accepted_at=datetime.now(UTC),
    )
    db.add(consent)
    await db.commit()
    return consent


async def record_consent(
    db: AsyncSession,
    person_id: uuid.UUID,
    notice: PrivacyNotice,
    *,
    channel: str,
    evidence_uri: str | None = None,
) -> PrivacyConsent:
    """Consent on a catalogued notice, flushed in the caller's transaction (D-82)."""
    consent = PrivacyConsent(
        person_id=person_id,
        notice_id=notice.id,
        notice_code=notice.code,
        notice_version=notice.version,
        notice_text_sha256=notice.body_sha256,
        channel=channel,
        evidence_uri=evidence_uri,
        accepted_at=datetime.now(UTC),
    )
    db.add(consent)
    await db.flush()
    return consent


# --- privacy notices (D-82) -------------------------------------------------------------------


async def current_notice(db: AsyncSession, code: str) -> PrivacyNotice | None:
    return (
        await db.execute(
            select(PrivacyNotice).where(
                col(PrivacyNotice.code) == code,
                col(PrivacyNotice.valid_to).is_(None),
                col(PrivacyNotice.deleted_at).is_(None),
            )
        )
    ).scalar_one_or_none()


async def list_notices(db: AsyncSession, code: str | None = None) -> list[PrivacyNotice]:
    statement = select(PrivacyNotice).where(col(PrivacyNotice.deleted_at).is_(None))
    if code:
        statement = statement.where(col(PrivacyNotice.code) == code)
    rows = await db.execute(
        statement.order_by(col(PrivacyNotice.code), col(PrivacyNotice.valid_from).desc())
    )
    return list(rows.scalars())


async def publish_notice(
    db: AsyncSession, *, code: str, version: str, title: str, body: str, is_sample: bool = False
) -> PrivacyNotice:
    """New current version of a notice; the previous one stays in the catalog, closed."""
    duplicate = (
        await db.execute(
            select(col(PrivacyNotice.id)).where(
                col(PrivacyNotice.code) == code,
                col(PrivacyNotice.version) == version,
                col(PrivacyNotice.deleted_at).is_(None),
            )
        )
    ).first()
    if duplicate is not None:
        raise ConflictError(f"Ya existe la versión «{version}» del aviso «{code}».")
    now = datetime.now(UTC)
    previous = await current_notice(db, code)
    if previous is not None:
        previous.valid_to = now
        await db.flush()
    notice = PrivacyNotice(
        code=code,
        version=version,
        title=title,
        body=body,
        body_sha256=hashlib.sha256(body.encode()).hexdigest(),
        is_sample=is_sample,
        valid_from=now,
    )
    db.add(notice)
    await db.commit()
    return notice


async def list_consents(
    db: AsyncSession, geo: GeoScope, person_id: uuid.UUID
) -> list[PrivacyConsent]:
    await visible_person(db, geo, person_id)
    rows = await db.execute(
        select(PrivacyConsent)
        .where(col(PrivacyConsent.person_id) == person_id, col(PrivacyConsent.deleted_at).is_(None))
        .order_by(col(PrivacyConsent.accepted_at).desc())
    )
    return list(rows.scalars())


async def purge_due(db: AsyncSession, *, today: date | None = None) -> int:
    """Anonymizes soft-deleted persons whose retention period ended (scheduled job). Rows stay,
    so historical candidacies keep their integrity, but no personal data remains."""
    today = today or date.today()
    due = (
        (
            await db.execute(
                select(col(Person.id)).where(
                    col(Person.deleted_at).is_not(None),
                    col(Person.purge_after) <= today,
                    col(Person.curp_ciphertext).is_not(None)
                    | (col(Person.given_names) != "[eliminado]"),
                )
            )
        )
        .scalars()
        .all()
    )
    for person_id in due:
        # ORM deletes so each removed row is audited (D-45); bytes are masked in the log.
        for model in (PersonContact, PersonAddress, PrivacyConsent):
            rows = await db.execute(select(model).where(col(model.person_id) == person_id))
            for row in rows.scalars():
                await db.delete(row)
        person = await db.get(Person, person_id)
        assert person is not None  # noqa: S101
        person.given_names = "[eliminado]"
        person.paternal_surname = "[eliminado]"
        person.maternal_surname = None
        person.birth_date = None
        person.birth_entity = None
        person.curp_ciphertext = None
        person.curp_hash = None
        person.key_version = None
    await db.commit()
    return len(due)


def decoded_address(crypto: Crypto, address: PersonAddress) -> dict[str, Any]:
    if address.address_ciphertext is None:
        return {}
    decoded: dict[str, Any] = json.loads(
        crypto.cipher.decrypt(address.address_ciphertext, context=ADDRESS_CONTEXT)
    )
    return decoded
