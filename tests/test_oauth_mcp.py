import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import psycopg
import pytest

from personal_agent_memory.config import Settings
from personal_agent_memory.contracts.memory import GetContextData
from personal_agent_memory.server.adapters.mcp_http import create_mcp_http_server
from personal_agent_memory.server.application import ApplicationContext
from personal_agent_memory.server.auth.transport import OAuthTokenVerifier
from personal_agent_memory.services.memory import MemoryService
from personal_agent_memory.services.users import hash_token


def token_row(user="alice", scopes=None):
    return dict(
        user_id=user,
        client_id="client",
        resource="https://memory.test/mcp",
        scopes=scopes or ["memory:read"],
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


@pytest.mark.anyio
async def test_verifier_hashes_token_and_fails_closed():
    repository = SimpleNamespace(authenticate=AsyncMock(return_value=token_row()))
    verifier = OAuthTokenVerifier(
        lambda: repository, resource="https://memory.test/mcp", issuer="https://memory.test"
    )
    token = await verifier.verify_token("secret")
    repository.authenticate.assert_awaited_once_with(hash_token("secret"), verifier.resource)
    assert token.subject == "alice" and token.client_id == "client"
    assert token.claims == {"iss": "https://memory.test"}
    repository.authenticate.return_value = None
    assert await verifier.verify_token("legacy-token") is None
    repository.authenticate.side_effect = psycopg.OperationalError("unavailable")
    assert await verifier.verify_token("secret") is None
    assert await verifier.verify_token("") is None
    assert await verifier.verify_token("x" * 4097) is None


def rpc_result(response):
    assert response.status_code == 200, response.text
    if response.headers["content-type"].startswith("application/json"):
        return response.json()
    return json.loads(
        next(line[6:] for line in response.text.splitlines() if line.startswith("data: "))
    )


@pytest.mark.anyio
async def test_http_auth_scopes_identity_and_session_isolation():
    rows = {
        "read": token_row(),
        "write": token_row(scopes=["memory:write"]),
        "bob": token_row("bob"),
    }

    async def authenticate(digest, resource):
        return next((row for raw, row in rows.items() if hash_token(raw) == digest), None)

    context = ApplicationContext(
        Settings(
            database_url="postgresql://example",
            public_base_url="https://memory.test",
            mcp_http_allowed_hosts=("memory.test",),
        )
    )
    context._repository = SimpleNamespace(oauth_tokens=SimpleNamespace(authenticate=authenticate))
    context.startup = AsyncMock()
    context.shutdown = AsyncMock()
    context._memory_service = SimpleNamespace(
        get_context_as_user=AsyncMock(return_value={"ok": True}),
        ingest_turn_as_user=AsyncMock(return_value={"ok": True}),
    )
    server = create_mcp_http_server(context=context)
    app = server.streamable_http_app()
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="https://memory.test",
            headers={"Accept": "application/json, text/event-stream"},
        ) as client,
    ):
        metadata = await client.get("/.well-known/oauth-protected-resource/mcp")
        assert metadata.json()["scopes_supported"] == ["memory:read", "memory:write"]
        for headers in ({}, {"Authorization": "Bearer unknown"}):
            response = await client.post("/mcp", json={}, headers=headers)
            assert response.status_code == 401
            assert "resource_metadata=" in response.headers["www-authenticate"]
        client.headers["Authorization"] = "Bearer read"
        response = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
        )
        rpc_result(response)
        client.headers["Mcp-Session-Id"] = response.headers["mcp-session-id"]
        await client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"})

        async def call(name, arguments):
            return rpc_result(
                await client.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {"name": name, "arguments": arguments},
                    },
                )
            )["result"]

        tools = rpc_result(
            await client.post(
                "/mcp", json={"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}}
            )
        )["result"]["tools"]
        for tool in tools:
            assert not {"token", "user_id", "ctx"} & tool["inputSchema"]["properties"].keys()
        assert not (await call("get_context", {"input": "hello"})).get("isError")
        context._memory_service.get_context_as_user.assert_awaited_once()
        assert context._memory_service.get_context_as_user.call_args.kwargs == {"user_id": "alice"}
        ingest = {
            "user_input": "hello",
            "assistant_output": "world",
            "metadata": {
                "timestamp": "2026-09-18T00:00:00Z",
                "source": "test",
                "ingest_reason": "explicit_memory_request",
            },
        }
        assert (await call("ingest_turn", ingest))["isError"]
        context._memory_service.ingest_turn_as_user.assert_not_awaited()
        # Same principal, changed scope: use THIS request's credentials, not initial session scope.
        client.headers["Authorization"] = "Bearer write"
        assert (await call("get_context", {"input": "hello"}))["isError"]
        result = await call("ingest_turn", ingest)
        assert not result.get("isError"), result
        assert context._memory_service.ingest_turn_as_user.call_args.kwargs == {"user_id": "alice"}
        client.headers["Authorization"] = "Bearer bob"
        response = await client.post(
            "/mcp", json={"jsonrpc": "2.0", "id": 4, "method": "tools/list", "params": {}}
        )
        assert response.status_code in (403, 404)
        client.headers["Authorization"] = "Bearer read"
        del rows["read"]  # Revocation takes effect even for an existing MCP session.
        assert (await client.post("/mcp", json={})).status_code == 401


@pytest.mark.anyio
async def test_trusted_service_entry_overwrites_payload_identity():
    service = object.__new__(MemoryService)
    service.retrieval = SimpleNamespace(get_context=AsyncMock(return_value={}))
    service.user_service = SimpleNamespace(authenticate_token=AsyncMock())
    await service.get_context_as_user(GetContextData(input="hello", user_id="bob"), user_id="alice")
    assert service.retrieval.get_context.call_args.args[0].user_id == "alice"
    service.user_service.authenticate_token.assert_not_awaited()
    with pytest.raises(ValueError):
        await service.get_context_as_user(GetContextData(input="hello"), user_id="")
