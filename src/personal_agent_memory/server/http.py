from __future__ import annotations

from collections.abc import Iterable

from mcp.server.fastmcp import FastMCP
from starlette.routing import Route

from personal_agent_memory.config import Settings
from personal_agent_memory.server import restful
from personal_agent_memory.server.dependencies import get_settings
from personal_agent_memory.server.mcp_http import create_mcp_http_server


def create_http_server(settings: Settings | None = None) -> FastMCP:
    settings = settings or get_settings()
    server = create_mcp_http_server(settings)
    register_rest_routes(server, restful.routes)
    return server


def register_rest_routes(server: FastMCP, routes: Iterable[Route]) -> None:
    for route in routes:
        methods = sorted(method for method in route.methods if method != "HEAD")
        server.custom_route(route.path, methods=methods, name=route.name)(route.endpoint)


def main() -> None:
    settings = get_settings()
    if not settings.mcp_http_enabled:
        raise SystemExit("Unified HTTP server requires mcp_http.enabled=true in memory.json.")
    if not settings.rest_api_enabled:
        raise SystemExit("Unified HTTP server requires MEMORY_REST_API_ENABLED=true.")

    create_http_server(settings).run(transport="streamable-http")


if __name__ == "__main__":
    main()
