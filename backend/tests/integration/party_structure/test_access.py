"""Access to the system from appointments (D-104): the person's account, invitation, the grant
with the seat's territory, sticky TOTP, revocation and the daily expiry."""

from collections.abc import Callable
from datetime import date
from typing import Any

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.mail import MemoryMailer
from app.modules.party_structure.access import expire_due
from tests.integration.conftest import UserFactory, token_for
from tests.integration.geography.conftest import scalar
from tests.integration.party_structure.conftest import API, Geo
from tests.integration.party_structure.test_appointments import (
    _appoint,
    _body,
    _person,
    _seats,
)


async def _state_seats(client: AsyncClient, root: dict[str, str]) -> dict[str, Any]:
    return await _seats(client, root, await _body(client, root, "state_committee", state_code=1))


async def test_appointing_with_access_invites_the_person(
    client: AsyncClient,
    root: dict[str, str],
    geo: Geo,
    mailer: MemoryMailer,
    owner_engine: AsyncEngine,
) -> None:
    seats = await _state_seats(client, root)
    person = await _person(client, root)
    appointed = await _appoint(
        client,
        root,
        seats["cde_legal"]["id"],
        person,
        access={"email": "directora.juridica@example.com"},
    )
    assert appointed["access_pending"] is None
    assert appointed["has_access"] is True
    user_id = appointed["user_id"]
    assert mailer.outbox[-1].to == "directora.juridica@example.com"
    assert await scalar(
        owner_engine, "SELECT mfa_required FROM identity.users WHERE id = :u", u=user_id
    )
    [grant] = (await client.get(f"/api/v1/users/{user_id}/grants", headers=root)).json()
    assert grant["origin"] == "appointment"
    assert grant["source_id"] == appointed["id"]
    assert grant["role"]["code"] == "territorial_leader"
    assert grant["scopes"] == [
        {"id": grant["scopes"][0]["id"], "level": "state", "node_id": geo.state}
    ]

    # A second position reuses the account: one grant per appointment, no new invitation.
    sent = len(mailer.outbox)
    national = await _seats(client, root, await _body(client, root, "national_committee"))
    second = await _appoint(client, root, national["cdn_causes"]["id"], person, access={})
    assert second["user_id"] == user_id
    assert len(mailer.outbox) == sent
    grants = (await client.get(f"/api/v1/users/{user_id}/grants", headers=root)).json()
    assert {g["scopes"][0]["level"] for g in grants} == {"state", "national"}
    # Manual grant administration does not touch them.
    cleared = await client.put(f"/api/v1/users/{user_id}/grants", headers=root, json={"grants": []})
    assert len(cleared.json()) == 2

    # An e-mail that already belongs to another person's account is refused.
    other = await _appoint(client, root, seats["cde_causes"]["id"], await _person(client, root))
    taken = await client.post(
        f"{API}/appointments/{other['id']}/access",
        headers=root,
        json={"email": "directora.juridica@example.com"},
    )
    assert taken.status_code == 409
    no_email = await client.post(f"{API}/appointments/{other['id']}/access", headers=root, json={})
    assert no_email.status_code == 400
    twice = await client.post(f"{API}/appointments/{appointed['id']}/access", headers=root, json={})
    assert twice.status_code == 409


async def test_ending_revokes_only_that_access(
    client: AsyncClient, root: dict[str, str], geo: Geo, make_user: UserFactory
) -> None:
    account = await make_user(with_totp=True)
    person = await _person(client, root)
    seats = await _state_seats(client, root)
    national = await _seats(client, root, await _body(client, root, "national_committee"))
    first = await _appoint(
        client, root, seats["cde_legal"]["id"], person, access={"email": account.email}
    )
    assert first["user_id"] == str(account.id)  # an existing account is linked, not re-created
    second = await _appoint(client, root, national["cdn_causes"]["id"], person, access={})
    headers = await token_for(client, account)
    assert (await client.get(f"{API}/bodies", headers=headers)).status_code == 200

    ended = await client.post(
        f"{API}/appointments/{first['id']}/end",
        headers=root,
        json={"ended_on": "2026-06-30", "reason": "resignation"},
    )
    assert ended.json()["has_access"] is False
    # The other position keeps the account working: the session is not closed.
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200
    grants = (await client.get(f"/api/v1/users/{account.id}/grants", headers=root)).json()
    assert [g["source_id"] for g in grants] == [second["id"]]

    revoked = await client.delete(f"{API}/appointments/{second['id']}/access", headers=root)
    assert revoked.status_code == 200
    assert revoked.json()["current"] is True  # the position stands, without access
    # No grant left: its sessions are closed.
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401


