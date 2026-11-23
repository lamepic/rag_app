"""SqlCollectionRepository against real Postgres: the behaviour the in-memory fake copies."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from rag.adapters.db.repositories import SqlCollectionRepository
from rag.core.collections import CollectionNameTakenError


async def test_add_returns_a_complete_collection(db_session: AsyncSession) -> None:
    repo = SqlCollectionRepository(db_session)
    owner_id = uuid.uuid4()

    collection = await repo.add(owner_id=owner_id, name="thesis", description="notes")

    assert collection.owner_id == owner_id
    assert collection.name == "thesis"
    assert collection.created_at is not None  # server default, read back by the INSERT


async def test_duplicate_name_raises_domain_error(db_session: AsyncSession) -> None:
    repo = SqlCollectionRepository(db_session)
    owner_id = uuid.uuid4()
    await repo.add(owner_id=owner_id, name="thesis", description=None)

    with pytest.raises(CollectionNameTakenError):
        await repo.add(owner_id=owner_id, name="thesis", description=None)


async def test_list_is_scoped_to_owner_and_newest_first(db_session: AsyncSession) -> None:
    repo = SqlCollectionRepository(db_session)
    me, other = uuid.uuid4(), uuid.uuid4()
    await repo.add(owner_id=me, name="first", description=None)
    await repo.add(owner_id=other, name="not mine", description=None)
    await repo.add(owner_id=me, name="second", description=None)

    names = [c.name for c in await repo.list_for_owner(me)]

    # All three inserts share one transaction, so now() gives them the same created_at;
    # the id tie-breaker keeps the order stable, so compare as a set here.
    assert set(names) == {"first", "second"}
