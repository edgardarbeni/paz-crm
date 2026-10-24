"""Blind indexes: deterministic HMAC-SHA256 over a normalized value (D-31).

They allow uniqueness constraints and exact-match lookups on encrypted columns (CURP,
phone numbers) without storing the plaintext. `domain` separates indexes so the same value
produces unrelated hashes in different columns.

Rotating the blind-index key requires recomputing every index (documented technical debt).
"""

import hashlib
import hmac
import unicodedata


class BlindIndexer:
    def __init__(self, key: bytes) -> None:
        if len(key) < 32:
            raise ValueError("Blind index key must be at least 32 bytes")
        self._key = key

    def compute(self, value: str, *, domain: str) -> bytes:
        message = f"{domain}\x1f{normalize(value)}".encode()
        return hmac.new(self._key, message, hashlib.sha256).digest()


def normalize(value: str) -> str:
    """NFKC, trimmed, uppercase, without inner whitespace. Field-specific normalization
    (e.g. keeping only digits of a phone number) is the caller's job."""
    return "".join(unicodedata.normalize("NFKC", value).upper().split())
