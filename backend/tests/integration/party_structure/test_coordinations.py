"""Territorial coordinations (D-110): territory, exclusivity, scope and level, holders whose
grants follow the territory, and closing. The synthetic BGD has one state; municipality 1 has
sections 101, 102, 105 and 106, municipality 2 has 103, 104, 107 and 108."""

from typing import Any

import pytest
from httpx import AsyncClient

from app.modules.party_structure.coordinations import UnprocessableError, _ensure_one_state
from app.modules.party_structure.models import CoordinationKind
from tests.integration.party_structure.conftest import API, Geo
from tests.integration.party_structure.test_appointments import _appoint, _person, _seats


async def _create(
    client: AsyncClient,
    headers: dict[str, str],
    kind: str,
    nodes: list[str],
    *,
    name: str = "Coordinación Centro",
    expect: int = 201,
) -> dict[str, Any]:
    response = await client.post(
        f"{API}/coordinations",
        headers=headers,
        json={"kind": kind, "name": name, "node_ids": nodes, "created_on": "2026-01-01"},
    )
    assert response.status_code == expect, response.text
    result: dict[str, Any] = response.json()
    return result


async def _territory(
    client: AsyncClient, headers: dict[str, str], coordination_id: str, nodes: list[str], **kw: Any
) -> Any:
    return await client.put(
        f"{API}/coordinations/{coordination_id}/territory",
        headers=headers,
        json={"node_ids": nodes, "on": "2026-06-01", **kw},
    )


def test_local_and_sectional_coordinations_stay_in_one_state() -> None:
    _ensure_one_state(CoordinationKind.FEDERAL, {1, 2})  # federal: any states
    for kind in (CoordinationKind.LOCAL, CoordinationKind.SECTIONAL):
        _ensure_one_state(kind, {1})
        with pytest.raises(UnprocessableError):
            _ensure_one_state(kind, {1, 2})


async def test_territory_exclusivity_and_closing(
    client: AsyncClient, root: dict[str, str], geo: Geo
) -> None:
    sections = geo.sections
    centro = await _create(client, root, "sectional", [sections[101], sections[102]])
    assert centro["state_code"] == 1
    assert [t["label"] for t in centro["territory"]] == [
        "Sección 101, ESTADO DE PRUEBA",
        "Sección 102, ESTADO DE PRUEBA",
    ]
    seats = await _seats(client, root, centro["id"])
    assert set(seats) == {"sectional_coordinator"}

    taken = await _create(client, root, "sectional", [sections[102]], name="Otra", expect=409)
    assert "otra coordinación" in taken["detail"]
    # A different kind does not compete for the same territory.
    await _create(client, root, "local", [geo.local_districts[1]], name="Local 1")
    await _create(client, root, "federal", [geo.federal_districts[1]], name="Federal 1")
    wrong_kind = await _create(client, root, "local", [sections[105]], name="Equis", expect=400)
    assert "no existe" in wrong_kind["detail"]

    moved = await _territory(client, root, centro["id"], [sections[101], sections[105]])
    assert moved.status_code == 200, moved.text
    assert {t["id"] for t in moved.json()["territory"]} == {sections[101], sections[105]}
    norte = await _create(client, root, "sectional", [sections[102]], name="Norte")

    # Closing needs no current appointments, and frees the territory.
    holder = await _appoint(
        client, root, seats["sectional_coordinator"]["id"], await _person(client, root)
    )
    busy = await client.post(
        f"{API}/coordinations/{centro['id']}/close",
        headers=root,
        json={"closed_on": "2026-07-01"},
    )
    assert busy.status_code == 409
    ended = await client.post(
        f"{API}/appointments/{holder['id']}/end",
        headers=root,
        json={"ended_on": "2026-06-30", "reason": "other"},
    )
    assert ended.status_code == 200
    closed = await client.post(
        f"{API}/coordinations/{centro['id']}/close",
        headers=root,
        json={"closed_on": "2026-07-01", "agreement": "Acuerdo de cierre"},
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "closed"
    assert closed.json()["territory"] == []
    await _create(client, root, "sectional", [sections[101]], name="Centro nueva")

    listed = (
        await client.get(f"{API}/coordinations", headers=root, params={"kind": "sectional"})
    ).json()["items"]
    assert {c["name"] for c in listed} == {"Norte", "Centro nueva"}
    history = (
        await client.get(
            f"{API}/coordinations",
            headers=root,
            params={"kind": "sectional", "include_closed": True},
        )
    ).json()["items"]
    assert len(history) == 3
    assert norte["id"] in {c["id"] for c in history}


async def test_scope_and_level(
    client: AsyncClient, root: dict[str, str], scoped: Any, geo: Geo
) -> None:
    sections = geo.sections
    _, municipal = await scoped(
        ("coordinator",), [{"level": "municipality", "node_id": geo.municipalities[1]}]
    )
    mine = await _create(client, municipal, "sectional", [sections[101]])
    await _create(client, municipal, "sectional", [sections[103]], name="Ajena", expect=403)
    outside = await _territory(client, municipal, mine["id"], [sections[101], sections[104]])
    assert outside.status_code == 403
    # A section scope is the coordinations' own level: it manages none of them.
    _, sectional = await scoped(("coordinator",), [{"level": "section", "node_id": sections[106]}])
    await _create(client, sectional, "sectional", [sections[106]], name="Mía", expect=403)

    # Federal district 1 spans both municipalities: wider than the municipal scope.
    await _create(
        client, municipal, "federal", [geo.federal_districts[1]], name="Federal", expect=403
    )

    _, elsewhere = await scoped(
        ("viewer",), [{"level": "municipality", "node_id": geo.municipalities[2]}]
    )
    assert (
        await client.get(f"{API}/coordinations/{mine['id']}", headers=elsewhere)
    ).status_code == 404
    assert (await client.get(f"{API}/coordinations", headers=elsewhere)).json()["items"] == []
    _, viewer = await scoped(
        ("viewer",), [{"level": "municipality", "node_id": geo.municipalities[1]}]
    )
    assert (
        await client.get(f"{API}/coordinations/{mine['id']}", headers=viewer)
    ).status_code == 200
    await _create(client, viewer, "sectional", [sections[102]], name="Visor", expect=403)


async def test_holders_follow_the_territory(
    client: AsyncClient, root: dict[str, str], geo: Geo
) -> None:
    sections = geo.sections
    centro = await _create(client, root, "sectional", [sections[101], sections[102]])
    seat = (await _seats(client, root, centro["id"]))["sectional_coordinator"]
    appointed = await _appoint(
        client,
        root,
        seat["id"],
        await _person(client, root),
        access={"email": "coordinador@example.com"},
    )
    assert appointed["has_access"] is True
    assert appointed["role"]["code"] == "territorial_coordinator"

    async def grant_sections() -> set[str]:
        [grant] = (
            await client.get(f"/api/v1/users/{appointed['user_id']}/grants", headers=root)
        ).json()
        assert {s["level"] for s in grant["scopes"]} == {"section"}
        return {s["node_id"] for s in grant["scopes"]}

    assert await grant_sections() == {sections[101], sections[102]}
    changed = await _territory(client, root, centro["id"], [sections[102], sections[105]])
    assert changed.status_code == 200
    assert await grant_sections() == {sections[102], sections[105]}
