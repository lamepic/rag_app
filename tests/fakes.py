"""In-memory stand-ins for the core ports, for fast tests with no services running.

They mimic the behaviour that matters (uniqueness, ordering, owner scoping);
integration tests check that the real adapters behave the same way.
"""

import uuid
from datetime import UTC, datetime, timedelta

from rag.core.collections import Collection, CollectionNameTakenError


class InMemoryCollectionRepository:
    def __init__(self) -> None:
        self.rows: list[Collection] = []
        self._clock = datetime(2026, 1, 1, tzinfo=UTC)

    async def add(self, *, owner_id: uuid.UUID, name: str, description: str | None) -> Collection:
        if any(c.owner_id == owner_id and c.name == name for c in self.rows):
            raise CollectionNameTakenError(name)
        self._clock += timedelta(seconds=1)  # distinct, increasing created_at
        collection = Collection(
            id=uuid.uuid4(),
            owner_id=owner_id,
            name=name,
            description=description,
            created_at=self._clock,
        )
        self.rows.append(collection)
        return collection

    async def list_for_owner(self, owner_id: uuid.UUID) -> list[Collection]:
        mine = [c for c in self.rows if c.owner_id == owner_id]
        return sorted(mine, key=lambda c: c.created_at, reverse=True)


class InMemoryUnitOfWork:
    def __init__(self) -> None:
        self._collections = InMemoryCollectionRepository()
        self.commits = 0

    @property
    def collections(self) -> InMemoryCollectionRepository:
        return self._collections

    async def commit(self) -> None:
        self.commits += 1
