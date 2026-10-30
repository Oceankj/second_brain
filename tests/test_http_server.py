import httpx
import pytest

from personal_agent_memory.config import Settings
from personal_agent_memory.server.adapters import rest
from personal_agent_memory.server.entrypoints import http


def test_create_http_server_includes_mcp_and_rest_routes() -> None:
    server = http.create_http_server(Settings(database_url="postgresql://example"))

    app = server.streamable_http_app()
    paths = {route.path for route in app.routes}

    assert "/mcp" in paths
    assert "/health" in paths
    assert "/maintenance/daily-diary" in paths
    assert "/maintenance/review-candidates" in paths
    assert "/diary/{date:str}" in paths
    assert "/users" not in paths
    assert "/users/{user_id:str}" not in paths


@pytest.mark.anyio
@pytest.mark.parametrize("standalone", [False, True])
async def test_user_management_routes_are_removed(monkeypatch, standalone):
    # Old deployment settings must never re-enable the removed HTTP surface.
    monkeypatch.setenv("MEMORY_ADMIN_API_ENABLED", "true")
    monkeypatch.setenv("MEMORY_ADMIN_API_TOKEN", "a" * 32)
    app = rest.app if standalone else http.create_http_server(
        Settings(database_url="postgresql://example")
    ).streamable_http_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://localhost") as client:
        for method, path in [("GET", "/users"), ("GET", "/users/example"),
                             ("PUT", "/users/example"), ("PATCH", "/users/example")]:
            response = await client.request(method, path, headers={
                "authorization": "Bearer " + "a" * 32,
            })
            assert response.status_code == 404


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
