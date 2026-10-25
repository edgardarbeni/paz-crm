"""People (D-30, D-31): validated CURP, encryption with blind indexes, masking by permission,
geographic visibility and ARCO deletion."""

from datetime import date, timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.db.session import build_sessionmaker
from app.modules.people.service import purge_due
from tests.integration.candidacies.conftest import Geo, make_curp, new_person
from tests.integration.geography.conftest import rows, scalar

CURP = make_curp("GOME850315MASRRN0")  # 1985-03-15, woman, Aguascalientes


async def test_create_encrypts_and_masks(
    client: AsyncClient, root: dict[str, str], scoped: Any, geo: Geo, owner_engine: AsyncEngine
) -> None:
    response = await client.post(
        "/api/v1/people",
        headers=root,
        json={
            "given_names": "María José",
            "paternal_surname": "Gómez",
            "maternal_surname": "Martínez",
            "curp": CURP.lower(),
            "contacts": [
                {"contact_type": "mobile", "value": "+52 449 123 4567", "is_primary": True},
                {"contact_type": "email", "value": "Maria@Example.com"},
            ],
            "address": {
                "street": "Av. Siempre Viva",
                "exterior_number": "742",
                "postal_code": "20000",
                "state_id": geo.state,
                "municipality_id": geo.municipalities[1],
                "section_id": geo.sections[101],
            },
        },
    )
    assert response.status_code == 201, response.text
    person = response.json()
    # Derived from the CURP when not captured.
    assert (person["birth_date"], person["sex"], person["birth_entity"]) == (
        "1985-03-15",
        "M",
        "AS",
    )
    assert person["curp"] == CURP
    assert person["full_name"] == "María José Gómez Martínez"
    assert {c["value"] for c in person["contacts"]} == {"4491234567", "maria@example.com"}
    assert person["addresses"][0]["street"] == "Av. Siempre Viva"

    stored = (
        await rows(
            owner_engine,
            "SELECT p.curp_ciphertext, p.curp_hash, c.value_ciphertext FROM people.persons p "
            "JOIN people.person_contacts c ON c.person_id = p.id WHERE p.id = :id",
            id=person["id"],
        )
    )[0]
    assert CURP.encode() not in bytes(stored["curp_ciphertext"])
    assert b"4491234567" not in bytes(stored["value_ciphertext"])
    assert len(bytes(stored["curp_hash"])) == 32
    audit = await scalar(
        owner_engine,
        "SELECT string_agg(coalesce(after::text, ''), ' ') FROM audit.audit_log "
        "WHERE entity_table LIKE 'people.%'",
    )
    assert audit
    assert "4491234567" not in audit
    assert CURP not in audit

    _, viewer = await scoped(("viewer",), [{"level": "national"}])
    masked = (await client.get(f"/api/v1/people/{person['id']}", headers=viewer)).json()
    assert masked["curp"] == CURP[:4] + "******" + CURP[10:]
    assert {c["value"] for c in masked["contacts"]} == {"******4567", "m***@example.com"}
    assert masked["addresses"][0]["street"] is None
    assert masked["addresses"][0]["section_id"] == geo.sections[101]


