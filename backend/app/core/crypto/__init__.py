import base64
from functools import lru_cache

from app.core.config import Settings, get_settings
from app.core.crypto.blind_index import BlindIndexer
from app.core.crypto.envelope import DecryptionError, FieldCipher
from app.core.crypto.keys import EnvKeyProvider, KeyConfigurationError, KeyProvider

__all__ = [
    "BlindIndexer",
    "DecryptionError",
    "EnvKeyProvider",
    "FieldCipher",
    "KeyConfigurationError",
    "KeyProvider",
    "build_blind_indexer",
    "build_field_cipher",
    "get_blind_indexer",
    "get_field_cipher",
]


def build_field_cipher(settings: Settings) -> FieldCipher:
    provider = EnvKeyProvider.from_string(
        settings.encryption_keys.get_secret_value(), settings.encryption_active_key_version
    )
    return FieldCipher(provider)


def build_blind_indexer(settings: Settings) -> BlindIndexer:
    return BlindIndexer(base64.b64decode(settings.blind_index_key.get_secret_value()))


@lru_cache
def get_field_cipher() -> FieldCipher:
    return build_field_cipher(get_settings())


@lru_cache
def get_blind_indexer() -> BlindIndexer:
    return build_blind_indexer(get_settings())
