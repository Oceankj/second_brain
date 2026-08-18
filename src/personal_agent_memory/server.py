from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from personal_agent_memory.config import load_settings
from personal_agent_memory.embeddings import HashEmbeddingProvider
from personal_agent_memory.repository import PostgresMemoryRepository
from personal_agent_memory.service import MemoryService
from personal_agent_memory.tool_schemas import GetContextInput, IngestTurnInput

mcp = FastMCP("personal-agent-memory")
_service: MemoryService | None = None


def get_service() -> MemoryService:
    global _service
    if _service is None:
        settings = load_settings()
        _service = MemoryService(
            repository=PostgresMemoryRepository(settings.database_url),
            embedding_provider=HashEmbeddingProvider(settings.embedding_dimension),
            max_chunk_chars=settings.max_chunk_chars,
            chunk_overlap_chars=settings.chunk_overlap_chars,
        )
    return _service


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
    diary_lookback_days: int = 2,
    limit: int = 10,
    include_links: bool = True,
    link_expansion_depth: int = 1,
    include_chunks: bool = False,
) -> dict[str, Any]:
    """Retrieve compact durable memory context for the caller input."""

    payload = GetContextInput(
        input=input,
        user_id=user_id,
        session_id=session_id,
        memory_types=memory_types or ["note", "diary", "profile_memory"],
        diary_lookback_days=diary_lookback_days,
        limit=limit,
        include_links=include_links,
        link_expansion_depth=link_expansion_depth,
        include_chunks=include_chunks,
    )
    return await get_service().get_context(payload)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
