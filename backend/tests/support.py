"""Test helpers shared by unit and integration tests."""

import base64
import os

from app.core.config import Settings

TEST_KEY_V1 = base64.b64encode(b"1" * 32).decode()
TEST_KEY_V2 = base64.b64encode(b"2" * 32).decode()
TEST_BLIND_KEY = base64.b64encode(b"b" * 32).decode()


def make_settings(**overrides: object) -> Settings:
    """Settings for tests that do not need real services (URLs are never dialed)."""
    values: dict[str, object] = {
        "environment": "test",
        "database_url": "postgresql://paz_app:paz_app@127.0.0.1:1/paz",
        "redis_url": "redis://127.0.0.1:1/0",
        "encryption_keys": f"1:{TEST_KEY_V1},2:{TEST_KEY_V2}",
        "encryption_active_key_version": 2,
        "blind_index_key": TEST_BLIND_KEY,
        "cors_allowed_origins": ["https://panel.test"],
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def pg_image() -> str:
    return os.environ.get("PAZ_TEST_PG_IMAGE", "paz/postgres-postgis:18")
