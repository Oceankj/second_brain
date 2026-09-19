from __future__ import annotations

from collections.abc import Callable

import psycopg
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from mcp.server.fastmcp import Context

from personal_agent_memory.repository.oauth_tokens import OAuthTokensRepository
from personal_agent_memory.server.dependencies import get_user_service
from personal_agent_memory.services.users import AuthenticationError, UserService, hash_token

MCP_HTTP_SCOPES = ["memory:read", "memory:write"]


class OAuthTokenVerifier:
    def __init__(
        self, repository_factory: Callable[[], OAuthTokensRepository], *, resource: str, issuer: str
    ) -> None:
        self._repository_factory = repository_factory
        self.resource = resource
        self.issuer = issuer

    async def verify_token(self, token: str) -> AccessToken | None:
        if not token or len(token) > 4096:
            return None
        try:
            row = await self._repository_factory().authenticate(hash_token(token), self.resource)
        except psycopg.Error:
            # Fail closed; never try legacy credentials after a database failure.
            return None
        if row is None:
            return None
        return AccessToken(
            token=token,
            client_id=row["client_id"],
            subject=row["user_id"],
            scopes=row["scopes"],
            resource=row["resource"],
            expires_at=int(row["expires_at"].timestamp()),
            claims={"iss": self.issuer},
        )


def authenticated_user_id(context: Context, required_scope: str) -> str:
    # Use this message's HTTP request, not a ContextVar inherited by a long-lived session.
    request = context.request_context.request
    user = request.scope.get("user") if request is not None else None
    if not isinstance(user, AuthenticatedUser) or not user.access_token.subject:
        raise AuthenticationError("missing_token")
    if required_scope not in user.access_token.scopes:
        raise AuthenticationError("insufficient_scope")
    return user.access_token.subject


class MemoryTokenVerifier:
    def __init__(self, user_service_factory: Callable[[], UserService] | None = None) -> None:
        self._user_service_factory = user_service_factory

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            user_service_factory = self._user_service_factory or get_user_service
            user = await user_service_factory().authenticate_token(token)
        except AuthenticationError:
            return None

        user_id = user["id"]
        return AccessToken(
            token=token,
            client_id=user_id,
            subject=user_id,
            scopes=MCP_HTTP_SCOPES,
        )


def authenticated_bearer_token() -> str:
    access_token = get_access_token()
    if access_token is None:
        raise AuthenticationError("missing_token")
    return access_token.token
