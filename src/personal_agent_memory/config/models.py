from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from personal_agent_memory.config.defaults import (
    DEFAULT_CHUNK_OVERLAP_CHARS,
    DEFAULT_CLOUDFLARE_BASE_URL,
    DEFAULT_CLOUDFLARE_EMBEDDING_MODEL,
    DEFAULT_CLOUDFLARE_SUMMARY_MAX_TOKENS,
    DEFAULT_CLOUDFLARE_SUMMARY_MODEL,
    DEFAULT_CLOUDFLARE_SUMMARY_TEMPERATURE,
    DEFAULT_CLOUDFLARE_SUMMARY_TIMEOUT_SECONDS,
    DEFAULT_CLOUDFLARE_TIMEOUT_SECONDS,
    DEFAULT_DAILY_DIARY_TIMEZONE,
    DEFAULT_DATABASE_POOL_MAX_SIZE,
    DEFAULT_DATABASE_POOL_MIN_SIZE,
    DEFAULT_DATABASE_POOL_TIMEOUT_SECONDS,
    DEFAULT_EMBEDDING_DIMENSION,
    DEFAULT_EMBEDDING_PROVIDER,
    DEFAULT_LINK_EXPANSION_MAX_ITEMS,
    DEFAULT_LINK_EXPANSION_SOURCE_LIMIT,
    DEFAULT_LINK_EXPANSION_SOURCE_WEIGHT,
    DEFAULT_MAX_CHUNK_CHARS,
    DEFAULT_MCP_HTTP_ALLOWED_HOSTS,
    DEFAULT_MCP_HTTP_ALLOWED_ORIGINS,
    DEFAULT_MCP_HTTP_HOST,
    DEFAULT_MCP_HTTP_MAX_REQUEST_BODY_SIZE,
    DEFAULT_MCP_HTTP_PATH,
    DEFAULT_MCP_HTTP_PORT,
    DEFAULT_MCP_HTTP_PUBLIC_URL,
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_OLLAMA_EMBEDDING_MODEL,
    DEFAULT_OLLAMA_TIMEOUT_SECONDS,
    DEFAULT_RECENT_DIARY_LOOKBACK_DAYS,
    DEFAULT_RECENT_DIARY_MAX_CHARS,
    DEFAULT_RECENT_DIARY_MAX_ITEMS,
    DEFAULT_RECENT_DIARY_MIN_SCORE,
    DEFAULT_SUMMARY_PROVIDER,
    DEFAULT_SUMMARY_SOURCE_MAX_CHARS,
    DEFAULT_TAG_RETRIEVAL_MAX_TAGS,
    DEFAULT_TAG_RETRIEVAL_MIN_SCORE,
    DEFAULT_TAG_RETRIEVAL_TAG_WEIGHT,
    EMBEDDING_PROVIDERS,
    SUMMARY_PROVIDERS,
)


