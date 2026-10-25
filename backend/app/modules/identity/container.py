"""Process-wide identity collaborators, built once at startup (`app.state.identity`)."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis

from app.core.config import Settings
from app.core.crypto import BlindIndexer, FieldCipher, build_blind_indexer, build_field_cipher
from app.core.mail import Mailer
from app.core.rate_limit import RateLimiter
from app.modules.identity.security.passwords import Passwords
from app.modules.identity.security.tokens import TokenService


@dataclass(frozen=True, slots=True)
class IdentityServices:
    settings: Settings
    passwords: Passwords
    tokens: TokenService
    cipher: FieldCipher
    indexer: BlindIndexer
    redis: "Redis"
    rate_limiter: RateLimiter
    mailer: Mailer


def build_identity_services(settings: Settings, redis: "Redis", mailer: Mailer) -> IdentityServices:
    return IdentityServices(
        settings=settings,
        passwords=Passwords(settings),
        tokens=TokenService(settings),
        cipher=build_field_cipher(settings),
        indexer=build_blind_indexer(settings),
        redis=redis,
        rate_limiter=RateLimiter(redis),
        mailer=mailer,
    )


def get_identity_services(request: Request) -> IdentityServices:
    services: IdentityServices = request.app.state.identity
    return services


ServicesDep = Annotated[IdentityServices, Depends(get_identity_services)]
