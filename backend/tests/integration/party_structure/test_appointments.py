"""Seats and appointments (D-105, D-108): vacancies, periods, the Presídium, consecutive terms,
incompatibilities, delegations and delegated administration by level."""

import itertools
from typing import Any

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.integration.candidacies.conftest import make_curp, new_person
from tests.integration.party_structure.conftest import API, Geo

_curps = itertools.count(1)


def _curp() -> str:
    n = next(_curps)
    return make_curp(
        f"PEPE8001{(n % 28) + 1:02d}HASRRN{'0123456789ABCDEFGHJKLMNPRSTUVWXYZ'[n // 28]}"
    )


async def _person(client: AsyncClient, root: dict[str, str], *, with_curp: bool = True) -> str:
    fields = {"curp": _curp()} if with_curp else {}
    person: dict[str, Any] = await new_person(client, root, sex="H", **fields)
    return str(person["id"])


async def _body(client: AsyncClient, headers: dict[str, str], type_code: str, **params: Any) -> str:
    catalog = (await client.get(f"{API}/catalog", headers=headers)).json()
    type_id = next(b["id"] for b in catalog if b["code"] == type_code)
    bodies = (
        await client.get(
            f"{API}/bodies", headers=headers, params={"body_type_id": type_id, **params}
        )
    ).json()["items"]
    return str(bodies[0]["id"])


async def _seats(client: AsyncClient, headers: dict[str, str], body_id: str) -> dict[str, Any]:
    response = await client.get(f"{API}/bodies/{body_id}/positions", headers=headers)
    assert response.status_code == 200, response.text
    seats: dict[str, Any] = {}
    for seat in response.json():
        code = seat["position_type"]["code"]
        key = f"{code}:{seat['region_number']}" if seat["region_number"] else code
        seats[key] = seat
    return seats


async def _appoint(
    client: AsyncClient,
    headers: dict[str, str],
    seat_id: str,
    person_id: str,
    *,
    kind: str = "elected",
    starts_on: str = "2026-01-01",
    expect: int = 201,
    **extra: Any,
) -> dict[str, Any]:
    response = await client.post(
        f"{API}/positions/{seat_id}/appointments",
        headers=headers,
        json={"person_id": person_id, "kind": kind, "starts_on": starts_on, **extra},
    )
    assert response.status_code == expect, response.text
    result: dict[str, Any] = response.json()
    return result


async def _end(client: AsyncClient, headers: dict[str, str], appointment_id: str, day: str) -> None:
    response = await client.post(
        f"{API}/appointments/{appointment_id}/end",
        headers=headers,
        json={"ended_on": day, "reason": "term_end"},
    )
    assert response.status_code == 200, response.text


