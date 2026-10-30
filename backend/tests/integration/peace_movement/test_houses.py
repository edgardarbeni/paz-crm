"""Peace Houses (docs/modules/peace-movement.md, D-85, D-92): opening and credit, consolidation,
roles when a member leaves, meetings with guests, photos, the public-location consent and the
house scope."""

import uuid
from typing import Any

import httpx
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.storage import build_storage
from tests.conftest import S3_ACCESS_KEY, S3_SECRET_KEY
from tests.integration.candidacies.conftest import Geo
from tests.integration.geography.conftest import rows, scalar
from tests.integration.peace_movement.conftest import API, enroll
from tests.support import make_settings

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64


async def point(engine: AsyncEngine, section: str) -> tuple[float, float]:
    found = (
        await rows(
            engine,
            "SELECT ST_X(p) AS lon, ST_Y(p) AS lat FROM (SELECT ST_PointOnSurface(geom) AS p "
            "FROM geography.sections WHERE id = :id) q",
            id=section,
        )
    )[0]
    return float(found["lon"]), float(found["lat"])


async def open_house(
    client: AsyncClient,
    headers: dict[str, str],
    engine: AsyncEngine,
    section: str,
    *,
    opener: str,
    host: str,
    contact: str,
    members: list[str] | None = None,
    expect: int = 201,
) -> dict[str, Any]:
    lon, lat = await point(engine, section)
    response = await client.post(
        f"{API}/houses",
        headers=headers,
        json={
            "name": "Casa de Paz Las Flores",
            "schedule": [{"day": "sat", "starts_at": "10:00", "ends_at": "12:00"}],
            "capacity": 30,
            "address": {
                "street": "Calle Girasol",
                "exterior_number": "12",
                "postal_code": "20000",
                "longitude": lon,
                "latitude": lat,
            },
            "opened_by_member_id": opener,
            "host_member_id": host,
            "contact_member_id": contact,
            "member_ids": members or [],
        },
    )
    assert response.status_code == expect, response.text
    result: dict[str, Any] = response.json()
    return result


async def test_open_house_and_its_credit(  # noqa: PLR0917
    client: AsyncClient,
    root: dict[str, str],
    scoped: Any,
    geo: Geo,
    levels: dict[str, str],
    notice: dict[str, Any],
    owner_engine: AsyncEngine,
) -> None:
    ambassador = await enroll(client, root, levels, geo.sections[101], level="peace_ambassador")
    middle = await enroll(client, root, levels, geo.sections[101], recruiter=ambassador["id"])
    opener = await enroll(client, root, levels, geo.sections[101], recruiter=middle["id"])
    lonely = await enroll(client, root, levels, geo.sections[102])

    # Host = contact and nobody else: one member, not enough.
    await open_house(
        client, root, owner_engine, geo.sections[101],
        opener=opener["id"], host=opener["id"], contact=opener["id"], expect=400,
    )  # fmt: skip
    house = await open_house(
        client, root, owner_engine, geo.sections[101],
        opener=opener["id"], host=opener["id"], contact=middle["id"],
    )  # fmt: skip
    assert (house["status"], house["member_count"], house["section_id"]) == (
        "open",
        2,
        geo.sections[101],
    )
    # The credit goes to the first Ambassador up the opener's path.
    assert (house["credited_member_id"], house["credit_pending"]) == (ambassador["id"], False)
    assert house["address"]["street"] == "Calle Girasol"
    lon, lat = await point(owner_engine, geo.sections[101])
    assert house["address"]["longitude"] == lon
    assert (house["approx_longitude"], house["approx_latitude"]) == (round(lon, 3), round(lat, 3))
    assert (house["member_goal"], house["progress_pct"]) == (100, 2)
    assert house["host"]["id"] == opener["id"]

    # No Ambassador and no zone: the credit stays pending (D-92).
    pending = await open_house(
        client, root, owner_engine, geo.sections[102],
        opener=lonely["id"], host=lonely["id"], contact=opener["id"],
    )  # fmt: skip
    assert pending["credit_pending"] is True
    listed = (
        await client.get(f"{API}/houses", headers=root, params={"credit_pending": True})
    ).json()
    assert [h["id"] for h in listed["items"]] == [pending["id"]]

    # Without read_sensitive the exact address and point stay hidden.
    _, viewer = await scoped(("viewer",), [{"level": "national"}])
    masked = (await client.get(f"{API}/houses/{house['id']}", headers=viewer)).json()
    assert masked["address"] == {
        "street": None,
        "exterior_number": None,
        "interior_number": None,
        "references": None,
        "postal_code": "20000",
        "longitude": None,
        "latitude": None,
    }
    assert (
        await scalar(
            owner_engine,
            "SELECT count(*) FROM audit.access_log WHERE entity_table = 'peace_movement.peace_houses'",
        )
        >= 2
    )


