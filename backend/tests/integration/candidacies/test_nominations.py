"""Nominations and formulas (D-27..D-29): composition, business rules with overrides, status
transitions, substitutions with history and the read-vs-edit geographic scope (D-34)."""

from dataclasses import dataclass
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.integration.candidacies.conftest import Geo, new_person
from tests.integration.candidacies.test_processes import create_local_process, offices_by_code
from tests.integration.geography.conftest import scalar

API = "/api/v1"
REASON = "Acuerdo de la comisión"


@dataclass
class Setup:
    process: str
    offices: dict[str, str]
    paz: str


@pytest.fixture
async def setup(client: AsyncClient, root: dict[str, str], geo: Geo) -> Setup:
    process = await create_local_process(client, root, geo)
    ids = await offices_by_code(client, root)

    def member(code: str) -> dict[str, Any]:
        return {
            "office_type_id": ids[code],
            "is_enabled": True,
            "slate_parent_office_type_id": ids["municipal_president"],
        }

    configured = await client.put(
        f"{API}/processes/{process}/offices",
        headers=root,
        json=[
            {"office_type_id": ids["municipal_president"], "is_enabled": True},
            member("syndic"),
            member("councilor_mr"),
            member("councilor_rp"),
            {"office_type_id": ids["local_deputy_mr"], "is_enabled": True},
            {
                "office_type_id": ids["local_deputy_rp"],
                "is_enabled": True,
                "positions": 4,
                "rp_method": "closed_list",
            },
        ],
    )
    assert configured.status_code == 200, configured.text
    municipalities = await client.put(
        f"{API}/processes/{process}/municipalities",
        headers=root,
        json=[
            {
                "municipality_id": geo.municipalities[1],
                "syndic_count": 1,
                "mr_councilor_count": 2,
                "rp_councilor_count": 1,
            },
            {"municipality_id": geo.municipalities[2], "election_regime": "normative_system"},
        ],
    )
    assert municipalities.status_code == 200, municipalities.text
    parties = (await client.get(f"{API}/parties", headers=root)).json()
    paz = next(p["id"] for p in parties if p["acronym"] == "PAZ")
    return Setup(process=process, offices=ids, paz=paz)


async def nominate(
    client: AsyncClient, headers: dict[str, str], setup: Setup, office: str, node: str | None
) -> Response:
    return await client.post(
        f"{API}/nominations",
        headers=headers,
        json={
            "process_id": setup.process,
            "office_type_id": setup.offices[office],
            "node_id": node,
            "party_id": setup.paz,
        },
    )


async def add_formula(  # noqa: PLR0917
    client: AsyncClient,
    headers: dict[str, str],
    nomination: str,
    office_type_id: str,
    position: int,
    owner: str,
    substitute: str | None,
    **extra: Any,
) -> Response:
    return await client.post(
        f"{API}/nominations/{nomination}/formulas",
        headers=headers,
        json={
            "office_type_id": office_type_id,
            "position": position,
            "owner_person_id": owner,
            "substitute_person_id": substitute,
            **extra,
        },
    )


async def pair(client: AsyncClient, headers: dict[str, str], sex: str = "M") -> tuple[str, str]:
    owner = await new_person(client, headers, sex=sex)
    substitute = await new_person(client, headers, sex=sex)
    return owner["id"], substitute["id"]


async def set_rules(
    client: AsyncClient, setup: Setup, root: dict[str, str], rules: list[Any]
) -> None:
    response = await client.put(f"{API}/processes/{setup.process}/rules", headers=root, json=rules)
    assert response.status_code == 200, response.text


# --- composition ----------------------------------------------------------------------------


