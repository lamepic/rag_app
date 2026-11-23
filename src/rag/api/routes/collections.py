"""Create and list the caller's collections."""

from fastapi import APIRouter, HTTPException, status

from rag.api.deps import CurrentUserDep, UnitOfWorkDep
from rag.api.schemas import CollectionCreate, CollectionList, CollectionOut
from rag.core.collections import CollectionNameTakenError

router = APIRouter(prefix="/v1/collections", tags=["collections"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_collection(
    body: CollectionCreate, user: CurrentUserDep, uow: UnitOfWorkDep
) -> CollectionOut:
    try:
        collection = await uow.collections.add(
            owner_id=user.id, name=body.name, description=body.description
        )
    except CollectionNameTakenError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A collection with this name already exists"
        ) from exc
    await uow.commit()
    return CollectionOut.model_validate(collection)


@router.get("")
async def list_collections(user: CurrentUserDep, uow: UnitOfWorkDep) -> CollectionList:
    collections = await uow.collections.list_for_owner(user.id)
    return CollectionList(items=[CollectionOut.model_validate(c) for c in collections])