async def test_zone_credit_and_manual_reassignment(  # noqa: PLR0917
    client: AsyncClient,
    root: dict[str, str],
    scoped: Any,
    geo: Geo,
    levels: dict[str, str],
    notice: dict[str, Any],
    owner_engine: AsyncEngine,
) -> None:
    coordinator, _ = await scoped(("coordinator",), [{"level": "state", "node_id": geo.state}])
    zone = await client.post(
        f"{API}/zone-coordinators",
        headers=root,
        json={
            "user_id": str(coordinator.id),
            "state_id": geo.state,
            "nodes": [{"level": "municipality", "node_id": geo.municipalities[2]}],
        },
    )
    assert zone.status_code == 201
    a = await enroll(client, root, levels, geo.sections[103])
    b = await enroll(client, root, levels, geo.sections[103], recruiter=a["id"])
    house = await open_house(
        client, root, owner_engine, geo.sections[103], opener=a["id"], host=a["id"], contact=b["id"]
    )
    assert (house["credited_member_id"], house["credited_user_id"]) == (None, str(coordinator.id))

    def credit(**body: Any) -> Any:
        return client.post(f"{API}/houses/{house['id']}/credit", headers=root, json=body)

    assert (await credit(member_id=b["id"], reason="Ajuste de red")).status_code == 409
    assert (await credit(user_id=str(coordinator.id), reason="Igual")).status_code == 409
    ambassador = await enroll(client, root, levels, geo.sections[104], level="peace_ambassador")
    moved = await credit(member_id=ambassador["id"], reason="Acuerdo estatal")
    assert moved.status_code == 200, moved.text
    assert moved.json()["credited_member_id"] == ambassador["id"]
    history = await rows(
        owner_engine,
        "SELECT from_user_id::text AS f, to_member_id::text AS t, reason "
        "FROM peace_movement.peace_house_credit_changes",
    )
    assert history == [
        {"f": str(coordinator.id), "t": ambassador["id"], "reason": "Acuerdo estatal"}
    ]
    # Promotions never move the credit by themselves (D-92).
    await client.post(
        f"{API}/members/{a['id']}/level",
        headers=root,
        json={"level_id": levels["peace_ambassador"]},
    )
    again = (await client.get(f"{API}/houses/{house['id']}", headers=root)).json()
    assert again["credited_member_id"] == ambassador["id"]
    _, capturist = await scoped(("capturist",), [{"level": "national"}])
    denied = await client.post(
        f"{API}/houses/{house['id']}/credit",
        headers=capturist,
        json={"member_id": ambassador["id"], "reason": "No debería"},
    )
    assert denied.status_code == 403


async def test_consolidation_follows_the_members(  # noqa: PLR0917
    client: AsyncClient,
    root: dict[str, str],
    geo: Geo,
    levels: dict[str, str],
    notice: dict[str, Any],
    owner_engine: AsyncEngine,
) -> None:
    await client.post(
        f"{API}/house-goals", headers=root, json={"state_id": geo.state, "member_goal": 3}
    )
    host = await enroll(client, root, levels, geo.sections[101])
    contact = await enroll(client, root, levels, geo.sections[101], recruiter=host["id"])
    third = await enroll(client, root, levels, geo.sections[101], recruiter=host["id"])
    house = await open_house(
        client, root, owner_engine, geo.sections[101],
        opener=host["id"], host=host["id"], contact=contact["id"],
    )  # fmt: skip
    assert house["status"] == "open"
    added = await client.post(
        f"{API}/houses/{house['id']}/members", headers=root, json={"member_id": third["id"]}
    )
    assert added.status_code == 201
    assert {m["source"] for m in added.json()} == {"role", "assignment"}
    assert (
        await client.post(
            f"{API}/houses/{house['id']}/members", headers=root, json={"member_id": third["id"]}
        )
    ).status_code == 409
    full = (await client.get(f"{API}/houses/{house['id']}", headers=root)).json()
    assert (full["status"], full["progress_pct"]) == ("consolidated", 100)
    first = full["first_consolidated_on"]
    assert first is not None

    assert (
        await client.delete(f"{API}/houses/{house['id']}/members/{host['id']}", headers=root)
    ).status_code == 409  # change the host first
    gone = await client.delete(f"{API}/houses/{house['id']}/members/{third['id']}", headers=root)
    assert gone.status_code == 204
    back = (await client.get(f"{API}/houses/{house['id']}", headers=root)).json()
    # Below the goal again: open, but the first consolidation is remembered (D-92).
    assert (back["status"], back["consolidated_on"], back["first_consolidated_on"]) == (
        "open",
        None,
        first,
    )
    # Enrolling straight into the house.
    newcomer = await enroll(
        client, root, levels, geo.sections[101], recruiter=host["id"], house_id=house["id"]
    )
    members = (await client.get(f"{API}/houses/{house['id']}/members", headers=root)).json()
    assert {m["member"]["id"]: m["source"] for m in members}[newcomer["id"]] == "enrollment"

    closed = await client.post(
        f"{API}/houses/{house['id']}/close", headers=root, json={"reason": "Se mudó el anfitrión"}
    )
    assert (closed.json()["status"], closed.json()["status_reason"]) == (
        "closed",
        "Se mudó el anfitrión",
    )
    assert (
        await client.post(
            f"{API}/houses/{house['id']}/members", headers=root, json={"member_id": third["id"]}
        )
    ).status_code == 409


