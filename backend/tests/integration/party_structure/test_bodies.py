"""Installed bodies (D-107): seeded national and state bodies, installation and dissolution of
district and municipal committees, and the geographic scope (D-34, D-101). The synthetic BGD has
one state (code 1) with municipalities 1 and 2 and federal and local districts 1 and 2."""

from typing import Any

from httpx import AsyncClient

from tests.integration.party_structure.conftest import API, Geo


async def _types(client: AsyncClient, headers: dict[str, str]) -> dict[str, str]:
    catalog = (await client.get(f"{API}/catalog", headers=headers)).json()
    return {body["code"]: body["id"] for body in catalog}


async def _bodies(
    client: AsyncClient, headers: dict[str, str], **params: Any
) -> list[dict[str, Any]]:
    response = await client.get(f"{API}/bodies", headers=headers, params={"limit": 200, **params})
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


async def test_seeded_bodies_and_scope(
    client: AsyncClient, root: dict[str, str], scoped: Any, geo: Geo
) -> None:
    assert len(await _bodies(client, root, level="national")) == 10
    state_one = await _bodies(client, root, state_code=1)
    assert len(state_one) == 5
    assert {b["territory"] for b in state_one} == {"ESTADO DE PRUEBA"}
    assert len(await _bodies(client, root, level="state")) == 160

    # Scoped to municipality 1: national bodies and those of its state, not other states'.
    _, viewer = await scoped(
        ("viewer",), [{"level": "municipality", "node_id": geo.municipalities[1]}]
    )
    visible = await _bodies(client, viewer)
    assert len([b for b in visible if b["state_code"] is None]) == 10
    assert {b["state_code"] for b in visible if b["state_code"]} == {1}
    assert await _bodies(client, viewer, state_code=2) == []
    other_state = (await _bodies(client, root, state_code=2))[0]
    assert (
        await client.get(f"{API}/bodies/{other_state['id']}", headers=viewer)
    ).status_code == 404


async def test_install_and_dissolve_committees(
    client: AsyncClient, root: dict[str, str], scoped: Any, geo: Geo
) -> None:
    types = await _types(client, root)
    _, local = await scoped(
        ("coordinator",), [{"level": "municipality", "node_id": geo.municipalities[1]}]
    )

    async def install(headers: dict[str, str], **body: Any) -> Any:
        return await client.post(
            f"{API}/bodies",
            headers=headers,
            json={"installed_on": "2026-10-01", "installation_agreement": "CDN/001/2026", **body},
        )

    municipal = await install(
        local, body_type_id=types["municipal_committee"], municipality_id=geo.municipalities[1]
    )
    assert municipal.status_code == 201, municipal.text
    assert municipal.json()["status"] == "installed"
    assert municipal.json()["state_code"] == 1
    assert municipal.json()["territory"].endswith(", ESTADO DE PRUEBA")

    again = await install(
        local, body_type_id=types["municipal_committee"], municipality_id=geo.municipalities[1]
    )
    assert again.status_code == 409
    outside = await install(
        local, body_type_id=types["municipal_committee"], municipality_id=geo.municipalities[2]
    )
    assert outside.status_code == 403
    # Federal district 1 spans both municipalities: wider than the municipal scope.
    wide = await install(
        local,
        body_type_id=types["district_committee"],
        federal_district_id=geo.federal_districts[1],
    )
    assert wide.status_code == 403
    mismatched = await install(
        root,
        body_type_id=types["municipal_committee"],
        federal_district_id=geo.federal_districts[1],
    )
    assert mismatched.status_code == 400
    not_installable = await install(root, body_type_id=types["state_board"])
    assert not_installable.status_code == 400
    district = await install(
        root, body_type_id=types["district_committee"], local_district_id=geo.local_districts[1]
    )
    assert district.status_code == 201, district.text
    assert district.json()["district_kind"] == "local"
    assert district.json()["territory"].startswith("Distrito local 1")

    # Someone scoped elsewhere does not see the municipal committee.
    _, elsewhere = await scoped(
        ("viewer",), [{"level": "municipality", "node_id": geo.municipalities[2]}]
    )
    body_id = municipal.json()["id"]
    assert (await client.get(f"{API}/bodies/{body_id}", headers=elsewhere)).status_code == 404
    assert (await client.get(f"{API}/bodies/{body_id}", headers=local)).status_code == 200

    early = await client.post(
        f"{API}/bodies/{body_id}/dissolve",
        headers=local,
        json={"dissolved_on": "2026-09-01", "dissolution_agreement": "CDN/002/2026"},
    )
    assert early.status_code == 400
    dissolved = await client.post(
        f"{API}/bodies/{body_id}/dissolve",
        headers=local,
        json={"dissolved_on": "2026-10-15", "dissolution_agreement": "CDN/002/2026"},
    )
    assert dissolved.status_code == 200, dissolved.text
    assert dissolved.json()["status"] == "dissolved"
    twice = await client.post(
        f"{API}/bodies/{body_id}/dissolve",
        headers=local,
        json={"dissolved_on": "2026-10-16", "dissolution_agreement": "CDN/003/2026"},
    )
    assert twice.status_code == 409
    state_body = (await _bodies(client, root, state_code=1))[0]
    permanent = await client.post(
        f"{API}/bodies/{state_body['id']}/dissolve",
        headers=root,
        json={"dissolved_on": "2026-10-16", "dissolution_agreement": "CDN/004/2026"},
    )
    assert permanent.status_code == 409

    current = await _bodies(client, root, level="municipal")
    assert current == []
    history = await _bodies(client, root, level="municipal", include_dissolved=True)
    assert [b["id"] for b in history] == [body_id]
    # A dissolved committee can be installed again.
    reinstalled = await install(
        local, body_type_id=types["municipal_committee"], municipality_id=geo.municipalities[1]
    )
    assert reinstalled.status_code == 201, reinstalled.text

    _, viewer = await scoped(("viewer",), [{"level": "national"}])
    denied = await install(
        viewer, body_type_id=types["municipal_committee"], municipality_id=geo.municipalities[2]
    )
    assert denied.status_code == 403
