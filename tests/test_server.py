import pytest

from personal_agent_memory.config import Settings
from personal_agent_memory.server import mcp, mcp_tools


class FakeMemoryService:
    def __init__(self) -> None:
        self.payloads = []

    async def get_context(self, payload):
        self.payloads.append(payload)
        return {"diary_lookback_days": payload.diary_lookback_days}


@pytest.mark.anyio
async def test_get_context_uses_configured_recent_diary_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_service = FakeMemoryService()
    monkeypatch.setattr(
        mcp_tools,
        "get_settings",
        lambda: Settings(
            database_url="postgresql://example",
            recent_diary_lookback_days=4,
        ),
    )
    monkeypatch.setattr(mcp_tools, "get_memory_service", lambda: fake_service)

    result = await mcp.get_context("continue memory work", "test-token")

    assert result == {"diary_lookback_days": 4}
    assert fake_service.payloads[0].token == "test-token"
    assert fake_service.payloads[0].diary_lookback_days == 4


@pytest.mark.anyio
async def test_get_context_call_can_override_recent_diary_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_service = FakeMemoryService()
    settings = Settings(
        database_url="postgresql://example",
        recent_diary_lookback_days=4,
    )
    monkeypatch.setattr(mcp_tools, "get_settings", lambda: settings)
    monkeypatch.setattr(mcp_tools, "get_memory_service", lambda: fake_service)

    result = await mcp.get_context(
        "continue memory work",
        "test-token",
        diary_lookback_days=1,
    )

    assert result == {"diary_lookback_days": 1}
    assert fake_service.payloads[0].diary_lookback_days == 1