async def test_roles_when_members_leave(  # noqa: PLR0917
    client: AsyncClient,
    root: dict[str, str],
    geo: Geo,
    levels: dict[str, str],
    notice: dict[str, Any],
    owner_engine: AsyncEngine,
) -> None:
    host = await enroll(client, root, levels, geo.sections[101])
    contact = await enroll(client, root, levels, geo.sections[101], recruiter=host["id"])
    extra = await enroll(client, root, levels, geo.sections[101], recruiter=host["id"])
    house = await open_house(
        client, root, owner_engine, geo.sections[101],
        opener=host["id"], host=host["id"], contact=contact["id"], members=[extra["id"]],
    )  # fmt: skip

    await client.post(
        f"{API}/members/{host['id']}/leave", headers=root, json={"reason": "Renuncia"}
    )
    after = (await client.get(f"{API}/houses/{house['id']}", headers=root)).json()
    # The contact takes the host role; nothing to reassign yet.
    assert (after["host"]["id"], after["contact"]["id"], after["needs_reassignment"]) == (
        contact["id"],
        contact["id"],
        False,
    )
    assert after["member_count"] == 2

    # ARCO cancellation of the remaining host and contact: nobody left in either role.
    deleted = await client.delete(f"/api/v1/people/{contact['person']['id']}", headers=root)
    assert deleted.status_code == 200, deleted.text
    orphan = (await client.get(f"{API}/houses/{house['id']}", headers=root)).json()
    assert (orphan["host"], orphan["contact"], orphan["needs_reassignment"]) == (None, None, True)
    flagged = (
        await client.get(f"{API}/houses", headers=root, params={"needs_reassignment": True})
    ).json()
    assert [h["id"] for h in flagged["items"]] == [house["id"]]

    fixed = await client.patch(
        f"{API}/houses/{house['id']}",
        headers=root,
        json={"host_member_id": extra["id"], "contact_member_id": extra["id"], "capacity": 15},
    )
    assert fixed.status_code == 200, fixed.text
    assert (fixed.json()["needs_reassignment"], fixed.json()["capacity"]) == (False, 15)


async def test_meetings_with_members_and_guests(  # noqa: PLR0917
    client: AsyncClient,
    root: dict[str, str],
    geo: Geo,
    levels: dict[str, str],
    notice: dict[str, Any],
    owner_engine: AsyncEngine,
) -> None:
    host = await enroll(client, root, levels, geo.sections[101])
    contact = await enroll(client, root, levels, geo.sections[101], recruiter=host["id"])
    house = await open_house(
        client, root, owner_engine, geo.sections[101],
        opener=host["id"], host=host["id"], contact=contact["id"],
    )  # fmt: skip
    known_guest = await client.post(
        "/api/v1/people", headers=root, json={"given_names": "Rosa", "paternal_surname": "Luna"}
    )
    meeting = await client.post(
        f"{API}/houses/{house['id']}/meetings",
        headers=root,
        json={
            "held_at": "2026-10-25T18:00:00-06:00",
            "topic": "Mediación vecinal",
            "notes": "Se acordó una jornada de limpieza.",
            "member_ids": [host["id"], contact["id"]],
            "guest_person_ids": [known_guest.json()["id"]],
            "guests": [{"given_names": "Pedro", "paternal_surname": "Sol", "mobile": "4499998877"}],
        },
    )
    assert meeting.status_code == 201, meeting.text
    body = meeting.json()
    assert (body["attendee_count"], body["guest_count"]) == (4, 2)
    guests = [a for a in body["attendees"] if a["member_id"] is None]
    assert {g["person"]["full_name"].strip() for g in guests} == {"Rosa Luna", "Pedro Sol"}
    # The new guest is a person without CURP, ready to be enrolled later (D-92).
    pedro = next(g for g in guests if g["person"]["full_name"].startswith("Pedro"))
    assert pedro["person"]["curp"] is None
    listed = (await client.get(f"{API}/houses/{house['id']}/meetings", headers=root)).json()
    assert [(m["topic"], m["attendee_count"]) for m in listed["items"]] == [
        ("Mediación vecinal", 4)
    ]
    missing = await client.get(f"{API}/houses/{house['id']}/meetings/{uuid.uuid4()}", headers=root)
    assert missing.status_code == 404


