from __future__ import annotations

from typing import Any

from personal_agent_memory.repository.types import Connect


class UsersRepository:
    def __init__(self, connect: Connect) -> None:
        self._connect = connect

    async def create_login(
        self, user_id: str, username: str, password_hash: str, display_name: str | None
    ) -> dict[str, Any]:
        async with self._connect() as conn:
            cursor = await conn.execute(
                """
                insert into users (id, username, password_hash, display_name)
                values (%s, lower(%s), %s, %s)
                returning id, username, display_name, is_active
                """,
                (user_id, username, password_hash, display_name),
            )
            return dict(await cursor.fetchone())

    async def set_password(self, username: str, password_hash: str) -> bool:
        async with self._connect() as conn:
            cursor = await conn.execute(
                """
                update users set password_hash = %s, updated_at = now()
                where username = lower(%s)
                returning id
                """,
                (password_hash, username),
            )
            return await cursor.fetchone() is not None

    async def set_active(self, username: str, active: bool) -> bool:
        async with self._connect() as conn:
            cursor = await conn.execute(
                """
                update users set is_active = %s, updated_at = now()
                where username = lower(%s)
                returning id
                """,
                (active, username),
            )
            return await cursor.fetchone() is not None

    async def list_logins(self) -> list[dict[str, Any]]:
        async with self._connect() as conn:
            cursor = await conn.execute(
                """
                select id, username, display_name, is_active,
                       password_hash is not null as password_configured
                from users order by username nulls last, id
                """
            )
            return [dict(row) for row in await cursor.fetchall()]

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
                select id, display_name, created_at, updated_at, is_active
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
                select id, display_name, created_at, updated_at, is_active
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
