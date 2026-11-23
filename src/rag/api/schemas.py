"""Request and response bodies: the API's public contract.

Kept separate from domain objects so the API can stay stable while internals change.
"""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from rag.core.documents import DocumentStatus

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


class CollectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")  # a typo'd field is an error, not silently ignored

    name: Name
    description: Description | None = None


class CollectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # build from the domain dataclass

    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime


class CollectionList(BaseModel):
    # An object, not a bare array, so pagination fields can be added later without
    # breaking clients.
    items: list[CollectionOut]


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    collection_id: uuid.UUID
    filename: str
    size_bytes: int
    status: DocumentStatus
    created_at: datetime
    updated_at: datetime


class DocumentList(BaseModel):
    items: list[DocumentOut]
