from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import psycopg
import pytest
from starlette.applications import Starlette

from personal_agent_memory.config import Settings
from personal_agent_memory.server.adapters.oauth_token import pkce_s256, token_routes
from personal_agent_memory.server.application import ApplicationContext
from personal_agent_memory.services.users import hash_token

VERIFIER = "correct-verifier-which-is-at-least-forty-three-characters"


@pytest.fixture
def token_app():
    tokens = AsyncMock()
    valid = {
        "user_id": "alice",
        "client_id": "client",
        "resource": "https://memory.test/mcp",
        "scopes": ["memory:read"],
        "expires_at": datetime.now(UTC) + timedelta(hours=1),
        "refresh_token_issued": True,
    }
    tokens.exchange_authorization_code.return_value = valid
    tokens.rotate_refresh_token.return_value = valid
    context = ApplicationContext(
        Settings(database_url="postgresql://example", public_base_url="https://memory.test")
    )
    context._repository = SimpleNamespace(oauth_tokens=tokens)
    return Starlette(routes=token_routes(context)), tokens


@pytest.mark.anyio
async def test_code_exchange_uses_pkce_and_returns_opaque_tokens(token_app):
    app, tokens = token_app
    form = {
        "grant_type": "authorization_code",
        "code": "authorization-code-secret",
        "client_id": "client",
        "redirect_uri": "https://chatgpt.com/callback",
        "resource": "https://memory.test/mcp",
        "code_verifier": VERIFIER,
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://memory.test"
    ) as client:
        response = await client.post("/oauth/token", data=form)
    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "Bearer"
    assert payload["scope"] == "memory:read"
    assert 3500 <= payload["expires_in"] <= 3600
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    kwargs = tokens.exchange_authorization_code.call_args.kwargs
    assert kwargs["code_hash"] == hash_token(form["code"])
    assert kwargs["code_challenge"] == pkce_s256(VERIFIER)
    assert kwargs["access_token_hash"] == hash_token(payload["access_token"])
    assert kwargs["refresh_token_hash"] == hash_token(payload["refresh_token"])
    assert payload["access_token"] not in str(tokens.exchange_authorization_code.call_args)


@pytest.mark.anyio
async def test_refresh_rotates_token_and_can_downscope(token_app):
    app, tokens = token_app
    form = {
        "grant_type": "refresh_token",
        "refresh_token": "refresh-token-secret-value",
        "client_id": "client",
        "resource": "https://memory.test/mcp",
        "scope": "memory:read",
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://memory.test"
    ) as client:
        response = await client.post("/oauth/token", data=form)
    assert response.status_code == 200
    payload = response.json()
    kwargs = tokens.rotate_refresh_token.call_args.kwargs
    assert kwargs["refresh_token_hash"] == hash_token(form["refresh_token"])
    assert kwargs["next_refresh_token_hash"] == hash_token(payload["refresh_token"])
    assert kwargs["scopes"] == ["memory:read"]


@pytest.mark.anyio
async def test_code_exchange_omits_refresh_token_when_client_did_not_register_grant(token_app):
    app, tokens = token_app
    tokens.exchange_authorization_code.return_value["refresh_token_issued"] = False
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://memory.test"
    ) as client:
        response = await client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": "authorization-code-secret",
                "client_id": "client",
                "redirect_uri": "https://chatgpt.com/callback",
                "resource": "https://memory.test/mcp",
                "code_verifier": VERIFIER,
            },
        )
    assert response.status_code == 200
    assert "refresh_token" not in response.json()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("data", "headers", "error", "status"),
    [
        ({}, {}, "invalid_request", 400),
        ({"grant_type": "client_credentials"}, {}, "unsupported_grant_type", 400),
        ({"grant_type": "authorization_code"}, {}, "invalid_request", 400),
        ({"grant_type": "refresh_token"}, {}, "invalid_request", 400),
        (
            {
                "grant_type": "refresh_token",
                "refresh_token": "x" * 30,
                "client_id": "client",
                "resource": "https://memory.test/mcp",
                "scope": "admin",
            },
            {},
            "invalid_scope",
            400,
        ),
        (
            {
                "grant_type": "refresh_token",
                "refresh_token": "x" * 30,
                "client_id": "client",
                "resource": "https://memory.test/mcp",
            },
            {"Authorization": "Basic bad"},
            "invalid_client",
            401,
        ),
    ],
)
async def test_token_request_errors_do_not_call_repository(token_app, data, headers, error, status):
    app, tokens = token_app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://memory.test"
    ) as client:
        response = await client.post("/oauth/token", data=data, headers=headers)
    assert response.status_code == status and response.json() == {"error": error}
    tokens.exchange_authorization_code.assert_not_awaited()
    tokens.rotate_refresh_token.assert_not_awaited()


@pytest.mark.anyio
async def test_invalid_grant_replay_and_database_failure(token_app):
    app, tokens = token_app
    form = {
        "grant_type": "refresh_token",
        "refresh_token": "x" * 30,
        "client_id": "client",
        "resource": "https://memory.test/mcp",
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://memory.test"
    ) as client:
        tokens.rotate_refresh_token.return_value = {"replayed": True}
        assert (await client.post("/oauth/token", data=form)).json() == {"error": "invalid_grant"}
        tokens.rotate_refresh_token.side_effect = psycopg.OperationalError("unavailable")
        response = await client.post("/oauth/token", data=form)
    assert response.status_code == 503
    assert response.json() == {"error": "temporarily_unavailable"}
