import re
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from starlette.applications import Starlette

from personal_agent_memory.config import Settings
from personal_agent_memory.server.adapters.oauth_login import login_page, login_routes
from personal_agent_memory.server.application import ApplicationContext
from personal_agent_memory.services.users import hash_password, hash_token

PARAMS = {
    'client_id': 'client', 'redirect_uri': 'https://client.test/cb?keep=%2F',
    'response_type': 'code', 'resource': 'https://memory.test/mcp',
    'scope': 'memory:read', 'state': 'a+&測試',
    'code_challenge': 'A' * 43, 'code_challenge_method': 'S256',
}


def form_values(response):
    return dict(re.findall(r'name="(request_id|csrf_token)" value="([^"]+)"', response.text))


@pytest.mark.parametrize('error', ['', '帳號或密碼不正確，請再試一次。'])
@pytest.mark.parametrize(('redirect_uri', 'destinations'), [
    ('https://agent.meta.ai/api/hatch/oauth/callback', 'https://agent.meta.ai https://muse.ai'),
    ('https://chatgpt.com/connector_platform_oauth_redirect', 'https://chatgpt.com'),
    ('https://client.test/callback', 'https://client.test'),
    ('https://agent.meta.ai/other', 'https://agent.meta.ai'),
    ('https://agent.meta.ai/api/hatch/oauth/callback/', 'https://agent.meta.ai'),
    ('https://agent.meta.ai/api/hatch/oauth/callback?extra=1', 'https://agent.meta.ai'),
    ('https://agent.meta.ai.evil.test/api/hatch/oauth/callback', 'https://agent.meta.ai.evil.test'),
    ('http://agent.meta.ai/api/hatch/oauth/callback', 'http://agent.meta.ai'),
])
def test_login_csp_limits_muse_exception_to_exact_callback(redirect_uri, destinations, error):
    response = login_page(
        {'redirect_uri': redirect_uri, 'scopes': ['memory:write']}, 'request', 'csrf', error,
    )
    assert response.status_code == (401 if error else 200)
    assert response.headers['content-security-policy'] == (
        "default-src 'none'; style-src 'unsafe-inline'; "
        f"form-action 'self' {destinations}; frame-ancestors 'none'; base-uri 'none'"
    )


@pytest.fixture
def repository():
    clients = AsyncMock()
    clients.get.return_value = {
        'client_id': 'client', 'client_name': '<script>bad()</script>',
        'redirect_uris': [PARAMS['redirect_uri']],
        'grant_types': ['authorization_code'], 'scopes': ['memory:read', 'memory:write'],
    }
    users = AsyncMock()
    users.find_login.return_value = {
        'id': 'alice', 'password_hash': hash_password('correct private password'),
        'is_active': True,
    }
    authorizations = AsyncMock()
    rows = {}
    sessions = set()

    async def create(pending, current_session_hash=None):
        reused = current_session_hash in sessions
        session_hash = current_session_hash if reused else pending['session_hash']
        sessions.add(session_hash)
        rows[pending['request_hash']] = {**pending, 'session_hash': session_hash}
        return reused

    async def get_pending(request_hash, session_hash):
        pending = rows.get(request_hash)
        return pending if pending and pending['session_hash'] == session_hash else None

    async def finish(request_hash, session_hash, **kwargs):
        return rows.pop(request_hash, None)

    authorizations.create.side_effect = create
    authorizations.get_pending.side_effect = get_pending
    authorizations.finish.side_effect = finish
    return SimpleNamespace(oauth_clients=clients, users=users, oauth_authorizations=authorizations)


@pytest.fixture
def app(repository):
    context = ApplicationContext(Settings(database_url='postgresql://example',
                                          public_base_url='https://memory.test'))
    context._repository = repository
    return Starlette(routes=login_routes(context))


