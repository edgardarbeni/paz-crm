"""Field-level envelope encryption with AES-256-GCM (D-31, D-32).

Each value gets its own random data key (DEK). The DEK is wrapped by the provider's KEK and
stored next to the ciphertext, so rotating the KEK only rewraps DEKs (`rewrap`) and never
re-encrypts the data itself.

Binary layout (all integers big-endian)::

    magic(1)=0x01 | kek_version(2) | wrapped_len(2) | wrapped_dek | nonce(12) | ciphertext+tag

`context` is bound as AES-GCM associated data (e.g. ``"people.persons.curp"``) so a
ciphertext copied into another column or table fails to decrypt.
"""

import os
import struct

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.crypto.keys import KEY_BYTES, NONCE_BYTES, KeyProvider

FORMAT_V1 = 0x01
_HEADER = struct.Struct(">BHH")


class DecryptionError(ValueError):
    pass


class FieldCipher:
    def __init__(self, provider: KeyProvider) -> None:
        self._provider = provider

    def encrypt(self, plaintext: str, *, context: str) -> bytes:
        data_key = os.urandom(KEY_BYTES)
        version, wrapped = self._provider.wrap(data_key)
        nonce = os.urandom(NONCE_BYTES)
        ciphertext = AESGCM(data_key).encrypt(nonce, plaintext.encode(), context.encode())
        return _HEADER.pack(FORMAT_V1, version, len(wrapped)) + wrapped + nonce + ciphertext

    def decrypt(self, blob: bytes, *, context: str) -> str:
        version, wrapped, nonce, ciphertext = _split(blob)
        try:
            data_key = self._provider.unwrap(wrapped, version=version)
            return AESGCM(data_key).decrypt(nonce, ciphertext, context.encode()).decode()
        except InvalidTag:
            raise DecryptionError("Ciphertext is corrupt or bound to another context") from None

    def key_version(self, blob: bytes) -> int:
        return _split(blob)[0]

    def rewrap(self, blob: bytes) -> bytes:
        """Re-encrypts only the data key with the active KEK (key rotation)."""
        version, wrapped, nonce, ciphertext = _split(blob)
        if version == self._provider.active_version:
            return blob
        try:
            data_key = self._provider.unwrap(wrapped, version=version)
        except InvalidTag:
            raise DecryptionError("Wrapped data key is corrupt") from None
        new_version, new_wrapped = self._provider.wrap(data_key)
        return (
            _HEADER.pack(FORMAT_V1, new_version, len(new_wrapped))
            + new_wrapped
            + nonce
            + ciphertext
        )


def _split(blob: bytes) -> tuple[int, bytes, bytes, bytes]:
    if len(blob) < _HEADER.size:
        raise DecryptionError("Ciphertext is too short")
    magic, version, wrapped_len = _HEADER.unpack_from(blob)
    if magic != FORMAT_V1:
        raise DecryptionError(f"Unknown ciphertext format {magic:#x}")
    start = _HEADER.size
    wrapped = blob[start : start + wrapped_len]
    nonce = blob[start + wrapped_len : start + wrapped_len + NONCE_BYTES]
    ciphertext = blob[start + wrapped_len + NONCE_BYTES :]
    if len(wrapped) != wrapped_len or len(nonce) != NONCE_BYTES or not ciphertext:
        raise DecryptionError("Ciphertext is truncated")
    return version, wrapped, nonce, ciphertext
