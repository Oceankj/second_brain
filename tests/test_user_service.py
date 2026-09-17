from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from personal_agent_memory.services.users import (
    DEFAULT_USER_ID,
    AuthenticationError,
    UserService,
    hash_token,
)


class FakeUsersRepository:
    def __init__(self) -> None:
        self.rows = {
            DEFAULT_USER_ID: make_user(DEFAULT_USER_ID, "Default User"),
        }
        self.upsert_calls = []
        self.update_calls = []
        self.token_hashes = {}

    async def upsert(self, user_id: str, display_name: str | None = None) -> dict[str, Any]:
        self.upsert_calls.append((user_id, display_name))
        existing = self.rows.get(user_id)
        if existing:
            if display_name is not None:
                existing = {**existing, "display_name": display_name}
                self.rows[user_id] = existing
            return existing

        user = make_user(user_id, display_name)
        self.rows[user_id] = user
        return user

    async def get(self, user_id: str) -> dict[str, Any] | None:
        return self.rows.get(user_id)

    async def find_by_token_hash(self, token_hash: str) -> dict[str, Any] | None:
        user_id = self.token_hashes.get(token_hash)
        return self.rows.get(user_id) if user_id else None

    async def set_token_hash(self, user_id: str, token_hash: str) -> dict[str, Any] | None:
        if user_id not in self.rows:
            return None
        self.token_hashes[token_hash] = user_id
        return self.rows[user_id]

    async def list(self) -> list[dict[str, Any]]:
        return list(self.rows.values())

    async def update(self, user_id: str, display_name: str | None) -> dict[str, Any] | None:
        self.update_calls.append((user_id, display_name))
        existing = self.rows.get(user_id)
        if existing is None:
            return None
        updated = {**existing, "display_name": display_name}
        self.rows[user_id] = updated
        return updated


class FakeRepository:
    def __init__(self) -> None:
        self.users = FakeUsersRepository()


def make_user(user_id: str, display_name: str | None) -> dict[str, Any]:
    return {
        "id": user_id,
        "display_name": display_name,
        "created_at": datetime(2026, 8, 31, tzinfo=UTC),
        "updated_at": datetime(2026, 8, 31, tzinfo=UTC),
    }


@pytest.mark.anyio
async def test_ensure_user_defaults_to_user_zero() -> None:
    repository = FakeRepository()
    service = UserService(repository=repository)

    user = await service.ensure_user()

    assert repository.users.upsert_calls == [(DEFAULT_USER_ID, None)]
    assert user["id"] == DEFAULT_USER_ID
    assert user["display_name"] == "Default User"
    assert user["created_at"] == "2026-08-31T00:00:00+00:00"


@pytest.mark.anyio
async def test_update_user_returns_serialized_user() -> None:
    repository = FakeRepository()
    service = UserService(repository=repository)

    user = await service.update_user(DEFAULT_USER_ID, display_name="Ching")

    assert repository.users.update_calls == [(DEFAULT_USER_ID, "Ching")]
    assert user is not None
    assert user["display_name"] == "Ching"


@pytest.mark.anyio
async def test_update_user_returns_none_for_missing_user() -> None:
    repository = FakeRepository()
    service = UserService(repository=repository)

    user = await service.update_user("missing", display_name="Nobody")

    assert user is None


@pytest.mark.anyio
async def test_authenticate_default_user_token_seeds_token_hash() -> None:
    repository = FakeRepository()
    service = UserService(repository=repository, default_user_token="x" * 32)

    user = await service.authenticate_token("x" * 32)

    assert user["id"] == DEFAULT_USER_ID
    assert repository.users.token_hashes == {hash_token("x" * 32): DEFAULT_USER_ID}


@pytest.mark.anyio
async def test_authenticate_existing_token_hash_returns_matching_user() -> None:
    repository = FakeRepository()
    repository.users.token_hashes[hash_token("y" * 32)] = DEFAULT_USER_ID
    service = UserService(repository=repository)

    user = await service.authenticate_token("y" * 32)

    assert user["id"] == DEFAULT_USER_ID


@pytest.mark.anyio
async def test_authenticate_token_rejects_unknown_token() -> None:
    repository = FakeRepository()
    service = UserService(repository=repository, default_user_token="x" * 32)

    with pytest.raises(AuthenticationError, match="invalid_token"):
        await service.authenticate_token("z" * 32)


@pytest.mark.anyio
@pytest.mark.parametrize("seeded", [True, False])
async def test_disabled_user_cannot_use_default_token(seeded: bool) -> None:
    repository = FakeRepository()
    repository.users.rows[DEFAULT_USER_ID]["is_active"] = False
    token = "x" * 32
    if seeded:
        repository.users.token_hashes[hash_token(token)] = DEFAULT_USER_ID
    service = UserService(repository=repository, default_user_token=token)

    with pytest.raises(AuthenticationError, match="^invalid_token$"):
        await service.authenticate_token(token)
    assert not repository.users.upsert_calls


@pytest.mark.anyio
async def test_user_responses_exclude_credentials() -> None:
    repository = FakeRepository()
    repository.users.rows[DEFAULT_USER_ID].update(
        password_hash="private-password-hash", api_token_hash="private-token-hash"
    )
    repository.users.token_hashes[hash_token("token")] = DEFAULT_USER_ID
    service = UserService(repository=repository)

    responses = [
        await service.get_user(),
        *(await service.list_users()),
        await service.ensure_user(),
        await service.update_user(DEFAULT_USER_ID, display_name="Updated"),
        await service.authenticate_token("token"),
    ]
    for response in responses:
        assert response is not None
        assert "password_hash" not in response
        assert "api_token_hash" not in response
        assert "private-" not in str(response)
