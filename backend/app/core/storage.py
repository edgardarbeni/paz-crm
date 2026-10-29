"""S3-compatible object storage (D-38): MinIO in development and tests, DigitalOcean Spaces or
AWS S3 in deployment. Only the endpoint and credentials change; no provider-specific API is
used.

The MinIO SDK is synchronous, so calls run in a worker thread. Objects are private: the browser
gets short-lived presigned URLs, signed against `PAZ_STORAGE_PUBLIC_ENDPOINT` when the API reaches
the storage through an internal host name (e.g. `minio:9000` inside Docker).
"""

import io
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated
from urllib.parse import urlsplit

import anyio
from fastapi import Depends, Request
from minio import Minio
from minio.error import S3Error

from app.core.config import Settings
from app.core.errors import ServiceUnavailableError

DEFAULT_URL_TTL = timedelta(minutes=10)


@dataclass(frozen=True, slots=True)
class StoredObject:
    key: str
    size: int
    content_type: str


def _client(endpoint: str, settings: Settings) -> Minio:
    parts = urlsplit(endpoint if "://" in endpoint else f"http://{endpoint}")
    return Minio(
        parts.netloc,
        access_key=settings.storage_access_key,
        secret_key=settings.storage_secret_key.get_secret_value()
        if settings.storage_secret_key
        else None,
        secure=parts.scheme == "https",
        # A fixed region avoids a network round trip when presigning.
        region=settings.storage_region,
    )


class ObjectStorage:
    def __init__(self, client: Minio, presigner: Minio, bucket: str) -> None:
        self._client = client
        self._presigner = presigner
        self.bucket = bucket

    @staticmethod
    def new_key(prefix: str, extension: str = "") -> str:
        """Non-guessable key under a module prefix, e.g. `peace_movement/houses/<uuid>.jpg`."""
        suffix = f".{extension.lstrip('.')}" if extension else ""
        return f"{prefix.strip('/')}/{uuid.uuid4().hex}{suffix}"

    async def ensure_bucket(self) -> bool:
        """Creates the bucket if missing (development); returns True when it was created."""

        def run() -> bool:
            if self._client.bucket_exists(self.bucket):
                return False
            self._client.make_bucket(self.bucket)
            return True

        return await anyio.to_thread.run_sync(run)

    async def put(self, key: str, data: bytes, content_type: str) -> StoredObject:
        await anyio.to_thread.run_sync(
            lambda: self._client.put_object(
                self.bucket, key, io.BytesIO(data), len(data), content_type=content_type
            )
        )
        return StoredObject(key=key, size=len(data), content_type=content_type)

    async def get(self, key: str) -> bytes:
        def run() -> bytes:
            response = self._client.get_object(self.bucket, key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()

        return await anyio.to_thread.run_sync(run)

    async def exists(self, key: str) -> bool:
        def run() -> bool:
            try:
                self._client.stat_object(self.bucket, key)
            except S3Error as error:
                if error.code in {"NoSuchKey", "NoSuchObject"}:
                    return False
                raise
            return True

        return await anyio.to_thread.run_sync(run)

    async def delete(self, key: str) -> None:
        await anyio.to_thread.run_sync(lambda: self._client.remove_object(self.bucket, key))

    async def url(self, key: str, *, expires: timedelta = DEFAULT_URL_TTL) -> str:
        """Presigned GET URL, valid for `expires`."""
        return await anyio.to_thread.run_sync(
            lambda: self._presigner.presigned_get_object(self.bucket, key, expires=expires)
        )

    async def ping(self) -> None:
        await anyio.to_thread.run_sync(lambda: self._client.bucket_exists(self.bucket))


def build_storage(settings: Settings) -> ObjectStorage | None:
    """None when no endpoint is configured: modules that need files answer 503."""
    if not settings.storage_endpoint:
        return None
    client = _client(settings.storage_endpoint, settings)
    public = settings.storage_public_endpoint
    presigner = _client(public, settings) if public else client
    return ObjectStorage(client, presigner, settings.storage_bucket)


def get_storage(request: Request) -> ObjectStorage:
    storage: ObjectStorage | None = getattr(request.app.state, "storage", None)
    if storage is None:
        raise ServiceUnavailableError("El almacenamiento de archivos no está configurado.")
    return storage


StorageDep = Annotated[ObjectStorage, Depends(get_storage)]
