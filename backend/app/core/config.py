"""Application settings, loaded only from environment variables (or a secrets manager
that injects them). Every variable is documented in the repository's `.env.example`."""

from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Literal

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

    # Public URL of the panel, used to build links in e-mails (invitations, password reset).
    public_base_url: str = "https://localhost"

    # Authentication settings: see decisions D-33 to D-35 and D-48.
    jwt_secret: SecretStr
    jwt_issuer: str = "pazos"
    jwt_audience: str = "pazos-api"
    access_token_ttl_seconds: int = 900
    mfa_challenge_ttl_seconds: int = 300
    refresh_token_ttl_seconds: int = 7 * 24 * 3600
    session_absolute_ttl_seconds: int = 30 * 24 * 3600
    refresh_cookie_name: str = "paz_refresh"
    refresh_cookie_secure: bool = True
    invitation_ttl_seconds: int = 72 * 3600
    password_reset_ttl_seconds: int = 30 * 60
    password_min_length: int = 12
    argon2_time_cost: int = 3
    argon2_memory_cost_kib: int = 65_536
    argon2_parallelism: int = 4
    max_failed_logins: int = 5
    lockout_seconds: int = 15 * 60
    login_rate_limit_per_ip: int = 20
    login_rate_limit_window_seconds: int = 60
    totp_issuer: str = "PAZOS"

    # E-mail (D-35). "memory" keeps messages in-process (tests); "console" logs them.
    mail_backend: Literal["smtp", "console", "memory"] = "smtp"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_starttls: bool = False
    smtp_use_tls: bool = False
    mail_from: str = "PAZOS <no-reply@localhost>"

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
        return as_asyncpg_url(str(self.database_url))

    @property
    def async_migrations_database_url(self) -> str:
        return as_asyncpg_url(str(self.migrations_database_url or self.database_url))


def as_asyncpg_url(url: str) -> str:
    scheme, _, rest = url.partition("://")
    if scheme in {"postgres", "postgresql", "postgresql+psycopg"}:
        return f"postgresql+asyncpg://{rest}"
    return url


@lru_cache
def get_settings() -> Settings:
    return Settings()  # values come from the environment
