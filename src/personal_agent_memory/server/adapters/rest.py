from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from personal_agent_memory.contracts import CreateDailyDiaryInput
from personal_agent_memory.server.dependencies import (
    get_memory_service,
    get_settings,
    get_user_service,
)
from personal_agent_memory.services.users import AuthenticationError


async def require_api_enabled_and_authenticated(request: Request) -> JSONResponse | None:
    if not get_settings().rest_api_enabled:
        return JSONResponse({"error": "rest_api_disabled"}, status_code=404)

    token = bearer_token(request)
    try:
        await get_user_service().authenticate_token(token)
    except AuthenticationError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)
    return None


def bearer_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer" and token:
        return token
    return request.headers.get("x-memory-token", "")


async def list_users(request: Request) -> JSONResponse:
    if error := await require_api_enabled_and_authenticated(request):
        return error
    return JSONResponse({"users": await get_user_service().list_users()})


async def get_user(request: Request) -> JSONResponse:
    if error := await require_api_enabled_and_authenticated(request):
        return error
    user = await get_user_service().get_user(request.path_params["user_id"])
    if user is None:
        return JSONResponse({"error": "user_not_found"}, status_code=404)
    return JSONResponse(user)


async def upsert_user(request: Request) -> JSONResponse:
    if error := await require_api_enabled_and_authenticated(request):
        return error
    payload = await read_json_body(request)
    user = await get_user_service().ensure_user(
        request.path_params["user_id"],
        display_name=payload.get("display_name"),
    )
    return JSONResponse(user)


async def update_user(request: Request) -> JSONResponse:
    if error := await require_api_enabled_and_authenticated(request):
        return error
    payload = await read_json_body(request)
    if "display_name" not in payload:
        return JSONResponse({"error": "display_name_required"}, status_code=400)

    user = await get_user_service().update_user(
        request.path_params["user_id"],
        display_name=payload["display_name"],
    )
    if user is None:
        return JSONResponse({"error": "user_not_found"}, status_code=404)
    return JSONResponse(user)


async def health(request: Request) -> JSONResponse:
    if not get_settings().rest_api_enabled:
        return JSONResponse({"status": "disabled"}, status_code=404)
    return JSONResponse({"status": "ok"})


async def create_daily_diary(request: Request) -> JSONResponse:
    if not get_settings().rest_api_enabled:
        return JSONResponse({"error": "rest_api_disabled"}, status_code=404)

    payload = await read_json_body(request)
    payload["token"] = bearer_token(request)
    try:
        diary_input = CreateDailyDiaryInput(**payload)
    except ValidationError as exc:
        return JSONResponse({"error": "invalid_request", "details": exc.errors()}, status_code=400)

    try:
        result = await get_memory_service().create_daily_diary(diary_input)
    except AuthenticationError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)
    return JSONResponse(result)


async def read_json_body(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return {}
    return body if isinstance(body, dict) else {}


routes = [
    Route("/health", health, methods=["GET"]),
    Route("/users", list_users, methods=["GET"]),
    Route("/users/{user_id:str}", get_user, methods=["GET"]),
    Route("/users/{user_id:str}", upsert_user, methods=["PUT"]),
    Route("/users/{user_id:str}", update_user, methods=["PATCH"]),
    Route("/maintenance/daily-diary", create_daily_diary, methods=["POST"]),
]

app = Starlette(debug=False, routes=routes)
