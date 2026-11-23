"""SqlDocumentRepository against real Postgres."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from rag.adapters.db.repositories import SqlCollectionRepository, SqlDocumentRepository
from rag.core.collections import Collection
from rag.core.documents import Document, DocumentStatus, DuplicateDocumentError


@pytest.fixture
async def collection(db_session: AsyncSession) -> Collection:
    repo = SqlCollectionRepository(db_session)
    return await repo.add(owner_id=uuid.uuid4(), name="thesis", description=None)


async def add(
    repo: SqlDocumentRepository, collection: Collection, file_hash: str = "a" * 64
) -> Document:
    document_id = uuid.uuid4()
    return await repo.add(
        id=document_id,
        collection_id=collection.id,
        owner_id=collection.owner_id,
        filename="paper.pdf",
        file_hash=file_hash,
        size_bytes=1234,
        storage_key=f"{collection.owner_id}/{document_id}.pdf",
    )


async def test_add_returns_a_queued_document_with_timestamps(
    db_session: AsyncSession, collection: Collection
) -> None:
    document = await add(SqlDocumentRepository(db_session), collection)

    assert document.status is DocumentStatus.QUEUED
    assert document.created_at is not None
    assert document.updated_at is not None


async def test_duplicate_hash_raises_domain_error(
    db_session: AsyncSession, collection: Collection
) -> None:
    repo = SqlDocumentRepository(db_session)
    await add(repo, collection)

    with pytest.raises(DuplicateDocumentError):
        await add(repo, collection)


async def test_get_is_scoped_to_owner(db_session: AsyncSession, collection: Collection) -> None:
    repo = SqlDocumentRepository(db_session)
    document = await add(repo, collection)

    assert await repo.get(document.id, owner_id=collection.owner_id) == document
    assert await repo.get(document.id, owner_id=uuid.uuid4()) is None


async def test_get_by_hash_finds_within_the_collection(
    db_session: AsyncSession, collection: Collection
) -> None:
    repo = SqlDocumentRepository(db_session)
    document = await add(repo, collection, file_hash="b" * 64)

    assert await repo.get_by_hash(collection.id, "b" * 64) == document
    assert await repo.get_by_hash(collection.id, "c" * 64) is None


async def test_list_for_collection_is_scoped_to_owner(
    db_session: AsyncSession, collection: Collection
) -> None:
    repo = SqlDocumentRepository(db_session)
    await add(repo, collection, file_hash="1" * 64)
    await add(repo, collection, file_hash="2" * 64)

    assert len(await repo.list_for_collection(collection.id, owner_id=collection.owner_id)) == 2
    assert await repo.list_for_collection(collection.id, owner_id=uuid.uuid4()) == []
