"""Phase 4 discovery and public-client registration; login/token exchange follows later."""

import json
import secrets
import time
from collections import deque
from urllib.parse import urlsplit

import psycopg
from pydantic import AnyHttpUrl
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from personal_agent_memory.server.application import ApplicationContext
from personal_agent_memory.server.auth.transport import MCP_HTTP_SCOPES


def valid_redirect(uri: object) -> bool:
    if not isinstance(uri, str) or not uri or len(uri) > 2048:
        return False
    if any(ord(c) <= 32 or ord(c) == 127 for c in uri) or any(c in uri for c in '\\#*'):
        return False
    try:
        parsed = urlsplit(uri)
        _ = parsed.port
        return bool(parsed.hostname and not parsed.username and not parsed.password and (
            parsed.scheme == 'https' or (
                parsed.scheme == 'http' and parsed.hostname in {'localhost', '127.0.0.1', '::1'}
            )
        ))
    except ValueError:
        return False


def registration_metadata(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ValueError('invalid_client_metadata')
    redirects = payload.get('redirect_uris')
    if (not isinstance(redirects, list) or not 1 <= len(redirects) <= 10
            or not all(valid_redirect(uri) for uri in redirects)):
        raise ValueError('invalid_redirect_uri')
    name = payload.get('client_name')
    if name is not None and (not isinstance(name, str) or len(name) > 200):
        raise ValueError('invalid_client_metadata')
    if payload.get('token_endpoint_auth_method', 'none') != 'none':
        raise ValueError('invalid_client_metadata')
    grants = payload.get('grant_types', ['authorization_code'])
    if (not isinstance(grants, list) or 'authorization_code' not in grants
            or any(g not in ('authorization_code', 'refresh_token') for g in grants)):
        raise ValueError('invalid_client_metadata')
    if payload.get('response_types', ['code']) != ['code']:
        raise ValueError('invalid_client_metadata')
    scope = payload.get('scope', ' '.join(MCP_HTTP_SCOPES))
    if not isinstance(scope, str) or not set(scope.split()).issubset(MCP_HTTP_SCOPES):
        raise ValueError('invalid_client_metadata')
    return {
        'redirect_uris': list(dict.fromkeys(redirects)),
        'client_name': name,
        'token_endpoint_auth_method': 'none',
        'grant_types': list(dict.fromkeys(grants)),
        'response_types': ['code'],
        'scope': ' '.join(dict.fromkeys(scope.split())),
    }


def oauth_routes(context: ApplicationContext) -> list[Route]:
    settings = context.settings
    base = settings.oauth_base_url
    resource = str(AnyHttpUrl(settings.oauth_resource_url))
    attempts: deque[float] = deque()

    async def metadata(request: Request) -> JSONResponse:
        return JSONResponse({
            'issuer': settings.oauth_issuer_url,
            'authorization_endpoint': base + '/oauth/authorize',
            'token_endpoint': base + '/oauth/token',
            'registration_endpoint': base + '/oauth/register',
            'response_types_supported': ['code'],
            'grant_types_supported': ['authorization_code', 'refresh_token'],
            'token_endpoint_auth_methods_supported': ['none'],
            'code_challenge_methods_supported': ['S256'],
            'scopes_supported': MCP_HTTP_SCOPES,
        })

    async def resource_metadata(request: Request) -> JSONResponse:
        return JSONResponse({
            'resource': resource,
            'authorization_servers': [settings.oauth_issuer_url],
            'scopes_supported': MCP_HTTP_SCOPES,
            'bearer_methods_supported': ['header'],
        })

    async def register(request: Request) -> JSONResponse:
        now = time.monotonic()
        while attempts and attempts[0] <= now - 60:
            attempts.popleft()
        if len(attempts) >= 60:
            return JSONResponse({'error': 'temporarily_unavailable'}, status_code=429,
                                headers={'Retry-After': '60'})
        attempts.append(now)
        if request.headers.get('content-type', '').split(';')[0].strip() != 'application/json':
            return JSONResponse({'error': 'invalid_client_metadata'}, status_code=415)
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > 16384:
                return JSONResponse({'error': 'invalid_client_metadata'}, status_code=413)
            body.extend(chunk)
        try:
            client = registration_metadata(json.loads(body))
        except (ValueError, UnicodeError, RecursionError) as exc:
            error = str(exc) if str(exc) in {
                'invalid_client_metadata', 'invalid_redirect_uri'
            } else 'invalid_client_metadata'
            return JSONResponse({'error': error}, status_code=400)
        client['client_id'] = secrets.token_urlsafe(32)
        try:
            row = await context.repository().oauth_clients.create(client)
        except psycopg.Error:
            return JSONResponse({'error': 'temporarily_unavailable'}, status_code=503)
        client['client_id_issued_at'] = int(row['created_at'].timestamp())
        return JSONResponse(client, status_code=201, headers={'Cache-Control': 'no-store'})

    routes = [
        Route('/.well-known/oauth-authorization-server', metadata, methods=['GET']),
        Route('/oauth/register', register, methods=['POST']),
    ]
    # FastMCP already publishes path-specific resource discovery and the 401 challenge.
    if urlsplit(resource).path not in ('', '/'):
        routes.append(Route('/.well-known/oauth-protected-resource', resource_metadata,
                            methods=['GET']))
    return routes
