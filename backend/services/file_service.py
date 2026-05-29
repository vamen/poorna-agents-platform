"""FileService — abstract file storage with local and S3 backends.

Usage::

    ref = await FileService.put(b"...", filename="photo.jpg", mime_type="image/jpeg")
    data = await FileService.get(ref)
    await FileService.delete(ref)

Backend is selected by ``settings.file_backend``:
  - "local" (default) — stores files in ``settings.file_local_dir``
  - "s3" — stores in ``settings.file_s3_bucket`` (requires boto3)
"""

from __future__ import annotations

import logging
import os
from uuid import uuid4

from agents.file_ref import FileRef

logger = logging.getLogger(__name__)


class FileService:

    @staticmethod
    async def put(
        data: bytes,
        filename: str,
        mime_type: str = "application/octet-stream",
    ) -> FileRef:
        """Store *data* and return a FileRef."""
        from config import settings

        backend = getattr(settings, "file_backend", "local")
        if backend == "s3":
            return await _put_s3(data, filename, mime_type, settings)
        return await _put_local(data, filename, mime_type, settings)

    @staticmethod
    async def get(ref: FileRef) -> bytes:
        """Retrieve the raw bytes for *ref*."""
        if ref.backend == "s3":
            return await _get_s3(ref)
        return await _get_local(ref)

    @staticmethod
    async def delete(ref: FileRef) -> None:
        """Delete the stored file (best-effort; logs on failure)."""
        try:
            if ref.backend == "s3":
                await _delete_s3(ref)
            else:
                await _delete_local(ref)
        except Exception as exc:
            logger.warning("FileService.delete failed for %s: %s", ref.file_id, exc)


# ── Local backend ──────────────────────────────────────────────────────────────

async def _put_local(data: bytes, filename: str, mime_type: str, settings) -> FileRef:
    base_dir = getattr(settings, "file_local_dir", "/tmp/agent_files")
    os.makedirs(base_dir, exist_ok=True)
    file_id = str(uuid4())
    path = os.path.join(base_dir, file_id)
    with open(path, "wb") as f:
        f.write(data)
    logger.debug("FileService: stored %s → %s", filename, path)
    return FileRef(
        file_id=file_id,
        filename=filename,
        mime_type=mime_type,
        size_bytes=len(data),
        backend="local",
        uri=path,
    )


async def _get_local(ref: FileRef) -> bytes:
    with open(ref.uri, "rb") as f:
        return f.read()


async def _delete_local(ref: FileRef) -> None:
    if os.path.exists(ref.uri):
        os.remove(ref.uri)


# ── S3 backend ─────────────────────────────────────────────────────────────────

async def _put_s3(data: bytes, filename: str, mime_type: str, settings) -> FileRef:
    import aioboto3  # type: ignore
    bucket = settings.file_s3_bucket
    file_id = str(uuid4())
    key = f"agent-files/{file_id}/{filename}"
    session = aioboto3.Session()
    async with session.client("s3") as s3:
        await s3.put_object(Bucket=bucket, Key=key, Body=data, ContentType=mime_type)
    return FileRef(
        file_id=file_id,
        filename=filename,
        mime_type=mime_type,
        size_bytes=len(data),
        backend="s3",
        uri=f"s3://{bucket}/{key}",
    )


async def _get_s3(ref: FileRef) -> bytes:
    import aioboto3  # type: ignore
    # uri = "s3://bucket/key"
    parts = ref.uri[5:].split("/", 1)
    bucket, key = parts[0], parts[1]
    session = aioboto3.Session()
    async with session.client("s3") as s3:
        resp = await s3.get_object(Bucket=bucket, Key=key)
        return await resp["Body"].read()


async def _delete_s3(ref: FileRef) -> None:
    import aioboto3  # type: ignore
    parts = ref.uri[5:].split("/", 1)
    bucket, key = parts[0], parts[1]
    session = aioboto3.Session()
    async with session.client("s3") as s3:
        await s3.delete_object(Bucket=bucket, Key=key)