async def test_access_needs_its_own_permission_and_no_escalation(
    client: AsyncClient, root: dict[str, str], scoped: Any, geo: Geo
) -> None:
    catalog = (await client.get(f"{API}/catalog", headers=root)).json()
    municipal_type = next(b["id"] for b in catalog if b["code"] == "municipal_committee")
    installed = await client.post(
        f"{API}/bodies",
        headers=root,
        json={
            "body_type_id": municipal_type,
            "municipality_id": geo.municipalities[1],
            "installed_on": "2026-01-01",
            "installation_agreement": "CDN/001/2026",
        },
    )
    municipal = await _seats(client, root, installed.json()["id"])

    # A coordinator appoints but cannot grant access: the appointment stands, access pending.
    _, coordinator = await scoped(("coordinator",), [{"level": "state", "node_id": geo.state}])
    pending = await _appoint(
        client,
        coordinator,
        municipal["cdm_president"]["id"],
        await _person(client, root),
        access={"email": "presidencia@example.com"},
    )
    assert pending["has_access"] is False
    assert "permiso" in pending["access_pending"]

    # An admin cannot hand out, through an appointment, a role with powers they lack.
    powerful = await client.post(
        "/api/v1/roles",
        headers=root,
        json={"code": "test_powerful", "name": "Poderoso", "permissions": ["identity.role.delete"]},
    )
    _, admin = await scoped(("admin",), [{"level": "state", "node_id": geo.state}])
    refused = await _appoint(
        client,
        admin,
        municipal["cdm_legal"]["id"],
        await _person(client, root),
        access={"email": "juridico@example.com", "role_id": powerful.json()["id"]},
    )
    assert refused["has_access"] is False
    assert refused["access_pending"]
    granted = await client.post(
        f"{API}/appointments/{refused['id']}/access",
        headers=admin,
        json={"email": "juridico@example.com"},
    )
    assert granted.status_code == 200, granted.text
    assert granted.json()["has_access"] is True


async def test_daily_expiry(
    client: AsyncClient,
    root: dict[str, str],
    geo: Geo,
    db_session: Callable[[], AsyncSession],
    owner_engine: AsyncEngine,
) -> None:
    seats = await _state_seats(client, root)
    expired = await _appoint(
        client,
        root,
        seats["cde_legal"]["id"],
        await _person(client, root),
        starts_on="2020-01-01",
        ends_on="2022-12-31",
        access={"email": "vencida@example.com"},
    )
    current = await _appoint(
        client, root, seats["cde_causes"]["id"], await _person(client, root), starts_on="2026-01-01"
    )
    async with db_session() as db:
        assert await expire_due(db, date(2026, 10, 30)) == 1
    history = (
        await client.get(f"{API}/positions/{seats['cde_legal']['id']}/appointments", headers=root)
    ).json()
    assert history[0]["id"] == expired["id"]
    assert history[0]["ended_on"] == "2022-12-31"
    assert history[0]["end_reason"] == "term_end"
    assert history[0]["has_access"] is False
    assert (
        await scalar(
            owner_engine,
            "SELECT count(*) FROM identity.user_grants WHERE source_id = :a",
            a=expired["id"],
        )
        == 0
    )
    seats = await _state_seats(client, root)
    assert seats["cde_legal"]["vacant_since"] == "2022-12-31"
    assert seats["cde_causes"]["current"]["id"] == current["id"]
    async with owner_engine.connect() as connection:
        assert (
            await connection.execute(text("SELECT count(*) FROM party_structure.person_accounts"))
        ).scalar_one() == 1  # the account stays linked to the person
