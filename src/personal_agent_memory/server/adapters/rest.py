from __future__ import annotations

import json
from datetime import date

from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from personal_agent_memory.contracts import CreateDailyDiaryInput
from personal_agent_memory.contracts.memory import IngestMessagesInput, ReviewCandidatesInput
from personal_agent_memory.server.dependencies import get_memory_service
from personal_agent_memory.services.memory.consolidation import InvalidReview, ReviewConflict
from personal_agent_memory.services.memory.diary_preparation import DiarySourceConflict
from personal_agent_memory.services.memory.message_ingestion import (
    InvalidMessageBatch,
    MessageConflict,
)
from personal_agent_memory.services.users import AuthenticationError


def bearer_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer" and token:
        return token
    return request.headers.get("x-memory-token", "")


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


public_routes = [
    Route("/health", health, methods=["GET"]),
]

maintenance_routes = [
    Route("/memory/messages", ingest_messages, methods=["POST"]),
    Route("/maintenance/daily-diary", create_daily_diary, methods=["POST"]),
    Route("/maintenance/review-candidates", review_candidates, methods=["POST"]),
]

diary_routes = [Route("/diary/{date:str}", get_daily_diary, methods=["GET"])]

routes = [*public_routes, *maintenance_routes, *diary_routes]

app = Starlette(debug=False, routes=routes)