async def test_seats_vacancies_and_the_presidium(
    client: AsyncClient, root: dict[str, str], geo: Geo
) -> None:
    board = await _seats(client, root, await _body(client, root, "national_board"))
    assert set(board) == {
        "cdn_president",
        "cdn_sg_political_relations",
        "cdn_sg_electoral_strategy",
    }
    committee = await _seats(client, root, await _body(client, root, "national_committee"))
    assert {k for k in committee if k.startswith("cdn_circumscription_secretary")} == {
        f"cdn_circumscription_secretary:{n}" for n in range(1, 6)
    }

    president = await _person(client, root)
    appointed = await _appoint(client, root, board["cdn_president"]["id"], president)
    assert appointed["current"] is True
    assert appointed["ends_on"] == "2028-12-31"  # 3 years, editable
    assert appointed["role"]["code"] == "territorial_leader"
    occupied = await _appoint(
        client, root, board["cdn_president"]["id"], await _person(client, root), expect=409
    )
    assert "vigente" in occupied["detail"]
    await _appoint(
        client,
        root,
        board["cdn_sg_political_relations"]["id"],
        await _person(client, root, with_curp=False),
        expect=400,
    )

    presidium = await _seats(client, root, await _body(client, root, "national_presidium"))
    assert presidium["np_president"]["derived_holder"]["id"] == president
    await _appoint(client, root, presidium["np_president"]["id"], president, expect=409)
    # The vice-presidency is chosen in each period between the two general secretariats.
    vice = presidium["np_vice_president"]
    assert vice["choice_pending"] is True
    strategist = await _person(client, root)
    await _appoint(client, root, board["cdn_sg_electoral_strategy"]["id"], strategist)
    catalog = (await client.get(f"{API}/catalog", headers=root)).json()
    codes = {p["code"]: p["id"] for b in catalog for p in b["positions"]}
    chosen = await client.post(
        f"{API}/positions/{vice['id']}/derived-choice",
        headers=root,
        json={
            "source_position_type_id": codes["cdn_sg_electoral_strategy"],
            "starts_on": "2026-01-01",
        },
    )
    assert chosen.status_code == 200, chosen.text
    presidium = await _seats(client, root, await _body(client, root, "national_presidium"))
    assert presidium["np_vice_president"]["derived_holder"]["id"] == strategist
    assert presidium["np_vice_president"]["derived_from"]["code"] == "cdn_sg_electoral_strategy"
    stale = await client.post(
        f"{API}/positions/{vice['id']}/derived-choice",
        headers=root,
        json={
            "source_position_type_id": codes["cdn_sg_political_relations"],
            "starts_on": "2025-12-01",
        },
    )
    assert stale.status_code == 400
    not_an_option = await client.post(
        f"{API}/positions/{vice['id']}/derived-choice",
        headers=root,
        json={"source_position_type_id": codes["cdn_legal"], "starts_on": "2027-01-01"},
    )
    assert not_an_option.status_code == 400

    # Ending leaves the seat vacant and keeps the history.
    await _end(client, root, appointed["id"], "2026-06-30")
    board = await _seats(client, root, await _body(client, root, "national_board"))
    assert board["cdn_president"]["current"] is None
    assert board["cdn_president"]["vacant_since"] == "2026-06-30"
    successor = await _person(client, root)
    await _appoint(client, root, board["cdn_president"]["id"], successor, starts_on="2026-07-01")
    history = (
        await client.get(
            f"{API}/positions/{board['cdn_president']['id']}/appointments", headers=root
        )
    ).json()
    assert [(h["person"]["id"], h["current"]) for h in history] == [
        (successor, True),
        (president, False),
    ]
    assert history[1]["end_reason"] == "term_end"


async def test_terms_incompatibilities_and_delegates(
    client: AsyncClient, root: dict[str, str], geo: Geo
) -> None:
    causes = await _seats(client, root, await _body(client, root, "causes_coordinations"))
    seat = causes["cause_01"]["id"]
    holder, other = await _person(client, root), await _person(client, root)
    first = await _appoint(client, root, seat, holder, starts_on="2020-01-01")
    await _end(client, root, first["id"], "2022-12-31")
    second = await _appoint(client, root, seat, holder, starts_on="2023-01-01")
    await _end(client, root, second["id"], "2025-12-31")
    third = await _appoint(client, root, seat, holder, starts_on="2026-01-01", expect=409)
    assert "consecutivos" in third["detail"]
    await _appoint(client, root, seat, other, starts_on="2026-01-01")

    catalog = (await client.get(f"{API}/catalog", headers=root)).json()
    codes = {p["code"]: p["id"] for b in catalog for p in b["positions"]}
    pair = await client.post(
        f"{API}/incompatibilities",
        headers=root,
        json={"position_type_a_id": codes["cdn_legal"], "position_type_b_id": codes["cde_legal"]},
    )
    assert pair.status_code == 201
    lawyer = await _person(client, root)
    committee = await _seats(client, root, await _body(client, root, "national_committee"))
    await _appoint(client, root, committee["cdn_legal"]["id"], lawyer)
    state_committee = await _seats(
        client, root, await _body(client, root, "state_committee", state_code=1)
    )
    clash = await _appoint(client, root, state_committee["cde_legal"]["id"], lawyer, expect=409)
    assert "incompatible" in clash["detail"]

    state_board = await _seats(client, root, await _body(client, root, "state_board", state_code=1))
    delegate = await _appoint(
        client,
        root,
        state_board["ced_president"]["id"],
        await _person(client, root),
        kind="delegate",
        starts_on="2026-02-01",
    )
    assert delegate["ends_on"] == "2026-07-31"  # 6 months, extendable by editing ends_on
    extended = await client.patch(
        f"{API}/appointments/{delegate['id']}",
        headers=root,
        json={"ends_on": "2027-01-31", "agreement_ref": "CDN/030/2026"},
    )
    assert extended.status_code == 200
    assert extended.json()["ends_on"] == "2027-01-31"
    await _appoint(
        client,
        root,
        committee["cdn_strategy_communication"]["id"],
        await _person(client, root),
        kind="delegate",
        expect=400,
    )


