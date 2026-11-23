"""Documents: uploaded papers and where each one is in the ingestion pipeline."""

import enum
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


class DocumentStatus(enum.StrEnum):
    QUEUED = "queued"  # stored, waiting for the worker (M2)
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Document:
    id: uuid.UUID
    collection_id: uuid.UUID
    owner_id: uuid.UUID
    filename: str
    file_hash: str  # SHA-256 of the bytes, hex
    size_bytes: int
    storage_key: str
    status: DocumentStatus
    created_at: datetime
    updated_at: datetime


class DuplicateDocumentError(Exception):
    """The same file is already in this collection. Maps to 409."""

    def __init__(self, existing_id: uuid.UUID | None) -> None:
        super().__init__(f"duplicate of {existing_id}")
        self.existing_id = existing_id


class DocumentRepository(Protocol):
    async def add(
        self,
        *,
        id: uuid.UUID,
        collection_id: uuid.UUID,
        owner_id: uuid.UUID,
        filename: str,
        file_hash: str,
        size_bytes: int,
        storage_key: str,
    ) -> Document:
        """Create a queued document. Raises DuplicateDocumentError (existing_id unknown)."""
        ...

    async def get(self, document_id: uuid.UUID, *, owner_id: uuid.UUID) -> Document | None:
        """The document, or None if it doesn't exist or isn't this owner's."""
        ...

    async def get_by_hash(self, collection_id: uuid.UUID, file_hash: str) -> Document | None: ...

    async def list_for_collection(
        self, collection_id: uuid.UUID, *, owner_id: uuid.UUID
    ) -> list[Document]:
        """The collection's documents, newest first."""
        ...
