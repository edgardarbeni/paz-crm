"""Refresh-token rotation, reuse detection, logout and session revocation."""

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.integration.identity.conftest import PASSWORD, UserFactory, bearer, login

REFRESH = "/api/v1/auth/refresh"


def _refresh_cookie(client: AsyncClient) -> str:
    value = client.cookies.get("paz_refresh", path="/api/v1/auth")
    assert value
    return value


async def test_refresh_rotates_the_token(client: AsyncClient, make_user: UserFactory) -> None:
    user = await make_user()
    first = await login(client, user)
    old_cookie = _refresh_cookie(client)

    response = await client.post(REFRESH)
    assert response.status_code == 200
    assert response.json()["access_token"] != first["access_token"]
    assert _refresh_cookie(client) != old_cookie
    me = await client.get("/api/v1/auth/me", headers=bearer(response.json()["access_token"]))
    assert me.status_code == 200


async def test_reusing_a_rotated_token_revokes_the_session(
    client: AsyncClient, make_user: UserFactory, owner_engine: AsyncEngine
) -> None:
    user = await make_user()
    await login(client, user)
    stolen = _refresh_cookie(client)
    rotated = (await client.post(REFRESH)).json()
    access = bearer(rotated["access_token"])

    client.cookies.clear()
    client.cookies.set("paz_refresh", stolen, path="/api/v1/auth")
    reuse = await client.post(REFRESH)
    assert reuse.status_code == 401
    assert "reuso" in reuse.json()["detail"]

    # Both the attacker's and the legitimate user's tokens are dead now.
    assert (await client.get("/api/v1/auth/me", headers=access)).status_code == 401
    async with owner_engine.connect() as connection:
        actions = set(
            (
                await connection.execute(
                    text(
                        "SELECT action FROM audit.audit_log WHERE action = 'refresh_reuse_detected'"
                    )
                )
            ).scalars()
        )
        reason = (
            await connection.execute(
                text("SELECT revoke_reason FROM identity.user_sessions WHERE user_id = :id"),
                {"id": user.id},
            )
        ).scalar_one()
    assert actions == {"refresh_reuse_detected"}
    assert reason == "refresh_reuse"


async def test_refresh_requires_cookie_and_allowed_origin(
    client: AsyncClient, make_user: UserFactory
) -> None:
    missing = await client.post(REFRESH)
    assert missing.status_code == 401
    assert missing.json()["code"] == "invalid-refresh-token"

    await login(client, await make_user())
    cross_site = await client.post(REFRESH, headers={"Origin": "https://evil.example.com"})
    assert cross_site.status_code == 403
    same_site = await client.post(REFRESH, headers={"Origin": "https://panel.test"})
    assert same_site.status_code == 200


async def test_logout_kills_access_and_refresh(client: AsyncClient, make_user: UserFactory) -> None:
    user = await make_user()
    headers = bearer((await login(client, user))["access_token"])
    cookie = _refresh_cookie(client)

    response = await client.post("/api/v1/auth/logout", headers=headers)
    assert response.status_code == 204
    assert 'paz_refresh=""' in response.headers["set-cookie"]
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401
    client.cookies.set("paz_refresh", cookie, path="/api/v1/auth")
    assert (await client.post(REFRESH)).status_code == 401


async def test_manage_own_sessions(client: AsyncClient, make_user: UserFactory) -> None:
    user = await make_user()
    phone = bearer((await login(client, user))["access_token"])
    laptop = bearer((await login(client, user))["access_token"])
    tablet = bearer((await login(client, user))["access_token"])

    listed = (await client.get("/api/v1/auth/sessions", headers=laptop)).json()
    assert len(listed) == 3
    assert sum(session["current"] for session in listed) == 1

    phone_id = (await client.get("/api/v1/auth/me", headers=phone)).json()["session_id"]
    assert (
        await client.delete(f"/api/v1/auth/sessions/{phone_id}", headers=laptop)
    ).status_code == 204
    assert (await client.get("/api/v1/auth/me", headers=phone)).status_code == 401

    others = await client.post("/api/v1/auth/sessions/revoke-others", headers=laptop)
    assert others.json() == {"revoked": 1}
    assert (await client.get("/api/v1/auth/me", headers=tablet)).status_code == 401
    assert (await client.get("/api/v1/auth/me", headers=laptop)).status_code == 200


async def test_cannot_revoke_someone_elses_session(
    client: AsyncClient, make_user: UserFactory
) -> None:
    alice, bob = await make_user(), await make_user()
    alice_headers = bearer((await login(client, alice))["access_token"])
    bob_headers = bearer((await login(client, bob))["access_token"])
    bob_session = (await client.get("/api/v1/auth/me", headers=bob_headers)).json()["session_id"]

    response = await client.delete(f"/api/v1/auth/sessions/{bob_session}", headers=alice_headers)
    assert response.status_code == 404
    assert (await client.get("/api/v1/auth/me", headers=bob_headers)).status_code == 200


async def test_expired_session_is_rejected(
    client: AsyncClient, make_user: UserFactory, owner_engine: AsyncEngine
) -> None:
    user = await make_user()
    headers = bearer((await login(client, user))["access_token"])
    async with owner_engine.begin() as connection:
        await connection.execute(
            text("UPDATE identity.user_sessions SET expires_at = now() WHERE user_id = :id"),
            {"id": user.id},
        )
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401
    assert (await client.post(REFRESH)).status_code == 401
    assert PASSWORD  # the user can log in again
    assert (
        await client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})
    ).status_code == 200
