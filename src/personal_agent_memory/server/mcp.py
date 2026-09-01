from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from personal_agent_memory.server.dependencies import get_memory_service, get_settings
from personal_agent_memory.tool_schemas import GetContextInput, IngestTurnInput

mcp = FastMCP("personal-agent-memory")


@mcp.tool()
async def ingest_turn(
    token: str,
    user_input: str,
    assistant_output: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Store one interaction as candidate durable memory."""

    payload = IngestTurnInput(
        token=token,
        user_input=user_input,
        assistant_output=assistant_output,
        metadata=metadata,
    )
    return await get_memory_service().ingest_turn(payload)


@mcp.tool()
async def get_context(
    input: str,
    token: str,
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
        token=token,
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
    return await get_memory_service().get_context(payload)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
