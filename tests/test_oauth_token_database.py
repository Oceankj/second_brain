from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from starlette.applications import Starlette
from test_oauth_login import PARAMS, form_values
from test_oauth_login_database import database_repository  # noqa: F401

from personal_agent_memory.config import Settings
from personal_agent_memory.repository.oauth_tokens import OAuthTokensRepository
from personal_agent_memory.server.adapters.oauth import oauth_routes
from personal_agent_memory.server.adapters.oauth_token import pkce_s256, token_routes
from personal_agent_memory.server.application import ApplicationContext
from personal_agent_memory.services.users import hash_token

VERIFIER = "database-verifier-which-is-at-least-forty-three-characters"
RAW_CODE = "database-authorization-code"


@pytest.mark.anyio
async def test_complete_browser_login_to_access_token_flow(database_repository):  # noqa: F811
    _, repository, _ = database_repository

    @asynccontextmanager
    async def connect():
        yield database_repository[0]

    repository.oauth_tokens = OAuthTokensRepository(connect)
    context = ApplicationContext(
        Settings(database_url="postgresql://example", public_base_url="https://memory.test")
    )
    context._repository = repository
    app = Starlette(routes=oauth_routes(context))
    params = {**PARAMS, "code_challenge": pkce_s256(VERIFIER)}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://memory.test"
    ) as browser:
        page = await browser.get("/oauth/authorize", params=params)
        callback = await browser.post(
            "/oauth/authorize",
            data={
                **form_values(page),
                "decision": "approve",
                "username": "alice",
                "password": "correct private password",
            },
        )
        code = parse_qs(urlsplit(callback.headers["location"]).query)["code"][0]
        response = await browser.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": "client",
                "redirect_uri": PARAMS["redirect_uri"],
                "resource": "https://memory.test/mcp",
                "code_verifier": VERIFIER,
            },
        )
    assert response.status_code == 200
    token = response.json()
    assert token["scope"] == "memory:read" and "refresh_token" in token
    identity = await repository.oauth_tokens.authenticate(
        hash_token(token["access_token"]), "https://memory.test/mcp"
    )
    assert identity["user_id"] == "alice" and identity["client_id"] == "client"


@pytest.fixture
async def token_database(database_repository):  # noqa: F811
    conn, repository, _ = database_repository
    await conn.execute(
        """insert into oauth_login_sessions
        (session_hash, csrf_token_hash, user_id, expires_at)
        values (%s, %s, 'alice', clock_timestamp() + interval '10 minutes')""",
        ("1" * 64, "2" * 64),
    )
    await conn.execute(
        """insert into oauth_authorization_requests
        (request_hash, session_hash, client_id, redirect_uri, resource, scopes,
         code_challenge, expires_at, consumed_at)
        values (%s, %s, 'client', %s, 'https://memory.test/mcp', array['memory:read'],
                %s, clock_timestamp() + interval '10 minutes', clock_timestamp())""",
        ("3" * 64, "1" * 64, PARAMS["redirect_uri"], pkce_s256(VERIFIER)),
    )
    await conn.execute(
        """insert into oauth_authorization_codes
        (code_hash, request_hash, client_id, user_id, redirect_uri, resource,
         scopes, code_challenge, expires_at)
        values (%s, %s, 'client', 'alice', %s, 'https://memory.test/mcp',
                array['memory:read'], %s, clock_timestamp() + interval '5 minutes')""",
        (hash_token(RAW_CODE), "3" * 64, PARAMS["redirect_uri"], pkce_s256(VERIFIER)),
    )

    @asynccontextmanager
    async def connect():
        yield conn

    repository.oauth_tokens = OAuthTokensRepository(connect)
    context = ApplicationContext(
        Settings(database_url="postgresql://example", public_base_url="https://memory.test")
    )
    context._repository = repository
    yield conn, repository.oauth_tokens, Starlette(routes=token_routes(context))


def code_form(**changes):
    return {
        "grant_type": "authorization_code",
        "code": RAW_CODE,
        "client_id": "client",
        "redirect_uri": PARAMS["redirect_uri"],
        "resource": "https://memory.test/mcp",
        "code_verifier": VERIFIER,
        **changes,
    }


