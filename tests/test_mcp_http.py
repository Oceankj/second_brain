import pytest

from personal_agent_memory.config import Settings
from personal_agent_memory.server import auth, mcp_http
from personal_agent_memory.services.users import AuthenticationError


class FakeUserService:
    def __init__(self, user: dict | None = None) -> None:
        self.user = user or {
            "id": "user-1",
            "display_name": "Test User",
            "created_at": "2026-09-08T00:00:00Z",
            "updated_at": "2026-09-08T00:00:00Z",
        }
        self.tokens: list[str] = []

    async def authenticate_token(self, token: str) -> dict:
        self.tokens.append(token)
        if token == "bad-token":
            raise AuthenticationError("invalid_token")
        return self.user


@pytest.mark.anyio
async def test_memory_token_verifier_reuses_user_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_service = FakeUserService()
    monkeypatch.setattr(auth, "get_user_service", lambda: fake_service)

    access_token = await auth.MemoryTokenVerifier().verify_token("good-token")

    assert fake_service.tokens == ["good-token"]
    assert access_token is not None
    assert access_token.token == "good-token"
    assert access_token.client_id == "user-1"
    assert access_token.subject == "user-1"
    assert access_token.scopes == ["memory:read", "memory:write"]


@pytest.mark.anyio
async def test_memory_token_verifier_rejects_invalid_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth, "get_user_service", lambda: FakeUserService())

    assert await auth.MemoryTokenVerifier().verify_token("bad-token") is None


def test_authenticated_bearer_token_reads_mcp_auth_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        auth,
        "get_access_token",
        lambda: type("AccessToken", (), {"token": "transport-token"})(),
    )

    assert auth.authenticated_bearer_token() == "transport-token"


def test_authenticated_bearer_token_requires_auth_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth, "get_access_token", lambda: None)

    with pytest.raises(AuthenticationError, match="missing_token"):
        auth.authenticated_bearer_token()


def test_create_mcp_http_server_uses_http_settings() -> None:
    settings = Settings(
        database_url="postgresql://example",
        mcp_http_enabled=True,
        mcp_http_host="0.0.0.0",
        mcp_http_port=9001,
        mcp_http_path="/memory-mcp",
        mcp_http_public_url="https://memory.example.test",
        mcp_http_allowed_hosts=("memory.example.test",),
        mcp_http_allowed_origins=("https://agent.example.test",),
        mcp_http_max_request_body_size=12345,
    )

    server = mcp_http.create_mcp_http_server(settings)

    assert server.settings.host == "0.0.0.0"
    assert server.settings.port == 9001
    assert server.settings.streamable_http_path == "/memory-mcp"
    assert server.settings.max_request_body_size == 12345
    assert server.settings.auth is not None
    assert str(server.settings.auth.issuer_url).rstrip("/") == "https://memory.example.test"
    assert server.settings.auth.required_scopes == ["memory:read", "memory:write"]
    assert server.settings.transport_security is not None
    assert server.settings.transport_security.allowed_hosts == ["memory.example.test"]
    assert server.settings.transport_security.allowed_origins == ["https://agent.example.test"]
