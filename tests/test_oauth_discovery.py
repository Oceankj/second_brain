from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from personal_agent_memory.config import Settings
from personal_agent_memory.repository.oauth_clients import OAuthClientsRepository
from personal_agent_memory.server.adapters.oauth import oauth_routes, registration_metadata
from personal_agent_memory.server.application import ApplicationContext
from personal_agent_memory.server.entrypoints.http import create_http_server, register_rest_routes


@pytest.mark.anyio
async def test_discovery_and_challenge_use_configured_origin():
    settings = Settings(database_url='postgresql://example', public_base_url='https://MEMORY.test:443')
    app = create_http_server(settings).streamable_http_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url='https://memory.test') as client:
        metadata = (await client.get('/.well-known/oauth-authorization-server')).json()
        root = (await client.get('/.well-known/oauth-protected-resource')).json()
        path = (await client.get('/.well-known/oauth-protected-resource/mcp')).json()
        assert metadata['issuer'] == root['authorization_servers'][0] == 'https://memory.test/'
        assert root['resource'] == path['resource'] == 'https://memory.test/mcp'
        assert metadata['registration_endpoint'] == 'https://memory.test/oauth/register'
        assert metadata['token_endpoint_auth_methods_supported'] == ['none']
        assert metadata['code_challenge_methods_supported'] == ['S256']
        assert metadata['response_types_supported'] == ['code']
        assert 'client_id_metadata_document_supported' not in metadata
        response = await client.post('/mcp')
        assert response.status_code == 401
        assert 'https://memory.test/.well-known/oauth-protected-resource/mcp' in (
            response.headers['www-authenticate']
        )
        spoof = (await client.get('/.well-known/oauth-authorization-server',
                                 headers={'host': 'evil.test'})).json()
        assert spoof['issuer'] == metadata['issuer']


@pytest.fixture
def app_and_repository():
    settings = Settings(database_url='postgresql://example')
    context = ApplicationContext(settings)
    clients = AsyncMock()
    clients.create.return_value = {'created_at': datetime(2026, 1, 1, tzinfo=UTC)}
    context._repository = SimpleNamespace(oauth_clients=clients)
    # Use the same custom-route mounting code as the HTTP entrypoint.
    from mcp.server.fastmcp import FastMCP
    server = FastMCP('registration-test')
    register_rest_routes(server, oauth_routes(context))
    return server.streamable_http_app(), clients


@pytest.mark.anyio
async def test_register_persists_exact_redirects_and_negotiated_metadata(app_and_repository):
    app, repository = app_and_repository
    payload = {'redirect_uris': ['https://chatgpt.com/callback?x=%2F'],
               'token_endpoint_auth_method': 'none', 'client_name': 'ChatGPT',
               'grant_types': ['authorization_code', 'refresh_token'], 'scope': 'memory:read'}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url='http://localhost') as client:
        first = await client.post('/oauth/register', json=payload)
        second = await client.post('/oauth/register', json=payload)
    assert first.status_code == 201
    data = first.json()
    assert data['redirect_uris'] == payload['redirect_uris']
    assert data['scope'] == 'memory:read'
    assert data['client_id'] != second.json()['client_id']
    assert 'client_secret' not in data
    assert first.headers['cache-control'] == 'no-store'
    assert repository.create.call_args.args[0]['grant_types'] == payload['grant_types']


@pytest.mark.parametrize('payload', [
    {}, [], {'redirect_uris': []}, {'redirect_uris': ['javascript:alert(1)']},
    {'redirect_uris': ['http://public.example/callback']},
    {'redirect_uris': ['https://example.com/callback#fragment']},
    {'redirect_uris': ['https://name:password@example.com/callback']},
    {'redirect_uris': ['https://example.com/\ncallback']},
    {'redirect_uris': ['https://example.com'], 'token_endpoint_auth_method': 'client_secret_basic'},
    {'redirect_uris': ['https://example.com'], 'grant_types': ['client_credentials']},
    {'redirect_uris': ['https://example.com'], 'scope': 'admin'},
    {'redirect_uris': ['https://example.com'], 'response_types': ['token']},
])
@pytest.mark.anyio
async def test_bad_registration_does_not_write(payload, app_and_repository):
    app, repository = app_and_repository
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url='http://localhost') as client:
        response = await client.post('/oauth/register', json=payload)
    assert response.status_code == 400
    repository.create.assert_not_called()


@pytest.mark.anyio
async def test_body_limits_and_rate_limit(app_and_repository):
    app, repository = app_and_repository
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url='http://localhost') as client:
        assert (await client.post('/oauth/register', content='x')).status_code == 415
        assert (await client.post('/oauth/register', content='x' * 16385,
                                  headers={'content-type': 'application/json'})).status_code == 413
        for _ in range(58):
            await client.post('/oauth/register', json={})
        response = await client.post('/oauth/register', json={})
        assert response.status_code == 429
        assert response.headers['retry-after'] == '60'
    repository.create.assert_not_called()


@pytest.mark.anyio
async def test_exact_redirect_matching_and_revoked_client():
    repository = OAuthClientsRepository(None)
    repository.get = AsyncMock(return_value={'redirect_uris': ['https://example.com/cb?x=%2F']})
    assert await repository.allows_redirect('id', 'https://example.com/cb?x=%2F')
    assert not await repository.allows_redirect('id', 'https://example.com/cb?x=/')
    assert not await repository.allows_redirect('id', 'https://example.com/cb?x=%2F/extra')
    repository.get.return_value = None
    assert not await repository.allows_redirect('id', 'https://example.com/cb?x=%2F')


def test_loopback_redirect_and_invalid_public_origin():
    assert registration_metadata({'redirect_uris': ['http://127.0.0.1:1234/cb']})
    for origin in ['http://public.test', 'https://example.com/path',
                   'https://example.com?query=1', 'https://user:pass@example.com']:
        with pytest.raises(ValueError):
            Settings(database_url='postgresql://example', public_base_url=origin)
