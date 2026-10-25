"""Single-use recovery codes: 10 codes of 80 random bits (XXXX-XXXX-XXXX-XXXX, Crockford-like
base32 without ambiguous characters). High entropy allows a keyed HMAC instead of Argon2, so
checking all codes on login stays cheap."""

import secrets

from app.core.crypto import BlindIndexer

COUNT = 10
_ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ23456789"  # no 0/O, 1/I/L, U
_GROUPS, _GROUP_LENGTH = 4, 4
_DOMAIN = "identity.recovery_code"


def generate() -> list[str]:
    return [
        "-".join(
            "".join(secrets.choice(_ALPHABET) for _ in range(_GROUP_LENGTH)) for _ in range(_GROUPS)
        )
        for _ in range(COUNT)
    ]


def normalize(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


def hash_code(indexer: BlindIndexer, code: str) -> bytes:
    return indexer.compute(normalize(code), domain=_DOMAIN)