async def test_photos(  # noqa: PLR0917
    app: FastAPI,
    client: AsyncClient,
    root: dict[str, str],
    geo: Geo,
    levels: dict[str, str],
    notice: dict[str, Any],
    owner_engine: AsyncEngine,
    s3_endpoint: str,
) -> None:
    host = await enroll(client, root, levels, geo.sections[101])
    contact = await enroll(client, root, levels, geo.sections[101], recruiter=host["id"])
    house = await open_house(
        client, root, owner_engine, geo.sections[101],
        opener=host["id"], host=host["id"], contact=contact["id"],
    )  # fmt: skip
    photos = f"{API}/houses/{house['id']}/photos"
    assert (await client.get(photos, headers=root)).status_code == 503  # no storage configured

    storage = build_storage(
        make_settings(
            storage_endpoint=s3_endpoint,
            storage_bucket=f"h{uuid.uuid4().hex[:12]}",
            storage_access_key=S3_ACCESS_KEY,
            storage_secret_key=S3_SECRET_KEY,
        )
    )
    assert storage is not None
    await storage.ensure_bucket()
    app.state.storage = storage
    try:
        uploaded = await client.post(
            photos,
            headers=root,
            files={"file": ("fachada.jpg", JPEG, "image/jpeg")},
            data={"caption": "Fachada"},
        )
        assert uploaded.status_code == 201, uploaded.text
        assert (uploaded.json()["caption"], uploaded.json()["size_bytes"]) == ("Fachada", len(JPEG))
        async with httpx.AsyncClient() as http:
            assert (await http.get(uploaded.json()["url"])).content == JPEG
        wrong = await client.post(
            photos, headers=root, files={"file": ("nota.txt", b"hola", "text/plain")}
        )
        assert wrong.status_code == 400
        listed = (await client.get(photos, headers=root)).json()
        assert [p["id"] for p in listed] == [uploaded.json()["id"]]
        gone = await client.delete(f"{photos}/{uploaded.json()['id']}", headers=root)
        assert gone.status_code == 204
        assert (await client.get(photos, headers=root)).json() == []
    finally:
        app.state.storage = None


async def test_public_location_consent(  # noqa: PLR0917
    client: AsyncClient,
    root: dict[str, str],
    geo: Geo,
    levels: dict[str, str],
    notice: dict[str, Any],
    owner_engine: AsyncEngine,
) -> None:
    host = await enroll(client, root, levels, geo.sections[101])
    contact = await enroll(client, root, levels, geo.sections[101], recruiter=host["id"])
    house = await open_house(
        client, root, owner_engine, geo.sections[101],
        opener=host["id"], host=host["id"], contact=contact["id"],
    )  # fmt: skip
    assert house["publishable"] is False
    consent = f"{API}/houses/{house['id']}/public-location-consent"
    assert (await client.post(consent, headers=root, json={})).status_code == 409  # no notice
    await client.post(
        "/api/v1/people/privacy-notices",
        headers=root,
        json={
            "code": "peace_house_location",
            "version": "2026-10",
            "title": "Publicación de la ubicación de la Casa de Paz",
            "body": "Autorizo publicar la ubicación exacta de la Casa de Paz que hospedo.",
        },
    )
    given = await client.post(
        consent, headers=root, json={"channel": "paper", "evidence_uri": "s3://pazos/c/1.pdf"}
    )
    assert given.json()["publishable"] is True
    publishable = (
        await client.get(f"{API}/houses", headers=root, params={"publishable": True})
    ).json()
    assert [h["id"] for h in publishable["items"]] == [house["id"]]
    revoked = await client.delete(consent, headers=root)
    assert revoked.json()["publishable"] is False


