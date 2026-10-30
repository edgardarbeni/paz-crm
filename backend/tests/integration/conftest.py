"""Integration fixtures shared by modules: clean identity tables and Redis per test, users,
login helpers."""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pyotp
import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.db.session import build_sessionmaker
from app.core.mail import MemoryMailer
from app.modules.identity import repository as repo
from app.modules.identity.container import IdentityServices
from app.modules.identity.models import TotpCredential, User, UserGrant, UserStatus
from app.modules.identity.services.auth import TOTP_CONTEXT

PASSWORD = "correcto-caballo-bateria-grapa"
IDENTITY_TABLES = (
    "user_grant_sections",
    "user_grant_scopes",
    "refresh_tokens",
    "user_sessions",
    "recovery_codes",
    "totp_credentials",
    "password_reset_tokens",
    "user_invitations",
    "user_grants",
    "users",
)


@pytest.fixture(autouse=True)
async def clean_identity(owner_engine: AsyncEngine, redis_url: str) -> None:
    async with owner_engine.begin() as connection:
        tables = ", ".join(f"identity.{name}" for name in IDENTITY_TABLES)
        await connection.execute(text(f"TRUNCATE {tables} CASCADE"))
        await connection.execute(text("DELETE FROM identity.roles WHERE NOT is_system"))
    redis = Redis.from_url(redis_url)
    await redis.flushdb()
    await redis.aclose()


@dataclass
class Account:
    id: uuid.UUID
    email: str
    password: str = PASSWORD
    totp_secret: str | None = None
    _last_code_at: datetime | None = field(default=None, repr=False)

    def totp_code(self) -> str:
        """A fresh code each call: every call moves to a later step (anti-replay friendly)."""
        assert self.totp_secret is not None
        at = (
            datetime.now(UTC)
            if self._last_code_at is None
            else self._last_code_at + timedelta(seconds=30)
        )
        self._last_code_at = at
        return pyotp.TOTP(self.totp_secret).at(at)


UserFactory = Callable[..., Awaitable[Account]]


@pytest.fixture
def services(app: FastAPI) -> IdentityServices:
    identity: IdentityServices = app.state.identity
    return identity


@pytest.fixture
def mailer(app: FastAPI) -> MemoryMailer:
    outbox: MemoryMailer = app.state.mailer
    return outbox


@pytest.fixture
def db_session(owner_engine: AsyncEngine) -> Callable[[], AsyncSession]:
    return build_sessionmaker(owner_engine)


@pytest.fixture
def make_user(services: IdentityServices, db_session: Callable[[], AsyncSession]) -> UserFactory:
    async def factory(
        email: str | None = None,
        *,
        roles: tuple[str, ...] = (),
        status: UserStatus = UserStatus.ACTIVE,
        with_totp: bool = False,
        full_name: str = "Persona de Prueba",
    ) -> Account:
        email = email or f"user-{uuid.uuid4().hex[:8]}@example.com"
        async with db_session() as db:
            user = User(
                email=email,
                full_name=full_name,
                status=status,
                password_hash=services.passwords.hash(PASSWORD)
                if status is not UserStatus.INVITED
                else None,
            )
            db.add(user)
            await db.flush()
            assert user.id is not None
            for code in roles:
                role = await repo.role_by_code(db, code)
                assert role is not None, code
                assert role.id is not None
                db.add(UserGrant(user_id=user.id, role_id=role.id))
            secret = None
            if with_totp:
                secret = pyotp.random_base32(32)
                blob = services.cipher.encrypt(secret, context=TOTP_CONTEXT)
                db.add(
                    TotpCredential(
                        user_id=user.id,
                        secret_ciphertext=blob,
                        key_version=services.cipher.key_version(blob),
                        confirmed_at=datetime.now(UTC),
                    )
                )
            await db.commit()
            return Account(id=user.id, email=email, totp_secret=secret)

    return factory


async def login(
    client: AsyncClient, user: Account, *, password: str | None = None
) -> dict[str, object]:
    response = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": password or user.password}
    )
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    if body["status"] == "mfa_required":
        response = await client.post(
            "/api/v1/auth/mfa/verify",
            json={"mfa_token": body["mfa_token"], "code": user.totp_code()},
        )
        assert response.status_code == 200, response.text
        body = response.json()
    return body


def bearer(token: object) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def token_for(client: AsyncClient, user: Account) -> dict[str, str]:
    body = await login(client, user)
    assert body["scope"] == "full", body
    return bearer(body["access_token"])


async def set_scopes(
    client: AsyncClient,
    headers: dict[str, str],
    user_id: uuid.UUID,
    scopes: list[dict[str, Any]],
    *,
    expect: int = 200,
) -> Response:
    """Gives every manual grant of the user the same scopes (the pre-D-101 "user scope")."""
    grants = await client.get(f"/api/v1/users/{user_id}/grants", headers=headers)
    assert grants.status_code == 200, grants.text
    body = {
        "grants": [
            {"id": g["id"], "role_id": g["role"]["id"], "scopes": scopes}
            for g in grants.json()
            if g["origin"] == "manual"
        ]
    }
    response = await client.put(f"/api/v1/users/{user_id}/grants", headers=headers, json=body)
    assert response.status_code == expect, response.text
    return response


async def set_roles(
    client: AsyncClient,
    headers: dict[str, str],
    user_id: uuid.UUID,
    role_ids: list[str],
    *,
    scopes: list[dict[str, Any]] | None = None,
    expect: int = 200,
) -> Response:
    """Replaces the user's manual grants with one grant per role (all with `scopes`)."""
    body = {"grants": [{"role_id": role_id, "scopes": scopes or []} for role_id in role_ids]}
    response = await client.put(f"/api/v1/users/{user_id}/grants", headers=headers, json=body)
    assert response.status_code == expect, response.text
    return response


async def grant_of(client: AsyncClient, headers: dict[str, str], user_id: uuid.UUID) -> str:
    """The id of the user's only grant."""
    response = await client.get(f"/api/v1/users/{user_id}/grants", headers=headers)
    assert response.status_code == 200, response.text
    [grant] = response.json()
    grant_id: str = grant["id"]
    return grant_id
