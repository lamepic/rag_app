"""Postgres implementations of the core repositories.

They translate between ORM rows (adapters.db.models) and domain objects (core),
so nothing outside this package ever sees SQLAlchemy.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from rag.adapters.db import models
from rag.core.collections import Collection, CollectionNameTakenError
from rag.core.documents import Document, DuplicateDocumentError


def _violates(exc: IntegrityError, constraint: str) -> bool:
    """Did this insert break *that* constraint? Our naming convention makes the name reliable."""
    return constraint in str(exc.orig)


def _to_collection(row: models.Collection) -> Collection:
    return Collection(
        id=row.id,
        owner_id=row.owner_id,
        name=row.name,
        description=row.description,
        created_at=row.created_at,
    )


def _to_document(row: models.Document) -> Document:
    return Document(
        id=row.id,
        collection_id=row.collection_id,
        owner_id=row.owner_id,
        filename=row.filename,
        file_hash=row.file_hash,
        size_bytes=row.size_bytes,
        storage_key=row.storage_key,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlCollectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, *, owner_id: uuid.UUID, name: str, description: str | None) -> Collection:
        row = models.Collection(owner_id=owner_id, name=name, description=description)
        self._session.add(row)
        try:
            # Flush sends the INSERT now (still uncommitted), so a duplicate name fails
            # here, where we can translate it, rather than later at commit().
            await self._session.flush()
        except IntegrityError as exc:
            if _violates(exc, "uq_collections_owner_id_name"):
                raise CollectionNameTakenError(name) from exc
            raise
        return _to_collection(row)

    async def get(self, collection_id: uuid.UUID, *, owner_id: uuid.UUID) -> Collection | None:
        row = await self._session.scalar(
            select(models.Collection).where(
                models.Collection.id == collection_id,
                models.Collection.owner_id == owner_id,  # someone else's -> None, same as missing
            )
        )
        return _to_collection(row) if row else None

    async def list_for_owner(self, owner_id: uuid.UUID) -> list[Collection]:
        rows = await self._session.scalars(
            select(models.Collection)
            .where(models.Collection.owner_id == owner_id)
            .order_by(models.Collection.created_at.desc(), models.Collection.id)
        )
        return [_to_collection(row) for row in rows]


class SqlDocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

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
        row = models.Document(
            id=id,
            collection_id=collection_id,
            owner_id=owner_id,
            filename=filename,
            file_hash=file_hash,
            size_bytes=size_bytes,
            storage_key=storage_key,
        )
        self._session.add(row)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            if _violates(exc, "uq_documents_collection_id_file_hash"):
                # The transaction is now aborted, so we can't look up the existing row here.
                raise DuplicateDocumentError(existing_id=None) from exc
            raise
        return _to_document(row)

    async def get(self, document_id: uuid.UUID, *, owner_id: uuid.UUID) -> Document | None:
        row = await self._session.scalar(
            select(models.Document).where(
                models.Document.id == document_id, models.Document.owner_id == owner_id
            )
        )
        return _to_document(row) if row else None

    async def get_by_hash(self, collection_id: uuid.UUID, file_hash: str) -> Document | None:
        row = await self._session.scalar(
            select(models.Document).where(
                models.Document.collection_id == collection_id,
                models.Document.file_hash == file_hash,
            )
        )
        return _to_document(row) if row else None

    async def list_for_collection(
        self, collection_id: uuid.UUID, *, owner_id: uuid.UUID
    ) -> list[Document]:
        rows = await self._session.scalars(
            select(models.Document)
            .where(
                models.Document.collection_id == collection_id,
                models.Document.owner_id == owner_id,
            )
            .order_by(models.Document.created_at.desc(), models.Document.id)
        )
        return [_to_document(row) for row in rows]