@pytest.mark.anyio
async def test_code_exchange_and_refresh_replay_revoke_family(token_database):
    conn, repository, app = token_database
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://memory.test"
    ) as client:
        exchange = await client.post("/oauth/token", data=code_form())
        assert exchange.status_code == 200
        first = exchange.json()
        assert await repository.authenticate(
            hash_token(first["access_token"]), "https://memory.test/mcp"
        )
        assert (await client.post("/oauth/token", data=code_form())).json() == {
            "error": "invalid_grant"
        }
        cursor = await conn.execute("select count(*) as n from oauth_token_families")
        assert (await cursor.fetchone())["n"] == 1
        cursor = await conn.execute("select token_hash from oauth_access_tokens")
        assert (await cursor.fetchone())["token_hash"] == hash_token(first["access_token"])

        refresh_form = {
            "grant_type": "refresh_token",
            "refresh_token": first["refresh_token"],
            "client_id": "client",
            "resource": "https://memory.test/mcp",
        }
        refreshed = await client.post("/oauth/token", data=refresh_form)
        assert refreshed.status_code == 200
        second = refreshed.json()
        assert second["refresh_token"] != first["refresh_token"]
        assert await repository.authenticate(
            hash_token(second["access_token"]), "https://memory.test/mcp"
        )
        replay = await client.post("/oauth/token", data=refresh_form)
        assert replay.status_code == 400 and replay.json() == {"error": "invalid_grant"}
        assert (
            await repository.authenticate(
                hash_token(first["access_token"]), "https://memory.test/mcp"
            )
            is None
        )
        assert (
            await repository.authenticate(
                hash_token(second["access_token"]), "https://memory.test/mcp"
            )
            is None
        )
        cursor = await conn.execute(
            "select consumed_at, revoked_at from oauth_refresh_tokens where token_hash = %s",
            (hash_token(first["refresh_token"]),),
        )
        old = await cursor.fetchone()
        assert old["consumed_at"] is not None and old["revoked_at"] is not None


@pytest.mark.anyio
@pytest.mark.parametrize(
    "change",
    [
        {"client_id": "other"},
        {"redirect_uri": "https://client.test/wrong"},
        {"resource": "https://wrong.test/mcp"},
        {"code_verifier": "wrong-verifier-which-is-at-least-forty-three-characters"},
    ],
)
async def test_invalid_code_binding_does_not_consume_code(token_database, change):
    conn, _, app = token_database
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://memory.test"
    ) as client:
        response = await client.post("/oauth/token", data=code_form(**change))
        assert response.status_code == 400 and response.json() == {"error": "invalid_grant"}
        assert (await client.post("/oauth/token", data=code_form())).status_code == 200
    cursor = await conn.execute(
        "select consumed_at from oauth_authorization_codes where code_hash = %s",
        (hash_token(RAW_CODE),),
    )
    assert (await cursor.fetchone())["consumed_at"] is not None


@pytest.mark.anyio
async def test_client_without_refresh_grant_gets_access_token_only(token_database):
    conn, repository, app = token_database
    await conn.execute(
        "update oauth_clients set grant_types = array['authorization_code'] "
        "where client_id = 'client'"
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://memory.test"
    ) as client:
        response = await client.post("/oauth/token", data=code_form())
    assert response.status_code == 200 and "refresh_token" not in response.json()
    cursor = await conn.execute("select count(*) as n from oauth_refresh_tokens")
    assert (await cursor.fetchone())["n"] == 0
    assert await repository.authenticate(
        hash_token(response.json()["access_token"]), "https://memory.test/mcp"
    )


@pytest.mark.anyio
async def test_invalid_refresh_scope_or_binding_does_not_consume_token(token_database):
    conn, _, app = token_database
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://memory.test"
    ) as client:
        first = (await client.post("/oauth/token", data=code_form())).json()
        base = {
            "grant_type": "refresh_token",
            "refresh_token": first["refresh_token"],
            "client_id": "client",
            "resource": "https://memory.test/mcp",
        }
        invalid_scope = await client.post(
            "/oauth/token", data={**base, "scope": "memory:write"}
        )
        assert invalid_scope.status_code == 400
        assert invalid_scope.json() == {"error": "invalid_scope"}
        wrong_client = await client.post("/oauth/token", data={**base, "client_id": "other"})
        assert wrong_client.status_code == 400
        assert wrong_client.json() == {"error": "invalid_grant"}
        assert (await client.post("/oauth/token", data=base)).status_code == 200
    cursor = await conn.execute(
        "select consumed_at from oauth_refresh_tokens where token_hash = %s",
        (hash_token(first["refresh_token"]),),
    )
    assert (await cursor.fetchone())["consumed_at"] is not None
