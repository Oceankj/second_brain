from __future__ import annotations

from personal_agent_memory.config import Settings, load_settings
from personal_agent_memory.providers.embeddings import EmbeddingProvider, OllamaEmbeddingProvider
from personal_agent_memory.repository import PostgresMemoryRepository
from personal_agent_memory.services.memory import MemoryService
from personal_agent_memory.services.users import UserService

_settings: Settings | None = None
_repository: PostgresMemoryRepository | None = None
_embedding_provider: EmbeddingProvider | None = None
_memory_service: MemoryService | None = None
_user_service: UserService | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def get_repository() -> PostgresMemoryRepository:
    global _repository
    if _repository is None:
        _repository = PostgresMemoryRepository(get_settings().database_url)
    return _repository


def get_embedding_provider() -> EmbeddingProvider:
    global _embedding_provider
    if _embedding_provider is None:
        _embedding_provider = build_embedding_provider(get_settings())
    return _embedding_provider


def get_user_service() -> UserService:
    global _user_service
    if _user_service is None:
        _user_service = UserService(
            repository=get_repository(),
            default_user_token=get_settings().default_user_token,
        )
    return _user_service


def get_memory_service() -> MemoryService:
    global _memory_service
    if _memory_service is None:
        settings = get_settings()
        _memory_service = MemoryService(
            repository=get_repository(),
            embedding_provider=get_embedding_provider(),
            user_service=get_user_service(),
            max_chunk_chars=settings.max_chunk_chars,
            chunk_overlap_chars=settings.chunk_overlap_chars,
            recent_diary_max_items=settings.recent_diary_max_items,
            recent_diary_min_score=settings.recent_diary_min_score,
            recent_diary_max_chars=settings.recent_diary_max_chars,
            tag_retrieval_min_score=settings.tag_retrieval_min_score,
            tag_retrieval_max_tags=settings.tag_retrieval_max_tags,
            tag_retrieval_tag_weight=settings.tag_retrieval_tag_weight,
            link_expansion_max_items=settings.link_expansion_max_items,
            link_expansion_source_limit=settings.link_expansion_source_limit,
            link_expansion_source_weight=settings.link_expansion_source_weight,
        )
    return _memory_service


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    return OllamaEmbeddingProvider(
        model=settings.ollama_embedding_model,
        dimension=settings.embedding_dimension,
        base_url=settings.ollama_base_url,
        timeout_seconds=settings.ollama_timeout_seconds,
    )
