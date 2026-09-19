"""Browser authorization flow. Raw credentials are never logged or persisted."""

import hmac
import re
import secrets
import time
from collections import deque
from html import escape
from urllib.parse import parse_qsl, urlencode, urlsplit

import psycopg
from pydantic import AnyHttpUrl
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Route

from personal_agent_memory.server.application import ApplicationContext
from personal_agent_memory.server.auth.transport import MCP_HTTP_SCOPES
from personal_agent_memory.services.users import hash_password, hash_token, verify_password

HEADERS = {
    'Cache-Control': 'no-store',
    'Pragma': 'no-cache',
    'Referrer-Policy': 'no-referrer',
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; "
                               "form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
}


def callback(uri: str, issuer: str, state: str | None, **result: str) -> Response:
    # Preserve the registered query byte-for-byte; only append OAuth response fields.
    params = {**result, 'iss': issuer}
    if state is not None:
        params['state'] = state
    separator = '&' if '?' in uri else '?'
    return RedirectResponse(uri + separator + urlencode(params), status_code=303, headers=HEADERS)


def login_page(pending: dict, request_id: str, csrf: str, error: str = '') -> HTMLResponse:
    labels = {'memory:read': '讀取你的記憶資料', 'memory:write': '寫入你的記憶資料'}
    permissions = ''.join(f'<li>{escape(labels[s])}</li>' for s in pending['scopes'])
    app = escape(pending.get('client_name') or '未命名應用程式')
    destination = escape(urlsplit(pending['redirect_uri']).netloc)
    message = f'<p role="alert">{escape(error)}</p>' if error else ''
    # Browsers may enforce form-action on the 303 destination too. Permit the
    # registered callback origin without interpolating arbitrary text into CSP.
    target = urlsplit(str(AnyHttpUrl(pending['redirect_uri'])))
    origin = f'{target.scheme}://{target.netloc}'
    if not re.fullmatch(r'https?://[A-Za-z0-9.\-:\[\]]+', origin):
        return HTMLResponse('無法使用此回呼網址。', status_code=400, headers=HEADERS)
    headers = {**HEADERS, 'Content-Security-Policy': HEADERS['Content-Security-Policy'].replace(
        "form-action 'self';", f"form-action 'self' {origin};",
    )}
    return HTMLResponse(f'''<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>登入並授權 · Personal Agent Memory</title>
<style>
body {{font-family:system-ui,sans-serif;background:#f4f5f7;color:#18202b;
margin:0;padding:32px 16px}}
main {{max-width:440px;margin:5vh auto;background:white;padding:32px;border-radius:16px}}
h1 {{font-size:1.6rem}} p,li {{line-height:1.7;overflow-wrap:anywhere}}
label {{display:block;margin-top:18px}} input {{box-sizing:border-box;width:100%;padding:12px;
margin-top:6px;border:1px solid #8390a2;border-radius:6px;font-size:1rem}}
button {{padding:12px 18px;margin-top:24px;border:0;border-radius:6px;cursor:pointer;
font-size:1rem;background:#1747a6;color:white}} .cancel {{background:#e9edf4;color:#18202b}}
[role=alert] {{color:#a31b1b}} small {{color:#546174}}
</style></head><body><main>
<small>Personal Agent Memory</small><h1>登入並授權</h1>
<p>應用程式 <strong>{app}</strong> 要求以下權限：</p><ul>{permissions}</ul>
<p><small>完成後返回：{destination}</small></p>{message}
<form method="post" action="/oauth/authorize">
<input type="hidden" name="request_id" value="{escape(request_id)}">
<input type="hidden" name="csrf_token" value="{escape(csrf)}">
<label for="username">帳號</label><input id="username" name="username" autocomplete="username"
maxlength="256" required autofocus>
<label for="password">密碼</label><input id="password" name="password" type="password"
autocomplete="current-password" maxlength="1024" required>
<button name="decision" value="approve" type="submit">登入並允許</button>
<button name="decision" value="deny" type="submit" class="cancel" formnovalidate>拒絕</button>
</form><p><small>帳號由管理員建立，此處不提供註冊。</small></p>
</main></body></html>''', headers=headers, status_code=401 if error else 200)