async def test_house_scope(  # noqa: PLR0917
    client: AsyncClient,
    root: dict[str, str],
    scoped: Any,
    geo: Geo,
    levels: dict[str, str],
    notice: dict[str, Any],
    owner_engine: AsyncEngine,
) -> None:
    near = await enroll(client, root, levels, geo.sections[101])
    near_contact = await enroll(client, root, levels, geo.sections[102], recruiter=near["id"])
    far = await enroll(client, root, levels, geo.sections[103])
    far_contact = await enroll(client, root, levels, geo.sections[104], recruiter=far["id"])
    mine = await open_house(
        client, root, owner_engine, geo.sections[101],
        opener=near["id"], host=near["id"], contact=near_contact["id"],
    )  # fmt: skip
    # In municipality 2, but opened by a member of municipality 1: visible through its opener.
    bridged = await open_house(
        client, root, owner_engine, geo.sections[103],
        opener=near["id"], host=far["id"], contact=far_contact["id"],
    )  # fmt: skip
    foreign = await open_house(
        client, root, owner_engine, geo.sections[104],
        opener=far["id"], host=far["id"], contact=far_contact["id"],
    )  # fmt: skip

    _, local = await scoped(
        ("capturist",), [{"level": "municipality", "node_id": geo.municipalities[1]}]
    )
    listed = (await client.get(f"{API}/houses", headers=local)).json()
    assert {h["id"] for h in listed["items"]} == {mine["id"], bridged["id"]}
    assert (await client.get(f"{API}/houses/{foreign['id']}", headers=local)).status_code == 404
    # Opening a house outside the scope, without a branch, is not allowed.
    await open_house(
        client, local, owner_engine, geo.sections[104],
        opener=near["id"], host=near["id"], contact=near_contact["id"], expect=403,
    )  # fmt: skip
    _, viewer = await scoped(("viewer",), [{"level": "national"}])
    await open_house(
        client, viewer, owner_engine, geo.sections[101],
        opener=near["id"], host=near["id"], contact=near_contact["id"], expect=403,
    )  # fmt: skip


async def test_houses_map(  # noqa: PLR0917
    client: AsyncClient,
    root: dict[str, str],
    scoped: Any,
    geo: Geo,
    levels: dict[str, str],
    notice: dict[str, Any],
    owner_engine: AsyncEngine,
) -> None:
    near = await enroll(client, root, levels, geo.sections[101])
    near_contact = await enroll(client, root, levels, geo.sections[101], recruiter=near["id"])
    far = await enroll(client, root, levels, geo.sections[104])
    far_contact = await enroll(client, root, levels, geo.sections[104], recruiter=far["id"])
    mine = await open_house(
        client, root, owner_engine, geo.sections[101],
        opener=near["id"], host=near["id"], contact=near_contact["id"],
    )  # fmt: skip
    other = await open_house(
        client, root, owner_engine, geo.sections[104],
        opener=far["id"], host=far["id"], contact=far_contact["id"],
    )  # fmt: skip
    everything = (await client.get(f"{API}/houses/map", headers=root)).json()
    assert everything["type"] == "FeatureCollection"
    assert everything["truncated"] is False
    by_id = {f["properties"]["id"]: f for f in everything["features"]}
    assert set(by_id) == {mine["id"], other["id"]}
    # Approximate point only (3 decimals), never the exact one.
    lon, lat = by_id[mine["id"]]["geometry"]["coordinates"]
    assert (lon, lat) == (mine["approx_longitude"], mine["approx_latitude"])
    assert by_id[mine["id"]]["properties"]["status"] == "open"

    _, local = await scoped(
        ("viewer",), [{"level": "municipality", "node_id": geo.municipalities[1]}]
    )
    scoped_map = (await client.get(f"{API}/houses/map", headers=local)).json()
    assert [f["properties"]["id"] for f in scoped_map["features"]] == [mine["id"]]
    await client.post(f"{API}/houses/{other['id']}/close", headers=root, json={"reason": "Fin"})
    current = (await client.get(f"{API}/houses/map", headers=root)).json()
    assert [f["properties"]["id"] for f in current["features"]] == [mine["id"]]
    closed = (
        await client.get(f"{API}/houses/map", headers=root, params={"status": "closed"})
    ).json()
    assert [f["properties"]["id"] for f in closed["features"]] == [other["id"]]