@dataclass(frozen=True)
class Settings:
    database_url: str
    database_pool_min_size: int = DEFAULT_DATABASE_POOL_MIN_SIZE
    database_pool_max_size: int = DEFAULT_DATABASE_POOL_MAX_SIZE
    database_pool_timeout_seconds: float = DEFAULT_DATABASE_POOL_TIMEOUT_SECONDS
    rest_api_enabled: bool = False
    admin_api_enabled: bool = False
    default_user_token: str | None = None
    embedding_provider: str = DEFAULT_EMBEDDING_PROVIDER
    embedding_dimension: int = DEFAULT_EMBEDDING_DIMENSION
    ollama_embedding_model: str = DEFAULT_OLLAMA_EMBEDDING_MODEL
    ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL
    ollama_timeout_seconds: float = DEFAULT_OLLAMA_TIMEOUT_SECONDS
    cloudflare_account_id: str | None = None
    cloudflare_api_token: str | None = None
    cloudflare_embedding_model: str = DEFAULT_CLOUDFLARE_EMBEDDING_MODEL
    cloudflare_base_url: str = DEFAULT_CLOUDFLARE_BASE_URL
    cloudflare_timeout_seconds: float = DEFAULT_CLOUDFLARE_TIMEOUT_SECONDS
    cloudflare_pooling: str | None = None
    summary_provider: str = DEFAULT_SUMMARY_PROVIDER
    cloudflare_summary_account_id: str | None = None
    cloudflare_summary_api_token: str | None = None
    cloudflare_summary_model: str = DEFAULT_CLOUDFLARE_SUMMARY_MODEL
    cloudflare_summary_base_url: str = DEFAULT_CLOUDFLARE_BASE_URL
    cloudflare_summary_timeout_seconds: float = DEFAULT_CLOUDFLARE_SUMMARY_TIMEOUT_SECONDS
    cloudflare_summary_max_tokens: int = DEFAULT_CLOUDFLARE_SUMMARY_MAX_TOKENS
    cloudflare_summary_temperature: float = DEFAULT_CLOUDFLARE_SUMMARY_TEMPERATURE
    summary_source_max_chars: int = DEFAULT_SUMMARY_SOURCE_MAX_CHARS
    daily_diary_timezone: str = DEFAULT_DAILY_DIARY_TIMEZONE
    max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS
    chunk_overlap_chars: int = DEFAULT_CHUNK_OVERLAP_CHARS
    recent_diary_lookback_days: int = DEFAULT_RECENT_DIARY_LOOKBACK_DAYS
    recent_diary_max_items: int = DEFAULT_RECENT_DIARY_MAX_ITEMS
    recent_diary_min_score: float = DEFAULT_RECENT_DIARY_MIN_SCORE
    recent_diary_max_chars: int = DEFAULT_RECENT_DIARY_MAX_CHARS
    tag_retrieval_min_score: float = DEFAULT_TAG_RETRIEVAL_MIN_SCORE
    tag_retrieval_max_tags: int = DEFAULT_TAG_RETRIEVAL_MAX_TAGS
    tag_retrieval_tag_weight: float = DEFAULT_TAG_RETRIEVAL_TAG_WEIGHT
    link_expansion_max_items: int = DEFAULT_LINK_EXPANSION_MAX_ITEMS
    link_expansion_source_limit: int = DEFAULT_LINK_EXPANSION_SOURCE_LIMIT
    link_expansion_source_weight: float = DEFAULT_LINK_EXPANSION_SOURCE_WEIGHT
    mcp_http_host: str = DEFAULT_MCP_HTTP_HOST
    mcp_http_port: int = DEFAULT_MCP_HTTP_PORT
    mcp_http_path: str = DEFAULT_MCP_HTTP_PATH
    mcp_http_public_url: str = DEFAULT_MCP_HTTP_PUBLIC_URL
    mcp_http_allowed_hosts: tuple[str, ...] = DEFAULT_MCP_HTTP_ALLOWED_HOSTS
    mcp_http_allowed_origins: tuple[str, ...] = DEFAULT_MCP_HTTP_ALLOWED_ORIGINS
    mcp_http_max_request_body_size: int = DEFAULT_MCP_HTTP_MAX_REQUEST_BODY_SIZE

    def __post_init__(self) -> None:
        self._validate_database()
        self._validate_embedding()
        self._validate_summary()
        self._validate_diary()
        self._validate_chunking()
        self._validate_retrieval()
        self._validate_mcp_http()

    def _validate_database(self) -> None:
        if self.database_pool_min_size < 0:
            raise ValueError("database_pool_min_size cannot be negative")
        if self.database_pool_max_size <= 0:
            raise ValueError("database_pool_max_size must be positive")
        if self.database_pool_min_size > self.database_pool_max_size:
            raise ValueError("database_pool_min_size cannot exceed database_pool_max_size")
        if self.database_pool_timeout_seconds <= 0:
            raise ValueError("database_pool_timeout_seconds must be positive")

    def _validate_embedding(self) -> None:
        if self.embedding_provider not in EMBEDDING_PROVIDERS:
            allowed = ", ".join(sorted(EMBEDDING_PROVIDERS))
            raise ValueError(f"embedding_provider must be one of: {allowed}")
        if self.embedding_dimension <= 0:
            raise ValueError("embedding_dimension must be positive")
        if not self.ollama_embedding_model:
            raise ValueError("ollama_embedding_model is required")
        if self.ollama_timeout_seconds <= 0:
            raise ValueError("ollama_timeout_seconds must be positive")
        if not self.cloudflare_embedding_model:
            raise ValueError("cloudflare_embedding_model is required")
        if self.cloudflare_timeout_seconds <= 0:
            raise ValueError("cloudflare_timeout_seconds must be positive")
        if self.cloudflare_pooling is not None and self.cloudflare_pooling not in {"mean", "cls"}:
            raise ValueError("cloudflare_pooling must be mean or cls")

    def _validate_summary(self) -> None:
        if self.summary_provider not in SUMMARY_PROVIDERS:
            allowed = ", ".join(sorted(SUMMARY_PROVIDERS))
            raise ValueError(f"summary_provider must be one of: {allowed}")
        if not self.cloudflare_summary_model:
            raise ValueError("cloudflare_summary_model is required")
        if self.cloudflare_summary_timeout_seconds <= 0:
            raise ValueError("cloudflare_summary_timeout_seconds must be positive")
        if self.cloudflare_summary_max_tokens <= 0:
            raise ValueError("cloudflare_summary_max_tokens must be positive")
        if not 0 <= self.cloudflare_summary_temperature <= 5:
            raise ValueError("cloudflare_summary_temperature must be between 0 and 5")
        if self.summary_source_max_chars <= 0:
            raise ValueError("summary_source_max_chars must be positive")

    def _validate_diary(self) -> None:
        try:
            ZoneInfo(self.daily_diary_timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("daily_diary_timezone must be a valid IANA timezone") from exc

    def _validate_chunking(self) -> None:
        if self.max_chunk_chars <= 0:
            raise ValueError("max_chunk_chars must be positive")
        if self.default_user_token is not None and len(self.default_user_token) < 32:
            raise ValueError("default_user_token must be at least 32 characters")
        if self.chunk_overlap_chars < 0:
            raise ValueError("chunk_overlap_chars cannot be negative")
        if self.chunk_overlap_chars >= self.max_chunk_chars:
            raise ValueError("chunk_overlap_chars must be smaller than max_chunk_chars")

    def _validate_retrieval(self) -> None:
        if not 0 <= self.recent_diary_lookback_days <= 7:
            raise ValueError("recent_diary_lookback_days must be between 0 and 7")
        if self.recent_diary_max_items < 0:
            raise ValueError("recent_diary_max_items cannot be negative")
        if not 0 <= self.recent_diary_min_score <= 1:
            raise ValueError("recent_diary_min_score must be between 0 and 1")
        if self.recent_diary_max_chars < 0:
            raise ValueError("recent_diary_max_chars cannot be negative")
        if not 0 <= self.tag_retrieval_min_score <= 1:
            raise ValueError("tag_retrieval_min_score must be between 0 and 1")
        if self.tag_retrieval_max_tags < 0:
            raise ValueError("tag_retrieval_max_tags cannot be negative")
        if not 0 <= self.tag_retrieval_tag_weight <= 1:
            raise ValueError("tag_retrieval_tag_weight must be between 0 and 1")
        if self.link_expansion_max_items < 0:
            raise ValueError("link_expansion_max_items cannot be negative")
        if self.link_expansion_source_limit < 0:
            raise ValueError("link_expansion_source_limit cannot be negative")
        if not 0 <= self.link_expansion_source_weight <= 1:
            raise ValueError("link_expansion_source_weight must be between 0 and 1")

    def _validate_mcp_http(self) -> None:
        if not self.mcp_http_host:
            raise ValueError("mcp_http_host is required")
        if not 1 <= self.mcp_http_port <= 65535:
            raise ValueError("mcp_http_port must be between 1 and 65535")
        if not self.mcp_http_path.startswith("/"):
            raise ValueError("mcp_http_path must start with /")
        parsed_public_url = urlparse(self.mcp_http_public_url)
        if parsed_public_url.scheme not in {"http", "https"} or not parsed_public_url.netloc:
            raise ValueError("mcp_http_public_url must be an http(s) URL")
        if self.mcp_http_max_request_body_size <= 0:
            raise ValueError("mcp_http_max_request_body_size must be positive")
