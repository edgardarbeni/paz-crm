"""Invitations, password reset and password change (D-35)."""

import re

from httpx import AsyncClient

from app.core.mail import MemoryMailer
from app.modules.identity.models import UserStatus
from tests.integration.identity.conftest import PASSWORD, UserFactory, bearer, login, token_for

NEW_PASSWORD = "otra-frase-larga-y-segura-2026"


def _token_from(mailer: MemoryMailer, *, to: str) -> str:
    message = next(m for m in reversed(mailer.outbox) if m.to == to)
    match = re.search(r"token=([\w%-]+)", message.text)
    assert match, message.text
    return match.group(1)


async def test_invitation_lifecycle(
    client: AsyncClient, make_user: UserFactory, mailer: MemoryMailer
) -> None:
    admin = await make_user(roles=("admin",), with_totp=True)
    headers = await token_for(client, admin)
    roles = (await client.get("/api/v1/roles", headers=headers)).json()
    viewer_id = next(role["id"] for role in roles if role["code"] == "viewer")

    invited = await client.post(
        "/api/v1/users",
        headers=headers,
        json={"email": "nueva@example.com", "full_name": "Nueva Persona", "role_ids": [viewer_id]},
    )
    assert invited.status_code == 201, invited.text
    assert invited.json()["status"] == UserStatus.INVITED
    assert [role["code"] for role in invited.json()["roles"]] == ["viewer"]

    message = mailer.outbox[-1]
    assert message.subject == "Invitación a PAZOS"
    assert "https://panel.test/aceptar-invitacion?token=" in message.text
    token = _token_from(mailer, to="nueva@example.com")

    info = await client.post("/api/v1/auth/invitations/inspect", json={"token": token})
    assert info.json()["email"] == "nueva@example.com"

    weak = await client.post(
        "/api/v1/auth/invitations/accept", json={"token": token, "password": "corta"}
    )
    assert weak.status_code == 400
    assert weak.json()["code"] == "weak-password"

    accepted = await client.post(
        "/api/v1/auth/invitations/accept",
        json={"token": token, "password": NEW_PASSWORD, "full_name": "Nueva P. Apellido"},
    )
    assert accepted.status_code == 204
    again = await client.post(
        "/api/v1/auth/invitations/accept", json={"token": token, "password": NEW_PASSWORD}
    )
    assert again.json()["code"] == "invalid-link"

    session = await client.post(
        "/api/v1/auth/login", json={"email": "nueva@example.com", "password": NEW_PASSWORD}
    )
    assert session.status_code == 200
    me = await client.get("/api/v1/auth/me", headers=bearer(session.json()["access_token"]))
    assert me.json()["full_name"] == "Nueva P. Apellido"


async def test_resending_an_invitation_invalidates_the_previous_link(
    client: AsyncClient, make_user: UserFactory, mailer: MemoryMailer
) -> None:
    admin = await make_user(roles=("admin",), with_totp=True)
    headers = await token_for(client, admin)
    created = await client.post(
        "/api/v1/users",
        headers=headers,
        json={"email": "otra@example.com", "full_name": "Otra Persona"},
    )
    first = _token_from(mailer, to="otra@example.com")
    resent = await client.post(f"/api/v1/users/{created.json()['id']}/invitation", headers=headers)
    assert resent.status_code == 200
    second = _token_from(mailer, to="otra@example.com")
    assert first != second

    old = await client.post("/api/v1/auth/invitations/inspect", json={"token": first})
    assert old.json()["code"] == "invalid-link"
    assert (
        await client.post("/api/v1/auth/invitations/inspect", json={"token": second})
    ).status_code == 200

    duplicate = await client.post(
        "/api/v1/users", headers=headers, json={"email": "otra@example.com", "full_name": "Dup"}
    )
    assert duplicate.status_code == 409


async def test_password_reset_flow(
    client: AsyncClient, make_user: UserFactory, mailer: MemoryMailer
) -> None:
    user = await make_user()
    old_session = bearer((await login(client, user))["access_token"])

    unknown = await client.post("/api/v1/auth/password/forgot", json={"email": "nadie@example.com"})
    assert unknown.status_code == 202
    assert mailer.outbox == []

    known = await client.post("/api/v1/auth/password/forgot", json={"email": user.email})
    assert known.status_code == 202
    token = _token_from(mailer, to=user.email)

    reset = await client.post(
        "/api/v1/auth/password/reset", json={"token": token, "new_password": NEW_PASSWORD}
    )
    assert reset.status_code == 204
    assert (await client.get("/api/v1/auth/me", headers=old_session)).status_code == 401
    reused = await client.post(
        "/api/v1/auth/password/reset", json={"token": token, "new_password": NEW_PASSWORD}
    )
    assert reused.json()["code"] == "invalid-link"

    old_password = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": PASSWORD}
    )
    assert old_password.status_code == 401
    new_password = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": NEW_PASSWORD}
    )
    assert new_password.status_code == 200


async def test_change_password_keeps_only_the_current_session(
    client: AsyncClient, make_user: UserFactory
) -> None:
    user = await make_user()
    other = bearer((await login(client, user))["access_token"])
    current = bearer((await login(client, user))["access_token"])

    wrong = await client.post(
        "/api/v1/auth/password/change",
        headers=current,
        json={"current_password": "no-es-la-mia", "new_password": NEW_PASSWORD},
    )
    assert wrong.status_code == 401
    contains_email = await client.post(
        "/api/v1/auth/password/change",
        headers=current,
        json={"current_password": PASSWORD, "new_password": f"{user.email.split('@')[0]}-segura"},
    )
    assert contains_email.json()["code"] == "weak-password"

    ok = await client.post(
        "/api/v1/auth/password/change",
        headers=current,
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert ok.status_code == 204
    assert (await client.get("/api/v1/auth/me", headers=current)).status_code == 200
    assert (await client.get("/api/v1/auth/me", headers=other)).status_code == 401
