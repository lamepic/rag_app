"""The database constraints that the upload rules rely on."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from rag.adapters.db.models import Collection, Document, DocumentStatus

FILE_HASH = "a" * 64


async def make_collection(session: AsyncSession, owner_id: uuid.UUID, name: str) -> Collection:
    collection = Collection(owner_id=owner_id, name=name)
    session.add(collection)
    await session.flush()
    return collection


def make_document(collection: Collection, file_hash: str = FILE_HASH) -> Document:
    return Document(
        collection_id=collection.id,
        owner_id=collection.owner_id,
        filename="paper.pdf",
        file_hash=file_hash,
        size_bytes=1024,
        storage_key=f"{collection.owner_id}/{uuid.uuid4()}.pdf",
    )


async def test_same_file_twice_in_one_collection_is_rejected(db_session: AsyncSession) -> None:
    collection = await make_collection(db_session, uuid.uuid4(), "thesis")
    db_session.add(make_document(collection))
    await db_session.flush()

    db_session.add(make_document(collection))
    with pytest.raises(IntegrityError, match="uq_documents_collection_id_file_hash"):
        await db_session.flush()


async def test_same_file_in_two_collections_is_allowed(db_session: AsyncSession) -> None:
    owner_id = uuid.uuid4()
    thesis = await make_collection(db_session, owner_id, "thesis")
    reading = await make_collection(db_session, owner_id, "reading list")

    db_session.add_all([make_document(thesis), make_document(reading)])
    await db_session.flush()


async def test_collection_names_are_unique_per_owner(db_session: AsyncSession) -> None:
    owner_id = uuid.uuid4()
    await make_collection(db_session, owner_id, "thesis")
    await make_collection(db_session, uuid.uuid4(), "thesis")  # another owner: fine

    with pytest.raises(IntegrityError, match="uq_collections_owner_id_name"):
        await make_collection(db_session, owner_id, "thesis")


async def test_status_defaults_to_queued_and_is_stored_as_its_value(
    db_session: AsyncSession,
) -> None:
    collection = await make_collection(db_session, uuid.uuid4(), "thesis")
    document = make_document(collection)
    db_session.add(document)
    await db_session.flush()

    assert document.status is DocumentStatus.QUEUED
    stored = await db_session.scalar(
        text("SELECT status FROM documents WHERE id = :id"), {"id": document.id}
    )
    assert stored == "queued"  # the value, not the member name "QUEUED"
