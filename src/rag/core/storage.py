"""The port for storing uploaded files (blobs) by key."""

from typing import BinaryIO, Protocol


class BlobStoreError(Exception):
    """The store failed (unreachable, refused, timed out). Maps to 503."""


class BlobStore(Protocol):
    async def put(self, key: str, data: BinaryIO, *, content_type: str) -> None:
        """Store `data` under `key`, replacing anything already there."""
        ...

    async def delete(self, key: str) -> None:
        """Remove `key`. Deleting a missing key is not an error."""
        ...
