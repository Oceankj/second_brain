import pytest

from personal_agent_memory.config import Settings
from personal_agent_memory.server import http


def test_create_http_server_includes_mcp_and_rest_routes() -> None:
    server = http.create_http_server(
        Settings(
            database_url="postgresql://example",
            rest_api_enabled=True,
            mcp_http_enabled=True,
        )
    )

    app = server.streamable_http_app()
    paths = {route.path for route in app.routes}

    assert "/mcp" in paths
    assert "/health" in paths
    assert "/users" in paths
    assert "/users/{user_id:str}" in paths
    assert "/maintenance/daily-diary" in paths


def test_main_requires_mcp_http_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        http,
        "get_settings",
        lambda: Settings(
            database_url="postgresql://example",
            rest_api_enabled=True,
            mcp_http_enabled=False,
        ),
    )

    with pytest.raises(SystemExit, match="mcp_http.enabled=true"):
        http.main()


def test_main_requires_rest_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        http,
        "get_settings",
        lambda: Settings(
            database_url="postgresql://example",
            rest_api_enabled=False,
            mcp_http_enabled=True,
        ),
    )

    with pytest.raises(SystemExit, match="MEMORY_REST_API_ENABLED=true"):
        http.main()