class LoginHandler:
    def __init__(self, context: ApplicationContext) -> None:
        self.context = context
        self.resource = str(AnyHttpUrl(context.settings.oauth_resource_url))
        self.secure = context.settings.oauth_base_url.startswith('https://')
        self.cookie = '__Host-memory-oauth' if self.secure else 'memory-oauth-local'
        self.get_attempts: deque[float] = deque()
        self.post_attempts: deque[float] = deque()
        self.dummy_hash = hash_password(secrets.token_urlsafe(32))

    def set_cookie(self, response: Response, value: str) -> None:
        response.set_cookie(self.cookie, value, max_age=600, path='/',
                            secure=self.secure, httponly=True, samesite='lax')

    async def handle(self, request: Request) -> Response:
        attempts = self.get_attempts if request.method == 'GET' else self.post_attempts
        limit = 120 if request.method == 'GET' else 30
        now = time.monotonic()
        while attempts and attempts[0] <= now - 60:
            attempts.popleft()
        if len(attempts) >= limit:
            return JSONResponse({'error': 'temporarily_unavailable'}, status_code=429,
                                headers={**HEADERS, 'Retry-After': '60'})
        attempts.append(now)
        try:
            return await (self.start(request) if request.method == 'GET' else self.submit(request))
        except psycopg.Error:
            return JSONResponse({'error': 'temporarily_unavailable'}, status_code=503,
                                headers=HEADERS)

    async def start(self, request: Request) -> Response:
        pairs = request.query_params.multi_items()
        if len(request.scope.get('query_string', b'')) > 8192 or len(pairs) != len(dict(pairs)):
            return self.invalid()
        params = dict(pairs)
        repository = self.context.repository()
        client = await repository.oauth_clients.get(params.get('client_id', ''))
        uri = params.get('redirect_uri', '')
        if not client or uri not in client['redirect_uris']:
            return self.invalid()  # Never redirect to an unverified URI.
        state = params.get('state')
        error = None
        if params.get('response_type') != 'code':
            error = 'unsupported_response_type'
        elif 'authorization_code' not in client['grant_types']:
            error = 'unauthorized_client'
        elif params.get('resource') != self.resource:
            error = 'invalid_target'
        elif (params.get('code_challenge_method') != 'S256'
              or not re.fullmatch(r'[A-Za-z0-9_-]{43}', params.get('code_challenge', ''))):
            error = 'invalid_request'
        scopes = list(dict.fromkeys(params.get('scope', ' '.join(client['scopes'])).split()))
        if not set(scopes).issubset(set(client['scopes']) & set(MCP_HTTP_SCOPES)):
            error = 'invalid_scope'
        if error:
            return callback(uri, self.context.settings.oauth_issuer_url, state, error=error)
        session, csrf, request_id = (secrets.token_urlsafe(32) for _ in range(3))
        pending = {
            'request_hash': hash_token(request_id), 'session_hash': hash_token(session),
            'client_id': client['client_id'], 'client_name': client['client_name'],
            'redirect_uri': uri, 'resource': self.resource, 'scopes': scopes, 'state': state,
            'code_challenge': params['code_challenge'],
        }
        await repository.oauth_authorizations.create(pending, hash_token(csrf))
        response = login_page(pending, request_id, csrf)
        self.set_cookie(response, session)
        return response

    async def submit(self, request: Request) -> Response:
        if (request.headers.get('origin') not in (None, self.context.settings.oauth_base_url)
                or request.headers.get('content-type', '').split(';')[0].strip()
                != 'application/x-www-form-urlencoded'):
            return self.invalid()
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > 16384:
                return self.invalid()
            body.extend(chunk)
        try:
            pairs = parse_qsl(body.decode('utf-8'), keep_blank_values=True, max_num_fields=8)
        except (ValueError, UnicodeError):
            return self.invalid()
        if len(pairs) != len(dict(pairs)):
            return self.invalid()
        form = dict(pairs)
        session = request.cookies.get(self.cookie, '')
        request_id, csrf = form.get('request_id', ''), form.get('csrf_token', '')
        if not all(re.fullmatch(r'[A-Za-z0-9_-]{43}', v) for v in (session, request_id, csrf)):
            return self.invalid()
        repository = self.context.repository()
        authorizations = repository.oauth_authorizations
        request_hash, session_hash, csrf_hash = map(hash_token, (request_id, session, csrf))
        pending = await authorizations.get_pending(request_hash, session_hash)
        if not pending or not hmac.compare_digest(pending['csrf_token_hash'], csrf_hash):
            return self.invalid()
        decision = form.get('decision')
        if decision == 'deny':
            completed = await authorizations.finish(request_hash, session_hash, csrf_hash)
            if not completed:
                return self.invalid()
            response = callback(completed['redirect_uri'], self.context.settings.oauth_issuer_url,
                                completed['state'], error='access_denied')
            response.delete_cookie(self.cookie, path='/', secure=self.secure,
                                   httponly=True, samesite='lax')
            return response
        if decision != 'approve':
            return self.invalid()
        username, password = form.get('username', ''), form.get('password', '')
        if len(username) > 256 or len(password) > 1024:
            return self.invalid()
        user = await repository.users.find_login(username.lower())
        encoded = user['password_hash'] if user and user['password_hash'] else self.dummy_hash
        valid = await run_in_threadpool(verify_password, password, encoded)
        if not valid or not user or not user['is_active'] or not user['password_hash']:
            return login_page(pending, request_id, csrf, '帳號或密碼不正確，請再試一次。')
        code, new_session, new_csrf = (secrets.token_urlsafe(32) for _ in range(3))
        completed = await authorizations.finish(
            request_hash, session_hash, csrf_hash, user_id=user['id'], password_hash=encoded,
            code_hash=hash_token(code), new_session_hash=hash_token(new_session),
            new_csrf_hash=hash_token(new_csrf),
        )
        if not completed:
            return self.invalid()
        response = callback(completed['redirect_uri'], self.context.settings.oauth_issuer_url,
                            completed['state'], code=code)
        self.set_cookie(response, new_session)
        return response

    @staticmethod
    def invalid() -> Response:
        return JSONResponse({'error': 'invalid_request'}, status_code=400, headers=HEADERS)


def login_routes(context: ApplicationContext) -> list[Route]:
    handler = LoginHandler(context)
    return [Route('/oauth/authorize', handler.handle, methods=['GET', 'POST'])]
