from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Protocol

import boto3  # pyright: ignore[reportMissingTypeStubs]
from botocore.config import Config as BotoConfig  # pyright: ignore[reportMissingTypeStubs]
from botocore.exceptions import ClientError  # pyright: ignore[reportMissingTypeStubs]

from ursache.config import Settings


class BlobStore(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...
    async def get(self, key: str) -> bytes: ...
    async def exists(self, key: str) -> bool: ...
    def public_url(self, key: str) -> str | None: ...


class LocalBlobStore:
    """Filesystem-backed store for local development."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def _path(self, key: str) -> Path:
        path = (self._root / key).resolve()
        if not path.is_relative_to(self._root):
            raise ValueError(f"key escapes store root: {key!r}")
        return path

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self._path(key).read_bytes)

    async def exists(self, key: str) -> bool:
        return await asyncio.to_thread(self._path(key).is_file)

    def public_url(self, key: str) -> str | None:
        return None


class S3BlobStore:
    """S3-compatible store; used with Backblaze B2's S3 API in production."""

    def __init__(
        self,
        *,
        endpoint_url: str,
        bucket: str,
        key_id: str,
        secret: str,
        public_base_url: str | None = None,
    ) -> None:
        self._bucket = bucket
        self._public_base_url = public_base_url.rstrip("/") if public_base_url else None
        # boto3 ships without type stubs; keep the untyped surface contained here.
        self._client: Any = boto3.client(  # pyright: ignore[reportUnknownMemberType]
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=key_id,
            aws_secret_access_key=secret,
            config=BotoConfig(retries={"max_attempts": 3, "mode": "standard"}),
        )

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )

    async def get(self, key: str) -> bytes:
        response = await asyncio.to_thread(self._client.get_object, Bucket=self._bucket, Key=key)
        body: bytes = await asyncio.to_thread(response["Body"].read)
        return body

    async def exists(self, key: str) -> bool:
        try:
            await asyncio.to_thread(self._client.head_object, Bucket=self._bucket, Key=key)
        except ClientError as exc:
            error: Any = exc
            if error.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise
        return True

    def public_url(self, key: str) -> str | None:
        return f"{self._public_base_url}/{key}" if self._public_base_url else None


def make_blob_store(settings: Settings) -> BlobStore:
    if settings.blob_backend == "local":
        return LocalBlobStore(Path(settings.blob_local_root))
    missing = [
        name
        for name in ("s3_endpoint_url", "s3_bucket", "s3_key_id", "s3_secret")
        if getattr(settings, name) is None
    ]
    if missing or settings.s3_key_id is None or settings.s3_secret is None:
        raise ValueError(f"BLOB_BACKEND=s3 requires: {', '.join(m.upper() for m in missing)}")
    return S3BlobStore(
        endpoint_url=str(settings.s3_endpoint_url),
        bucket=str(settings.s3_bucket),
        key_id=settings.s3_key_id.get_secret_value(),
        secret=settings.s3_secret.get_secret_value(),
        public_base_url=settings.s3_public_base_url,
    )
