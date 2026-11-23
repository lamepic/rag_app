"""Who am I? The simplest authenticated endpoint: proves a token works."""

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from rag.api.deps import CurrentUserDep

router = APIRouter(prefix="/v1", tags=["auth"])


class MeResponse(BaseModel):
    id: uuid.UUID
    email: str | None


@router.get("/me")
async def me(user: CurrentUserDep) -> MeResponse:
    return MeResponse(id=user.id, email=user.email)
