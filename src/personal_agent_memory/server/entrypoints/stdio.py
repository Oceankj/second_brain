from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from personal_agent_memory.server.tools.memory import (
    get_context_with_token,
    ingest_turn_with_token,
)

mcp = FastMCP("personal-agent-memory")


@mcp.tool()
async def ingest_turn(
    token: str,
    user_input: str,
    assistant_output: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Store one interaction as candidate durable memory."""

    return await ingest_turn_with_token(
        token=token,
        user_input=user_input,
        assistant_output=assistant_output,
        metadata=metadata,
    )


@mcp.tool()
async def get_context(
    input: str,
    token: str,
    session_id: str | None = None,
    diary_lookback_days: int | None = None,
    max_context_chars: int = 6000,
    include_chunks: bool = False,
) -> dict[str, Any]:
    """Retrieve compact durable memory context for the caller input."""

    return await get_context_with_token(
        input=input,
        token=token,
        session_id=session_id,
        diary_lookback_days=diary_lookback_days,
        max_context_chars=max_context_chars,
        include_chunks=include_chunks,
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
