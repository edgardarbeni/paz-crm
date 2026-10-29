"""Members of the Peace Movement: enrollment rules, the ltree pyramid, lifecycle, history and the
hooks from `people` (docs/modules/peace-movement.md, D-82, D-91, D-92)."""

from datetime import date, timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.db.session import build_sessionmaker
from app.modules.people.service import purge_due
from tests.integration.candidacies.conftest import Geo
from tests.integration.geography.conftest import rows, scalar
from tests.integration.peace_movement.conftest import API, curp, enroll, person


async def test_enrollment_needs_the_movement_notice(
    client: AsyncClient, root: dict[str, str], geo: Geo, levels: dict[str, str]
) -> None:
    response = await client.post(
        f"{API}/members",
        headers=root,
        json={
            "person": person(geo.sections[101]),
            "level_id": levels["pacifier"],
            "origin": "structure",
            "consent": {"channel": "panel"},
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "notice-unavailable"


async def test_enroll_builds_the_pyramid(  # noqa: PLR0917
    client: AsyncClient,
    root: dict[str, str],
    geo: Geo,
    levels: dict[str, str],
    notice: dict[str, Any],
    owner_engine: AsyncEngine,
) -> None:
    top = await enroll(client, root, levels, geo.sections[101], level="peace_promoter")
    assert (top["status"], top["depth"], top["origin"], top["channel"]) == (
        "active",
        0,
        "structure",
        "panel",
    )
    assert top["recruited_by"] is None
    assert top["person"]["curp"]  # the person was created with the member
    assert len(top["referral_code"]) >= 16

    child = await enroll(client, root, levels, geo.sections[103], recruiter=top["id"])
    grandchild = await enroll(client, root, levels, geo.sections[104], recruiter=child["id"])
    assert (child["depth"], grandchild["depth"]) == (1, 2)
    assert grandchild["recruited_by"]["id"] == child["id"]

    paths = {
        str(row["id"]): row["path"]
        for row in await rows(owner_engine, "SELECT id, path::text FROM peace_movement.members")
    }
    assert paths[grandchild["id"]].startswith(paths[child["id"]] + ".")
    assert paths[child["id"]].startswith(paths[top["id"]] + ".")

    detail = (await client.get(f"{API}/members/{top['id']}", headers=root)).json()
    assert detail["direct"] == {"active": 1, "pending": 0, "total": 1, "hidden": 0}
    # Promotor de la Paz: 10 recruits nationally; 1 active direct recruit = 10 %.
    assert (detail["recruit_goal"], detail["progress_pct"], detail["traffic_light"]) == (
        10,
        10,
        "red",
    )

    consent = (
        await rows(
            owner_engine,
            "SELECT c.notice_code, c.notice_version, c.notice_text_sha256, c.channel "
            "FROM people.privacy_consents c JOIN peace_movement.members m ON m.consent_id = c.id "
            "WHERE m.id = :id",
            id=top["id"],
        )
    )[0]
    assert consent == {
        "notice_code": "peace_movement",
        "notice_version": "2026-10",
        "notice_text_sha256": notice["body_sha256"],
        "channel": "panel",
    }
    # Each enrollment lands in the outbox for the aggregates job (phase 3).
    assert (
        await scalar(
            owner_engine,
            "SELECT count(*) FROM peace_movement.network_changes WHERE kind = 'enrolled'",
        )
        == 3
    )


async def test_enrollment_requirements(
    client: AsyncClient,
    root: dict[str, str],
    geo: Geo,
    levels: dict[str, str],
    notice: dict[str, Any],
) -> None:
    def body(**fields: Any) -> dict[str, Any]:
        return {
            "level_id": levels["pacifier"],
            "origin": "structure",
            "consent": {"channel": "paper"},
            **fields,
        }

    no_curp = await client.post(
        f"{API}/members",
        headers=root,
        json=body(person=person(geo.sections[101], with_curp=False)),
    )
    assert no_curp.status_code == 400
    assert no_curp.json()["code"] == "member-requirements"

    homeless = person(geo.sections[101])
    del homeless["address"]
    no_address = await client.post(f"{API}/members", headers=root, json=body(person=homeless))
    assert no_address.status_code == 400

    both = await client.post(
        f"{API}/members",
        headers=root,
        json=body(person=person(geo.sections[101]), person_id=geo.state),
    )
    assert both.status_code == 422
    orphan = await client.post(
        f"{API}/members",
        headers=root,
        json={**body(person=person(geo.sections[101])), "origin": "recruiter"},
    )
    assert orphan.status_code == 422

    data = person(geo.sections[102], name="Original")
    first = await client.post(f"{API}/members", headers=root, json=body(person=data))
    assert first.status_code == 201, first.text
    # Same CURP: the person is reused, never overwritten, and cannot enroll twice.
    again = await client.post(
        f"{API}/members",
        headers=root,
        json=body(person={**data, "given_names": "Cambiado"}),
    )
    assert again.status_code == 409
    by_id = await client.post(
        f"{API}/members",
        headers=root,
        json=body(person_id=first.json()["person"]["id"]),
    )
    assert by_id.status_code == 409
    stored = await client.get(f"/api/v1/people/{first.json()['person']['id']}", headers=root)
    assert stored.json()["given_names"] == "Original"


async def test_existing_person_and_recruiter_status(
    client: AsyncClient,
    root: dict[str, str],
    geo: Geo,
    levels: dict[str, str],
    notice: dict[str, Any],
) -> None:
    created = await client.post("/api/v1/people", headers=root, json=person(geo.sections[105]))
    assert created.status_code == 201, created.text
    member = await client.post(
        f"{API}/members",
        headers=root,
        json={
            "person_id": created.json()["id"],
            "level_id": levels["pacifier"],
            "origin": "event",
            "origin_detail": "Foro por la paz, Aguascalientes",
            "consent": {"channel": "paper", "evidence_uri": "s3://pazos/consents/1.pdf"},
        },
    )
    assert member.status_code == 201, member.text
    assert member.json()["origin_detail"] == "Foro por la paz, Aguascalientes"

    gone = await client.post(
        f"{API}/members/{member.json()['id']}/leave",
        headers=root,
        json={"reason": "Se muda al extranjero"},
    )
    assert gone.status_code == 200
    assert (gone.json()["status"], gone.json()["left_on"]) == ("left", date.today().isoformat())
    # A recruiter who left the movement cannot recruit.
    await enroll(client, root, levels, geo.sections[101], recruiter=member.json()["id"], expect=409)


async def test_level_changes_and_goals_per_state(
    client: AsyncClient,
    root: dict[str, str],
    geo: Geo,
    levels: dict[str, str],
    notice: dict[str, Any],
) -> None:
    top = await enroll(client, root, levels, geo.sections[101])
    await enroll(client, root, levels, geo.sections[102], recruiter=top["id"])
    # Pacificador: 1 recruit nationally, so one recruit is 100 %.
    detail = (await client.get(f"{API}/members/{top['id']}", headers=root)).json()
    assert (detail["progress_pct"], detail["traffic_light"]) == (100, "green")

    goal = await client.post(
        f"{API}/level-goals",
        headers=root,
        json={"level_id": levels["pacifier"], "state_id": geo.state, "recruit_goal": 2},
    )
    assert goal.status_code == 201, goal.text
    detail = (await client.get(f"{API}/members/{top['id']}", headers=root)).json()
    assert (detail["recruit_goal"], detail["progress_pct"], detail["traffic_light"]) == (
        2,
        50,
        "yellow",
    )

    same = await client.post(
        f"{API}/members/{top['id']}/level", headers=root, json={"level_id": levels["pacifier"]}
    )
    assert same.status_code == 409
    changed = await client.post(
        f"{API}/members/{top['id']}/level",
        headers=root,
        json={"level_id": levels["peace_builder"], "reason": "Se compromete a más"},
    )
    assert changed.status_code == 200
    assert changed.json()["level_id"] == levels["peace_builder"]
    assert changed.json()["recruit_goal"] == 100
    history = (await client.get(f"{API}/members/{top['id']}/history", headers=root)).json()
    assert [(h["from_level_id"], h["to_level_id"], h["reason"]) for h in history["levels"]] == [
        (levels["pacifier"], levels["peace_builder"], "Se compromete a más")
    ]


async def test_reassign_moves_the_whole_subtree(  # noqa: PLR0917
    client: AsyncClient,
    root: dict[str, str],
    geo: Geo,
    levels: dict[str, str],
    notice: dict[str, Any],
    owner_engine: AsyncEngine,
) -> None:
    a = await enroll(client, root, levels, geo.sections[101])
    b = await enroll(client, root, levels, geo.sections[101], recruiter=a["id"])
    c = await enroll(client, root, levels, geo.sections[101], recruiter=b["id"])
    d = await enroll(client, root, levels, geo.sections[103])

    def reassign(member: str, recruiter: str) -> Any:
        return client.post(
            f"{API}/members/{member}/reassign",
            headers=root,
            json={"recruiter_member_id": recruiter, "reason": "Acuerdo de coordinación"},
        )

    assert (await reassign(b["id"], b["id"])).status_code == 409  # itself
    assert (await reassign(b["id"], c["id"])).status_code == 409  # a descendant
    assert (await reassign(b["id"], a["id"])).status_code == 409  # already its recruiter

    moved = await reassign(b["id"], d["id"])
    assert moved.status_code == 200, moved.text
    assert (moved.json()["depth"], moved.json()["recruited_by"]["id"]) == (1, d["id"])
    paths = {
        str(row["id"]): (row["path"], row["depth"])
        for row in await rows(
            owner_engine, "SELECT id, path::text, depth FROM peace_movement.members"
        )
    }
    assert paths[b["id"]][0].startswith(paths[d["id"]][0] + ".")
    assert paths[c["id"]] == (f"{paths[b['id']][0]}.{paths[c['id']][0].rsplit('.', 1)[1]}", 2)

    history = (await client.get(f"{API}/members/{b['id']}/history", headers=root)).json()
    assert [
        (h["from_member_id"], h["to_member_id"], h["subtree_size"]) for h in history["recruiters"]
    ] == [(a["id"], d["id"], 2)]
    bulk = (
        await rows(
            owner_engine,
            "SELECT after FROM audit.audit_log WHERE action = 'member_subtree_moved'",
        )
    )[0]["after"]
    assert bulk["count"] == 2
    assert set(bulk["ids"]) == {b["id"], c["id"]}


async def test_validation_of_pending_enrollments(  # noqa: PLR0917
    client: AsyncClient,
    root: dict[str, str],
    geo: Geo,
    levels: dict[str, str],
    notice: dict[str, Any],
    owner_engine: AsyncEngine,
) -> None:
    top = await enroll(client, root, levels, geo.sections[101])
    pending = await enroll(client, root, levels, geo.sections[102], recruiter=top["id"])
    other = await enroll(client, root, levels, geo.sections[102], recruiter=top["id"])
    # Public-link and field-app enrollments arrive pending (phase 4); simulated here.
    async with owner_engine.begin() as connection:
        await connection.exec_driver_sql(
            "UPDATE peace_movement.members SET status = 'pending_validation' "
            f"WHERE id IN ('{pending['id']}', '{other['id']}')"
        )
    detail = (await client.get(f"{API}/members/{top['id']}", headers=root)).json()
    assert detail["direct"]["pending"] == 2
    assert detail["progress_pct"] == 0  # pending recruits do not count

    valid = await client.post(f"{API}/members/{pending['id']}/validate", headers=root)
    assert valid.status_code == 200
    assert valid.json()["status"] == "active"
    assert (
        await client.post(f"{API}/members/{pending['id']}/validate", headers=root)
    ).status_code == 409
    rejected = await client.post(
        f"{API}/members/{other['id']}/reject", headers=root, json={"reason": "Datos falsos"}
    )
    assert (rejected.json()["status"], rejected.json()["status_reason"]) == (
        "rejected",
        "Datos falsos",
    )
    # The rejected person stays in `people` (D-92) and may enroll again.
    person_id = rejected.json()["person"]["id"]
    assert (await client.get(f"/api/v1/people/{person_id}", headers=root)).status_code == 200
    retry = await client.post(
        f"{API}/members",
        headers=root,
        json={
            "person_id": person_id,
            "level_id": levels["pacifier"],
            "origin": "campaign",
            "consent": {"channel": "panel"},
        },
    )
    assert retry.status_code == 201, retry.text


async def test_arco_withdraws_the_node_and_purge_keeps_it(  # noqa: PLR0917
    client: AsyncClient,
    root: dict[str, str],
    geo: Geo,
    levels: dict[str, str],
    notice: dict[str, Any],
    owner_engine: AsyncEngine,
) -> None:
    top = await enroll(client, root, levels, geo.sections[101])
    child = await enroll(client, root, levels, geo.sections[102], recruiter=top["id"])
    deleted = await client.delete(f"/api/v1/people/{top['person']['id']}", headers=root)
    assert deleted.status_code == 200, deleted.text

    node = (await client.get(f"{API}/members/{top['id']}", headers=root)).json()
    assert node["status"] == "withdrawn"
    assert (await client.get(f"{API}/members/{child['id']}", headers=root)).json()["recruited_by"][
        "id"
    ] == top["id"]
    # A withdrawn node cannot recruit.
    await enroll(client, root, levels, geo.sections[101], recruiter=top["id"], expect=409)

    async with build_sessionmaker(owner_engine)() as db:
        assert await purge_due(db, today=date.today() + timedelta(days=31)) == 1
    kept = (
        await rows(
            owner_engine,
            "SELECT status, consent_id, section_id::text AS section FROM peace_movement.members "
            "WHERE id = :id",
            id=top["id"],
        )
    )[0]
    # The consent is gone with the purge; the node and its section stay (D-92).
    assert kept == {"status": "withdrawn", "consent_id": None, "section": geo.sections[101]}


async def test_member_follows_the_primary_address(
    client: AsyncClient,
    root: dict[str, str],
    geo: Geo,
    levels: dict[str, str],
    notice: dict[str, Any],
) -> None:
    member = await enroll(client, root, levels, geo.sections[101])
    moved = await client.patch(
        f"/api/v1/people/{member['person']['id']}",
        headers=root,
        json={"address": {"street": "Otra calle", "section_id": geo.sections[108]}},
    )
    assert moved.status_code == 200, moved.text
    detail = (await client.get(f"{API}/members/{member['id']}", headers=root)).json()
    assert detail["section_id"] == geo.sections[108]


async def test_search_and_reads_are_logged(  # noqa: PLR0917
    client: AsyncClient,
    root: dict[str, str],
    geo: Geo,
    levels: dict[str, str],
    notice: dict[str, Any],
    owner_engine: AsyncEngine,
) -> None:
    top = await enroll(client, root, levels, geo.sections[101])
    for section in (102, 103):
        await enroll(client, root, levels, geo.sections[section], recruiter=top["id"])
    page = (
        await client.get(f"{API}/members", headers=root, params={"recruiter_id": top["id"]})
    ).json()
    assert len(page["items"]) == 2
    assert (
        await client.get(f"{API}/members", headers=root, params={"q": "juan", "limit": 1})
    ).json()["has_more"] is True
    assert (await client.get(f"{API}/members", headers=root, params={"status": "left"})).json()[
        "items"
    ] == []
    children = (await client.get(f"{API}/members/{top['id']}/children", headers=root)).json()
    assert (len(children["items"]), children["hidden"]) == (2, 0)
    assert (
        await scalar(
            owner_engine,
            "SELECT count(*) FROM audit.access_log WHERE entity_table = 'peace_movement.members' "
            "AND entity_id = :id",
            id=top["id"],
        )
        >= 1
    )
    assert curp()  # helper stays importable for other tests
