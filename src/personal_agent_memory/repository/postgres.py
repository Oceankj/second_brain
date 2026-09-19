from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import psycopg
from psycopg.rows import dict_row

from personal_agent_memory.repository.memory_chunks import MemoryChunksRepository
from personal_agent_memory.repository.memory_item_events import MemoryItemEventsRepository
from personal_agent_memory.repository.memory_item_tags import MemoryItemTagsRepository
from personal_agent_memory.repository.memory_items import MemoryItemsRepository
from personal_agent_memory.repository.memory_links import MemoryLinksRepository
from personal_agent_memory.repository.oauth_authorizations import OAuthAuthorizationsRepository
from personal_agent_memory.repository.oauth_clients import OAuthClientsRepository
from personal_agent_memory.repository.oauth_tokens import OAuthTokensRepository
from personal_agent_memory.repository.tags import TagsRepository
from personal_agent_memory.repository.users import UsersRepository

if TYPE_CHECKING:
    from psycopg_pool import AsyncConnectionPool


class PostgresMemoryRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._pool: AsyncConnectionPool | None = None
        self.memory_items = MemoryItemsRepository(self._connect)
        self.memory_chunks = MemoryChunksRepository(self._connect)
        self.memory_links = MemoryLinksRepository(self._connect)
        self.tags = TagsRepository(self._connect)
        self.users = UsersRepository(self._connect)
        self.oauth_clients = OAuthClientsRepository(self._connect)
        self.oauth_tokens = OAuthTokensRepository(self._connect)
        self.oauth_authorizations = OAuthAuthorizationsRepository(self._connect)
        self.memory_item_tags = MemoryItemTagsRepository(self._connect)
        self.memory_item_events = MemoryItemEventsRepository(self._connect)

    async def open_pool(
        self,
        *,
        min_size: int,
        max_size: int,
        timeout_seconds: float,
    ) -> None:
        if self._pool is not None:
            return

        try:
            from psycopg_pool import AsyncConnectionPool
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "psycopg_pool is required for server connection pooling; "
                "install the project with the declared runtime dependencies."
            ) from exc

        self._pool = AsyncConnectionPool(
            self.database_url,
            min_size=min_size,
            max_size=max_size,
            timeout=timeout_seconds,
            kwargs={"row_factory": dict_row},
            open=False,
        )
        await self._pool.open()

    async def close_pool(self) -> None:
        if self._pool is None:
            return

        await self._pool.close()
        self._pool = None

    @asynccontextmanager
    async def _connect(self) -> AsyncIterator[psycopg.AsyncConnection]:
        if self._pool is not None:
            async with self._pool.connection() as conn:
                yield conn
            return

        async with await psycopg.AsyncConnection.connect(
            self.database_url,
            row_factory=dict_row,
        ) as conn:
            yield conn
