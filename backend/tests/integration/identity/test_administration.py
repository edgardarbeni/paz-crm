"""Users, roles, permissions and audit viewer — including what users must NOT be able to do."""

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.modules.identity.permissions import PERMISSIONS, SYSTEM_ROLES
from tests.integration.identity.conftest import Account, UserFactory, bearer, login, token_for


async def _role_ids(client: AsyncClient, headers: dict[str, str]) -> dict[str, str]:
    return {
        role["code"]: role["id"]
        for role in (await client.get("/api/v1/roles", headers=headers)).json()
    }


async def _custom_role(
    client: AsyncClient, headers: dict[str, str], code: str, permissions: list[str]
) -> str:
    response = await client.post(
        "/api/v1/roles",
        headers=headers,
        json={"code": code, "name": code.title(), "permissions": permissions},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


@pytest.fixture
async def superadmin(make_user: UserFactory) -> Account:
    return await make_user(roles=("superadmin",), with_totp=True)


# --- authorization: the negative cases -------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/v1/users"),
        ("post", "/api/v1/users"),
        ("get", "/api/v1/roles"),
        ("post", "/api/v1/roles"),
        ("get", "/api/v1/permissions"),
        ("get", "/api/v1/audit-log"),
    ],
)
async def test_viewer_cannot_reach_administration(
    client: AsyncClient, make_user: UserFactory, method: str, path: str
) -> None:
    viewer = await make_user(roles=("viewer",))
    headers = await token_for(client, viewer)
    response = await client.request(method, path, headers=headers, json={})
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


async def test_admin_cannot_escalate_to_superadmin(
    client: AsyncClient, make_user: UserFactory, superadmin: Account
) -> None:
    admin = await make_user(roles=("admin",), with_totp=True)
    target = await make_user(roles=("viewer",))
    headers = await token_for(client, admin)
    ids = await _role_ids(client, headers)

    for user_id in (target.id, admin.id):  # neither for others nor for themselves
        response = await client.put(
            f"/api/v1/users/{user_id}/roles",
            headers=headers,
            json={"role_ids": [ids["superadmin"]]},
        )
        assert response.status_code == 403
    invite = await client.post(
        "/api/v1/users",
        headers=headers,
        json={"email": "x@example.com", "full_name": "X Persona", "role_ids": [ids["superadmin"]]},
    )
    assert invite.status_code == 403


async def test_admin_cannot_manage_a_superadmin_account(
    client: AsyncClient, make_user: UserFactory, superadmin: Account
) -> None:
    admin = await make_user(roles=("admin",), with_totp=True)
    headers = await token_for(client, admin)
    for method, path in (
        ("post", f"/api/v1/users/{superadmin.id}/disable"),
        ("patch", f"/api/v1/users/{superadmin.id}"),
        ("post", f"/api/v1/users/{superadmin.id}/mfa/reset"),
        ("post", f"/api/v1/users/{superadmin.id}/sessions/revoke"),
    ):
        response = await client.request(
            method, path, headers=headers, json={"full_name": "Hackeado"}
        )
        assert response.status_code == 403, path


async def test_cannot_grant_permissions_one_does_not_hold(
    client: AsyncClient, make_user: UserFactory, superadmin: Account
) -> None:
    root = await token_for(client, superadmin)
    lead_role = await _custom_role(
        client, root, "lead", ["identity.role.read", "identity.role.create", "identity.role.update"]
    )
    lead = await make_user()
    await client.put(f"/api/v1/users/{lead.id}/roles", headers=root, json={"role_ids": [lead_role]})
    headers = await token_for(client, lead)

    beyond = await client.post(
        "/api/v1/roles",
        headers=headers,
        json={"code": "spy", "name": "Spy", "permissions": ["audit.log.read"]},
    )
    assert beyond.status_code == 403
    within = await client.post(
        "/api/v1/roles",
        headers=headers,
        json={"code": "reader", "name": "Reader", "permissions": ["identity.role.read"]},
    )
    assert within.status_code == 201
    widen = await client.put(
        f"/api/v1/roles/{within.json()['id']}/permissions",
        headers=headers,
        json={"permissions": ["identity.role.read", "identity.user.disable"]},
    )
    assert widen.status_code == 403
    unknown = await client.post(
        "/api/v1/roles",
        headers=root,
        json={"code": "bad", "name": "Bad", "permissions": ["nope.x"]},
    )
    assert unknown.status_code == 400


