from __future__ import annotations

from typing import Any

from mcp.server.auth.routes import create_protected_resource_routes
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette

from personal_agent_memory.config import Settings
from personal_agent_memory.contracts.memory import GetContextData, IngestTurnData
from personal_agent_memory.server.auth.transport import (
    MCP_HTTP_SCOPES,
    OAuthTokenVerifier,
    authenticated_user_id,
)
from personal_agent_memory.server.dependencies import (
    ApplicationContext,
    create_application_context,
    set_application_context,
)


class ScopedFastMCP(FastMCP):
    def streamable_http_app(self) -> Starlette:
        app = super().streamable_http_app()
        auth = self.settings.auth
        assert auth is not None and auth.resource_server_url is not None
        routes = create_protected_resource_routes(
            auth.resource_server_url,
            [auth.issuer_url],
            scopes_supported=MCP_HTTP_SCOPES,
        )
        # Advertise supported scopes without requiring BOTH scopes at the transport layer.
        paths = {route.path for route in routes}
        app.router.routes[:] = [r for r in app.routes if getattr(r, "path", None) not in paths]
        app.router.routes.extend(routes)
        return app


def create_mcp_http_server(
    settings: Settings | None = None,
    *,
    context: ApplicationContext | None = None,
) -> FastMCP:
    context = context or create_application_context(settings)
    settings = context.settings
    set_application_context(context)
    server = ScopedFastMCP(
        "personal-agent-memory",
        host=settings.mcp_http_host,
        port=settings.mcp_http_port,
        streamable_http_path=settings.mcp_http_path,
        max_request_body_size=settings.mcp_http_max_request_body_size,
        lifespan=context.lifespan,
        auth=AuthSettings(
            issuer_url=settings.oauth_issuer_url,
            resource_server_url=settings.oauth_resource_url,
            required_scopes=[],
        ),
        token_verifier=OAuthTokenVerifier(
            lambda: context.repository().oauth_tokens,
            resource=settings.oauth_resource_url,
            issuer=settings.oauth_issuer_url,
        ),
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=list(settings.mcp_http_allowed_hosts),
            allowed_origins=list(settings.mcp_http_allowed_origins),
        ),
    )
    register_authenticated_tools(server, context)
    return server


def register_authenticated_tools(server: FastMCP, context: ApplicationContext) -> None:
    @server.tool(name="ingest_turn")
    async def ingest_turn(
        user_input: str,
        assistant_output: str,
        metadata: dict[str, Any],
        ctx: Context,
    ) -> dict[str, Any]:
        """Store one interaction as candidate durable memory."""

        user_id = authenticated_user_id(ctx, "memory:write")
        payload = IngestTurnData(
            user_input=user_input,
            assistant_output=assistant_output,
            metadata=metadata,
        )
        return await context.memory_service().ingest_turn_as_user(payload, user_id=user_id)

    @server.tool(name="get_context")
    async def get_context(
        input: str,
        ctx: Context,
        session_id: str | None = None,
        diary_lookback_days: int | None = None,
        max_context_chars: int = 6000,
        include_chunks: bool = False,
    ) -> dict[str, Any]:
        """Retrieve compact durable memory context for the caller input."""

        user_id = authenticated_user_id(ctx, "memory:read")
        payload = GetContextData(
            input=input,
            session_id=session_id,
            diary_lookback_days=(
                context.settings.recent_diary_lookback_days
                if diary_lookback_days is None
                else diary_lookback_days
            ),
            max_context_chars=max_context_chars,
            include_chunks=include_chunks,
        )
        return await context.memory_service().get_context_as_user(payload, user_id=user_id)