@pytest.mark.anyio
@pytest.mark.parametrize("include_resource", [True, False])
async def test_approve_keeps_browser_session_and_binds_code(app, repository, include_resource):
    authorization_params = dict(PARAMS)
    if not include_resource:
        authorization_params.pop("resource")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url='https://memory.test') as browser:
        page = await browser.get('/oauth/authorize', params=authorization_params)
        pending = repository.oauth_authorizations.create.call_args.args[0]
        assert pending['resource'] == 'https://memory.test/mcp'
        assert page.status_code == 200
        assert '<script>bad()' not in page.text
        assert '&lt;script&gt;' in page.text
        assert '讀取你的記憶資料' in page.text
        assert '寫入你的記憶資料' not in page.text
        assert 'no-store' in page.headers['cache-control']
        assert "frame-ancestors 'none'" in page.headers['content-security-policy']
        assert "form-action 'self' https://client.test;" in page.headers['content-security-policy']
        cookie = browser.cookies.get('__Host-memory-oauth')
        for flag in ('Secure', 'HttpOnly', 'SameSite=lax'):
            assert flag in page.headers['set-cookie']
        form = {**form_values(page), 'username': 'ALICE',
                'password': 'correct private password', 'decision': 'approve',
                'redirect_uri': 'https://evil.test', 'scope': 'memory:write'}
        response = await browser.post('/oauth/authorize', data=form)
        assert response.status_code == 303
        assert response.headers['location'].startswith(PARAMS['redirect_uri'] + '&')
        params = parse_qs(urlsplit(response.headers['location']).query)
        assert params['state'] == [PARAMS['state']]
        assert params['iss'] == ['https://memory.test/']
        args = repository.oauth_authorizations.finish.call_args.kwargs
        assert args['user_id'] == 'alice'
        assert args['code_hash'] == hash_token(params['code'][0])
        assert browser.cookies.get('__Host-memory-oauth') == cookie
        repository.users.find_login.assert_awaited_once_with('alice')
        replay = await browser.post('/oauth/authorize', data=form)
        assert replay.status_code == 400
        assert '授權請求已失效' in replay.text


@pytest.mark.anyio
async def test_multiple_pages_share_one_session_and_remain_independent(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url='https://memory.test') as browser:
        first = await browser.get('/oauth/authorize', params=PARAMS)
        cookie = browser.cookies.get('__Host-memory-oauth')
        second = await browser.get('/oauth/authorize', params={**PARAMS, 'state': 'second'})
        assert browser.cookies.get('__Host-memory-oauth') == cookie
        for page in (first, second):
            response = await browser.post('/oauth/authorize', data={
                **form_values(page), 'decision': 'approve', 'username': 'alice',
                'password': 'correct private password',
            })
            assert response.status_code == 303
            assert 'code=' in response.headers['location']


@pytest.mark.anyio
@pytest.mark.parametrize('change', [
    {'redirect_uri': 'https://evil.test'}, {'client_id': 'unknown'},
    {'response_type': 'token'}, {'code_challenge_method': 'plain'},
    {'code_challenge': 'short'}, {'resource': 'https://other.test'}, {'scope': 'admin'},
    {'resource': ''}, {'resource': 'https://memory.test/'},
])
async def test_invalid_authorization_requests(app, repository, change):
    if change.get('client_id') == 'unknown':
        repository.oauth_clients.get.return_value = None
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url='https://memory.test') as browser:
        response = await browser.get('/oauth/authorize', params={**PARAMS, **change})
    if 'redirect_uri' in change or 'client_id' in change:
        assert response.status_code == 400
        assert 'location' not in response.headers
    else:
        assert response.status_code == 303
        params = parse_qs(urlsplit(response.headers['location']).query)
        assert 'error' in params and params['iss'] == ['https://memory.test/']
    repository.oauth_authorizations.create.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize('failure', [
    'csrf', 'cookie', 'origin', 'content-type', 'expired', 'duplicate',
])
async def test_invalid_form_cannot_issue_code(app, repository, failure):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url='https://memory.test') as browser:
        page = await browser.get('/oauth/authorize', params=PARAMS)
        form = {**form_values(page), 'decision': 'approve',
                'username': 'alice', 'password': 'correct private password'}
        headers = {}
        if failure == 'csrf':
            form['csrf_token'] = 'x' * 43
        if failure == 'cookie':
            browser.cookies.clear()
        if failure == 'origin':
            headers['origin'] = 'https://evil.test'
        if failure == 'content-type':
            response = await browser.post('/oauth/authorize', content='request_id=x')
        else:
            if failure == 'expired':
                repository.oauth_authorizations.get_pending.side_effect = None
                repository.oauth_authorizations.get_pending.return_value = None
            if failure == 'duplicate':
                response = await browser.post('/oauth/authorize',
                                              content='decision=approve&decision=deny',
                                              headers={'content-type':
                                                       'application/x-www-form-urlencoded'})
            else:
                response = await browser.post('/oauth/authorize', data=form, headers=headers)
        assert response.status_code == 400
        assert response.headers['content-type'].startswith('text/html')
        assert '授權請求已失效' in response.text
        assert '>返回<' in response.text
        assert '清除登入狀態' in response.text
    repository.oauth_authorizations.finish.assert_not_called()
    repository.users.find_login.assert_not_called()