async def test_curp_validation_and_uniqueness(
    client: AsyncClient, root: dict[str, str], scoped: Any, geo: Geo
) -> None:
    bad = await client.post(
        "/api/v1/people",
        headers=root,
        json={"given_names": "A", "paternal_surname": "B", "curp": CURP[:17] + "X"},
    )
    assert bad.status_code == 400
    assert bad.json()["code"] == "invalid-curp"

    await new_person(client, root, curp=CURP)
    duplicate = await client.post(
        "/api/v1/people",
        headers=root,
        json={"given_names": "Otra", "paternal_surname": "Persona", "curp": CURP},
    )
    assert duplicate.status_code == 409

    # Incoherent with captured data: capturists cannot force it, coordinators can.
    other = make_curp("LOPJ900101HASRRN0")
    body = {"given_names": "Juan", "paternal_surname": "López", "sex": "M", "curp": other}
    _, capturist = await scoped(("capturist",), [{"level": "national"}])
    refused = await client.post(
        "/api/v1/people", headers=capturist, json={**body, "accept_curp_incoherence": True}
    )
    assert refused.status_code == 409
    assert refused.json()["code"] == "curp-incoherent"
    _, coordinator = await scoped(("coordinator",), [{"level": "national"}])
    forced = await client.post(
        "/api/v1/people", headers=coordinator, json={**body, "accept_curp_incoherence": True}
    )
    assert forced.status_code == 201, forced.text
    assert forced.json()["curp_coherence_overridden"] is True
    assert forced.json()["warnings"]

    # Editing a field against the stored CURP is checked too.
    person = await new_person(client, root, sex="H", curp=make_curp("RUIP900101HASRRN0"))
    changed = await client.patch(
        f"/api/v1/people/{person['id']}",
        headers=root,
        json={"birth_date": "1990-01-02", "accept_curp_incoherence": True},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["warnings"]
    refused_edit = await client.patch(
        f"/api/v1/people/{person['id']}",
        headers=capturist,
        json={"birth_date": "1990-01-03", "accept_curp_incoherence": True},
    )
    assert refused_edit.status_code == 409


async def test_search(client: AsyncClient, root: dict[str, str], geo: Geo) -> None:
    target = await new_person(
        client,
        root,
        given_names="Ángela",
        paternal_surname="Núñez",
        curp=CURP,
        contacts=[{"contact_type": "mobile", "value": "4497654321"}],
    )
    await new_person(client, root, given_names="Pedro", paternal_surname="Ruiz")

    async def ids(**params: str) -> list[str]:
        response = await client.get("/api/v1/people", headers=root, params=params)
        assert response.status_code == 200, response.text
        return [item["id"] for item in response.json()["items"]]

    assert await ids(q="angela nunez") == [target["id"]]
    assert await ids(curp=CURP) == [target["id"]]
    assert await ids(phone="(449) 765-4321") == [target["id"]]
    assert len(await ids()) == 2


async def test_scope_visibility(
    client: AsyncClient, root: dict[str, str], scoped: Any, geo: Geo
) -> None:
    def address(section: int, municipality: int) -> dict[str, str]:
        return {
            "state_id": geo.state,
            "municipality_id": geo.municipalities[municipality],
            "section_id": geo.sections[section],
        }

    inside = await new_person(client, root, address=address(101, 1))
    outside = await new_person(client, root, address=address(103, 2))
    homeless = await new_person(client, root)

    _, capturist = await scoped(
        ("capturist",), [{"level": "municipality", "node_id": geo.municipalities[1]}]
    )
    listed = (await client.get("/api/v1/people", headers=capturist)).json()["items"]
    assert {p["id"] for p in listed} == {inside["id"], homeless["id"]}
    assert (
        await client.get(f"/api/v1/people/{outside['id']}", headers=capturist)
    ).status_code == 403
    assert (
        await client.patch(
            f"/api/v1/people/{outside['id']}", headers=capturist, json={"given_names": "X"}
        )
    ).status_code == 403

    refused = await client.post(
        "/api/v1/people",
        headers=capturist,
        json={"given_names": "A", "paternal_surname": "B", "address": address(103, 2)},
    )
    assert refused.status_code == 403
    mismatch = await client.post(
        "/api/v1/people",
        headers=root,
        json={"given_names": "A", "paternal_surname": "B", "address": address(103, 1)},
    )
    assert mismatch.status_code == 400
    await new_person(client, capturist, address=address(105, 1))


async def test_consents_and_arco_deletion(
    client: AsyncClient, root: dict[str, str], scoped: Any, geo: Geo, owner_engine: AsyncEngine
) -> None:
    person = await new_person(
        client, root, curp=CURP, contacts=[{"contact_type": "email", "value": "a@example.com"}]
    )
    consent = await client.post(
        f"/api/v1/people/{person['id']}/consents",
        headers=root,
        json={"notice_version": "2026-01", "channel": "paper"},
    )
    assert consent.status_code == 201, consent.text
    listed = (await client.get(f"/api/v1/people/{person['id']}/consents", headers=root)).json()
    assert [c["notice_version"] for c in listed] == ["2026-01"]

    _, viewer = await scoped(("viewer",), [{"level": "national"}])
    assert (
        await client.delete(f"/api/v1/people/{person['id']}", headers=viewer)
    ).status_code == 403
    deleted = await client.delete(f"/api/v1/people/{person['id']}", headers=root)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["purge_after"] == (date.today() + timedelta(days=30)).isoformat()
    assert (await client.get(f"/api/v1/people/{person['id']}", headers=root)).status_code == 404

    async with build_sessionmaker(owner_engine)() as db:
        assert await purge_due(db) == 0  # retention not over yet
        assert await purge_due(db, today=date.today() + timedelta(days=31)) == 1
        assert await purge_due(db, today=date.today() + timedelta(days=31)) == 0
    remaining = (
        await rows(
            owner_engine,
            "SELECT given_names, curp_hash, "
            "(SELECT count(*) FROM people.person_contacts c WHERE c.person_id = p.id) AS contacts "
            "FROM people.persons p WHERE id = :id",
            id=person["id"],
        )
    )[0]
    assert remaining == {"given_names": "[eliminado]", "curp_hash": None, "contacts": 0}


async def test_update_replaces_contacts_and_address(
    client: AsyncClient, root: dict[str, str], geo: Geo
) -> None:
    person = await new_person(
        client, root, contacts=[{"contact_type": "mobile", "value": "4491111111"}]
    )
    short = await client.patch(
        f"/api/v1/people/{person['id']}",
        headers=root,
        json={"contacts": [{"contact_type": "landline", "value": "12345"}]},
    )
    assert short.status_code == 400
    updated = await client.patch(
        f"/api/v1/people/{person['id']}",
        headers=root,
        json={
            "contacts": [{"contact_type": "landline", "value": "449 222 2222", "is_primary": True}],
            "address": {
                "street": "Calle Nueva",
                "municipality_id": geo.municipalities[2],
                "section_id": geo.sections[104],
            },
        },
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert [c["value"] for c in body["contacts"]] == ["4492222222"]
    assert [(a["street"], a["section_id"]) for a in body["addresses"]] == [
        ("Calle Nueva", geo.sections[104])
    ]
