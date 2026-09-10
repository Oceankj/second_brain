from __future__ import annotations

from personal_agent_memory.config import Settings
from personal_agent_memory.providers.embeddings import EmbeddingProvider
from personal_agent_memory.providers.summaries import SummaryProvider
from personal_agent_memory.repository import PostgresMemoryRepository
from personal_agent_memory.server.application import (
    ApplicationContext,
    build_embedding_provider,
    build_summary_provider,
)
from personal_agent_memory.services.memory import MemoryService
from personal_agent_memory.services.users import UserService

_application_context: ApplicationContext | None = None


def create_application_context(settings: Settings | None = None) -> ApplicationContext:
    return ApplicationContext(settings)


def set_application_context(context: ApplicationContext) -> None:
    global _application_context
    _application_context = context


def reset_application_context() -> None:
    global _application_context
    _application_context = None


def get_application_context() -> ApplicationContext:
    global _application_context
    if _application_context is None:
        _application_context = create_application_context()
    return _application_context


def get_settings() -> Settings:
    return get_application_context().settings


def get_repository() -> PostgresMemoryRepository:
    return get_application_context().repository()


def get_embedding_provider() -> EmbeddingProvider:
    return get_application_context().embedding_provider()


def get_summary_provider() -> SummaryProvider:
    return get_application_context().summary_provider()


def get_user_service() -> UserService:
    return get_application_context().user_service()


def get_memory_service() -> MemoryService:
    return get_application_context().memory_service()


__all__ = [
    "ApplicationContext",
    "build_embedding_provider",
    "build_summary_provider",
    "create_application_context",
    "get_application_context",
    "get_embedding_provider",
    "get_memory_service",
    "get_repository",
    "get_settings",
    "get_summary_provider",
    "get_user_service",
    "reset_application_context",
    "set_application_context",
]
