import base64

import pytest

from app.core.crypto import (
    BlindIndexer,
    DecryptionError,
    EnvKeyProvider,
    FieldCipher,
    KeyConfigurationError,
    build_blind_indexer,
    build_field_cipher,
)
from app.core.crypto.keys import generate_key, parse_versioned_keys
from tests.support import TEST_BLIND_KEY, TEST_KEY_V1, TEST_KEY_V2, make_settings

KEYS = {1: b"1" * 32, 2: b"2" * 32}
CURP = "GODE561231HDFRRN09"


def cipher(active: int = 2, keys: dict[int, bytes] | None = None) -> FieldCipher:
    return FieldCipher(EnvKeyProvider(keys or KEYS, active))


def test_roundtrip_and_random_nonce() -> None:
    c = cipher()
    first = c.encrypt(CURP, context="people.persons.curp")
    second = c.encrypt(CURP, context="people.persons.curp")
    assert first != second
    assert CURP.encode() not in first
    assert c.decrypt(first, context="people.persons.curp") == CURP
    assert c.key_version(first) == 2


def test_ciphertext_is_bound_to_its_context() -> None:
    c = cipher()
    blob = c.encrypt(CURP, context="people.persons.curp")
    with pytest.raises(DecryptionError, match="context"):
        c.decrypt(blob, context="people.person_contacts.value")


@pytest.mark.parametrize("position", [-1, 8, 30])
def test_tampering_is_detected(position: int) -> None:
    c = cipher()
    blob = bytearray(c.encrypt(CURP, context="ctx"))
    blob[position] ^= 0x01
    with pytest.raises(DecryptionError):
        c.decrypt(bytes(blob), context="ctx")


@pytest.mark.parametrize(
    "blob", [b"", b"\x01\x00", b"\x02" + b"\x00" * 40, b"\x01\x00\x01\x00\x30abc"]
)
def test_malformed_ciphertexts(blob: bytes) -> None:
    with pytest.raises(DecryptionError):
        cipher().decrypt(blob, context="ctx")


def test_rotation_rewraps_only_the_data_key() -> None:
    old = cipher(active=1)
    blob_v1 = old.encrypt(CURP, context="ctx")
    assert old.key_version(blob_v1) == 1

    new = cipher(active=2)
    assert new.decrypt(blob_v1, context="ctx") == CURP  # old versions stay readable
    blob_v2 = new.rewrap(blob_v1)
    assert new.key_version(blob_v2) == 2
    assert blob_v2[-40:] == blob_v1[-40:]  # data ciphertext untouched
    assert new.decrypt(blob_v2, context="ctx") == CURP
    assert new.rewrap(blob_v2) is blob_v2

    retired = cipher(active=2, keys={2: KEYS[2]})
    with pytest.raises(KeyConfigurationError, match="version 1"):
        retired.decrypt(blob_v1, context="ctx")


def test_key_provider_validation() -> None:
    with pytest.raises(KeyConfigurationError, match="Active key version 3"):
        EnvKeyProvider(KEYS, 3)
    with pytest.raises(KeyConfigurationError, match="32 bytes"):
        EnvKeyProvider({1: b"short"}, 1)


@pytest.mark.parametrize(
    ("raw", "message"),
    [("", "No encryption keys"), ("abc", "version:base64key"), ("1:!!notb64", "base64")],
)
def test_parse_versioned_keys_errors(raw: str, message: str) -> None:
    with pytest.raises(KeyConfigurationError, match=message):
        parse_versioned_keys(raw)


def test_parse_versioned_keys_and_generate() -> None:
    assert parse_versioned_keys(f"1:{TEST_KEY_V1}, 2:{TEST_KEY_V2}") == KEYS
    assert len(base64.b64decode(generate_key())) == 32


def test_builders_from_settings() -> None:
    settings = make_settings()
    c = build_field_cipher(settings)
    assert c.decrypt(c.encrypt("x", context="c"), context="c") == "x"
    indexer = build_blind_indexer(settings)
    assert indexer.compute("x", domain="d") == BlindIndexer(
        base64.b64decode(TEST_BLIND_KEY)
    ).compute("x", domain="d")


def test_blind_index_is_deterministic_normalized_and_domain_separated() -> None:
    indexer = BlindIndexer(b"k" * 32)
    a = indexer.compute(" gode561231hdfrrn09 ", domain="curp")
    assert a == indexer.compute("GODE561231HDFRRN09", domain="curp")
    assert a != indexer.compute("GODE561231HDFRRN09", domain="phone")
    assert len(a) == 32
    with pytest.raises(ValueError, match="32 bytes"):
        BlindIndexer(b"short")
