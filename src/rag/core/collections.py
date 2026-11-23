"""Collections: named groups of papers that are searched together."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Collection:
    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime


class CollectionNameTakenError(Exception):
    """This owner already has a collection with that name. Maps to 409."""


class CollectionNotFoundError(Exception):
    """No such collection for this owner (it may exist for someone else). Maps to 404."""


class CollectionRepository(Protocol):
    async def add(self, *, owner_id: uuid.UUID, name: str, description: str | None) -> Collection:
        """Create a collection. Raises CollectionNameTakenError on a duplicate name."""
        ...

    async def get(self, collection_id: uuid.UUID, *, owner_id: uuid.UUID) -> Collection | None:
        """The collection, or None if it doesn't exist or isn't this owner's."""
        ...

    async def list_for_owner(self, owner_id: uuid.UUID) -> list[Collection]:
        """The owner's collections, newest first."""
        ...
