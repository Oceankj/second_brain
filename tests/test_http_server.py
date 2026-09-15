import pytest

from personal_agent_memory.config import Settings
from personal_agent_memory.server.entrypoints import http


def test_create_http_server_includes_mcp_and_rest_routes() -> None:
    server = http.create_http_server(Settings(database_url="postgresql://example"))

    app = server.streamable_http_app()
    paths = {route.path for route in app.routes}

    assert "/mcp" in paths
    assert "/health" in paths
    assert "/maintenance/daily-diary" in paths
    assert "/users" not in paths
    assert "/users/{user_id:str}" not in paths


def test_create_http_server_registers_only_enabled_api_groups() -> None:
    server = http.create_http_server(
        Settings(
            database_url="postgresql://example",
            admin_api_enabled=True,
        )
    )

    paths = {route.path for route in server.streamable_http_app().routes}

    assert "/mcp" in paths
    assert "/health" in paths
    assert "/users" in paths
    assert "/users/{user_id:str}" in paths
    assert "/maintenance/daily-diary" in paths


def test_main_starts_unified_http_server(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Settings, str]] = []
    settings = Settings(database_url="postgresql://example")

    class FakeServer:
        def run(self, *, transport: str) -> None:
            calls.append((settings, transport))

    monkeypatch.setattr(
        http,
        "get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(http, "create_http_server", lambda _: FakeServer())

    http.main()

    assert calls == [(settings, "streamable-http")]