@pytest.mark.anyio
async def test_opaque_origin_can_submit_valid_csrf_protected_form(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url='https://memory.test') as browser:
        page = await browser.get('/oauth/authorize', params=PARAMS)
        response = await browser.post('/oauth/authorize', data={
            **form_values(page), 'decision': 'approve', 'username': 'alice',
            'password': 'correct private password',
        }, headers={'origin': 'null'})
        assert response.status_code == 303
        assert 'code=' in response.headers['location']


@pytest.mark.anyio
@pytest.mark.parametrize('failure', ['wrong-password', 'unknown-user', 'disabled', 'no-password'])
async def test_login_errors_are_identical_and_do_not_echo_credentials(app, repository, failure):
    user = repository.users.find_login.return_value
    if failure == 'unknown-user':
        repository.users.find_login.return_value = None
    elif failure == 'disabled':
        user['is_active'] = False
    elif failure == 'no-password':
        user['password_hash'] = None
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url='https://memory.test') as browser:
        page = await browser.get('/oauth/authorize', params=PARAMS)
        password = 'wrong' if failure == 'wrong-password' else 'correct private password'
        response = await browser.post('/oauth/authorize', data={
            **form_values(page), 'decision': 'approve', 'username': 'alice', 'password': password,
        })
        assert response.status_code == 401
        assert '帳號或密碼不正確' in response.text
        assert password not in response.text
        assert '$argon2' not in response.text
    repository.oauth_authorizations.finish.assert_not_called()


@pytest.mark.anyio
async def test_deny_requires_csrf_but_not_password(app, repository):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url='https://memory.test') as browser:
        page = await browser.get('/oauth/authorize', params=PARAMS)
        response = await browser.post('/oauth/authorize', data={
            **form_values(page), 'decision': 'deny',
        })
        params = parse_qs(urlsplit(response.headers['location']).query)
        assert params['error'] == ['access_denied'] and 'code' not in params
        assert params['state'] == [PARAMS['state']]
        assert browser.cookies.get('__Host-memory-oauth') is not None
    repository.users.find_login.assert_not_called()
    assert repository.oauth_authorizations.finish.call_args.kwargs == {}


@pytest.mark.anyio
async def test_clear_session_removes_cookie(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url='https://memory.test') as browser:
        await browser.get('/oauth/authorize', params=PARAMS)
        assert browser.cookies.get('__Host-memory-oauth')
        response = await browser.post('/oauth/session/clear', content='', headers={
            'content-type': 'application/x-www-form-urlencoded',
        })
        assert response.status_code == 200
        assert browser.cookies.get('__Host-memory-oauth') is None
        assert '登入狀態已清除' in response.text
        assert '>返回<' in response.text


@pytest.mark.anyio
async def test_clear_session_rejects_cross_origin_request(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url='https://memory.test') as browser:
        await browser.get('/oauth/authorize', params=PARAMS)
        response = await browser.post('/oauth/session/clear', content='', headers={
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://evil.test',
        })
        assert response.status_code == 400
        assert browser.cookies.get('__Host-memory-oauth') is not None


@pytest.mark.anyio
async def test_post_rate_limit(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url='https://memory.test') as browser:
        for _ in range(30):
            await browser.post('/oauth/authorize', data={})
        response = await browser.post('/oauth/authorize', data={})
        assert response.status_code == 429 and response.headers['retry-after'] == '60'
