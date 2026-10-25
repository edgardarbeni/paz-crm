"""Login, lockout, rate limiting and the second factor (TOTP and recovery codes)."""

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.modules.identity.models import UserStatus
from tests.integration.identity.conftest import PASSWORD, UserFactory, bearer, login

LOGIN = "/api/v1/auth/login"
GENERIC = "Credenciales inválidas o cuenta bloqueada temporalmente."


async def _audit_actions(engine: AsyncEngine, entity_id: object) -> list[str]:
    async with engine.connect() as connection:
        rows = await connection.execute(
            text("SELECT action FROM audit.audit_log WHERE entity_id = :id ORDER BY chain_seq"),
            {"id": str(entity_id)},
        )
        return list(rows.scalars())


async def test_login_issues_tokens_and_secure_cookie(
    client: AsyncClient, make_user: UserFactory
) -> None:
    user = await make_user(roles=("viewer",))
    response = await client.post(LOGIN, json={"email": user.email, "password": PASSWORD})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "authenticated"
    assert body["scope"] == "full"
    assert body["expires_in"] == 900
    cookie = response.headers["set-cookie"]
    for flag in ("paz_refresh=", "HttpOnly", "Secure", "SameSite=strict", "Path=/api/v1/auth"):
        assert flag in cookie

    me = await client.get("/api/v1/auth/me", headers=bearer(body["access_token"]))
    assert me.status_code == 200
    assert me.json()["email"] == user.email
    assert me.json()["roles"][0]["code"] == "viewer"
    assert me.json()["mfa"] == {"enabled": False, "required": False}


async def test_failures_are_indistinguishable(client: AsyncClient, make_user: UserFactory) -> None:
    active = await make_user()
    invited = await make_user(status=UserStatus.INVITED)
    disabled = await make_user(status=UserStatus.DISABLED)
    attempts = [
        {"email": active.email, "password": "otra-contraseña-mala"},
        {"email": "nadie@example.com", "password": PASSWORD},
        {"email": invited.email, "password": PASSWORD},
        {"email": disabled.email, "password": PASSWORD},
    ]
    bodies = []
    for attempt in attempts:
        response = await client.post(LOGIN, json=attempt)
        assert response.status_code == 401
        body = response.json()
        bodies.append((body["code"], body["detail"]))
    assert set(bodies) == {("invalid-credentials", GENERIC)}


async def test_lockout_after_repeated_failures(
    client: AsyncClient, make_user: UserFactory, owner_engine: AsyncEngine
) -> None:
    user = await make_user()
    for _ in range(5):
        assert (
            await client.post(LOGIN, json={"email": user.email, "password": "mala-mala-mala"})
        ).status_code == 401

    locked = await client.post(LOGIN, json={"email": user.email, "password": PASSWORD})
    assert locked.status_code == 401
    assert locked.json()["detail"] == GENERIC
    assert "account_locked" in await _audit_actions(owner_engine, user.id)

    async with owner_engine.begin() as connection:
        await connection.execute(
            text("UPDATE identity.users SET locked_until = now() - interval '1 s' WHERE id = :id"),
            {"id": user.id},
        )
    assert (
        await client.post(LOGIN, json={"email": user.email, "password": PASSWORD})
    ).status_code == 200


async def test_rate_limit_per_email(client: AsyncClient) -> None:
    for _ in range(10):
        response = await client.post(
            LOGIN, json={"email": "objetivo@example.com", "password": "x" * 12}
        )
        assert response.status_code == 401
    limited = await client.post(LOGIN, json={"email": "objetivo@example.com", "password": "x" * 12})
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) > 0
    assert limited.json()["code"] == "too-many-requests"


async def test_protected_endpoints_require_a_valid_token(client: AsyncClient) -> None:
    missing = await client.get("/api/v1/auth/me")
    assert missing.status_code == 401
    assert missing.headers["www-authenticate"] == "Bearer"
    forged = await client.get("/api/v1/auth/me", headers=bearer("eyJhbGciOiJub25lIn0.e30."))
    assert forged.status_code == 401
    assert forged.json()["code"] == "invalid-token"


