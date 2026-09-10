from __future__ import annotations

from typing import Any

from personal_agent_memory.repository.types import Connect


class UsersRepository:
    def __init__(self, connect: Connect) -> None:
        self._connect = connect

    async def upsert(self, user_id: str, display_name: str | None = None) -> dict[str, Any]:
        async with self._connect() as conn:
            row = await conn.execute(
                """
                insert into users (id, display_name)
                values (%s, %s)
                on conflict (id) do update
                set display_name = coalesce(excluded.display_name, users.display_name),
                    updated_at = now()
                returning id, display_name, created_at, updated_at
                """,
                (user_id, display_name),
            )
            return dict(await row.fetchone())

    async def set_token_hash(self, user_id: str, token_hash: str) -> dict[str, Any] | None:
        async with self._connect() as conn:
            cursor = await conn.execute(
                """
                update users
                set api_token_hash = %s,
                    updated_at = now()
                where id = %s
                returning id, display_name, created_at, updated_at
                """,
                (token_hash, user_id),
            )
            user = await cursor.fetchone()
            return dict(user) if user else None

    async def find_by_token_hash(self, token_hash: str) -> dict[str, Any] | None:
        async with self._connect() as conn:
            cursor = await conn.execute(
                """
                select id, display_name, created_at, updated_at
                from users
                where api_token_hash = %s
                """,
                (token_hash,),
            )
            user = await cursor.fetchone()
            return dict(user) if user else None

    async def get(self, user_id: str) -> dict[str, Any] | None:
        async with self._connect() as conn:
            row = await conn.execute(
                """
                select id, display_name, created_at, updated_at
                from users
                where id = %s
                """,
                (user_id,),
            )
            user = await row.fetchone()
            return dict(user) if user else None

    async def list(self) -> list[dict[str, Any]]:
        async with self._connect() as conn:
            cursor = await conn.execute(
                """
                select id, display_name, created_at, updated_at
                from users
                order by id
                """
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def update(self, user_id: str, display_name: str | None) -> dict[str, Any] | None:
        async with self._connect() as conn:
            cursor = await conn.execute(
                """
                update users
                set display_name = %s,
                    updated_at = now()
                where id = %s
                returning id, display_name, created_at, updated_at
                """,
                (display_name, user_id),
            )
            user = await cursor.fetchone()
            return dict(user) if user else None
