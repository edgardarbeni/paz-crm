"""S3-compatible object storage (D-38) against a real S3 server (SeaweedFS)."""

import uuid
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from app.core.errors import ServiceUnavailableError
from app.core.storage import ObjectStorage, build_storage, get_storage
from tests.conftest import S3_ACCESS_KEY, S3_SECRET_KEY
from tests.support import make_settings


def _storage(endpoint: str, **extra: Any) -> ObjectStorage:
    storage = build_storage(
        make_settings(
            storage_endpoint=endpoint,
            storage_bucket=f"t{uuid.uuid4().hex[:12]}",
            storage_access_key=S3_ACCESS_KEY,
            storage_secret_key=S3_SECRET_KEY,
            **extra,
        )
    )
    assert storage is not None
    return storage


async def test_objects_round_trip_and_presigned_urls(s3_endpoint: str) -> None:
    storage = _storage(s3_endpoint)
    assert await storage.ensure_bucket() is True
    assert await storage.ensure_bucket() is False
    await storage.ping()

    key = ObjectStorage.new_key("peace_movement/houses", "jpg")
    assert key.startswith("peace_movement/houses/")
    assert key.endswith(".jpg")
    stored = await storage.put(key, b"\xff\xd8 foto", "image/jpeg")
    assert (stored.size, stored.content_type) == (7, "image/jpeg")
    assert await storage.exists(key)
    assert await storage.get(key) == b"\xff\xd8 foto"

    async with httpx.AsyncClient() as http:
        signed = await http.get(await storage.url(key))
        assert signed.status_code == 200
        assert signed.content == b"\xff\xd8 foto"
        # Objects are private: without a signature the server refuses.
        anonymous = await http.get(f"{s3_endpoint}/{storage.bucket}/{key}")
        assert anonymous.status_code == 403

    await storage.delete(key)
    assert not await storage.exists(key)


async def test_presigned_urls_use_the_public_endpoint(s3_endpoint: str) -> None:
    storage = _storage("http://internal-host:8333", storage_public_endpoint=s3_endpoint)
    url = await storage.url("a/b.txt")
    assert url.startswith(f"{s3_endpoint}/{storage.bucket}/a/b.txt?")


def test_storage_is_optional() -> None:
    assert build_storage(make_settings()) is None
    request: Any = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(storage=None)))
    with pytest.raises(ServiceUnavailableError):
        get_storage(request)
