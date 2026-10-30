"""Statutory catalog (D-105, D-107): the seed transcribed from cargos_paz.md and its management."""

from typing import Any

from httpx import AsyncClient

from tests.integration.party_structure.conftest import API


async def _catalog(client: AsyncClient, headers: dict[str, str]) -> dict[str, dict[str, Any]]:
    response = await client.get(f"{API}/catalog", headers=headers)
    assert response.status_code == 200, response.text
    return {body["code"]: body for body in response.json()}


def _positions(catalog: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {p["code"]: p for body in catalog.values() for p in body["positions"]}


async def test_seed_follows_the_statute(client: AsyncClient, root: dict[str, str]) -> None:
    catalog = await _catalog(client, root)
    assert len(catalog) == 17
    levels = {code: body["territorial_level"] for code, body in catalog.items()}
    assert sorted(levels.values()).count("national") == 10
    assert sorted(levels.values()).count("state") == 5
    assert catalog["district_committee"]["requires_installation"] is True
    assert catalog["municipal_committee"]["requires_installation"] is True
    assert catalog["state_board"]["requires_installation"] is False

    positions = _positions(catalog)
    assert len(positions) == 88
    circumscription = positions["cdn_circumscription_secretary"]
    assert circumscription["scope_rule"] == "circumscription"
    assert circumscription["statutory_basis"] == "Arts. 30, 36, 42, 70 y 83"

    causes = [p for code, p in positions.items() if code.startswith("cause_")]
    assert len(causes) == 22
    assert {p["max_consecutive_terms"] for p in causes} == {2}
    assert positions["cause_01"]["statutory_basis"] == "Art. 94 fracc. I y 95"

    # Presídium: derived from its source positions; the national vice-presidency is chosen in
    # each period among the two general secretariats (D-105).
    vice = positions["np_vice_president"]
    assert vice["is_derived"] is True
    assert {s["code"] for s in vice["derived_from"]} == {
        "cdn_sg_political_relations",
        "cdn_sg_electoral_strategy",
    }
    assert [s["code"] for s in positions["sp_vice_president"]["derived_from"]] == [
        "ced_sg_electoral_strategy"
    ]
    derived = [p for p in positions.values() if p["is_derived"]]
    assert len(derived) == 6
    assert all(p["default_role"] is None for p in derived)
    assert {p["default_role"]["code"] for p in positions.values() if not p["is_derived"]} == {
        "territorial_leader"
    }

    coordination = (await client.get(f"{API}/coordination-position-types", headers=root)).json()
    assert {(c["kind"], c["code"]) for c in coordination} == {
        ("federal", "coordinator"),
        ("local", "coordinator"),
        ("sectional", "coordinator"),
    }
    assert {c["default_role"]["code"] for c in coordination} == {"territorial_coordinator"}
    assert (await client.get(f"{API}/incompatibilities", headers=root)).json() == []


async def test_catalog_management(client: AsyncClient, root: dict[str, str], scoped: Any) -> None:
    created = await client.post(
        f"{API}/body-types",
        headers=root,
        json={"code": "test_board", "name": "Junta de prueba", "territorial_level": "state"},
    )
    assert created.status_code == 201, created.text
    body_type_id = created.json()["id"]
    duplicate = await client.post(
        f"{API}/body-types",
        headers=root,
        json={"code": "test_board", "name": "Otra", "territorial_level": "state"},
    )
    assert duplicate.status_code == 409

    positions = _positions(await _catalog(client, root))
    position = await client.post(
        f"{API}/position-types",
        headers=root,
        json={
            "body_type_id": body_type_id,
            "code": "test_secretary",
            "name": "Secretaría de prueba",
            "term_years": 3,
            "default_role_id": positions["cdn_legal"]["default_role"]["id"],
        },
    )
    assert position.status_code == 201, position.text
    assert position.json()["default_role"]["code"] == "territorial_leader"
    derived_of_derived = await client.post(
        f"{API}/position-types",
        headers=root,
        json={
            "body_type_id": body_type_id,
            "code": "test_derived",
            "name": "Derivado",
            "derived_from": [positions["np_president"]["id"]],
        },
    )
    assert derived_of_derived.status_code == 400
    derived = await client.post(
        f"{API}/position-types",
        headers=root,
        json={
            "body_type_id": body_type_id,
            "code": "test_derived",
            "name": "Derivado",
            "derived_from": [position.json()["id"]],
            "default_role_id": positions["cdn_legal"]["default_role"]["id"],
        },
    )
    assert derived.status_code == 201, derived.text
    assert derived.json()["is_derived"] is True
    assert derived.json()["default_role"] is None  # derived positions grant no access

    edited = await client.patch(
        f"{API}/position-types/{position.json()['id']}",
        headers=root,
        json={"name": "Secretaría de prueba editada", "term_years": 2, "default_role_id": None},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["default_role"] is None

    a, b = positions["cdn_legal"]["id"], positions["cde_legal"]["id"]
    added = await client.post(
        f"{API}/incompatibilities",
        headers=root,
        json={"position_type_a_id": b, "position_type_b_id": a, "notes": "Prueba"},
    )
    assert added.status_code == 201, added.text
    pair = {added.json()["position_type_a"]["code"], added.json()["position_type_b"]["code"]}
    assert pair == {"cdn_legal", "cde_legal"}
    again = await client.post(
        f"{API}/incompatibilities",
        headers=root,
        json={"position_type_a_id": a, "position_type_b_id": b},
    )
    assert again.status_code == 409
    itself = await client.post(
        f"{API}/incompatibilities",
        headers=root,
        json={"position_type_a_id": a, "position_type_b_id": a},
    )
    assert itself.status_code == 400
    removed = await client.delete(f"{API}/incompatibilities/{added.json()['id']}", headers=root)
    assert removed.status_code == 204
    assert (await client.get(f"{API}/incompatibilities", headers=root)).json() == []

    coordination = await client.post(
        f"{API}/coordination-position-types",
        headers=root,
        json={"kind": "sectional", "code": "test_liaison", "name": "Enlace seccional"},
    )
    assert coordination.status_code == 201, coordination.text

    # Reading the catalog is not managing it.
    _, viewer = await scoped(("viewer",), [{"level": "national"}])
    assert (await client.get(f"{API}/catalog", headers=viewer)).status_code == 200
    denied = await client.post(
        f"{API}/body-types",
        headers=viewer,
        json={"code": "test_x", "name": "X", "territorial_level": "state"},
    )
    assert denied.status_code == 403
    _, nobody = await scoped((), [{"level": "national"}])
    assert (await client.get(f"{API}/catalog", headers=nobody)).status_code == 403


async def test_default_role_needs_its_permissions(
    client: AsyncClient, root: dict[str, str], scoped: Any
) -> None:
    """An admin cannot make a position hand out a role with permissions they lack (D-52)."""
    role = await client.post(
        "/api/v1/roles",
        headers=root,
        json={"code": "test_powerful", "name": "Poderoso", "permissions": ["identity.role.delete"]},
    )
    assert role.status_code == 201, role.text
    _, admin = await scoped(("admin",), [{"level": "national"}])
    catalog = await _catalog(client, root)
    response = await client.post(
        f"{API}/position-types",
        headers=admin,
        json={
            "body_type_id": catalog["state_board"]["id"],
            "code": "test_escalation",
            "name": "Escalamiento",
            "default_role_id": role.json()["id"],
        },
    )
    assert response.status_code == 403
