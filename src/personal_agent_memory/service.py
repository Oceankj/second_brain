from __future__ import annotations

from typing import Any

from personal_agent_memory.embeddings import EmbeddingProvider
from personal_agent_memory.repository import PostgresMemoryRepository
from personal_agent_memory.services.ingestion import IngestionService
from personal_agent_memory.services.retrieval import RetrievalService
from personal_agent_memory.tool_schemas import GetContextInput, IngestTurnInput


class MemoryService:
    """Thin facade that keeps the MCP adapter independent from individual use cases."""

    def __init__(
        self,
        *,
        repository: PostgresMemoryRepository,
        embedding_provider: EmbeddingProvider,
        max_chunk_chars: int,
        chunk_overlap_chars: int,
    ) -> None:
        self.ingestion = IngestionService(
            repository=repository,
            embedding_provider=embedding_provider,
            max_chunk_chars=max_chunk_chars,
            chunk_overlap_chars=chunk_overlap_chars,
        )
        self.retrieval = RetrievalService(
            repository=repository,
            embedding_provider=embedding_provider,
        )

    async def ingest_turn(self, payload: IngestTurnInput) -> dict[str, Any]:
        return await self.ingestion.ingest_turn(payload)

    async def get_context(self, payload: GetContextInput) -> dict[str, Any]:
        return await self.retrieval.get_context(payload)
