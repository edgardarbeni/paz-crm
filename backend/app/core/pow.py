"""Self-hosted proof of work for public forms (D-86, ALTCHA-style, no third parties).

The server issues a challenge: `sha256(salt + number)` for a secret random `number` below
`max_number`, signed with HMAC. The browser finds the number by brute force (milliseconds for a
person, real cost for a bot farm) and sends it back. The signature makes challenges unforgeable,
the salt carries issue and expiry times, and Redis rejects a solved challenge used twice.
"""

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from urllib.parse import parse_qs

from redis.asyncio import Redis

from app.core.config import Settings
from app.core.errors import BadRequestError

ALGORITHM = "SHA-256"
DEFAULT_MAX_NUMBER = 100_000
DEFAULT_TTL_SECONDS = 15 * 60


class InvalidChallengeError(BadRequestError):
    code = "invalid-challenge"
    title = "La verificación anti-bots no es válida"


@dataclass(frozen=True, slots=True)
class Challenge:
    algorithm: str
    challenge: str
    salt: str
    signature: str
    max_number: int


@dataclass(frozen=True, slots=True)
class Solution:
    challenge: str
    salt: str
    number: int
    signature: str


def secret_key(settings: Settings) -> bytes:
    """Dedicated key when configured; otherwise derived from the JWT secret (domain-separated)."""
    if settings.pow_secret is not None:
        return settings.pow_secret.get_secret_value().encode()
    return hmac.new(
        settings.jwt_secret.get_secret_value().encode(), b"paz-proof-of-work", hashlib.sha256
    ).digest()


def _digest(salt: str, number: int) -> str:
    return hashlib.sha256(f"{salt}{number}".encode()).hexdigest()


def _sign(key: bytes, challenge: str) -> str:
    return hmac.new(key, challenge.encode(), hashlib.sha256).hexdigest()


def create_challenge(
    key: bytes, *, max_number: int = DEFAULT_MAX_NUMBER, ttl_seconds: int = DEFAULT_TTL_SECONDS
) -> Challenge:
    now = int(time.time())
    salt = f"{secrets.token_hex(12)}?issued={now}&expires={now + ttl_seconds}&"
    challenge = _digest(salt, secrets.randbelow(max_number))
    return Challenge(ALGORITHM, challenge, salt, _sign(key, challenge), max_number)


def solve(challenge: Challenge) -> int:
    """Brute force, as the browser does (used by tests and tools)."""
    for number in range(challenge.max_number + 1):
        if _digest(challenge.salt, number) == challenge.challenge:
            return number
    raise ValueError("unsolvable challenge")


async def verify(redis: Redis, key: bytes, solution: Solution) -> int:
    """Checks the solution and burns it. Returns the issue time (seconds since the epoch), which
    callers use to require a minimum fill time."""
    if not hmac.compare_digest(_sign(key, solution.challenge), solution.signature):
        raise InvalidChallengeError("La verificación no corresponde a este servidor.")
    if not hmac.compare_digest(_digest(solution.salt, solution.number), solution.challenge):
        raise InvalidChallengeError("La verificación no está resuelta.")
    params = parse_qs(solution.salt.partition("?")[2])
    try:
        issued, expires = int(params["issued"][0]), int(params["expires"][0])
    except (KeyError, ValueError):
        raise InvalidChallengeError("La verificación está mal formada.") from None
    now = int(time.time())
    if now > expires:
        raise InvalidChallengeError("La verificación expiró; vuelve a cargar el formulario.")
    burned = await redis.set(f"pow:{solution.challenge}", "1", nx=True, ex=max(expires - now, 1))
    if not burned:
        raise InvalidChallengeError("La verificación ya se usó.")
    return issued
