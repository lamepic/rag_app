"""Health check: is the process up and serving requests?"""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]


@router.get("/health")
async def health() -> HealthResponse:
    return HealthResponse(status="ok")
