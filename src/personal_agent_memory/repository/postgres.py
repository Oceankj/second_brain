from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

from personal_agent_memory.repository.memory_chunks import MemoryChunksRepository
from personal_agent_memory.repository.memory_item_events import MemoryItemEventsRepository
from personal_agent_memory.repository.memory_item_tags import MemoryItemTagsRepository
from personal_agent_memory.repository.memory_items import MemoryItemsRepository
from personal_agent_memory.repository.memory_links import MemoryLinksRepository
from personal_agent_memory.repository.tags import TagsRepository
from personal_agent_memory.repository.users import UsersRepository


class PostgresMemoryRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.memory_items = MemoryItemsRepository(self._connect)
        self.memory_chunks = MemoryChunksRepository(self._connect)
        self.memory_links = MemoryLinksRepository(self._connect)
        self.tags = TagsRepository(self._connect)
        self.users = UsersRepository(self._connect)
        self.memory_item_tags = MemoryItemTagsRepository(self._connect)
        self.memory_item_events = MemoryItemEventsRepository(self._connect)

    async def _connect(self) -> psycopg.AsyncConnection:
        return await psycopg.AsyncConnection.connect(self.database_url, row_factory=dict_row)
