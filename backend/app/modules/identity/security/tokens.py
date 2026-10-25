"""Access tokens (JWT), MFA challenge tokens (JWT) and opaque single-use tokens.

- Access token: short-lived JWT sent as ``Authorization: Bearer``; carries the session id
  (``sid``) so revoking a session takes effect immediately (Redis check, see dependencies).
- MFA challenge: 5-minute JWT returned after a correct password when TOTP is enrolled.
- Opaque tokens (refresh, invitation, password reset): 256-bit random values; only their
  SHA-256 is stored.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import jwt

from app.core.config import Settings
from app.core.errors import UnauthorizedError

_ALGORITHM = "HS256"


class TokenScope(StrEnum):
    FULL = "full"
    # Password accepted but a role requires MFA and the user has not enrolled TOTP yet:
    # only MFA-enrollment endpoints are allowed.
    MFA_ENROLLMENT = "mfa_enrollment"


@dataclass(frozen=True, slots=True)
class AccessClaims:
    user_id: uuid.UUID
    session_id: uuid.UUID
    scope: TokenScope
    auth_methods: tuple[str, ...]


class InvalidTokenError(UnauthorizedError):
    code = "invalid-token"
    title = "Token inválido o expirado"


class TokenService:
    def __init__(self, settings: Settings) -> None:
        self._secret = settings.jwt_secret.get_secret_value()
        self._issuer = settings.jwt_issuer
        self._audience = settings.jwt_audience
        self.access_ttl = timedelta(seconds=settings.access_token_ttl_seconds)
        self._mfa_ttl = timedelta(seconds=settings.mfa_challenge_ttl_seconds)

    def issue_access(
        self,
        *,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        scope: TokenScope,
        auth_methods: list[str],
    ) -> str:
        now = datetime.now(UTC)
        payload = {
            "iss": self._issuer,
            "aud": self._audience,
            "sub": str(user_id),
            "sid": str(session_id),
            "typ": "access",
            "scope": scope.value,
            "amr": auth_methods,
            "iat": now,
            "exp": now + self.access_ttl,
            "jti": secrets.token_hex(8),
        }
        return jwt.encode(payload, self._secret, algorithm=_ALGORITHM)

    def decode_access(self, token: str) -> AccessClaims:
        payload = self._decode(token, expected_type="access")
        try:
            return AccessClaims(
                user_id=uuid.UUID(payload["sub"]),
                session_id=uuid.UUID(payload["sid"]),
                scope=TokenScope(payload["scope"]),
                auth_methods=tuple(payload.get("amr", ())),
            )
        except (KeyError, ValueError):
            raise InvalidTokenError() from None

    def issue_mfa_challenge(self, *, user_id: uuid.UUID) -> str:
        now = datetime.now(UTC)
        payload = {
            "iss": self._issuer,
            "aud": self._audience,
            "sub": str(user_id),
            "typ": "mfa_challenge",
            "iat": now,
            "exp": now + self._mfa_ttl,
            "jti": secrets.token_hex(8),
        }
        return jwt.encode(payload, self._secret, algorithm=_ALGORITHM)

    def decode_mfa_challenge(self, token: str) -> uuid.UUID:
        payload = self._decode(token, expected_type="mfa_challenge")
        try:
            return uuid.UUID(payload["sub"])
        except (KeyError, ValueError):
            raise InvalidTokenError() from None

    def _decode(self, token: str, *, expected_type: str) -> dict[str, Any]:
        try:
            payload: dict[str, Any] = jwt.decode(
                token,
                self._secret,
                algorithms=[_ALGORITHM],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "iat", "sub", "typ"]},
            )
        except jwt.PyJWTError:
            raise InvalidTokenError() from None
        if payload.get("typ") != expected_type:
            raise InvalidTokenError()
        return payload


def new_opaque_token() -> tuple[str, bytes]:
    """Returns (token for the client, hash to store)."""
    token = secrets.token_urlsafe(32)
    return token, hash_opaque_token(token)


def hash_opaque_token(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()
