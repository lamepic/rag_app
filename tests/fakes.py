"""In-memory stand-ins for the core ports, for fast tests with no services running.

They mimic the behaviour that matters (uniqueness, ordering, owner scoping);
integration tests check that the real adapters behave the same way.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import BinaryIO

from rag.core.collections import Collection, CollectionNameTakenError
from rag.core.documents import Document, DocumentStatus, DuplicateDocumentError
from rag.core.storage import BlobStoreError


class FakeClock:
    """Distinct, increasing timestamps so 'newest first' is testable."""

    def __init__(self) -> None:
        self._now = datetime(2026, 1, 1, tzinfo=UTC)

    def tick(self) -> datetime:
        self._now += timedelta(seconds=1)
        return self._now


class InMemoryCollectionRepository:
    def __init__(self, clock: FakeClock) -> None:
        self.rows: list[Collection] = []
        self._clock = clock

    async def add(self, *, owner_id: uuid.UUID, name: str, description: str | None) -> Collection:
        if any(c.owner_id == owner_id and c.name == name for c in self.rows):
            raise CollectionNameTakenError(name)
        collection = Collection(
            id=uuid.uuid4(),
            owner_id=owner_id,
            name=name,
            description=description,
            created_at=self._clock.tick(),
        )
        self.rows.append(collection)
        return collection

    async def get(self, collection_id: uuid.UUID, *, owner_id: uuid.UUID) -> Collection | None:
        return next(
            (c for c in self.rows if c.id == collection_id and c.owner_id == owner_id), None
        )

    async def list_for_owner(self, owner_id: uuid.UUID) -> list[Collection]:
        mine = [c for c in self.rows if c.owner_id == owner_id]
        return sorted(mine, key=lambda c: c.created_at, reverse=True)


class InMemoryDocumentRepository:
    def __init__(self, clock: FakeClock) -> None:
        self.rows: list[Document] = []
        self._clock = clock

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
        if any(d.collection_id == collection_id and d.file_hash == file_hash for d in self.rows):
            raise DuplicateDocumentError(existing_id=None)  # like the DB: id unknown here
        now = self._clock.tick()
        document = Document(
            id=id,
            collection_id=collection_id,
            owner_id=owner_id,
            filename=filename,
            file_hash=file_hash,
            size_bytes=size_bytes,
            storage_key=storage_key,
            status=DocumentStatus.QUEUED,
            created_at=now,
            updated_at=now,
        )
        self.rows.append(document)
        return document

    async def get(self, document_id: uuid.UUID, *, owner_id: uuid.UUID) -> Document | None:
        return next((d for d in self.rows if d.id == document_id and d.owner_id == owner_id), None)

    async def get_by_hash(self, collection_id: uuid.UUID, file_hash: str) -> Document | None:
        return next(
            (d for d in self.rows if d.collection_id == collection_id and d.file_hash == file_hash),
            None,
        )

    async def list_for_collection(
        self, collection_id: uuid.UUID, *, owner_id: uuid.UUID
    ) -> list[Document]:
        mine = [d for d in self.rows if d.collection_id == collection_id and d.owner_id == owner_id]
        return sorted(mine, key=lambda d: d.created_at, reverse=True)


class InMemoryUnitOfWork:
    def __init__(self) -> None:
        clock = FakeClock()
        self._collections = InMemoryCollectionRepository(clock)
        self._documents = InMemoryDocumentRepository(clock)
        self.commits = 0
        self.rollbacks = 0
        self.fail_commit = False

    @property
    def collections(self) -> InMemoryCollectionRepository:
        return self._collections

    @property
    def documents(self) -> InMemoryDocumentRepository:
        return self._documents

    async def commit(self) -> None:
        if self.fail_commit:
            raise RuntimeError("database went away")
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class InMemoryBlobStore:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}  # key -> (bytes, content type)
        self.fail = False

    async def put(self, key: str, data: BinaryIO, *, content_type: str) -> None:
        if self.fail:
            raise BlobStoreError("storage is down")
        self.objects[key] = (data.read(), content_type)

    async def delete(self, key: str) -> None:
        if self.fail:
            raise BlobStoreError("storage is down")
        self.objects.pop(key, None)
