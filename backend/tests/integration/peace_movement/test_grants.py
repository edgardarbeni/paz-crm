"""Grants (D-101): each role's permissions apply only inside the scope of its own grant.

Municipality 1 and municipality 2 of the synthetic BGD play two different states."""

import uuid
from typing import Any

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.integration.candidacies.conftest import Geo
from tests.integration.conftest import UserFactory, token_for
from tests.integration.peace_movement.conftest import enroll

USERS = "/api/v1/users"


async def _role(
    client: AsyncClient, root: dict[str, str], code: str, permissions: list[str]
) -> str:
    response = await client.post(
        "/api/v1/roles",
        headers=root,
        json={"code": code, "name": code.title(), "permissions": permissions},
    )
    assert response.status_code == 201, response.text
    role_id: str = response.json()["id"]
    return role_id


def _municipality(geo: Geo, number: int) -> list[dict[str, Any]]:
    return [{"level": "municipality", "node_id": geo.municipalities[number]}]


async def _user_with(
    client: AsyncClient,
    root: dict[str, str],
    make_user: UserFactory,
    grants: list[tuple[str, list[dict[str, Any]]]],
) -> tuple[uuid.UUID, dict[str, str]]:
    user = await make_user()
    body = {"grants": [{"role_id": role, "scopes": scopes} for role, scopes in grants]}
    response = await client.put(f"{USERS}/{user.id}/grants", headers=root, json=body)
    assert response.status_code == 200, response.text
    return user.id, await token_for(client, user)


async def test_a_grant_does_not_lend_its_permissions_to_another_territory(  # noqa: PLR0917
    client: AsyncClient,
    root: dict[str, str],
    make_user: UserFactory,
    geo: Geo,
    levels: dict[str, str],
    notice: dict[str, Any],
) -> None:
    here = await enroll(client, root, levels, geo.sections[101])  # municipality 1
    there = await enroll(client, root, levels, geo.sections[107])  # municipality 2
    people_reader = await _role(client, root, "people_reader", ["people.person.read"])
    member_reader = await _role(client, root, "member_reader", ["peace_movement.member.read"])
    # People in municipality 1, Peace Movement members in municipality 2.
    _, headers = await _user_with(
        client,
        root,
        make_user,
        [(people_reader, _municipality(geo, 1)), (member_reader, _municipality(geo, 2))],
    )

    people = (await client.get("/api/v1/people", headers=headers)).json()["items"]
    assert here["person"]["id"] in {p["id"] for p in people}
    assert there["person"]["id"] not in {p["id"] for p in people}
    assert (
        await client.get(f"/api/v1/people/{there['person']['id']}", headers=headers)
    ).status_code == 403  # people answers 403 outside the scope (D-66)

    members = (await client.get("/api/v1/peace-movement/members", headers=headers)).json()
    assert {m["id"] for m in members["items"]} == {there["id"]}
    assert (
        await client.get(f"/api/v1/peace-movement/members/{here['id']}", headers=headers)
    ).status_code == 404


async def test_unmasking_needs_its_grant_to_cover_the_read_scope(  # noqa: PLR0917
    client: AsyncClient,
    root: dict[str, str],
    make_user: UserFactory,
    geo: Geo,
    levels: dict[str, str],
    notice: dict[str, Any],
) -> None:
    member = await enroll(client, root, levels, geo.sections[101])
    reader = await _role(client, root, "reader", ["people.person.read"])
    sensitive = await _role(
        client, root, "sensitive", ["people.person.read", "people.person.read_sensitive"]
    )
    national = [{"level": "national"}]
    # Reads the whole country, unmasks only in municipality 1: masked everywhere (conservative).
    _, wide = await _user_with(
        client, root, make_user, [(reader, national), (sensitive, _municipality(geo, 1))]
    )
    # Reads and unmasks in the same municipality: unmasked.
    _, local = await _user_with(client, root, make_user, [(sensitive, _municipality(geo, 1))])

    path = f"/api/v1/people/{member['person']['id']}"
    masked = (await client.get(path, headers=wide)).json()
    assert masked["contacts"][0]["value"] == "******4567"
    clear = (await client.get(path, headers=local)).json()
    assert clear["contacts"][0]["value"] == "4491234567"


