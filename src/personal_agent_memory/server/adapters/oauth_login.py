"""Browser authorization flow. Raw credentials are never logged or persisted."""

import base64
import hashlib
import hmac
import logging
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
LOGGER = logging.getLogger(__name__)
RETURN_URL = 'https://chatgpt.com/'


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


def csrf_token(session: str, request_id: str) -> str:
    digest = hmac.new(session.encode('ascii'), request_id.encode('ascii'), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b'=').decode('ascii')


def recovery_page(*, cleared: bool = False) -> HTMLResponse:
    title = '登入狀態已清除' if cleared else '授權請求已失效'
    message = ('請返回後重新開始連線。' if cleared else
               '此授權請求已過期或不再有效，請重新開始連線。')
    clear = '' if cleared else '''
<form method="post" action="/oauth/session/clear">
<button type="submit" class="secondary">清除登入狀態</button>
</form>'''
    return HTMLResponse(f'''<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Personal Agent Memory</title>
<style>
body {{font-family:system-ui,sans-serif;background:#f4f5f7;color:#18202b;
margin:0;padding:32px 16px}}
main {{max-width:440px;margin:10vh auto;background:white;padding:32px;border-radius:16px}}
h1 {{font-size:1.6rem}} p {{line-height:1.7}}
a,button {{display:inline-block;box-sizing:border-box;padding:12px 18px;margin:12px 8px 0 0;
border:0;border-radius:6px;font:inherit;text-decoration:none;cursor:pointer;
background:#1747a6;color:white}}
form {{display:inline}} button.secondary {{background:#e9edf4;color:#18202b}}
</style></head><body><main><small>Personal Agent Memory</small>
<h1>{title}</h1><p>{message}</p>
<a href="{RETURN_URL}">返回</a>{clear}
</main></body></html>''', status_code=200 if cleared else 400, headers=HEADERS)


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
            return self.initial_invalid()
        params = dict(pairs)
        repository = self.context.repository()
        client = await repository.oauth_clients.get(params.get('client_id', ''))
        uri = params.get('redirect_uri', '')
        if not client or uri not in client['redirect_uris']:
            return self.initial_invalid()  # Never redirect to an unverified URI.
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
        current_session = request.cookies.get(self.cookie, '')
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}', current_session):
            current_session = ''
        new_session, request_id = (secrets.token_urlsafe(32) for _ in range(2))
        pending = {
            'request_hash': hash_token(request_id), 'session_hash': hash_token(new_session),
            'client_id': client['client_id'], 'client_name': client['client_name'],
            'redirect_uri': uri, 'resource': self.resource, 'scopes': scopes, 'state': state,
            'code_challenge': params['code_challenge'],
        }
        reused = await repository.oauth_authorizations.create(
            pending,
            hash_token(current_session) if current_session else None,
        )
        session = current_session if reused else new_session
        csrf = csrf_token(session, request_id)
        response = login_page(pending, request_id, csrf)
        self.set_cookie(response, session)
        return response

    async def submit(self, request: Request) -> Response:
        origin = request.headers.get('origin')
        if origin not in (None, 'null', self.context.settings.oauth_base_url):
            return self.form_invalid('origin_mismatch')
        if (request.headers.get('content-type', '').split(';')[0].strip()
                != 'application/x-www-form-urlencoded'):
            return self.form_invalid('invalid_content_type')
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > 16384:
                return self.form_invalid('body_too_large')
            body.extend(chunk)
        try:
            pairs = parse_qsl(body.decode('utf-8'), keep_blank_values=True, max_num_fields=8)
        except (ValueError, UnicodeError):
            return self.form_invalid('malformed_form')
        if len(pairs) != len(dict(pairs)):
            return self.form_invalid('duplicate_fields')
        form = dict(pairs)
        session = request.cookies.get(self.cookie, '')
        request_id, csrf = form.get('request_id', ''), form.get('csrf_token', '')
        if not all(re.fullmatch(r'[A-Za-z0-9_-]{43}', v) for v in (session, request_id, csrf)):
            return self.form_invalid('missing_or_malformed_state')
        expected_csrf = csrf_token(session, request_id)
        if not hmac.compare_digest(csrf, expected_csrf):
            return self.form_invalid('csrf_mismatch')
        repository = self.context.repository()
        authorizations = repository.oauth_authorizations
        request_hash, session_hash = map(hash_token, (request_id, session))
        pending = await authorizations.get_pending(request_hash, session_hash)
        if not pending:
            return self.form_invalid('session_or_request_expired')
        decision = form.get('decision')
        if decision == 'deny':
            completed = await authorizations.finish(request_hash, session_hash)
            if not completed:
                return self.form_invalid('authorization_race')
            response = callback(completed['redirect_uri'], self.context.settings.oauth_issuer_url,
                                completed['state'], error='access_denied')
            return response
        if decision != 'approve':
            return self.form_invalid('invalid_decision')
        username, password = form.get('username', ''), form.get('password', '')
        if len(username) > 256 or len(password) > 1024:
            return self.form_invalid('oversized_credentials')
        user = await repository.users.find_login(username.lower())
        encoded = user['password_hash'] if user and user['password_hash'] else self.dummy_hash
        valid = await run_in_threadpool(verify_password, password, encoded)
        if not valid or not user or not user['is_active'] or not user['password_hash']:
            return login_page(pending, request_id, csrf, '帳號或密碼不正確，請再試一次。')
        code = secrets.token_urlsafe(32)
        completed = await authorizations.finish(
            request_hash, session_hash, user_id=user['id'], password_hash=encoded,
            code_hash=hash_token(code),
        )
        if not completed:
            return self.form_invalid('authorization_race')
        response = callback(completed['redirect_uri'], self.context.settings.oauth_issuer_url,
                            completed['state'], code=code)
        return response

    @staticmethod
    def initial_invalid() -> Response:
        return JSONResponse({'error': 'invalid_request'}, status_code=400, headers=HEADERS)

    @staticmethod
    def form_invalid(reason: str) -> Response:
        LOGGER.warning('OAuth authorization form rejected: %s', reason)
        return recovery_page()

    async def clear_session(self, request: Request) -> Response:
        origin = request.headers.get('origin')
        if origin not in (None, 'null', self.context.settings.oauth_base_url):
            return self.form_invalid('session_clear_origin_mismatch')
        if (request.headers.get('content-type', '').split(';')[0].strip()
                != 'application/x-www-form-urlencoded'):
            return self.form_invalid('session_clear_invalid_content_type')
        response = recovery_page(cleared=True)
        response.delete_cookie(self.cookie, path='/', secure=self.secure,
                               httponly=True, samesite='lax')
        return response


def login_routes(context: ApplicationContext) -> list[Route]:
    handler = LoginHandler(context)
    return [
        Route('/oauth/authorize', handler.handle, methods=['GET', 'POST']),
        Route('/oauth/session/clear', handler.clear_session, methods=['POST']),
    ]
