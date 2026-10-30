"""Member scope (D-83, D-101): geographic OR branch (per grant), anti-escalation of branches, totals outside the
scope and the permissions of each role. The synthetic BGD has one state, so municipality 1
plays "my state" and municipality 2 "another state"."""

from typing import Any

from httpx import AsyncClient

from tests.integration.candidacies.conftest import Geo
from tests.integration.conftest import grant_of
from tests.integration.peace_movement.conftest import API, enroll, person


async def _network(
    client: AsyncClient, root: dict[str, str], geo: Geo, levels: dict[str, str]
) -> dict[str, dict[str, Any]]:
    """top (mun. 1) → near (mun. 1) and far (mun. 2) → far_child (mun. 2); stranger (mun. 2)."""
    top = await enroll(client, root, levels, geo.sections[101])
    near = await enroll(client, root, levels, geo.sections[102], recruiter=top["id"])
    far = await enroll(client, root, levels, geo.sections[103], recruiter=top["id"])
    far_child = await enroll(client, root, levels, geo.sections[104], recruiter=far["id"])
    stranger = await enroll(client, root, levels, geo.sections[107])
    return {"top": top, "near": near, "far": far, "far_child": far_child, "stranger": stranger}


async def test_geographic_scope_and_totals_outside_it(  # noqa: PLR0917
    client: AsyncClient,
    root: dict[str, str],
    scoped: Any,
    geo: Geo,
    levels: dict[str, str],
    notice: dict[str, Any],
) -> None:
    net = await _network(client, root, geo, levels)
    _, local = await scoped(
        ("viewer",), [{"level": "municipality", "node_id": geo.municipalities[1]}]
    )
    listed = (await client.get(f"{API}/members", headers=local)).json()
    assert {m["id"] for m in listed["items"]} == {net["top"]["id"], net["near"]["id"]}
    for hidden in ("far", "far_child", "stranger"):
        response = await client.get(f"{API}/members/{net[hidden]['id']}", headers=local)
        assert response.status_code == 404

    detail = (await client.get(f"{API}/members/{net['top']['id']}", headers=local)).json()
    # Outside the scope only totals: the recruit in municipality 2 counts but is not listed.
    assert detail["direct"] == {"active": 2, "pending": 0, "total": 2, "hidden": 1}
    children = await client.get(f"{API}/members/{net['top']['id']}/children", headers=local)
    assert [c["id"] for c in children.json()["items"]] == [net["near"]["id"]]
    assert children.json()["hidden"] == 1


async def test_branch_scope_crosses_the_geography(  # noqa: PLR0917
    client: AsyncClient,
    root: dict[str, str],
    scoped: Any,
    geo: Geo,
    levels: dict[str, str],
    notice: dict[str, Any],
) -> None:
    net = await _network(client, root, geo, levels)
    branch_user, branch = await scoped(
        ("capturist",), [{"level": "municipality", "node_id": geo.municipalities[1]}]
    )
    branches = f"{API}/grants/{await grant_of(client, root, branch_user.id)}/branches"
    granted = await client.put(
        branches,
        headers=root,
        json={"member_ids": [net["far"]["id"]]},
    )
    assert granted.status_code == 200, granted.text
    assert [b["member_id"] for b in granted.json()] == [net["far"]["id"]]

    listed = (await client.get(f"{API}/members", headers=branch, params={"limit": 50})).json()
    # Municipality 1 (geographic) plus the whole branch under `far` (municipality 2).
    assert {m["id"] for m in listed["items"]} == {
        net["top"]["id"],
        net["near"]["id"],
        net["far"]["id"],
        net["far_child"]["id"],
    }
    assert (
        await client.get(f"{API}/members/{net['stranger']['id']}", headers=branch)
    ).status_code == 404

    # Inside the branch the user may enroll a recruit living outside their geographic scope
    # (explicit exception to D-66); outside any branch, not.
    inside = await enroll(client, branch, levels, geo.sections[108], recruiter=net["far"]["id"])
    assert inside["depth"] == 2
    response = await client.post(
        f"{API}/members",
        headers=branch,
        json={
            "person": person(geo.sections[108]),
            "level_id": levels["pacifier"],
            "recruiter_member_id": net["near"]["id"],
            "consent": {"channel": "panel"},
        },
    )
    assert response.status_code == 403  # the address is outside the geographic scope

    listed_branches = (await client.get(branches, headers=root)).json()
    assert [b["member_id"] for b in listed_branches] == [net["far"]["id"]]
    removed = await client.put(branches, headers=root, json={"member_ids": []})
    assert removed.json() == []
    assert (
        await client.get(f"{API}/members/{net['far_child']['id']}", headers=branch)
    ).status_code == 404


