"""Accept an uploaded PDF: validate it, store the file, record the document.

Order matters. The file goes to storage *before* the row is committed:
  - if storing fails, nothing was recorded, so there is nothing to undo;
  - if recording fails, we delete the stored file;
  - if the process dies in between, the worst case is an orphan file nobody points
    to (harmless, cleanable later), never a row pointing at a missing file.
"""

import contextlib
import hashlib
import uuid
from dataclasses import dataclass
from pathlib import PureWindowsPath
from typing import BinaryIO

import anyio.to_thread

from rag.core.collections import CollectionNotFoundError
from rag.core.documents import Document, DuplicateDocumentError
from rag.core.storage import BlobStore, BlobStoreError
from rag.core.uow import UnitOfWork

PDF_MAGIC = b"%PDF-"
CHUNK_SIZE = 1024 * 1024
MAX_FILENAME_LENGTH = 255


class NotAPdfError(Exception):
    """The bytes don't start like a PDF, whatever the filename or Content-Type say. Maps to 415."""


class FileTooLargeError(Exception):
    """Maps to 413."""

    def __init__(self, max_bytes: int) -> None:
        super().__init__(f"file exceeds {max_bytes} bytes")
        self.max_bytes = max_bytes


@dataclass(frozen=True, slots=True)
class FileFacts:
    sha256: str
    size_bytes: int


def inspect_pdf(file: BinaryIO, max_bytes: int) -> FileFacts:
    """Check the magic bytes, enforce the size limit and hash the file in one pass.

    Blocking (file reads, hashing): call it through a worker thread.
    """
    file.seek(0)
    head = file.read(len(PDF_MAGIC))
    if head != PDF_MAGIC:
        raise NotAPdfError
    digest = hashlib.sha256(head)
    size = len(head)
    while chunk := file.read(CHUNK_SIZE):
        size += len(chunk)
        if size > max_bytes:
            raise FileTooLargeError(max_bytes)
        digest.update(chunk)
    file.seek(0)
    return FileFacts(sha256=digest.hexdigest(), size_bytes=size)


def clean_filename(raw: str | None) -> str:
    """Display name only (storage keys never use it). Drops any client-sent directory part."""
    name = PureWindowsPath(raw or "").name.strip()  # handles both / and \\ separators
    return (name or "upload.pdf")[:MAX_FILENAME_LENGTH]


async def upload_document(
    *,
    uow: UnitOfWork,
    blobs: BlobStore,
    owner_id: uuid.UUID,
    collection_id: uuid.UUID,
    filename: str | None,
    file: BinaryIO,
    max_bytes: int,
) -> Document:
    if await uow.collections.get(collection_id, owner_id=owner_id) is None:
        raise CollectionNotFoundError(collection_id)

    facts = await anyio.to_thread.run_sync(inspect_pdf, file, max_bytes)

    # Cheap early answer for the common case; the unique constraint still guards races.
    existing = await uow.documents.get_by_hash(collection_id, facts.sha256)
    if existing is not None:
        raise DuplicateDocumentError(existing.id)

    document_id = uuid.uuid4()
    storage_key = f"{owner_id}/{document_id}.pdf"
    await blobs.put(storage_key, file, content_type="application/pdf")

    try:
        document = await uow.documents.add(
            id=document_id,
            collection_id=collection_id,
            owner_id=owner_id,
            filename=clean_filename(filename),
            file_hash=facts.sha256,
            size_bytes=facts.size_bytes,
            storage_key=storage_key,
        )
        await uow.commit()
    except DuplicateDocumentError:
        # Lost a race: the same file was committed between our check and our insert.
        await _discard(blobs, storage_key)
        await uow.rollback()
        winner = await uow.documents.get_by_hash(collection_id, facts.sha256)
        raise DuplicateDocumentError(winner.id if winner else None) from None
    except Exception:
        await _discard(blobs, storage_key)
        raise
    return document


async def _discard(blobs: BlobStore, key: str) -> None:
    """Best-effort cleanup. If it fails we're left with an orphan file, which is harmless."""
    # TODO(observability milestone): log the failure so orphans can be swept.
    with contextlib.suppress(BlobStoreError):
        await blobs.delete(key)