async def test_grants_api(
    client: AsyncClient,
    root: dict[str, str],
    make_user: UserFactory,
    geo: Geo,
    owner_engine: AsyncEngine,
) -> None:
    user = await make_user(roles=("viewer",))
    [grant] = (await client.get(f"{USERS}/{user.id}/grants", headers=root)).json()
    assert grant["origin"] == "manual"
    assert grant["scopes"] == []

    kept = await client.put(
        f"{USERS}/{user.id}/grants",
        headers=root,
        json={
            "grants": [
                {"id": grant["id"], "role_id": grant["role"]["id"], "scopes": _municipality(geo, 1)}
            ]
        },
    )
    assert kept.status_code == 200, kept.text
    [changed] = kept.json()
    assert changed["id"] == grant["id"]
    assert [s["level"] for s in changed["scopes"]] == ["municipality"]

    other_role = await _role(client, root, "other", ["people.person.read"])
    for body, expected in (
        ({"id": grant["id"], "role_id": other_role, "scopes": []}, 400),  # a grant keeps its role
        ({"id": str(uuid.uuid4()), "role_id": other_role, "scopes": []}, 400),
        ({"role_id": other_role, "scopes": [{"level": "national"}, *_municipality(geo, 1)]}, 400),
    ):
        response = await client.put(
            f"{USERS}/{user.id}/grants", headers=root, json={"grants": [body]}
        )
        assert response.status_code == expected, body

    # Grants that come from an appointment are not replaced here (D-104).
    async with owner_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO identity.user_grants (user_id, role_id, origin, source_id) "
                "VALUES (:u, :r, 'appointment', :s)"
            ),
            {"u": user.id, "r": other_role, "s": uuid.uuid4()},
        )
    cleared = await client.put(f"{USERS}/{user.id}/grants", headers=root, json={"grants": []})
    assert cleared.status_code == 200, cleared.text
    assert [g["origin"] for g in cleared.json()] == ["appointment"]
    appointment_id = cleared.json()[0]["id"]
    touched = await client.put(
        f"{USERS}/{user.id}/grants",
        headers=root,
        json={"grants": [{"id": appointment_id, "role_id": other_role, "scopes": []}]},
    )
    assert touched.status_code == 400


async def test_anti_escalation_is_per_permission(
    client: AsyncClient, root: dict[str, str], make_user: UserFactory, geo: Geo
) -> None:
    manager = await _role(
        client,
        root,
        "manager",
        [
            "identity.user.read",
            "identity.user.assign_roles",
            "identity.user.assign_scopes",
            "people.person.read",
        ],
    )
    reader = await _role(client, root, "reader", ["people.person.read"])
    # Manages users in municipality 1; reads people in the whole country.
    _, headers = await _user_with(
        client,
        root,
        make_user,
        [(manager, _municipality(geo, 1)), (reader, [{"level": "national"}])],
    )
    target = await make_user()

    async def put(grants: list[dict[str, Any]]) -> int:
        response = await client.put(
            f"{USERS}/{target.id}/grants", headers=headers, json={"grants": grants}
        )
        return response.status_code

    # The identity permissions of `manager` only reach municipality 1.
    assert await put([{"role_id": manager, "scopes": _municipality(geo, 2)}]) == 403
    # people.person.read reaches the whole country, so `reader` may be handed out nationally.
    assert (
        await put(
            [
                {"role_id": manager, "scopes": _municipality(geo, 1)},
                {"role_id": reader, "scopes": [{"level": "national"}]},
            ]
        )
        == 200
    )
