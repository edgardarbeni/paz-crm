"""Catalogs and electoral-process configuration (D-21..D-28)."""

from typing import Any

from httpx import AsyncClient

from tests.integration.candidacies.conftest import Geo

API = "/api/v1"


async def offices_by_code(client: AsyncClient, headers: dict[str, str]) -> dict[str, str]:
    response = await client.get(f"{API}/office-types", headers=headers)
    assert response.status_code == 200, response.text
    return {o["code"]: o["id"] for o in response.json()}


async def create_local_process(client: AsyncClient, headers: dict[str, str], geo: Geo) -> str:
    response = await client.post(
        f"{API}/processes",
        headers=headers,
        json={
            "name": "Proceso local 2027",
            "election_year": 2027,
            "election_level": "local",
            "state_id": geo.state,
        },
    )
    assert response.status_code == 201, response.text
    process_id: str = response.json()["id"]
    return process_id


async def test_process_starts_disabled_with_default_rules(
    client: AsyncClient, root: dict[str, str], geo: Geo
) -> None:
    process_id = await create_local_process(client, root, geo)
    offices = (await client.get(f"{API}/processes/{process_id}/offices", headers=root)).json()
    assert {o["office_code"] for o in offices} == {
        "municipal_president", "syndic", "councilor_mr", "councilor_rp", "mayor",
        "council_member", "local_deputy_mr", "local_deputy_rp", "governor",
    }  # fmt: skip
    assert not any(o["is_enabled"] for o in offices)
    rules = (await client.get(f"{API}/processes/{process_id}/rules", headers=root)).json()
    assert {r["rule_code"]: r["is_enabled"] for r in rules} == {
        "unique_person_in_process": True,
        "substitute_same_sex": False,
        "list_alternation": False,
        "gender_parity": False,
    }
    parity = next(r for r in rules if r["rule_code"] == "gender_parity")
    assert parity["effective_params"] == {"min_female_ratio": 0.5}

    listed = (await client.get(f"{API}/processes", headers=root)).json()
    assert [p["id"] for p in listed] == [process_id]
    patched = await client.patch(
        f"{API}/processes/{process_id}", headers=root, json={"status": "active"}
    )
    assert patched.json()["status"] == "active"


async def test_process_validation_and_permissions(
    client: AsyncClient, root: dict[str, str], scoped: Any, geo: Geo
) -> None:
    base = {"name": "Proceso", "election_year": 2027}
    no_state = await client.post(
        f"{API}/processes", headers=root, json={**base, "election_level": "local"}
    )
    assert no_state.status_code == 400
    federal_with_state = await client.post(
        f"{API}/processes",
        headers=root,
        json={**base, "election_level": "federal", "state_id": geo.state},
    )
    assert federal_with_state.status_code == 400
    _, capturist = await scoped(("capturist",), [{"level": "national"}])
    forbidden = await client.post(
        f"{API}/processes",
        headers=capturist,
        json={**base, "election_level": "local", "state_id": geo.state},
    )
    assert forbidden.status_code == 403
    assert (await client.get(f"{API}/processes", headers=capturist)).status_code == 200
    missing = await client.get(f"{API}/processes/{geo.state}", headers=root)
    assert missing.status_code == 404


async def test_configure_offices(client: AsyncClient, root: dict[str, str], geo: Geo) -> None:
    process_id = await create_local_process(client, root, geo)
    ids = await offices_by_code(client, root)
    url = f"{API}/processes/{process_id}/offices"

    async def put(items: list[dict[str, Any]]) -> Any:
        return await client.put(url, headers=root, json=items)

    member_alone = await put([{"office_type_id": ids["councilor_mr"], "is_enabled": True}])
    assert member_alone.status_code == 400
    federal = await put([{"office_type_id": ids["president"], "is_enabled": True}])
    assert federal.status_code == 400
    bad_parent = await put(
        [
            {
                "office_type_id": ids["syndic"],
                "is_enabled": True,
                "slate_parent_office_type_id": ids["governor"],
            }
        ]
    )
    assert bad_parent.status_code == 400
    rp_on_mr = await put(
        [{"office_type_id": ids["local_deputy_mr"], "is_enabled": True, "rp_method": "mixed"}]
    )
    assert rp_on_mr.status_code == 400

    ok = await put(
        [
            {"office_type_id": ids["municipal_president"], "is_enabled": True},
            {
                "office_type_id": ids["syndic"],
                "is_enabled": True,
                "slate_parent_office_type_id": ids["municipal_president"],
            },
            {
                "office_type_id": ids["local_deputy_rp"],
                "is_enabled": True,
                "positions": 4,
                "rp_method": "closed_list",
            },
        ]
    )
    assert ok.status_code == 200, ok.text
    enabled = {o["office_code"]: o for o in ok.json() if o["is_enabled"]}
    assert set(enabled) == {"municipal_president", "syndic", "local_deputy_rp"}
    assert enabled["local_deputy_rp"]["positions"] == 4


