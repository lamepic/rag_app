"""Unit of Work: the repositories for one request, plus the one place that commits.

Everything done through a UnitOfWork is a single transaction. Nothing is saved
until commit(); if commit() is never reached (an error, an early return), the
work is rolled back when the request ends.
"""

from typing import Protocol

from rag.core.collections import CollectionRepository
from rag.core.documents import DocumentRepository


class UnitOfWork(Protocol):
    @property
    def collections(self) -> CollectionRepository: ...

    @property
    def documents(self) -> DocumentRepository: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None:
        """Undo uncommitted work so the transaction can be used again (e.g. after a conflict)."""
        ...