async def test_delegated_administration_by_level(
    client: AsyncClient, root: dict[str, str], scoped: Any, geo: Geo, owner_engine: AsyncEngine
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
    assert installed.status_code == 201
    municipal = await _seats(client, root, installed.json()["id"])
    assert set(municipal) >= {"cdm_president", "cdm_legal"}
    state_committee = await _seats(
        client, root, await _body(client, root, "state_committee", state_code=1)
    )
    national = await _seats(client, root, await _body(client, root, "national_committee"))

    # Manual grant with state scope: state level, so it appoints below the state only.
    _, state_admin = await scoped(("admin",), [{"level": "state", "node_id": geo.state}])
    await _appoint(
        client, state_admin, municipal["cdm_president"]["id"], await _person(client, root)
    )
    level = await _appoint(
        client,
        state_admin,
        state_committee["cde_legal"]["id"],
        await _person(client, root),
        expect=403,
    )
    assert "nivel inferior" in level["detail"]
    await _appoint(
        client, state_admin, national["cdn_legal"]["id"], await _person(client, root), expect=403
    )
    # A municipal scope is the same level as a municipal committee.
    _, municipal_admin = await scoped(
        ("admin",), [{"level": "municipality", "node_id": geo.municipalities[1]}]
    )
    await _appoint(
        client,
        municipal_admin,
        municipal["cdm_legal"]["id"],
        await _person(client, root),
        expect=403,
    )
    # A national manual grant administers every level, national seats included.
    _, national_admin = await scoped(("admin",), [{"level": "national"}])
    await _appoint(
        client, national_admin, state_committee["cde_legal"]["id"], await _person(client, root)
    )
    await _appoint(client, national_admin, national["cdn_legal"]["id"], await _person(client, root))

    # A grant from an appointment has the level of its position (here, a state seat): it
    # appoints in the municipal committee of its state, not in its own state committee.
    holder_user, holder_headers = await scoped(("admin",), [])
    holder_appointment = (
        await client.get(
            f"{API}/positions/{state_committee['cde_legal']['id']}/appointments", headers=root
        )
    ).json()[0]
    async with owner_engine.begin() as connection:
        await connection.execute(
            text("DELETE FROM identity.user_grants WHERE user_id = :u"), {"u": holder_user.id}
        )
        grant = (
            await connection.execute(
                text(
                    "INSERT INTO identity.user_grants (user_id, role_id, origin, source_id) "
                    "SELECT :u, id, 'appointment', :a FROM identity.roles WHERE code = 'admin' "
                    "RETURNING id"
                ),
                {"u": holder_user.id, "a": holder_appointment["id"]},
            )
        ).scalar_one()
        await connection.execute(
            text(
                "INSERT INTO identity.user_grant_scopes (grant_id, scope_level, state_id) "
                "VALUES (:g, 'state', :s)"
            ),
            {"g": grant, "s": geo.state},
        )
        await connection.execute(
            text(
                "INSERT INTO identity.user_grant_sections (grant_id, section_id) "
                "SELECT :g, id FROM geography.sections WHERE state_id = :s AND is_active"
            ),
            {"g": grant, "s": geo.state},
        )
    await _appoint(
        client,
        holder_headers,
        municipal["cdm_secretary_general"]["id"],
        await _person(client, root),
    )
    await _appoint(
        client,
        holder_headers,
        state_committee["cde_causes"]["id"],
        await _person(client, root),
        expect=403,
    )

    _, viewer = await scoped(("viewer",), [{"level": "national"}])
    await _appoint(
        client,
        viewer,
        municipal["cdm_electoral_strategy"]["id"],
        await _person(client, root),
        expect=403,
    )


async def test_person_appointments_follow_the_scope(
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
    national = await _seats(client, root, await _body(client, root, "national_committee"))
    person = await _person(client, root)
    await _appoint(client, root, municipal["cdm_president"]["id"], person)
    await _appoint(client, root, national["cdn_causes"]["id"], person)

    mine = (await client.get(f"{API}/people/{person}/appointments", headers=root)).json()
    assert {a["position_type"]["code"] for a in mine} == {"cdm_president", "cdn_causes"}
    assert any(a["territory"].endswith("ESTADO DE PRUEBA") for a in mine)

    _, elsewhere = await scoped(
        ("viewer",), [{"level": "municipality", "node_id": geo.municipalities[2]}]
    )
    seen = (await client.get(f"{API}/people/{person}/appointments", headers=elsewhere)).json()
    assert [a["position_type"]["code"] for a in seen] == ["cdn_causes"]
