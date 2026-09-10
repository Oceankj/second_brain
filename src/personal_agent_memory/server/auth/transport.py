from __future__ import annotations

from collections.abc import Callable

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken

from personal_agent_memory.server.dependencies import get_user_service
from personal_agent_memory.services.users import AuthenticationError, UserService

MCP_HTTP_SCOPES = ["memory:read", "memory:write"]


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
