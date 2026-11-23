"""S3BlobStore against the real local Supabase Storage."""

import io
import uuid
from collections.abc import AsyncIterator

import pytest
from botocore.exceptions import ClientError

from rag.adapters.storage.s3 import S3BlobStore, create_s3_client
from rag.config import Settings

PDF_BYTES = b"%PDF-1.7\n% a tiny stand-in for a real paper\n"


@pytest.fixture
async def stored_key(settings: Settings) -> AsyncIterator[str]:
    """A fresh key, deleted after the test whether it passed or not."""
    key = f"tests/{uuid.uuid4()}.pdf"
    yield key
    create_s3_client(settings).delete_object(Bucket=settings.storage_bucket, Key=key)


async def test_put_stores_the_bytes_and_content_type(settings: Settings, stored_key: str) -> None:
    client = create_s3_client(settings)
    store = S3BlobStore(client, settings.storage_bucket)

    await store.put(stored_key, io.BytesIO(PDF_BYTES), content_type="application/pdf")

    obj = client.get_object(Bucket=settings.storage_bucket, Key=stored_key)
    assert obj["Body"].read() == PDF_BYTES
    assert obj["ContentType"] == "application/pdf"


async def test_delete_removes_the_object(settings: Settings, stored_key: str) -> None:
    client = create_s3_client(settings)
    store = S3BlobStore(client, settings.storage_bucket)
    await store.put(stored_key, io.BytesIO(PDF_BYTES), content_type="application/pdf")

    await store.delete(stored_key)

    with pytest.raises(ClientError):
        client.head_object(Bucket=settings.storage_bucket, Key=stored_key)


async def test_delete_of_missing_key_is_not_an_error(settings: Settings) -> None:
    store = S3BlobStore(create_s3_client(settings), settings.storage_bucket)
    await store.delete(f"tests/{uuid.uuid4()}.pdf")