async def test_role_requiring_mfa_forces_enrollment(
    client: AsyncClient, make_user: UserFactory
) -> None:
    admin = await make_user(roles=("admin",))
    body = await login(client, admin)
    assert body["scope"] == "mfa_enrollment"
    limited = bearer(body["access_token"])

    blocked = await client.get("/api/v1/users", headers=limited)
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "mfa-enrollment-required"
    me = await client.get("/api/v1/auth/me", headers=limited)
    assert me.json()["mfa"] == {"enabled": False, "required": True}

    setup = (await client.post("/api/v1/auth/mfa/totp/setup", headers=limited)).json()
    assert setup["otpauth_uri"].startswith("otpauth://totp/PAZOS:")
    assert setup["qr_svg"].startswith("data:image/svg+xml")
    admin.totp_secret = setup["secret"]

    wrong = await client.post(
        "/api/v1/auth/mfa/totp/confirm", headers=limited, json={"code": "000000"}
    )
    assert wrong.status_code == 400
    confirmed = await client.post(
        "/api/v1/auth/mfa/totp/confirm", headers=limited, json={"code": admin.totp_code()}
    )
    assert confirmed.status_code == 200
    codes = confirmed.json()["recovery_codes"]
    assert len(codes) == 10
    assert len(set(codes)) == 10

    upgraded = bearer(confirmed.json()["access_token"])
    assert (await client.get("/api/v1/users", headers=upgraded)).status_code == 200

    # From now on the password alone is not enough.
    second = (await client.post(LOGIN, json={"email": admin.email, "password": PASSWORD})).json()
    assert second["status"] == "mfa_required"
    verified = await client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": second["mfa_token"], "code": admin.totp_code()},
    )
    assert verified.status_code == 200
    assert verified.json()["scope"] == "full"


async def test_totp_codes_cannot_be_replayed(client: AsyncClient, make_user: UserFactory) -> None:
    user = await make_user(with_totp=True)
    code = user.totp_code()
    challenge = (await client.post(LOGIN, json={"email": user.email, "password": PASSWORD})).json()
    ok = await client.post(
        "/api/v1/auth/mfa/verify", json={"mfa_token": challenge["mfa_token"], "code": code}
    )
    assert ok.status_code == 200

    challenge = (await client.post(LOGIN, json={"email": user.email, "password": PASSWORD})).json()
    replay = await client.post(
        "/api/v1/auth/mfa/verify", json={"mfa_token": challenge["mfa_token"], "code": code}
    )
    assert replay.status_code == 401


async def test_recovery_codes_are_single_use(client: AsyncClient, make_user: UserFactory) -> None:
    user = await make_user(with_totp=True)
    token = await login(client, user)
    codes = (
        await client.post(
            "/api/v1/auth/mfa/recovery-codes",
            headers=bearer(token["access_token"]),
            json={"code": user.totp_code()},
        )
    ).json()["recovery_codes"]

    challenge = (await client.post(LOGIN, json={"email": user.email, "password": PASSWORD})).json()
    used = await client.post(
        "/api/v1/auth/mfa/verify",
        json={
            "mfa_token": challenge["mfa_token"],
            "recovery_code": codes[0].lower().replace("-", ""),
        },
    )
    assert used.status_code == 200

    challenge = (await client.post(LOGIN, json={"email": user.email, "password": PASSWORD})).json()
    again = await client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": challenge["mfa_token"], "recovery_code": codes[0]},
    )
    assert again.status_code == 401


async def test_mfa_verify_rejects_bad_input(client: AsyncClient, make_user: UserFactory) -> None:
    user = await make_user(with_totp=True)
    challenge = (await client.post(LOGIN, json={"email": user.email, "password": PASSWORD})).json()
    both = await client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": challenge["mfa_token"], "code": "123456", "recovery_code": "AAAA"},
    )
    assert both.status_code == 401
    tampered = await client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": challenge["mfa_token"] + "x", "code": "123456"},
    )
    assert tampered.json()["code"] == "invalid-token"
    # An access token is not an MFA challenge (token type confusion).
    other = await make_user()
    access = (await login(client, other))["access_token"]
    confused = await client.post(
        "/api/v1/auth/mfa/verify", json={"mfa_token": access, "code": "123456"}
    )
    assert confused.json()["code"] == "invalid-token"


async def test_disable_totp_only_when_role_allows(
    client: AsyncClient, make_user: UserFactory
) -> None:
    plain = await make_user(with_totp=True, roles=("viewer",))
    headers = bearer((await login(client, plain))["access_token"])
    bad_password = await client.post(
        "/api/v1/auth/mfa/totp/disable",
        headers=headers,
        json={"password": "mala-mala-mala", "code": "000000"},
    )
    assert bad_password.status_code == 401
    ok = await client.post(
        "/api/v1/auth/mfa/totp/disable",
        headers=headers,
        json={"password": PASSWORD, "code": plain.totp_code()},
    )
    assert ok.status_code == 204

    admin = await make_user(with_totp=True, roles=("admin",))
    admin_headers = bearer((await login(client, admin))["access_token"])
    refused = await client.post(
        "/api/v1/auth/mfa/totp/disable",
        headers=admin_headers,
        json={"password": PASSWORD, "code": admin.totp_code()},
    )
    assert refused.status_code == 409


async def test_setup_rejected_when_already_enrolled(
    client: AsyncClient, make_user: UserFactory
) -> None:
    user = await make_user(with_totp=True)
    headers = bearer((await login(client, user))["access_token"])
    assert (await client.post("/api/v1/auth/mfa/totp/setup", headers=headers)).status_code == 409
    no_pending = await client.post(
        "/api/v1/auth/mfa/totp/confirm", headers=headers, json={"code": "123456"}
    )
    assert no_pending.status_code == 409