async def test_last_superadmin_is_protected(client: AsyncClient, superadmin: Account) -> None:
    headers = await token_for(client, superadmin)
    self_disable = await client.post(f"/api/v1/users/{superadmin.id}/disable", headers=headers)
    assert self_disable.status_code == 409
    demote = await client.put(
        f"/api/v1/users/{superadmin.id}/roles", headers=headers, json={"role_ids": []}
    )
    assert demote.status_code == 409


# --- user administration ----------------------------------------------------------------------


async def test_list_users_with_filters_and_cursor(
    client: AsyncClient, make_user: UserFactory, superadmin: Account
) -> None:
    for index in range(5):
        await make_user(
            f"persona{index}@example.com", roles=("viewer",), full_name=f"Persona {index}"
        )
    headers = await token_for(client, superadmin)

    seen: list[str] = []
    cursor = None
    while True:
        params: dict[str, str | int] = {"limit": 2, "sort": "email"}
        if cursor:
            params["cursor"] = cursor
        page = (await client.get("/api/v1/users", headers=headers, params=params)).json()
        seen.extend(item["email"] for item in page["items"])
        cursor = page["next_cursor"]
        if not page["has_more"]:
            break
    assert seen == sorted(seen)
    assert len(seen) == 6

    ids = await _role_ids(client, headers)
    by_role = (
        await client.get("/api/v1/users", headers=headers, params={"role_id": ids["viewer"]})
    ).json()
    assert len(by_role["items"]) == 5
    search = (await client.get("/api/v1/users", headers=headers, params={"q": "persona3"})).json()
    assert [u["email"] for u in search["items"]] == ["persona3@example.com"]
    bad_sort = await client.get("/api/v1/users", headers=headers, params={"sort": "password_hash"})
    assert bad_sort.status_code == 400


async def test_disable_activate_and_unlock(
    client: AsyncClient, make_user: UserFactory, superadmin: Account, owner_engine: AsyncEngine
) -> None:
    root = await token_for(client, superadmin)
    target = await make_user()
    target_headers = bearer((await login(client, target))["access_token"])

    disabled = await client.post(f"/api/v1/users/{target.id}/disable", headers=root)
    assert disabled.json()["status"] == "disabled"
    assert (await client.get("/api/v1/auth/me", headers=target_headers)).status_code == 401
    assert (await client.post(f"/api/v1/users/{target.id}/unlock", headers=root)).status_code == 200

    activated = await client.post(f"/api/v1/users/{target.id}/activate", headers=root)
    assert activated.json()["status"] == "active"
    again = await client.post(f"/api/v1/users/{target.id}/activate", headers=root)
    assert again.status_code == 409

    async with owner_engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE identity.users SET locked_until = now() + interval '1 hour' WHERE id = :id"
            ),
            {"id": target.id},
        )
    locked = (await client.get(f"/api/v1/users/{target.id}", headers=root)).json()
    assert locked["locked_until"] is not None
    unlocked = (await client.post(f"/api/v1/users/{target.id}/unlock", headers=root)).json()
    assert unlocked["locked_until"] is None

    renamed = await client.patch(
        f"/api/v1/users/{target.id}", headers=root, json={"full_name": "Nuevo Nombre"}
    )
    assert renamed.json()["full_name"] == "Nuevo Nombre"
    assert (
        await client.get("/api/v1/users/00000000-0000-7000-8000-000000000000", headers=root)
    ).status_code == 404


async def test_reset_mfa_and_revoke_sessions(
    client: AsyncClient, make_user: UserFactory, superadmin: Account
) -> None:
    root = await token_for(client, superadmin)
    target = await make_user(roles=("admin",), with_totp=True)
    target_headers = bearer((await login(client, target))["access_token"])
    assert len((await client.get(f"/api/v1/users/{target.id}/sessions", headers=root)).json()) == 1

    revoked = await client.post(f"/api/v1/users/{target.id}/sessions/revoke", headers=root)
    assert revoked.json() == {"revoked": 1}
    assert (await client.get("/api/v1/auth/me", headers=target_headers)).status_code == 401

    assert (
        await client.post(f"/api/v1/users/{target.id}/mfa/reset", headers=root)
    ).status_code == 204
    assert (await client.get(f"/api/v1/users/{target.id}", headers=root)).json()[
        "mfa_enabled"
    ] is False
    relogin = await login(client, target)
    assert relogin["scope"] == "mfa_enrollment"  # role still requires MFA: enroll again
    own = await client.post(f"/api/v1/users/{superadmin.id}/mfa/reset", headers=root)
    assert own.status_code == 409


