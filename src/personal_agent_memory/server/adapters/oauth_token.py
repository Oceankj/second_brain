"""OAuth token endpoint for public clients using PKCE and refresh rotation."""

import base64
import hashlib
import logging
import re
import secrets
import time
from collections import deque
from datetime import UTC, datetime
from urllib.parse import parse_qsl

import psycopg
from pydantic import AnyHttpUrl
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from personal_agent_memory.server.application import ApplicationContext
from personal_agent_memory.server.auth.transport import MCP_HTTP_SCOPES
from personal_agent_memory.services.users import hash_token

TOKEN_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}
FORM_CONTENT_TYPE = "application/x-www-form-urlencoded"
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{20,1024}")
VERIFIER_PATTERN = re.compile(r"[A-Za-z0-9._~-]{43,128}")
LOGGER = logging.getLogger(__name__)


def pkce_s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def oauth_error(error: str, status_code: int = 400, *, reason: str | None = None) -> JSONResponse:
    if reason:
        LOGGER.warning("OAuth token request rejected: %s", reason)
    return JSONResponse({"error": error}, status_code=status_code, headers=TOKEN_HEADERS)


class TokenHandler:
    def __init__(self, context: ApplicationContext) -> None:
        self.context = context
        # Match the canonical value published by protected-resource metadata and
        # stored by the authorization endpoint. AnyHttpUrl adds the root slash.
        self.resource = str(AnyHttpUrl(context.settings.oauth_resource_url))
        self.attempts: deque[float] = deque()

    async def handle(self, request: Request) -> JSONResponse:
        now = time.monotonic()
        while self.attempts and self.attempts[0] <= now - 60:
            self.attempts.popleft()
        if len(self.attempts) >= 120:
            return JSONResponse(
                {"error": "temporarily_unavailable"},
                status_code=429,
                headers={**TOKEN_HEADERS, "Retry-After": "60"},
            )
        self.attempts.append(now)
        if request.headers.get("content-type", "").split(";")[0].strip() != FORM_CONTENT_TYPE:
            return oauth_error("invalid_request", reason="invalid_content_type")
        if "authorization" in request.headers:
            return oauth_error("invalid_client", 401, reason="authorization_header")
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > 16384:
                return oauth_error("invalid_request", reason="body_too_large")
            body.extend(chunk)
        try:
            pairs = parse_qsl(body.decode("utf-8"), keep_blank_values=True, max_num_fields=12)
        except (ValueError, UnicodeError):
            return oauth_error("invalid_request", reason="malformed_form")
        if len(pairs) != len(dict(pairs)):
            return oauth_error("invalid_request", reason="duplicate_fields")
        form = dict(pairs)
        if "client_secret" in form or "client_assertion" in form:
            return oauth_error("invalid_client", 401, reason="unsupported_client_authentication")
        try:
            if form.get("grant_type") == "authorization_code":
                return await self.exchange_code(form)
            if form.get("grant_type") == "refresh_token":
                return await self.refresh(form)
            return oauth_error("unsupported_grant_type", reason="unsupported_grant_type")
        except psycopg.Error:
            return oauth_error("temporarily_unavailable", 503, reason="database_unavailable")

    async def exchange_code(self, form: dict[str, str]) -> JSONResponse:
        # Default only when absent; repository checks still bind the code to
        # this resource, client, callback and PKCE challenge.
        form = {"resource": self.resource, **form}
        required = ("code", "client_id", "redirect_uri", "resource", "code_verifier")
        if any(not form.get(field) for field in required):
            return oauth_error("invalid_request", reason="missing_code_exchange_field")
        code = form["code"]
        verifier = form["code_verifier"]
        if (
            not TOKEN_PATTERN.fullmatch(code)
            or not VERIFIER_PATTERN.fullmatch(verifier)
            or len(form["client_id"]) > 512
            or len(form["redirect_uri"]) > 2048
            or form["resource"] != self.resource
        ):
            return oauth_error("invalid_grant", reason="invalid_code_exchange_binding")
        access_token = secrets.token_urlsafe(48)
        refresh_token = secrets.token_urlsafe(48)
        result = await self.context.repository().oauth_tokens.exchange_authorization_code(
            code_hash=hash_token(code),
            client_id=form["client_id"],
            redirect_uri=form["redirect_uri"],
            resource=form["resource"],
            code_challenge=pkce_s256(verifier),
            access_token_hash=hash_token(access_token),
            refresh_token_hash=hash_token(refresh_token),
        )
        if result is None:
            return oauth_error("invalid_grant", reason="authorization_code_not_found_or_expired")
        return self.success(result, access_token, refresh_token)

    async def refresh(self, form: dict[str, str]) -> JSONResponse:
        # Keep the original token family's resource binding during rotation.
        form = {"resource": self.resource, **form}
        required = ("refresh_token", "client_id", "resource")
        if any(not form.get(field) for field in required):
            return oauth_error("invalid_request", reason="missing_refresh_field")
        raw_refresh_token = form["refresh_token"]
        if (
            not TOKEN_PATTERN.fullmatch(raw_refresh_token)
            or len(form["client_id"]) > 512
            or form["resource"] != self.resource
        ):
            return oauth_error("invalid_grant", reason="invalid_refresh_binding")
        scopes = None
        if "scope" in form:
            scopes = list(dict.fromkeys(form["scope"].split()))
            if not scopes or not set(scopes).issubset(MCP_HTTP_SCOPES):
                return oauth_error("invalid_scope", reason="invalid_refresh_scope")
        access_token = secrets.token_urlsafe(48)
        next_refresh_token = secrets.token_urlsafe(48)
        result = await self.context.repository().oauth_tokens.rotate_refresh_token(
            refresh_token_hash=hash_token(raw_refresh_token),
            client_id=form["client_id"],
            resource=form["resource"],
            scopes=scopes,
            access_token_hash=hash_token(access_token),
            next_refresh_token_hash=hash_token(next_refresh_token),
        )
        if result is not None and result.get("invalid_scope"):
            return oauth_error("invalid_scope", reason="refresh_scope_escalation")
        if result is None or result.get("replayed"):
            reason = (
                "refresh_token_replayed"
                if result and result.get("replayed")
                else "refresh_token_not_found_or_expired"
            )
            return oauth_error("invalid_grant", reason=reason)
        return self.success(result, access_token, next_refresh_token)

    @staticmethod
    def success(result: dict, access_token: str, refresh_token: str) -> JSONResponse:
        seconds = max(1, int((result["expires_at"] - datetime.now(UTC)).total_seconds()))
        payload = {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": seconds,
            "scope": " ".join(result["scopes"]),
        }
        if result.get("refresh_token_issued", True):
            payload["refresh_token"] = refresh_token
        return JSONResponse(payload, headers=TOKEN_HEADERS)


def token_routes(context: ApplicationContext) -> list[Route]:
    handler = TokenHandler(context)
    return [Route("/oauth/token", handler.handle, methods=["POST"])]
