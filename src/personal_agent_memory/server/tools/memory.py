from __future__ import annotations

from typing import Any

from personal_agent_memory.contracts import GetContextInput, IngestTurnInput
from personal_agent_memory.server.dependencies import get_memory_service, get_settings


async def ingest_turn_with_token(
    *,
    token: str,
    user_input: str,
    assistant_output: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    payload = IngestTurnInput(
        token=token,
        user_input=user_input,
        assistant_output=assistant_output,
        metadata=metadata,
    )
    return await get_memory_service().ingest_turn(payload)


async def get_context_with_token(
    *,
    input: str,
    token: str,
    session_id: str | None = None,
    diary_lookback_days: int | None = None,
    max_context_chars: int = 6000,
    include_chunks: bool = False,
) -> dict[str, Any]:
    settings = get_settings()
    payload = GetContextInput(
        input=input,
        token=token,
        session_id=session_id,
        diary_lookback_days=(
            settings.recent_diary_lookback_days
            if diary_lookback_days is None
            else diary_lookback_days
        ),
        max_context_chars=max_context_chars,
        include_chunks=include_chunks,
    )
    return await get_memory_service().get_context(payload)
