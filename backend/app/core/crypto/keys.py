"""Key providers for envelope encryption (D-32).

A provider wraps/unwraps per-record data keys (DEKs) with a versioned key-encryption key
(KEK). Development and tests use `EnvKeyProvider`; production plugs a KMS-backed provider
implementing the same protocol, without touching callers.
"""

import base64
import binascii
import os
from typing import Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_BYTES = 32
NONCE_BYTES = 12


class KeyConfigurationError(ValueError):
    pass


class KeyProvider(Protocol):
    @property
    def active_version(self) -> int: ...

    def wrap(self, data_key: bytes, *, version: int | None = None) -> tuple[int, bytes]:
        """Encrypts a data key. Returns (kek_version, wrapped_key)."""
        ...

    def unwrap(self, wrapped_key: bytes, *, version: int) -> bytes: ...


class EnvKeyProvider:
    """KEKs from an environment variable: ``"1:<base64>,2:<base64>"``."""

    def __init__(self, keys: dict[int, bytes], active_version: int) -> None:
        if active_version not in keys:
            raise KeyConfigurationError(f"Active key version {active_version} is not configured")
        for version, key in keys.items():
            if len(key) != KEY_BYTES:
                raise KeyConfigurationError(f"Key version {version} must be {KEY_BYTES} bytes")
        self._keys = dict(keys)
        self._active = active_version

    @classmethod
    def from_string(cls, raw: str, active_version: int) -> "EnvKeyProvider":
        return cls(parse_versioned_keys(raw), active_version)

    @property
    def active_version(self) -> int:
        return self._active

    def wrap(self, data_key: bytes, *, version: int | None = None) -> tuple[int, bytes]:
        version = self._active if version is None else version
        nonce = os.urandom(NONCE_BYTES)
        aad = _kek_aad(version)
        return version, nonce + AESGCM(self._kek(version)).encrypt(nonce, data_key, aad)

    def unwrap(self, wrapped_key: bytes, *, version: int) -> bytes:
        nonce, ciphertext = wrapped_key[:NONCE_BYTES], wrapped_key[NONCE_BYTES:]
        return AESGCM(self._kek(version)).decrypt(nonce, ciphertext, _kek_aad(version))

    def _kek(self, version: int) -> bytes:
        try:
            return self._keys[version]
        except KeyError:
            raise KeyConfigurationError(f"Key version {version} is not configured") from None


def _kek_aad(version: int) -> bytes:
    return f"paz:kek:v{version}".encode()


def parse_versioned_keys(raw: str) -> dict[int, bytes]:
    keys: dict[int, bytes] = {}
    for item in filter(None, (part.strip() for part in raw.split(","))):
        version_text, sep, encoded = item.partition(":")
        if not sep or not version_text.isdigit():
            raise KeyConfigurationError("Expected 'version:base64key' entries")
        try:
            keys[int(version_text)] = base64.b64decode(encoded, validate=True)
        except binascii.Error:
            raise KeyConfigurationError(f"Key version {version_text} is not valid base64") from None
    if not keys:
        raise KeyConfigurationError("No encryption keys configured")
    return keys


def generate_key() -> str:
    """Helper for `.env` bootstrapping: a random base64 32-byte key."""
    return base64.b64encode(os.urandom(KEY_BYTES)).decode()