async def test_resend_invitation_only_for_invited_users(
    client: AsyncClient, make_user: UserFactory, superadmin: Account
) -> None:
    root = await token_for(client, superadmin)
    active = await make_user()
    response = await client.post(f"/api/v1/users/{active.id}/invitation", headers=root)
    assert response.status_code == 409


# --- roles & permissions -----------------------------------------------------------------------


async def test_roles_crud_and_guards(
    client: AsyncClient, make_user: UserFactory, superadmin: Account
) -> None:
    root = await token_for(client, superadmin)
    ids = await _role_ids(client, root)
    assert set(SYSTEM_ROLES) <= set(ids)

    role_id = await _custom_role(client, root, "auditor", ["audit.log.read"])
    duplicate = await client.post(
        "/api/v1/roles", headers=root, json={"code": "auditor", "name": "Dup"}
    )
    assert duplicate.status_code == 409

    updated = await client.patch(
        f"/api/v1/roles/{role_id}", headers=root, json={"name": "Auditoría", "requires_mfa": True}
    )
    assert (updated.json()["name"], updated.json()["requires_mfa"]) == ("Auditoría", True)
    permissions = await client.put(
        f"/api/v1/roles/{role_id}/permissions",
        headers=root,
        json={"permissions": ["audit.log.read", "identity.user.read"]},
    )
    assert permissions.json()["permissions"] == ["audit.log.read", "identity.user.read"]

    member = await make_user()
    await client.put(f"/api/v1/users/{member.id}/roles", headers=root, json={"role_ids": [role_id]})
    assert (await client.get(f"/api/v1/roles/{role_id}", headers=root)).json()["user_count"] == 1
    in_use = await client.delete(f"/api/v1/roles/{role_id}", headers=root)
    assert in_use.status_code == 409
    await client.put(f"/api/v1/users/{member.id}/roles", headers=root, json={"role_ids": []})
    assert (await client.delete(f"/api/v1/roles/{role_id}", headers=root)).status_code == 204
    assert (await client.get(f"/api/v1/roles/{role_id}", headers=root)).status_code == 404

    assert (await client.delete(f"/api/v1/roles/{ids['viewer']}", headers=root)).status_code == 409
    frozen = await client.patch(
        f"/api/v1/roles/{ids['superadmin']}", headers=root, json={"name": "Otro nombre"}
    )
    assert frozen.status_code == 409
    superadmin_role = (await client.get(f"/api/v1/roles/{ids['superadmin']}", headers=root)).json()
    assert superadmin_role["permissions"] == sorted(PERMISSIONS)


async def test_permission_catalog_matches_code_registry(
    client: AsyncClient, superadmin: Account
) -> None:
    root = await token_for(client, superadmin)
    catalog = (await client.get("/api/v1/permissions", headers=root)).json()
    assert {permission["code"] for permission in catalog} == PERMISSIONS
    me = (await client.get("/api/v1/auth/me", headers=root)).json()
    assert me["grants_all"] is True
    assert me["permissions"] == sorted(PERMISSIONS)


# --- audit viewer --------------------------------------------------------------------------------


async def test_audit_log_viewer(
    client: AsyncClient, make_user: UserFactory, superadmin: Account
) -> None:
    root = await token_for(client, superadmin)
    target = await make_user()
    await client.patch(
        f"/api/v1/users/{target.id}", headers=root, json={"full_name": "Cambio Auditado"}
    )

    page = (
        await client.get(
            "/api/v1/audit-log",
            headers=root,
            params={
                "entity_table": "identity.users",
                "entity_id": str(target.id),
                "action": "update",
            },
        )
    ).json()
    assert len(page["items"]) == 1
    entry = page["items"][0]
    assert entry["actor_user_id"] == str(superadmin.id)
    assert entry["after"]["full_name"] == "Cambio Auditado"
    assert entry["actor_ip"] == "127.0.0.1"

    newest_first = (await client.get("/api/v1/audit-log", headers=root, params={"limit": 3})).json()
    seqs = [item["chain_seq"] for item in newest_first["items"]]
    assert seqs == sorted(seqs, reverse=True)
    older = (
        await client.get(
            "/api/v1/audit-log",
            headers=root,
            params={"limit": 3, "cursor": newest_first["next_cursor"]},
        )
    ).json()
    assert older["items"][0]["chain_seq"] < seqs[-1]
    passwords = (
        await client.get(
            "/api/v1/audit-log", headers=root, params={"entity_table": "identity.users"}
        )
    ).json()
    assert all(
        (item["after"] or {}).get("password_hash") in (None, "***") for item in passwords["items"]
    )
