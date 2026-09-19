"""Real PostgreSQL authorization checks, isolated in a fully rolled-back schema."""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
import psycopg
import pytest
from psycopg import sql
from psycopg.rows import dict_row
from starlette.applications import Starlette
from test_oauth_login import PARAMS, form_values

from personal_agent_memory.config import Settings
from personal_agent_memory.repository.oauth_authorizations import OAuthAuthorizationsRepository
from personal_agent_memory.repository.oauth_clients import OAuthClientsRepository
from personal_agent_memory.repository.users import UsersRepository
from personal_agent_memory.server.adapters.oauth_login import login_routes
from personal_agent_memory.server.application import ApplicationContext
from personal_agent_memory.services.users import hash_password, hash_token


@pytest.fixture
async def database_repository():
    dsn = os.environ.get('MEMORY_TEST_DATABASE_URL')
    if not dsn:
        pytest.skip('MEMORY_TEST_DATABASE_URL is not configured')
    async with await psycopg.AsyncConnection.connect(
        dsn, row_factory=dict_row, connect_timeout=15, prepare_threshold=None, autocommit=True,
    ) as conn, conn.transaction(force_rollback=True):
        schema = 'test_oauth_login_' + uuid4().hex
        await conn.execute(sql.SQL('create schema {}').format(sql.Identifier(schema)))
        await conn.execute(sql.SQL('set local search_path to {}').format(sql.Identifier(schema)))
        await conn.execute('''create table users (id text primary key, username text unique,
            password_hash text, is_active boolean not null default true)''')
        for name in ('003_oauth_storage.sql', '004_oauth_client_metadata.sql'):
            migration = (Path(__file__).resolve().parents[1] / 'migrations' / name).read_text()
            await conn.execute(migration.strip().removeprefix('begin;').removesuffix('commit;'))
        encoded = hash_password('correct private password')
        await conn.execute(
            "insert into users (id, username, password_hash) values ('alice', 'alice', %s)",
            (encoded,),
        )
        await conn.execute('''insert into oauth_clients (client_id, client_name, redirect_uris)
            values ('client', 'Test client', %s)''', ([PARAMS['redirect_uri']],))

        @asynccontextmanager
        async def connect():
            yield conn

        repository = SimpleNamespace(
            oauth_clients=OAuthClientsRepository(connect), users=UsersRepository(connect),
            oauth_authorizations=OAuthAuthorizationsRepository(connect),
        )
        yield conn, repository, encoded


@pytest.mark.anyio
async def test_browser_approval_persists_only_hashes_and_cannot_replay(database_repository):
    conn, repository, _ = database_repository
    context = ApplicationContext(Settings(database_url='postgresql://example',
                                          public_base_url='https://memory.test'))
    context._repository = repository
    async with httpx.AsyncClient(transport=httpx.ASGITransport(
        app=Starlette(routes=login_routes(context))), base_url='https://memory.test',
    ) as browser:
        page = await browser.get('/oauth/authorize', params=PARAMS)
        assert page.status_code == 200
        original_cookie = browser.cookies.get('__Host-memory-oauth')
        form = {**form_values(page), 'username': 'ALICE', 'password': 'correct private password',
                'decision': 'approve'}
        response = await browser.post('/oauth/authorize', data=form)
        assert response.status_code == 303
        raw_code = parse_qs(urlsplit(response.headers['location']).query)['code'][0]
        cursor = await conn.execute('select * from oauth_authorization_codes')
        code = await cursor.fetchone()
        assert code['code_hash'] == hash_token(raw_code) and code['user_id'] == 'alice'
        assert code['resource'] == PARAMS['resource']
        assert code['redirect_uri'] == PARAMS['redirect_uri']
        assert code['code_challenge'] == PARAMS['code_challenge']
        assert code['scopes'] == ['memory:read']
        assert 290 <= (code['expires_at'] - code['created_at']).total_seconds() <= 310
        cursor = await conn.execute('select * from oauth_login_sessions where session_hash = %s',
                                    (hash_token(original_cookie),))
        assert (await cursor.fetchone())['revoked_at'] is not None
        # Restore the old cookie to exercise the database replay checks as well.
        browser.cookies.clear()
        browser.cookies.set('__Host-memory-oauth', original_cookie)
        assert (await browser.post('/oauth/authorize', data=form)).status_code == 400
        cursor = await conn.execute('select count(*) as n from oauth_authorization_codes')
        assert (await cursor.fetchone())['n'] == 1


@pytest.mark.anyio
@pytest.mark.parametrize('mutation', [
    "update oauth_authorization_requests set expires_at = clock_timestamp() - interval '1 second', "
    "created_at = clock_timestamp() - interval '1 hour'",
    "update oauth_login_sessions set expires_at = clock_timestamp() - interval '1 second', "
    "created_at = clock_timestamp() - interval '1 hour'",
    "update oauth_login_sessions set revoked_at = now()",
    "update oauth_clients set revoked_at = now()",
    "update oauth_clients set scopes = array[]::text[]",
    "update oauth_clients set redirect_uris = array['https://different.test/cb']",
    "update users set is_active = false",
    "update users set password_hash = 'changed'",
])
async def test_transaction_revalidates_expiry_client_and_user(database_repository, mutation):
    conn, repository, encoded = database_repository
    pending = {
        'request_hash': 'a' * 64, 'session_hash': 'b' * 64, 'client_id': 'client',
        'redirect_uri': PARAMS['redirect_uri'], 'resource': PARAMS['resource'],
        'scopes': ['memory:read'], 'state': 'test', 'code_challenge': 'A' * 43,
    }
    auth = repository.oauth_authorizations
    await auth.create(pending, 'c' * 64)
    assert await auth.get_pending('a' * 64, 'b' * 64)
    await conn.execute(mutation)
    assert await auth.finish(
        'a' * 64, 'b' * 64, 'c' * 64, user_id='alice', password_hash=encoded,
        code_hash='d' * 64, new_session_hash='e' * 64, new_csrf_hash='f' * 64,
    ) is None
    cursor = await conn.execute('select count(*) as n from oauth_authorization_codes')
    assert (await cursor.fetchone())['n'] == 0