async def test_slate_composition_and_creation_checks(
    client: AsyncClient, root: dict[str, str], geo: Geo, setup: Setup
) -> None:
    created = await nominate(client, root, setup, "municipal_president", geo.municipalities[1])
    assert created.status_code == 201, created.text
    nomination = created.json()
    slots = {s["office_code"]: s["expected"] for s in nomination["slots"]}
    assert slots == {"municipal_president": 1, "syndic": 1, "councilor_mr": 2, "councilor_rp": 1}
    assert nomination["complete"] is False
    assert nomination["editable"] is True
    assert nomination["node_id"] == geo.municipalities[1]

    duplicate = await nominate(client, root, setup, "municipal_president", geo.municipalities[1])
    assert duplicate.status_code == 409
    normative = await nominate(client, root, setup, "municipal_president", geo.municipalities[2])
    assert normative.status_code == 409
    wrong_level = await nominate(client, root, setup, "municipal_president", geo.local_districts[1])
    assert wrong_level.status_code == 400
    not_enabled = await nominate(client, root, setup, "governor", geo.state)
    assert not_enabled.status_code == 400
    inside_slate = await nominate(client, root, setup, "syndic", geo.municipalities[1])
    assert inside_slate.status_code == 400
    member_kind = await nominate(client, root, setup, "councilor_mr", geo.municipalities[1])
    assert member_kind.status_code == 400
    no_node = await nominate(client, root, setup, "local_deputy_mr", None)
    assert no_node.status_code == 400
    two_nominators = await client.post(
        f"{API}/nominations",
        headers=root,
        json={
            "process_id": setup.process,
            "office_type_id": setup.offices["local_deputy_mr"],
            "node_id": geo.local_districts[1],
        },
    )
    assert two_nominators.status_code == 400

    rp_list = await nominate(client, root, setup, "local_deputy_rp", geo.state)
    assert rp_list.status_code == 201, rp_list.text
    assert [s["expected"] for s in rp_list.json()["slots"]] == [4]

    listed = (await client.get(f"{API}/nominations", headers=root)).json()["items"]
    assert len(listed) == 2
    filtered = await client.get(
        f"{API}/nominations",
        headers=root,
        params={"office_type_id": setup.offices["local_deputy_rp"], "status": "draft"},
    )
    assert [n["id"] for n in filtered.json()["items"]] == [rp_list.json()["id"]]
    notes = await client.patch(
        f"{API}/nominations/{nomination['id']}", headers=root, json={"notes": "Planilla A"}
    )
    assert notes.json()["notes"] == "Planilla A"


