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

    async def list_for_owner(self, owner_id: uuid.UUID) -> list[Collection]:
        rows = await self._session.scalars(
            select(models.Collection)
            .where(models.Collection.owner_id == owner_id)
            .order_by(models.Collection.created_at.desc(), models.Collection.id)
        )
        return [_to_collection(row) for row in rows]