async def test_branch_anti_escalation(  # noqa: PLR0917
    client: AsyncClient,
    root: dict[str, str],
    scoped: Any,
    geo: Geo,
    levels: dict[str, str],
    notice: dict[str, Any],
) -> None:
    net = await _network(client, root, geo, levels)
    admin_user, admin = await scoped(
        ("admin",), [{"level": "municipality", "node_id": geo.municipalities[1]}]
    )
    target, _ = await scoped(
        ("capturist",), [{"level": "municipality", "node_id": geo.municipalities[1]}]
    )
    target_branches = f"{API}/grants/{await grant_of(client, root, target.id)}/branches"
    admin_branches = f"{API}/grants/{await grant_of(client, root, admin_user.id)}/branches"
    # The admin sees `top` through its address, but its subtree reaches municipality 2: seeing
    # the node is not enough to hand out its branch.
    denied = await client.put(
        target_branches,
        headers=admin,
        json={"member_ids": [net["top"]["id"]]},
    )
    assert denied.status_code == 403
    # With `top`'s branch, the admin may hand out branches inside it.
    await client.put(
        admin_branches,
        headers=root,
        json={"member_ids": [net["top"]["id"]]},
    )
    allowed = await client.put(
        target_branches,
        headers=admin,
        json={"member_ids": [net["far"]["id"]]},
    )
    assert allowed.status_code == 200, allowed.text
    outside = await client.put(
        target_branches,
        headers=admin,
        json={"member_ids": [net["stranger"]["id"]]},
    )
    assert outside.status_code == 403
    repeated = await client.put(
        target_branches,
        headers=admin,
        json={"member_ids": [net["far"]["id"], net["far"]["id"]]},
    )
    assert repeated.status_code == 400


async def test_permissions_by_role(  # noqa: PLR0917
    client: AsyncClient,
    root: dict[str, str],
    scoped: Any,
    geo: Geo,
    levels: dict[str, str],
    notice: dict[str, Any],
) -> None:
    net = await _network(client, root, geo, levels)
    national = [{"level": "national"}]
    _, viewer = await scoped(("viewer",), national)
    _, capturist = await scoped(("capturist",), national)
    _, nobody = await scoped((), national)

    assert (await client.get(f"{API}/members", headers=nobody)).status_code == 403
    assert (await client.get(f"{API}/members", headers=viewer)).status_code == 200
    await enroll(client, viewer, levels, geo.sections[101], expect=403)
    await enroll(client, capturist, levels, geo.sections[101], recruiter=net["top"]["id"])
    member = net["near"]["id"]
    for path, body in (
        ("validate", None),
        ("reject", {"reason": "No procede"}),
        ("leave", {"reason": "Renuncia"}),
        ("reassign", {"recruiter_member_id": net["far"]["id"], "reason": "Ajuste"}),
    ):
        response = await client.post(f"{API}/members/{member}/{path}", headers=capturist, json=body)
        assert response.status_code == 403, path
    assert (
        await client.post(
            f"{API}/level-goals",
            headers=capturist,
            json={"level_id": levels["pacifier"], "recruit_goal": 3},
        )
    ).status_code == 403
    assert (
        await client.put(
            f"{API}/grants/{net['top']['id']}/branches", headers=capturist, json={"member_ids": []}
        )
    ).status_code == 403
    # Contacts are masked without people.person.read_sensitive (D-66).
    masked = (await client.get(f"{API}/members/{member}", headers=viewer)).json()
    assert masked["person"]["contacts"][0]["value"] == "******4567"
    assert masked["person"]["addresses"][0]["street"] is None