async def test_municipalities_rules_and_coalitions(
    client: AsyncClient, root: dict[str, str], scoped: Any, geo: Geo
) -> None:
    process_id = await create_local_process(client, root, geo)
    url = f"{API}/processes/{process_id}/municipalities"
    settings: list[dict[str, Any]] = [
        {
            "municipality_id": geo.municipalities[1],
            "mr_councilor_count": 7,
            "rp_councilor_count": 4,
            "syndic_count": 1,
        },
        {"municipality_id": geo.municipalities[2], "election_regime": "normative_system"},
    ]
    response = await client.put(url, headers=root, json=settings)
    assert response.status_code == 200, response.text
    # Upsert: sending again updates instead of duplicating.
    settings[0]["mr_councilor_count"] = 9
    response = await client.put(url, headers=root, json=settings[:1])
    assert sorted(s["mr_councilor_count"] for s in response.json()) == [0, 9]
    foreign = await client.put(url, headers=root, json=[{"municipality_id": geo.state}])
    assert foreign.status_code == 400
    assert len((await client.get(url, headers=root)).json()) == 2

    rules_url = f"{API}/processes/{process_id}/rules"
    unknown = await client.put(
        rules_url,
        headers=root,
        json=[{"rule_code": "gender_parity", "is_enabled": True, "params": {"x": 1}}],
    )
    assert unknown.status_code == 400
    missing = await client.put(
        rules_url, headers=root, json=[{"rule_code": "does_not_exist", "is_enabled": True}]
    )
    assert missing.status_code == 400
    ids = await offices_by_code(client, root)
    rules = await client.put(
        rules_url,
        headers=root,
        json=[
            {"rule_code": "gender_parity", "is_enabled": True, "params": {"min_female_ratio": 0.6}},
            {
                "rule_code": "list_alternation",
                "is_enabled": True,
                "severity": "warning",
                "office_type_id": ids["local_deputy_rp"],
            },
        ],
    )
    assert rules.status_code == 200, rules.text
    by_code = {(r["rule_code"], r["office_type_id"]): r for r in rules.json()}
    assert by_code["gender_parity", None]["effective_params"] == {"min_female_ratio": 0.6}
    assert by_code["list_alternation", ids["local_deputy_rp"]]["severity"] == "warning"

    party = await client.post(
        f"{API}/parties", headers=root, json={"acronym": "OTRO", "name": "Otro partido"}
    )
    assert party.status_code == 201, party.text
    duplicate = await client.post(
        f"{API}/parties", headers=root, json={"acronym": "OTRO", "name": "Repetido"}
    )
    assert duplicate.status_code == 409
    parties = {
        p["acronym"]: p["id"] for p in (await client.get(f"{API}/parties", headers=root)).json()
    }
    renamed = await client.put(
        f"{API}/parties/{parties['OTRO']}",
        headers=root,
        json={"acronym": "OTRO", "name": "Otro partido renombrado", "color_hex": "#112233"},
    )
    assert renamed.json()["color_hex"] == "#112233"
    coalition = await client.post(
        f"{API}/processes/{process_id}/coalitions",
        headers=root,
        json={"name": "Juntos", "party_ids": [parties["PAZ"], parties["OTRO"]]},
    )
    assert coalition.status_code == 201, coalition.text
    assert set(coalition.json()["party_ids"]) == {parties["PAZ"], parties["OTRO"]}
    listed = (await client.get(f"{API}/processes/{process_id}/coalitions", headers=root)).json()
    assert [c["name"] for c in listed] == ["Juntos"]
    bad = await client.post(
        f"{API}/processes/{process_id}/coalitions",
        headers=root,
        json={"name": "Fantasma", "party_ids": [parties["PAZ"], geo.state]},
    )
    assert bad.status_code == 400


async def test_office_types_are_data(
    client: AsyncClient, root: dict[str, str], scoped: Any, geo: Geo
) -> None:
    body = {
        "code": "presidencia_comunidad",
        "name": "Presidencia de comunidad",
        "election_level": "local",
        "geographic_level": "municipality",
        "principle": "mr",
        "nomination_kind": "single",
    }
    _, viewer = await scoped(("viewer",), [{"level": "national"}])
    assert (await client.post(f"{API}/office-types", headers=viewer, json=body)).status_code == 403
    created = await client.post(f"{API}/office-types", headers=root, json=body)
    assert created.status_code == 201, created.text
    assert (await client.post(f"{API}/office-types", headers=root, json=body)).status_code == 409
    # Available to new processes without any migration.
    process_id = await create_local_process(client, root, geo)
    offices = (await client.get(f"{API}/processes/{process_id}/offices", headers=root)).json()
    assert "presidencia_comunidad" in {o["office_code"] for o in offices}
    rules = (await client.get(f"{API}/validation-rules", headers=viewer)).json()
    assert len(rules) == 4
