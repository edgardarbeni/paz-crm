import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.core.errors import ConflictError
from app.modules.identity.bootstrap import create_superadmin
from app.modules.identity.permissions import PERMISSIONS, SYSTEM_ROLES
from tests.integration.conftest import PASSWORD


async def test_migrations_seed_the_registry(owner_engine: AsyncEngine) -> None:
    async with owner_engine.connect() as connection:
        permissions = set(
            (await connection.execute(text("SELECT code FROM identity.permissions"))).scalars()
        )
        roles = {
            row.code: (row.requires_mfa, row.grants_all, row.is_system)
            for row in await connection.execute(
                text("SELECT code, requires_mfa, grants_all, is_system FROM identity.roles")
            )
        }
    assert permissions == PERMISSIONS
    assert set(SYSTEM_ROLES) <= set(roles)
    assert roles["superadmin"] == (True, True, True)
    assert roles["admin"][0] is True
    assert roles["viewer"] == (False, False, True)


async def test_create_superadmin_bootstrap(
    integration_settings: Settings, client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    owner_settings = integration_settings.model_copy(
        update={"database_url": integration_settings.migrations_database_url}
    )
    user_id = await create_superadmin(owner_settings, "raiz@example.com", "Raíz", PASSWORD)

    login = await client.post(
        "/api/v1/auth/login", json={"email": "raiz@example.com", "password": PASSWORD}
    )
    assert login.json()["scope"] == "mfa_enrollment"  # must enroll TOTP first
    async with owner_engine.connect() as connection:
        action = (
            await connection.execute(
                text(
                    "SELECT action FROM audit.audit_log "
                    "WHERE entity_id = :id AND action LIKE 'superadmin%'"
                ),
                {"id": str(user_id)},
            )
        ).scalar_one()
    assert action == "superadmin_bootstrapped"

    with pytest.raises(ConflictError):
        await create_superadmin(owner_settings, "raiz@example.com", "Otra", PASSWORD)
