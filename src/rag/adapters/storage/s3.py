"""BlobStore over the S3 API: Supabase Storage locally, any S3-compatible store in production.

boto3 is synchronous. Calling it directly inside an async route would block the event
loop, freezing every other request on this process until the upload finished. So each
call runs in a worker thread via anyio.to_thread.run_sync. (A boto3 client is safe to
share between threads; a boto3 Session is not.)
"""

import functools
from typing import TYPE_CHECKING, BinaryIO

import anyio.to_thread
import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from rag.config import Settings
from rag.core.storage import BlobStoreError

if TYPE_CHECKING:
    # Type stubs are a dev dependency: import them for mypy only, never at runtime.
    from mypy_boto3_s3 import S3Client


def create_s3_client(settings: Settings) -> "S3Client":
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key_id.get_secret_value(),
        aws_secret_access_key=settings.s3_secret_access_key.get_secret_value(),
        config=Config(
            # Bucket in the path (host/bucket/key), not the hostname: 127.0.0.1 has no subdomains.
            s3={"addressing_style": "path"},
            retries={"mode": "standard", "max_attempts": 3},
            connect_timeout=5,
            read_timeout=60,
        ),
    )


class S3BlobStore:
    def __init__(self, client: "S3Client", bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    async def put(self, key: str, data: BinaryIO, *, content_type: str) -> None:
        # upload_fileobj streams from the file and switches to multipart for large files,
        # so a 50 MB upload is never held in memory all at once.
        upload = functools.partial(
            self._client.upload_fileobj,
            data,
            self._bucket,
            key,
            ExtraArgs={"ContentType": content_type},
        )
        try:
            await anyio.to_thread.run_sync(upload)
        except (BotoCoreError, ClientError) as exc:
            raise BlobStoreError(f"put {key!r} failed: {exc}") from exc

    async def delete(self, key: str) -> None:
        delete = functools.partial(self._client.delete_object, Bucket=self._bucket, Key=key)
        try:
            await anyio.to_thread.run_sync(delete)
        except (BotoCoreError, ClientError) as exc:
            raise BlobStoreError(f"delete {key!r} failed: {exc}") from exc
