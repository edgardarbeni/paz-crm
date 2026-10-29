"""Extension points of `people` for modules that build on a person (D-83, D-92).

`people` never imports those modules: they register callbacks here when the app starts
(`ModuleSpec.setup`). Callbacks run inside the caller's transaction, before the commit.
"""

import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.people.models import PersonAddress

PersonDeleted = Callable[[AsyncSession, uuid.UUID], Awaitable[None]]
AddressChanged = Callable[[AsyncSession, uuid.UUID, PersonAddress], Awaitable[None]]

_deleted: list[PersonDeleted] = []
_address_changed: list[AddressChanged] = []


def on_person_deleted(callback: PersonDeleted) -> PersonDeleted:
    """Runs when a person is deleted (ARCO cancellation), e.g. to withdraw dependent records."""
    if callback not in _deleted:
        _deleted.append(callback)
    return callback


def on_address_changed(callback: AddressChanged) -> AddressChanged:
    """Runs when a person's primary address is replaced."""
    if callback not in _address_changed:
        _address_changed.append(callback)
    return callback


async def person_deleted(db: AsyncSession, person_id: uuid.UUID) -> None:
    for callback in _deleted:
        await callback(db, person_id)


async def address_changed(db: AsyncSession, person_id: uuid.UUID, address: PersonAddress) -> None:
    for callback in _address_changed:
        await callback(db, person_id, address)
