from __future__ import annotations

import hashlib
import hmac
from typing import Any

from personal_agent_memory.repository import PostgresMemoryRepository
from personal_agent_memory.utils.serialization import json_datetime

DEFAULT_USER_ID = "0"
DEFAULT_USER_DISPLAY_NAME = "Default User"


class AuthenticationError(PermissionError):
    pass


class UserService:
    def __init__(
        self,
        *,
        repository: PostgresMemoryRepository,
        default_user_token: str | None = None,
    ) -> None:
        self.repository = repository
        self.default_user_token = default_user_token

    async def ensure_user(
        self,
        user_id: str | None = None,
        *,
        display_name: str | None = None,
    ) -> dict[str, Any]:
        return serialize_user(
            await self.repository.users.upsert(
                resolve_user_id(user_id),
                display_name=display_name,
            )
        )

    async def authenticate_token(self, token: str) -> dict[str, Any]:
        if not token:
            raise AuthenticationError("missing_token")

        token_hash = hash_token(token)
        user = await self.repository.users.find_by_token_hash(token_hash)
        if user:
            return serialize_user(user)

        if self.default_user_token and hmac.compare_digest(token, self.default_user_token):
            user = await self.ensure_user(
                DEFAULT_USER_ID,
                display_name=DEFAULT_USER_DISPLAY_NAME,
            )
            seeded_user = await self.repository.users.set_token_hash(user["id"], token_hash)
            return serialize_user(seeded_user) if seeded_user else user

        raise AuthenticationError("invalid_token")

    async def get_user(self, user_id: str | None = None) -> dict[str, Any] | None:
        user = await self.repository.users.get(resolve_user_id(user_id))
        return serialize_user(user) if user else None

    async def list_users(self) -> list[dict[str, Any]]:
        return [serialize_user(user) for user in await self.repository.users.list()]

    async def update_user(
        self,
        user_id: str,
        *,
        display_name: str | None,
    ) -> dict[str, Any] | None:
        user = await self.repository.users.update(resolve_user_id(user_id), display_name)
        return serialize_user(user) if user else None


def resolve_user_id(user_id: str | None) -> str:
    return user_id or DEFAULT_USER_ID


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def serialize_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user["id"],
        "display_name": user["display_name"],
        "created_at": json_datetime(user["created_at"]),
        "updated_at": json_datetime(user["updated_at"]),
    }
