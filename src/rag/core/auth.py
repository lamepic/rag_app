"""Who is calling: the authenticated user and the port that produces one from a token."""

import uuid
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class CurrentUser:
    id: uuid.UUID  # the token's `sub`; becomes owner_id on every row this user creates
    email: str | None


class InvalidTokenError(Exception):
    """The token is malformed, expired, forged or meant for someone else. Maps to 401."""


class AuthUnavailableError(Exception):
    """We could not fetch the keys needed to check tokens. Maps to 503: not the caller's fault."""


class TokenVerifier(Protocol):
    async def verify(self, token: str) -> CurrentUser:
        """Return the user the token belongs to, or raise InvalidTokenError."""
        ...
