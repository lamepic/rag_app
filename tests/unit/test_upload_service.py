"""upload_document: the rules, and what is left behind when something fails."""

import hashlib
import io
import uuid

import pytest

from rag.core.collections import Collection, CollectionNotFoundError
from rag.core.documents import Document, DocumentStatus, DuplicateDocumentError
from rag.core.storage import BlobStoreError
from rag.ingestion.upload import (
    FileTooLargeError,
    NotAPdfError,
    clean_filename,
    inspect_pdf,
    upload_document,
)
from tests.fakes import InMemoryBlobStore, InMemoryUnitOfWork

PDF = b"%PDF-1.7\n" + b"x" * 5000
MAX_BYTES = 10_000


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


@pytest.fixture
def blobs() -> InMemoryBlobStore:
    return InMemoryBlobStore()


@pytest.fixture
async def collection(uow: InMemoryUnitOfWork) -> Collection:
    return await uow.collections.add(owner_id=uuid.uuid4(), name="thesis", description=None)


async def upload(
    uow: InMemoryUnitOfWork,
    blobs: InMemoryBlobStore,
    collection: Collection,
    data: bytes = PDF,
    *,
    owner_id: uuid.UUID | None = None,
    filename: str | None = "paper.pdf",
) -> Document:
    return await upload_document(
        uow=uow,
        blobs=blobs,
        owner_id=owner_id or collection.owner_id,
        collection_id=collection.id,
        filename=filename,
        file=io.BytesIO(data),
        max_bytes=MAX_BYTES,
    )


# --- happy path -------------------------------------------------------------------------


async def test_stores_file_records_document_and_commits(
    uow: InMemoryUnitOfWork, blobs: InMemoryBlobStore, collection: Collection
) -> None:
    document = await upload(uow, blobs, collection)

    assert document.status is DocumentStatus.QUEUED
    assert document.file_hash == hashlib.sha256(PDF).hexdigest()
    assert document.size_bytes == len(PDF)
    assert document.storage_key == f"{collection.owner_id}/{document.id}.pdf"
    assert blobs.objects[document.storage_key] == (PDF, "application/pdf")
    assert uow.commits == 1


# --- rejected before anything is stored --------------------------------------------------


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(b"", id="empty"),
        pytest.param(b"PK\x03\x04 a zip file", id="zip"),
        pytest.param(b"<html>%PDF-</html>", id="magic-not-at-start"),
    ],
)
async def test_non_pdf_is_rejected(
    uow: InMemoryUnitOfWork, blobs: InMemoryBlobStore, collection: Collection, data: bytes
) -> None:
    with pytest.raises(NotAPdfError):
        await upload(uow, blobs, collection, data)
    assert blobs.objects == {}


async def test_too_large_is_rejected(
    uow: InMemoryUnitOfWork, blobs: InMemoryBlobStore, collection: Collection
) -> None:
    with pytest.raises(FileTooLargeError):
        await upload(uow, blobs, collection, b"%PDF-" + b"x" * MAX_BYTES)
    assert blobs.objects == {}


async def test_exactly_max_bytes_is_allowed(
    uow: InMemoryUnitOfWork, blobs: InMemoryBlobStore, collection: Collection
) -> None:
    data = b"%PDF-" + b"x" * (MAX_BYTES - 5)
    document = await upload(uow, blobs, collection, data)
    assert document.size_bytes == MAX_BYTES


async def test_someone_elses_collection_is_not_found(
    uow: InMemoryUnitOfWork, blobs: InMemoryBlobStore, collection: Collection
) -> None:
    with pytest.raises(CollectionNotFoundError):
        await upload(uow, blobs, collection, owner_id=uuid.uuid4())
    assert blobs.objects == {}


async def test_duplicate_reports_the_existing_document(
    uow: InMemoryUnitOfWork, blobs: InMemoryBlobStore, collection: Collection
) -> None:
    first = await upload(uow, blobs, collection)

    with pytest.raises(DuplicateDocumentError) as caught:
        await upload(uow, blobs, collection, filename="renamed-copy.pdf")

    assert caught.value.existing_id == first.id
    assert len(blobs.objects) == 1  # the copy was never stored


# --- failures after the file is stored ---------------------------------------------------


async def test_failed_commit_deletes_the_stored_file(
    uow: InMemoryUnitOfWork, blobs: InMemoryBlobStore, collection: Collection
) -> None:
    uow.fail_commit = True

    with pytest.raises(RuntimeError):
        await upload(uow, blobs, collection)

    assert blobs.objects == {}  # no orphan left behind


async def test_lost_race_deletes_file_and_reports_the_winner(
    uow: InMemoryUnitOfWork, blobs: InMemoryBlobStore, collection: Collection
) -> None:
    """Another request commits the same file between our duplicate check and our insert."""
    winner = await upload(uow, blobs, collection)
    real_get_by_hash = uow.documents.get_by_hash
    calls = 0

    async def miss_once(collection_id: uuid.UUID, file_hash: str) -> Document | None:
        nonlocal calls
        calls += 1
        return None if calls == 1 else await real_get_by_hash(collection_id, file_hash)

    uow.documents.get_by_hash = miss_once  # type: ignore[method-assign]

    with pytest.raises(DuplicateDocumentError) as caught:
        await upload(uow, blobs, collection)

    assert caught.value.existing_id == winner.id
    assert uow.rollbacks == 1
    assert list(blobs.objects) == [winner.storage_key]  # our copy was cleaned up


async def test_storage_failure_records_nothing(
    uow: InMemoryUnitOfWork, blobs: InMemoryBlobStore, collection: Collection
) -> None:
    blobs.fail = True

    with pytest.raises(BlobStoreError):
        await upload(uow, blobs, collection)

    assert uow.documents.rows == []
    assert uow.commits == 0


# --- helpers ----------------------------------------------------------------------------


def test_inspect_pdf_rewinds_the_file() -> None:
    file = io.BytesIO(PDF)
    inspect_pdf(file, MAX_BYTES)
    assert file.tell() == 0  # ready for the upload to read from the start


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("paper.pdf", "paper.pdf"),
        ("C:\\fakepath\\paper.pdf", "paper.pdf"),
        ("../../etc/passwd.pdf", "passwd.pdf"),
        ("  ", "upload.pdf"),
        (None, "upload.pdf"),
        ("a" * 300 + ".pdf", "a" * 255),
    ],
)
def test_clean_filename(raw: str | None, expected: str) -> None:
    assert clean_filename(raw) == expected
