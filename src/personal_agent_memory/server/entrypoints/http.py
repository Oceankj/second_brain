from __future__ import annotations

from collections.abc import Iterable

from mcp.server.fastmcp import FastMCP
from starlette.routing import Route

from personal_agent_memory.config import Settings
from personal_agent_memory.server.adapters.mcp_http import create_mcp_http_server
from personal_agent_memory.server.adapters.rest import routes as rest_routes
from personal_agent_memory.server.dependencies import (
    create_application_context,
    get_settings,
    set_application_context,
)


def create_http_server(settings: Settings | None = None) -> FastMCP:
    context = create_application_context(settings or get_settings())
    set_application_context(context)
    server = create_mcp_http_server(context=context)
    register_rest_routes(server, rest_routes)
    return server


def register_rest_routes(server: FastMCP, routes: Iterable[Route]) -> None:
    for route in routes:
        methods = sorted(method for method in route.methods if method != "HEAD")
        server.custom_route(route.path, methods=methods, name=route.name)(route.endpoint)


def main() -> None:
    settings = get_settings()
    create_http_server(settings).run(transport="streamable-http")


if __name__ == "__main__":
    main()
