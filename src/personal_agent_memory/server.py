from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from personal_agent_memory.config import Settings, load_settings
from personal_agent_memory.providers.embeddings import EmbeddingProvider, OllamaEmbeddingProvider
from personal_agent_memory.repository import PostgresMemoryRepository
from personal_agent_memory.service import MemoryService
from personal_agent_memory.tool_schemas import GetContextInput, IngestTurnInput

mcp = FastMCP("personal-agent-memory")
_service: MemoryService | None = None
_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def get_service() -> MemoryService:
    global _service
    if _service is None:
        settings = get_settings()
        _service = MemoryService(
            repository=PostgresMemoryRepository(settings.database_url),
            embedding_provider=build_embedding_provider(settings),
            max_chunk_chars=settings.max_chunk_chars,
            chunk_overlap_chars=settings.chunk_overlap_chars,
            recent_diary_max_items=settings.recent_diary_max_items,
            recent_diary_min_score=settings.recent_diary_min_score,
            recent_diary_max_chars=settings.recent_diary_max_chars,
            tag_retrieval_min_score=settings.tag_retrieval_min_score,
            tag_retrieval_max_tags=settings.tag_retrieval_max_tags,
            tag_retrieval_tag_weight=settings.tag_retrieval_tag_weight,
        )
    return _service


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    return OllamaEmbeddingProvider(
        model=settings.ollama_embedding_model,
        dimension=settings.embedding_dimension,
        base_url=settings.ollama_base_url,
        timeout_seconds=settings.ollama_timeout_seconds,
    )


@mcp.tool()
async def ingest_turn(
    user_input: str,
    assistant_output: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Store one interaction as candidate durable memory."""

    payload = IngestTurnInput(
        user_input=user_input,
        assistant_output=assistant_output,
        metadata=metadata,
    )
    return await get_service().ingest_turn(payload)


@mcp.tool()
async def get_context(
    input: str,
    user_id: str,
    session_id: str | None = None,
    memory_types: list[str] | None = None,
    diary_lookback_days: int | None = None,
    limit: int = 10,
    max_context_chars: int = 6000,
    include_links: bool = True,
    link_expansion_depth: int = 1,
    include_chunks: bool = False,
) -> dict[str, Any]:
    """Retrieve compact durable memory context for the caller input."""

    settings = get_settings()
    payload = GetContextInput(
        input=input,
        user_id=user_id,
        session_id=session_id,
        memory_types=memory_types or ["note", "diary", "profile_memory"],
        diary_lookback_days=(
            settings.recent_diary_lookback_days
            if diary_lookback_days is None
            else diary_lookback_days
        ),
        limit=limit,
        max_context_chars=max_context_chars,
        include_links=include_links,
        link_expansion_depth=link_expansion_depth,
        include_chunks=include_chunks,
    )
    return await get_service().get_context(payload)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
