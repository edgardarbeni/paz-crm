import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Surname = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Sex = Literal["H", "M", "X"]
EntityCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]
PostalCode = Annotated[str, StringConstraints(pattern=r"^\d{5}$")]


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class ContactIn(Schema):
    contact_type: Literal["mobile", "landline", "email"]
    value: Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=150)]
    is_primary: bool = False


class AddressIn(Schema):
    address_type: Literal["home", "work", "other"] = "home"
    street: Annotated[str | None, Field(max_length=200)] = None
    exterior_number: Annotated[str | None, Field(max_length=30)] = None
    interior_number: Annotated[str | None, Field(max_length=30)] = None
    references: Annotated[str | None, Field(max_length=300)] = None
    postal_code: PostalCode | None = None
    state_id: uuid.UUID | None = None
    municipality_id: uuid.UUID | None = None
    section_id: uuid.UUID | None = None
    locality_id: uuid.UUID | None = None
    neighborhood_id: uuid.UUID | None = None


class PersonCreate(Schema):
    given_names: Name
    paternal_surname: Surname
    maternal_surname: Surname | None = None
    birth_date: date | None = None
    sex: Sex | None = None
    birth_entity: EntityCode | None = None
    curp: Annotated[str | None, Field(min_length=18, max_length=22)] = None
    accept_curp_incoherence: bool = Field(
        default=False,
        description="Forzar el registro aunque la CURP no coincida con los datos (requiere "
        "permiso).",
    )
    contacts: list[ContactIn] = Field(default_factory=list, max_length=10)
    address: AddressIn | None = None


class PersonUpdate(Schema):
    given_names: Name | None = None
    paternal_surname: Surname | None = None
    maternal_surname: Surname | None = None
    birth_date: date | None = None
    sex: Sex | None = None
    birth_entity: EntityCode | None = None
    curp: Annotated[str | None, Field(min_length=18, max_length=22)] = None
    accept_curp_incoherence: bool = False
    contacts: list[ContactIn] | None = Field(default=None, max_length=10)
    address: AddressIn | None = None


class ContactOut(Schema):
    id: uuid.UUID
    contact_type: str
    value: str = Field(description="Enmascarado sin el permiso people.person.read_sensitive.")
    is_primary: bool


class AddressOut(Schema):
    id: uuid.UUID
    address_type: str
    street: str | None = None
    exterior_number: str | None = None
    interior_number: str | None = None
    references: str | None = None
    postal_code: str | None
    state_id: uuid.UUID | None
    municipality_id: uuid.UUID | None
    section_id: uuid.UUID | None
    locality_id: uuid.UUID | None
    neighborhood_id: uuid.UUID | None
    is_primary: bool


class PersonSummary(Schema):
    id: uuid.UUID
    full_name: str
    sex: str | None
    birth_date: date | None
    curp: str | None = Field(description="Enmascarada sin el permiso people.person.read_sensitive.")


class PersonOut(PersonSummary):
    given_names: str
    paternal_surname: str
    maternal_surname: str | None
    birth_entity: str | None
    curp_coherence_overridden: bool
    contacts: list[ContactOut]
    addresses: list[AddressOut]
    created_at: datetime
    warnings: list[str] = Field(default_factory=list)


class ConsentIn(Schema):
    notice_version: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
    ]
    channel: Literal["panel", "paper", "web"]
    evidence_uri: Annotated[str | None, Field(max_length=500)] = None


class ConsentOut(Schema):
    id: uuid.UUID
    notice_version: str
    channel: str
    evidence_uri: str | None
    accepted_at: datetime
