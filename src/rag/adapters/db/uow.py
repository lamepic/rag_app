"""UnitOfWork over one SQLAlchemy session: every repository shares its transaction."""

from sqlalchemy.ext.asyncio import AsyncSession

from rag.adapters.db.repositories import SqlCollectionRepository, SqlDocumentRepository


class SqlUnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._collections = SqlCollectionRepository(session)
        self._documents = SqlDocumentRepository(session)

    @property
    def collections(self) -> SqlCollectionRepository:
        return self._collections

    @property
    def documents(self) -> SqlDocumentRepository:
        return self._documents

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