async def test_formula_checks(
    client: AsyncClient, root: dict[str, str], geo: Geo, setup: Setup
) -> None:
    nomination = (await nominate(client, root, setup, "local_deputy_rp", geo.state)).json()["id"]
    office = setup.offices["local_deputy_rp"]
    owner, substitute = await pair(client, root)

    assert (
        await add_formula(client, root, nomination, office, 5, owner, substitute)
    ).status_code == 400
    assert (await add_formula(client, root, nomination, office, 1, owner, owner)).status_code == 400
    assert (await add_formula(client, root, nomination, office, 1, owner, None)).status_code == 400
    other_office = setup.offices["governor"]
    assert (
        await add_formula(client, root, nomination, other_office, 1, owner, substitute)
    ).status_code == 400
    ghost = await add_formula(client, root, nomination, office, 1, owner, setup.paz)
    assert ghost.status_code == 400
    origin = await add_formula(
        client, root, nomination, office, 1, owner, substitute, origin_party_id=setup.paz
    )
    assert origin.status_code == 400  # origin party only applies to coalitions

    created = await add_formula(client, root, nomination, office, 1, owner, substitute)
    assert created.status_code == 201, created.text
    formula = created.json()["formulas"][0]
    assert formula["owner"]["person_id"] == owner
    assert formula["substitute"]["person_id"] == substitute
    assert formula["status"] == "aspirant"
    another_owner, another_substitute = await pair(client, root)
    taken = await add_formula(
        client, root, nomination, office, 1, another_owner, another_substitute
    )
    assert taken.status_code == 409

    # Members are editable while aspirant.
    edited = await client.patch(
        f"{API}/formulas/{formula['id']}",
        headers=root,
        json={"substitute_person_id": another_substitute},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["formulas"][0]["substitute"]["person_id"] == another_substitute


async def test_unique_person_rule_and_override(  # noqa: PLR0917
    client: AsyncClient,
    root: dict[str, str],
    scoped: Any,
    geo: Geo,
    setup: Setup,
    owner_engine: AsyncEngine,
) -> None:
    nomination = (await nominate(client, root, setup, "local_deputy_rp", geo.state)).json()["id"]
    office = setup.offices["local_deputy_rp"]
    owner, substitute = await pair(client, root)
    assert (
        await add_formula(client, root, nomination, office, 1, owner, substitute)
    ).status_code == 201
    _, other = await pair(client, root)

    blocked = await add_formula(client, root, nomination, office, 2, owner, other)
    assert blocked.status_code == 409
    problem = blocked.json()
    assert problem["code"] == "rule-violation"
    # Both formulas sharing the person are reported (and later accepted together).
    assert [v["rule"] for v in problem["violations"]] == ["unique_person_in_process"] * 2

    override = {"rules": ["unique_person_in_process"], "reason": REASON}
    _, capturist = await scoped(("capturist",), [{"level": "national"}])
    refused = await add_formula(
        client, capturist, nomination, office, 2, owner, other, override=override
    )
    assert refused.status_code == 403
    partial = await add_formula(
        client,
        root,
        nomination,
        office,
        2,
        owner,
        other,
        override={"rules": ["gender_parity"], "reason": REASON},
    )
    assert partial.status_code == 409
    _, coordinator = await scoped(("coordinator",), [{"level": "national"}])
    accepted = await add_formula(
        client, coordinator, nomination, office, 2, owner, other, override=override
    )
    assert accepted.status_code == 201, accepted.text
    recorded = await scalar(
        owner_engine,
        "SELECT string_agg(DISTINCT reason, ',') || ':' || count(*) "
        "FROM candidacies.rule_overrides WHERE nomination_id = :n",
        n=nomination,
    )
    assert recorded == f"{REASON}:2"
    # Accepted violations are no longer reported as pending.
    assert accepted.json()["warnings"] == []

    # The person cannot be deleted while in an active formula.
    deleted = await client.delete(f"{API}/people/{owner}", headers=root)
    assert deleted.status_code == 409


async def test_configurable_rules_block_or_warn(
    client: AsyncClient, root: dict[str, str], geo: Geo, setup: Setup
) -> None:
    office = setup.offices["local_deputy_rp"]
    await set_rules(
        client,
        setup,
        root,
        [
            {"rule_code": "substitute_same_sex", "is_enabled": True},
            {
                "rule_code": "list_alternation",
                "is_enabled": True,
                "severity": "warning",
                "office_type_id": office,
            },
        ],
    )
    nomination = (await nominate(client, root, setup, "local_deputy_rp", geo.state)).json()["id"]
    woman = (await new_person(client, root, sex="M"))["id"]
    man = (await new_person(client, root, sex="H"))["id"]
    mixed = await add_formula(client, root, nomination, office, 1, woman, man)
    assert mixed.status_code == 409
    assert mixed.json()["violations"][0]["rule"] == "substitute_same_sex"

    first = await pair(client, root, "M")
    assert (await add_formula(client, root, nomination, office, 1, *first)).status_code == 201
    second = await pair(client, root, "M")
    warned = await add_formula(client, root, nomination, office, 2, *second)
    assert warned.status_code == 201, warned.text
    assert [w["rule"] for w in warned.json()["warnings"]] == ["list_alternation"]

    # Office-specific config can switch a process-wide rule off.
    await set_rules(
        client,
        setup,
        root,
        [{"rule_code": "substitute_same_sex", "is_enabled": False, "office_type_id": office}],
    )
    third_owner = (await new_person(client, root, sex="H"))["id"]
    third_substitute = (await new_person(client, root, sex="M"))["id"]
    allowed = await add_formula(client, root, nomination, office, 3, third_owner, third_substitute)
    assert allowed.status_code == 201, allowed.text


# --- lifecycle ------------------------------------------------------------------------------


async def _fill_slate(
    client: AsyncClient,
    headers: dict[str, str],
    setup: Setup,
    nomination: dict[str, Any],
    head_sex: str,
) -> None:
    for slot in nomination["slots"]:
        for position in slot["missing_positions"]:
            sex = head_sex if slot["office_code"] == "municipal_president" else "M"
            response = await add_formula(
                client,
                headers,
                nomination["id"],
                slot["office_type_id"],
                position,
                *await pair(client, headers, sex),
            )
            assert response.status_code == 201, response.text


async def test_submit_parity_transitions_and_substitution(  # noqa: PLR0915
    client: AsyncClient, root: dict[str, str], scoped: Any, geo: Geo, setup: Setup
) -> None:
    await set_rules(client, setup, root, [{"rule_code": "gender_parity", "is_enabled": True}])
    nomination = (
        await nominate(client, root, setup, "municipal_president", geo.municipalities[1])
    ).json()
    url = f"{API}/nominations/{nomination['id']}"

    incomplete = await client.post(f"{url}/submit", headers=root, json={})
    assert incomplete.status_code == 409
    await _fill_slate(client, root, setup, nomination, head_sex="H")
    detail = (await client.get(url, headers=root)).json()
    assert detail["complete"] is True

    dry_run = (await client.get(f"{url}/validation", headers=root)).json()
    assert [v["rule"] for v in dry_run] == ["gender_parity"]
    parity = await client.post(f"{url}/submit", headers=root, json={})
    assert parity.status_code == 409
    assert parity.json()["violations"][0]["rule"] == "gender_parity"
    submitted = await client.post(
        f"{url}/submit",
        headers=root,
        json={"override": {"rules": ["gender_parity"], "reason": REASON}},
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "submitted"

    # After submission, formulas change only through transitions and substitutions.
    head = next(
        f for f in submitted.json()["formulas"] if f["office_code"] == "municipal_president"
    )
    owner, substitute = await pair(client, root)
    office = setup.offices["municipal_president"]
    assert (
        await add_formula(client, root, nomination["id"], office, 1, owner, substitute)
    ).status_code == 409
    frozen = await client.patch(
        f"{API}/formulas/{head['id']}", headers=root, json={"owner_person_id": owner}
    )
    assert frozen.status_code == 409

    _, capturist = await scoped(("capturist",), [{"level": "national"}])
    _, coordinator = await scoped(("coordinator",), [{"level": "national"}])
    status_url = f"{API}/formulas/{head['id']}/status"
    skip = await client.post(status_url, headers=coordinator, json={"to_status": "approved"})
    assert skip.status_code == 409
    registered = await client.post(status_url, headers=capturist, json={"to_status": "registered"})
    assert registered.status_code == 200, registered.text
    refused = await client.post(status_url, headers=capturist, json={"to_status": "approved"})
    assert refused.status_code == 403
    approved = await client.post(status_url, headers=coordinator, json={"to_status": "approved"})
    assert approved.status_code == 200

    substitution = {"owner_person_id": owner, "reason": "Renuncia de la propietaria"}
    sub_url = f"{API}/formulas/{head['id']}/substitute"
    assert (await client.post(sub_url, headers=capturist, json=substitution)).status_code == 403
    same = await client.post(sub_url, headers=coordinator, json={"reason": "Sin cambios reales"})
    assert same.status_code == 400
    replaced = await client.post(sub_url, headers=coordinator, json=substitution)
    assert replaced.status_code == 200, replaced.text
    new_head = next(
        f for f in replaced.json()["formulas"] if f["office_code"] == "municipal_president"
    )
    assert new_head["replaces_formula_id"] == head["id"]
    assert new_head["status"] == "approved"
    assert new_head["owner"]["person_id"] == owner
    assert (await client.post(sub_url, headers=coordinator, json=substitution)).status_code == 409

    history = (await client.get(f"{url}/history", headers=root)).json()
    head_history = [
        (h["from_status"], h["to_status"]) for h in history if h["formula_id"] == head["id"]
    ]
    assert head_history == [
        (None, "aspirant"),
        ("aspirant", "registered"),
        ("registered", "approved"),
        ("approved", "substituted"),
    ]
    assert any(h["formula_id"] == new_head["id"] and h["to_status"] == "approved" for h in history)

    assert (await client.post(f"{url}/approve", headers=capturist, json={})).status_code == 403
    approved_nomination = await client.post(f"{url}/approve", headers=coordinator, json={})
    assert approved_nomination.status_code == 200, approved_nomination.text
    assert approved_nomination.json()["status"] == "approved"

    no_reason = await client.post(
        f"{API}/formulas/{new_head['id']}/status",
        headers=coordinator,
        json={"to_status": "cancelled"},
    )
    assert no_reason.status_code == 400
    assert (await client.post(f"{url}/cancel", headers=capturist, json={})).status_code == 403
    cancelled = await client.post(
        f"{url}/cancel", headers=coordinator, json={"reason": "Retiro de la planilla"}
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["formulas"] == []
    # A cancelled nomination frees the geography for a new one.
    again = await nominate(client, root, setup, "municipal_president", geo.municipalities[1])
    assert again.status_code == 201, again.text


async def test_closed_process_is_read_only(
    client: AsyncClient, root: dict[str, str], geo: Geo, setup: Setup
) -> None:
    nomination = (
        await nominate(client, root, setup, "local_deputy_mr", geo.local_districts[1])
    ).json()
    await client.patch(f"{API}/processes/{setup.process}", headers=root, json={"status": "closed"})
    owner, substitute = await pair(client, root)
    closed = await add_formula(
        client, root, nomination["id"], setup.offices["local_deputy_mr"], 1, owner, substitute
    )
    assert closed.status_code == 409
    assert (
        await nominate(client, root, setup, "local_deputy_mr", geo.local_districts[2])
    ).status_code == 409
    assert (
        await client.get(f"{API}/nominations/{nomination['id']}", headers=root)
    ).status_code == 200


# --- geographic scope -----------------------------------------------------------------------


async def test_scope_read_vs_edit(
    client: AsyncClient, root: dict[str, str], scoped: Any, geo: Geo, setup: Setup
) -> None:
    _, coordinator = await scoped(
        ("coordinator",), [{"level": "municipality", "node_id": geo.municipalities[1]}]
    )
    own = await nominate(client, coordinator, setup, "municipal_president", geo.municipalities[1])
    assert own.status_code == 201, own.text
    # Local district 1 also covers sections of municipality 2 → outside the scope to create.
    assert (
        await nominate(client, coordinator, setup, "local_deputy_mr", geo.local_districts[1])
    ).status_code == 403
    assert (
        await nominate(client, coordinator, setup, "local_deputy_rp", geo.state)
    ).status_code == 403

    shared = (await nominate(client, root, setup, "local_deputy_mr", geo.local_districts[1])).json()
    foreign = (
        await nominate(client, root, setup, "local_deputy_mr", geo.local_districts[2])
    ).json()

    visible = {
        n["id"]
        for n in (await client.get(f"{API}/nominations", headers=coordinator)).json()["items"]
    }
    assert visible == {own.json()["id"], shared["id"]}
    readonly = await client.get(f"{API}/nominations/{shared['id']}", headers=coordinator)
    assert readonly.status_code == 200
    assert readonly.json()["editable"] is False
    owner, substitute = await pair(client, coordinator)
    edit = await add_formula(
        client, coordinator, shared["id"], setup.offices["local_deputy_mr"], 1, owner, substitute
    )
    assert edit.status_code == 403
    assert (
        await client.get(f"{API}/nominations/{foreign['id']}", headers=coordinator)
    ).status_code == 404
    assert (
        await client.get(f"{API}/nominations/{foreign['id']}/history", headers=coordinator)
    ).status_code == 404

    _, viewer = await scoped(("viewer",), [{"level": "national"}])
    assert (
        await nominate(client, viewer, setup, "local_deputy_mr", geo.local_districts[2])
    ).status_code == 403
    assert len((await client.get(f"{API}/nominations", headers=viewer)).json()["items"]) == 3


async def test_coalition_nomination_with_origin_party(
    client: AsyncClient, root: dict[str, str], geo: Geo, setup: Setup
) -> None:
    other = (
        await client.post(f"{API}/parties", headers=root, json={"acronym": "ALI", "name": "Aliado"})
    ).json()["id"]
    outsider = (
        await client.post(f"{API}/parties", headers=root, json={"acronym": "AJE", "name": "Ajeno"})
    ).json()["id"]
    coalition = (
        await client.post(
            f"{API}/processes/{setup.process}/coalitions",
            headers=root,
            json={"name": "Alianza", "party_ids": [setup.paz, other]},
        )
    ).json()["id"]
    response = await client.post(
        f"{API}/nominations",
        headers=root,
        json={
            "process_id": setup.process,
            "office_type_id": setup.offices["local_deputy_mr"],
            "node_id": geo.local_districts[2],
            "coalition_id": coalition,
        },
    )
    assert response.status_code == 201, response.text
    nomination = response.json()
    assert nomination["coalition_id"] == coalition
    office = setup.offices["local_deputy_mr"]
    owner, substitute = await pair(client, root)
    foreign = await add_formula(
        client, root, nomination["id"], office, 1, owner, substitute, origin_party_id=outsider
    )
    assert foreign.status_code == 400
    created = await add_formula(
        client, root, nomination["id"], office, 1, owner, substitute, origin_party_id=other
    )
    assert created.status_code == 201, created.text
    assert created.json()["formulas"][0]["origin_party_id"] == other


async def test_national_nominations_need_national_scope(
    client: AsyncClient, root: dict[str, str], scoped: Any, geo: Geo
) -> None:
    process = await client.post(
        f"{API}/processes",
        headers=root,
        json={"name": "Federal 2030", "election_year": 2030, "election_level": "federal"},
    )
    assert process.status_code == 201, process.text
    ids = await offices_by_code(client, root)
    configured = await client.put(
        f"{API}/processes/{process.json()['id']}/offices",
        headers=root,
        json=[{"office_type_id": ids["president"], "is_enabled": True}],
    )
    assert configured.status_code == 200, configured.text
    paz = next(
        p["id"]
        for p in (await client.get(f"{API}/parties", headers=root)).json()
        if p["acronym"] == "PAZ"
    )
    body = {"process_id": process.json()["id"], "office_type_id": ids["president"], "party_id": paz}
    _, coordinator = await scoped(("coordinator",), [{"level": "state", "node_id": geo.state}])
    assert (
        await client.post(f"{API}/nominations", headers=coordinator, json=body)
    ).status_code == 403
    created = await client.post(f"{API}/nominations", headers=root, json=body)
    assert created.status_code == 201, created.text
    assert created.json()["geographic_level"] == "national"
    assert created.json()["node_id"] is None
    # A state-scoped user reads it (it covers their sections) but cannot edit it.
    readonly = await client.get(f"{API}/nominations/{created.json()['id']}", headers=coordinator)
    assert readonly.json()["editable"] is False
