from __future__ import annotations

from typing import Any

from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from personal_agent_memory.config import Settings
from personal_agent_memory.server.auth.transport import (
    MCP_HTTP_SCOPES,
    MemoryTokenVerifier,
    authenticated_bearer_token,
)
from personal_agent_memory.server.dependencies import (
    ApplicationContext,
    create_application_context,
    set_application_context,
)
from personal_agent_memory.server.tools.memory import (
    get_context_with_token,
    ingest_turn_with_token,
)


def create_mcp_http_server(
    settings: Settings | None = None,
    *,
    context: ApplicationContext | None = None,
) -> FastMCP:
    context = context or create_application_context(settings)
    settings = context.settings
    set_application_context(context)
    server = FastMCP(
        "personal-agent-memory",
        host=settings.mcp_http_host,
        port=settings.mcp_http_port,
        streamable_http_path=settings.mcp_http_path,
        max_request_body_size=settings.mcp_http_max_request_body_size,
        lifespan=context.lifespan,
        auth=AuthSettings(
            issuer_url=settings.mcp_http_public_url,
            resource_server_url=settings.mcp_http_public_url,
            required_scopes=MCP_HTTP_SCOPES,
        ),
        token_verifier=MemoryTokenVerifier(context.user_service),
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=list(settings.mcp_http_allowed_hosts),
            allowed_origins=list(settings.mcp_http_allowed_origins),
        ),
    )
    register_authenticated_tools(server)
    return server


def register_authenticated_tools(server: FastMCP) -> None:
    @server.tool(name="ingest_turn")
    async def ingest_turn(
        user_input: str,
        assistant_output: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """Store one interaction as candidate durable memory."""

        return await ingest_turn_with_token(
            token=authenticated_bearer_token(),
            user_input=user_input,
            assistant_output=assistant_output,
            metadata=metadata,
        )

    @server.tool(name="get_context")
    async def get_context(
        input: str,
        session_id: str | None = None,
        diary_lookback_days: int | None = None,
        max_context_chars: int = 6000,
        include_chunks: bool = False,
    ) -> dict[str, Any]:
        """Retrieve compact durable memory context for the caller input."""

        return await get_context_with_token(
            input=input,
            token=authenticated_bearer_token(),
            session_id=session_id,
            diary_lookback_days=diary_lookback_days,
            max_context_chars=max_context_chars,
            include_chunks=include_chunks,
        )
