from __future__ import annotations

import json
from datetime import date
from typing import Any

from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from personal_agent_memory.contracts import CreateDailyDiaryInput
from personal_agent_memory.contracts.memory import IngestMessagesInput, ReviewCandidatesInput
from personal_agent_memory.server.dependencies import (
    get_memory_service,
    get_settings,
    get_user_service,
)
from personal_agent_memory.services.memory.consolidation import InvalidReview, ReviewConflict
from personal_agent_memory.services.memory.diary_preparation import DiarySourceConflict
from personal_agent_memory.services.memory.message_ingestion import (
    InvalidMessageBatch,
    MessageConflict,
)
from personal_agent_memory.services.users import AuthenticationError


async def require_admin_api_enabled_and_authenticated(
    request: Request,
) -> JSONResponse | None:
    if not get_settings().admin_api_enabled:
        return JSONResponse({"error": "admin_api_disabled"}, status_code=404)

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
    if error := await require_admin_api_enabled_and_authenticated(request):
        return error
    return JSONResponse({"users": await get_user_service().list_users()})


async def get_user(request: Request) -> JSONResponse:
    if error := await require_admin_api_enabled_and_authenticated(request):
        return error
    user = await get_user_service().get_user(request.path_params["user_id"])
    if user is None:
        return JSONResponse({"error": "user_not_found"}, status_code=404)
    return JSONResponse(user)


async def upsert_user(request: Request) -> JSONResponse:
    if error := await require_admin_api_enabled_and_authenticated(request):
        return error
    payload = await read_json_body(request)
    user = await get_user_service().ensure_user(
        request.path_params["user_id"],
        display_name=payload.get("display_name"),
    )
    return JSONResponse(user)


async def update_user(request: Request) -> JSONResponse:
    if error := await require_admin_api_enabled_and_authenticated(request):
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
    return JSONResponse({"status": "ok"})


async def create_daily_diary(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    payload["token"] = bearer_token(request)
    try:
        diary_input = CreateDailyDiaryInput(**payload)
    except ValidationError as exc:
        return JSONResponse(
            {"error": "invalid_request", "details": exc.errors(include_input=False)},
            status_code=400,
        )

    try:
        result = await get_memory_service().create_daily_diary(diary_input)
    except DiarySourceConflict:
        return JSONResponse({"error": "diary_conflict", "retryable": True}, status_code=409)
    except AuthenticationError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)
    return JSONResponse(result)


async def get_daily_diary(request: Request) -> JSONResponse:
    try:
        diary_date = date.fromisoformat(request.path_params["date"])
    except ValueError:
        return JSONResponse({"error": "invalid_date"}, status_code=400)
    try:
        result = await get_memory_service().get_daily_diary(
            token=bearer_token(request),
            diary_date=diary_date,
        )
    except AuthenticationError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)
    if result is None:
        return JSONResponse({"error": "diary_not_found"}, status_code=404)
    return JSONResponse(result)


async def review_candidates(request: Request) -> JSONResponse:
    try:
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse({"error": "invalid_request"}, status_code=400)
        payload = ReviewCandidatesInput(**{**body, "token": bearer_token(request)})
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError):
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    try:
        result = await get_memory_service().review_candidates(payload)
    except AuthenticationError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)
    except ReviewConflict:
        return JSONResponse({"error": "review_conflict", "retryable": True}, status_code=409)
    except InvalidReview as exc:
        return JSONResponse({"error": "invalid_review", "message": str(exc)}, status_code=422)
    except (RuntimeError, TimeoutError):
        return JSONResponse({"error": "review_provider_failed"}, status_code=502)
    return JSONResponse(result)


async def ingest_messages(request: Request) -> JSONResponse:
    try:
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse({"error": "invalid_request"}, status_code=400)
        payload = IngestMessagesInput(**{**body, "token": bearer_token(request)})
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError):
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    try:
        return JSONResponse(await get_memory_service().ingest_messages(payload))
    except AuthenticationError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)
    except MessageConflict as exc:
        return JSONResponse({"error": "message_conflict", "message": str(exc)}, status_code=409)
    except InvalidMessageBatch as exc:
        return JSONResponse(
            {"error": "invalid_message_batch", "message": str(exc)}, status_code=422
        )


async def read_json_body(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return {}
    return body if isinstance(body, dict) else {}


public_routes = [
    Route("/health", health, methods=["GET"]),
]

admin_routes = [
    Route("/users", list_users, methods=["GET"]),
    Route("/users/{user_id:str}", get_user, methods=["GET"]),
    Route("/users/{user_id:str}", upsert_user, methods=["PUT"]),
    Route("/users/{user_id:str}", update_user, methods=["PATCH"]),
]

maintenance_routes = [
    Route("/memory/messages", ingest_messages, methods=["POST"]),
    Route("/maintenance/daily-diary", create_daily_diary, methods=["POST"]),
    Route("/maintenance/review-candidates", review_candidates, methods=["POST"]),
]

diary_routes = [Route("/diary/{date:str}", get_daily_diary, methods=["GET"])]

routes = [*public_routes, *admin_routes, *maintenance_routes, *diary_routes]

app = Starlette(debug=False, routes=routes)
