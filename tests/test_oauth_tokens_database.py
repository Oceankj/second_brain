from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from test_oauth_login_database import database_repository  # noqa: F401

from personal_agent_memory.repository.oauth_tokens import OAuthTokensRepository
from personal_agent_memory.services.users import hash_token


@pytest.fixture
async def token_database(database_repository):  # noqa: F811
    conn, _, _ = database_repository
    family = uuid4()
    await conn.execute(
        """insert into oauth_token_families
        (id, client_id, user_id, resource, scopes, expires_at)
        values (%s, 'client', 'alice', 'https://memory.test/mcp',
                array['memory:read'], clock_timestamp() + interval '1 hour')""",
        (family,),
    )
    await conn.execute(
        """insert into oauth_access_tokens
        (token_hash, family_id, client_id, user_id, resource, scopes, expires_at)
        values (%s, %s, 'client', 'alice', 'https://memory.test/mcp',
                array['memory:read'], clock_timestamp() + interval '5 minutes')""",
        (hash_token("access-secret"), family),
    )
    await conn.execute(
        """insert into oauth_refresh_tokens (token_hash, family_id, expires_at)
        values (%s, %s, clock_timestamp() + interval '1 hour')""",
        (hash_token("refresh-secret"), family),
    )

    @asynccontextmanager
    async def connect():
        yield conn

    yield conn, OAuthTokensRepository(connect)


@pytest.mark.anyio
async def test_access_token_identity_and_token_type(token_database):
    _, repo = token_database
    row = await repo.authenticate(hash_token("access-secret"), "https://memory.test/mcp")
    assert row["user_id"] == "alice" and row["client_id"] == "client"
    assert row["scopes"] == ["memory:read"]
    for secret in ("unknown", "refresh-secret", "access-secret"):
        resource = (
            "https://other.test/mcp" if secret == "access-secret" else "https://memory.test/mcp"
        )
        assert await repo.authenticate(hash_token(secret), resource) is None


@pytest.mark.anyio
@pytest.mark.parametrize(
    "mutation",
    [
        "update oauth_access_tokens set revoked_at = clock_timestamp()",
        "update oauth_token_families set revoked_at = clock_timestamp()",
        "update oauth_clients set revoked_at = clock_timestamp()",
        "update users set is_active = false",
        "update oauth_access_tokens set created_at = clock_timestamp() - interval '2 hours', "
        "expires_at = clock_timestamp() - interval '1 hour'",
        "update oauth_token_families set created_at = clock_timestamp() - interval '2 hours', "
        "expires_at = clock_timestamp() - interval '1 hour'",
        "update oauth_access_tokens set scopes = array['memory:write']",
        "update oauth_token_families set scopes = array[]::text[]",
        "update oauth_clients set scopes = array['memory:write']",
        "update oauth_access_tokens set created_at = clock_timestamp() + interval '1 minute'",
    ],
)
async def test_access_token_rechecks_revocation_expiry_and_scope(token_database, mutation):
    conn, repo = token_database
    assert await repo.authenticate(hash_token("access-secret"), "https://memory.test/mcp")
    await conn.execute(mutation)
    assert await repo.authenticate(hash_token("access-secret"), "https://memory.test/mcp") is None
