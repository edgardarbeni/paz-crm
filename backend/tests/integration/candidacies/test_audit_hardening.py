"""Audit hardening (D-89, D-90, D-93): Core writes now audited, personal data masked in the
immutable log, sensitive reads logged, and the audit viewers limited by the reader's scope."""

from datetime import date, timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.db.session import build_sessionmaker
from app.modules.people.service import purge_due
from tests.integration.candidacies.conftest import Geo, make_curp, new_person
from tests.integration.geography.conftest import rows, scalar

CURP = make_curp("AAXJ900101MASSXN0")


async def _actions(engine: AsyncEngine, table: str, person_id: str) -> list[str]:
    found = await rows(
        engine,
        f"SELECT a.action FROM audit.audit_log a JOIN people.{table} t ON a.entity_id = t.id::text "
        f"WHERE a.entity_table = 'people.{table}' AND t.person_id = :p ORDER BY a.chain_seq",
        p=person_id,
    )
    return [row["action"] for row in found]


async def test_person_writes_are_audited_without_personal_data(
    client: AsyncClient, root: dict[str, str], geo: Geo, owner_engine: AsyncEngine
) -> None:
    person = await new_person(
        client,
        root,
        given_names="Juana Inés",
        paternal_surname="Asbaje",
        curp=CURP,
        contacts=[{"contact_type": "mobile", "value": "4491112233"}],
        address={"postal_code": "20100", "section_id": geo.sections[101]},
    )
    updated = await client.patch(
        f"/api/v1/people/{person['id']}",
        headers=root,
        json={
            "paternal_surname": "Ramírez",
            "contacts": [{"contact_type": "mobile", "value": "4494445566"}],
            "address": {"section_id": geo.sections[104]},
        },
    )
    assert updated.status_code == 200, updated.text
    # The replaced contact and address are soft-deleted through the ORM, so they are audited.
    for table in ("person_contacts", "person_addresses"):
        actions = await _actions(owner_engine, table, person["id"])
        assert sorted(actions) == ["create", "create", "soft_delete"]

    assert (await client.delete(f"/api/v1/people/{person['id']}", headers=root)).status_code == 200
    async with build_sessionmaker(owner_engine)() as db:
        assert await purge_due(db, today=date.today() + timedelta(days=31)) == 1
    # Physical deletes of the purge are audited too (contacts, addresses).
    deleted = await scalar(
        owner_engine,
        "SELECT count(*) FROM audit.audit_log WHERE action = 'delete' "
        "AND entity_table IN ('people.person_contacts', 'people.person_addresses')",
    )
    assert deleted == 4

    log = await scalar(
        owner_engine,
        "SELECT string_agg(coalesce(before::text, '') || coalesce(after::text, ''), ' ') "
        "FROM audit.audit_log WHERE entity_table LIKE 'people.%'",
    )
    for value in ("Juana", "Asbaje", "Ramírez", "1990-01-01", "20100", CURP, "4491112233"):
        assert value not in log


async def test_person_detail_reads_are_logged(
    client: AsyncClient, root: dict[str, str], scoped: Any, geo: Geo, owner_engine: AsyncEngine
) -> None:
    person = await new_person(client, root)
    viewer_user, viewer = await scoped(("viewer",), [{"level": "national"}])
    assert (await client.get(f"/api/v1/people/{person['id']}", headers=root)).status_code == 200
    assert (await client.get(f"/api/v1/people/{person['id']}", headers=viewer)).status_code == 200
    reads = await rows(
        owner_engine,
        "SELECT actor_user_id::text AS actor, details FROM audit.access_log "
        "WHERE entity_table = 'people.persons' AND entity_id = :p ORDER BY occurred_at",
        p=person["id"],
    )
    assert [r["details"] for r in reads] == [{"unmasked": True}, {"unmasked": False}]
    assert reads[1]["actor"] == str(viewer_user.id)


async def test_scope_removal_is_audited(
    client: AsyncClient, root: dict[str, str], scoped: Any, geo: Geo, owner_engine: AsyncEngine
) -> None:
    user, _ = await scoped(("viewer",), [{"level": "state", "node_id": geo.state}])
    replaced = await client.put(
        f"/api/v1/users/{user.id}/scopes",
        headers=root,
        json={"scopes": [{"level": "municipality", "node_id": geo.municipalities[1]}]},
    )
    assert replaced.status_code == 200, replaced.text
    removed = await rows(
        owner_engine,
        "SELECT before FROM audit.audit_log WHERE entity_table = 'identity.user_scopes' "
        "AND action = 'delete' AND before->>'user_id' = :u",
        u=str(user.id),
    )
    assert [r["before"]["scope_level"] for r in removed] == ["state"]


async def test_audit_viewers_are_limited_by_scope(
    client: AsyncClient, root: dict[str, str], scoped: Any, geo: Geo
) -> None:
    admin_user, admin = await scoped(("admin",), [{"level": "state", "node_id": geo.state}])
    managed_user, managed = await scoped(
        ("capturist",), [{"level": "municipality", "node_id": geo.municipalities[1]}]
    )
    national_user, national = await scoped(("capturist",), [{"level": "national"}])
    mine = await new_person(client, admin)
    theirs = await new_person(client, managed)
    outsider = await new_person(client, national)
    from_root = await new_person(client, root)
    for headers, person in ((admin, mine), (managed, theirs), (national, outsider)):
        assert (await client.get(f"/api/v1/people/{person['id']}", headers=headers)).is_success

    async def ids(path: str, headers: dict[str, str]) -> set[str]:
        page = await client.get(
            f"/api/v1/audit-log{path}",
            headers=headers,
            params={"entity_table": "people.persons", "limit": 200},
        )
        assert page.status_code == 200, page.text
        return {item["entity_id"] for item in page.json()["items"]}

    expected = {mine["id"], theirs["id"]}
    assert await ids("", admin) == expected
    assert await ids("/access", admin) == expected
    everything = {mine["id"], theirs["id"], outsider["id"], from_root["id"]}
    assert await ids("", root) >= everything
    assert {admin_user.id, managed_user.id, national_user.id}  # three distinct actors

    # Without the permission, neither viewer is reachable.
    for path in ("", "/access"):
        assert (await client.get(f"/api/v1/audit-log{path}", headers=managed)).status_code == 403
