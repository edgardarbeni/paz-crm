"""Application settings, loaded only from environment variables (or a secrets manager
that injects them). Every variable is documented in the repository's `.env.example`."""

from enum import StrEnum
from functools import lru_cache
from typing import Annotated

from pydantic import Field, PostgresDsn, RedisDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PAZ_", extra="ignore", frozen=True)

    environment: Environment = Environment.DEVELOPMENT
    service_name: str = "paz-api"
    log_level: str = "INFO"

    # API surface
    api_docs_enabled: bool = True
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # Databases. The application connects with a least-privilege role; migrations use the owner.
    database_url: PostgresDsn
    migrations_database_url: PostgresDsn | None = None
    database_app_role: str = "paz_app"
    database_pool_size: int = 10
    database_max_overflow: int = 10
    database_statement_timeout_ms: int = 15_000

    redis_url: RedisDsn

    # Field-level encryption (D-31, D-32): "version:base64key" pairs, comma separated.
    encryption_keys: SecretStr
    encryption_active_key_version: int
    blind_index_key: SecretStr

    # Observability
    otel_exporter_otlp_endpoint: str | None = None

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION

    @property
    def async_database_url(self) -> str:
        return _as_asyncpg(str(self.database_url))

    @property
    def async_migrations_database_url(self) -> str:
        return _as_asyncpg(str(self.migrations_database_url or self.database_url))


def _as_asyncpg(url: str) -> str:
    scheme, _, rest = url.partition("://")
    if scheme in {"postgres", "postgresql", "postgresql+psycopg"}:
        return f"postgresql+asyncpg://{rest}"
    return url


@lru_cache
def get_settings() -> Settings:
    return Settings()  # values come from the environment
