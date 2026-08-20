# Source Architecture

這個 `src` 目錄是 Personal Agent Memory MCP 的第一版 Python FastMCP skeleton。它的目標不是一次做完整 agent runtime，而是先把 P0 的 durable memory vertical slice 跑通：

1. `ingest_turn` 可以把一次 interaction 寫成 candidate memory。
2. `get_context` 可以根據目前 input 查回 compact durable context。
3. PostgreSQL + pgvector 是唯一 durable store。
4. MCP 只是外部介面；memory domain logic 盡量不要綁死在 MCP handler 裡。

## Design Principles

### MCP-first, not agent-loop-first

本專案只提供 MCP tools，不負責完整 agent loop、reasoning、一般 tool decision，也不管理 recent chat。外層 runtime 例如 Codex、Claude Desktop、Dify 或其他 agent host 會決定什麼時候呼叫：

- `get_context`: 在回答或工作前讀 durable memory。
- `ingest_turn`: 在 turn 或 conversation 結束後寫 durable memory。

因此 `server.py` 應該保持很薄：負責 FastMCP tool registration、input model validation、呼叫 service，然後把結果回傳。

### Vertical slice before optimization

P0 先重視資料流完整，而不是 retrieval 品質最佳化。第一版允許簡單但完整：

- 建 candidate `memory_items`
- 切 `memory_chunks`
- 產生 embedding
- 寫 tags
- 偵測 wikilinks
- 寫 links
- 寫 usage/lifecycle events
- 用 pgvector 搜回 context

P1 之後再處理 hash-based chunk reuse、full-text search、reranking、daily maintenance、profile memory stability rules。

### Replaceable providers

目前 `providers/embeddings.py` 使用 `OllamaEmbeddingProvider` 作為 runtime embedding provider。Service layer 仍依賴 `EmbeddingProvider` protocol，讓測試可以注入 deterministic fake provider，而不是讓 production server 用 env 切換到測試 provider。

如果之後要支援其他 production embedding backend，應該新增明確的 provider 並符合這個 protocol：

```python
class EmbeddingProvider(Protocol):
    async def embed_text(self, text: str) -> list[float]:
        ...
```

不要把 Ollama 或其他 provider 的細節散落到 service/repository。

## Module Map

```text
personal_agent_memory/
  server.py       FastMCP app and tool handlers.
  config.py       Environment-backed runtime settings.
  tool_schemas.py Pydantic models matching docs/schemas JSON Schema intent.
  service.py      Thin facade that composes use-case services.
  repository/     PostgreSQL/pgvector persistence adapters by table.
  providers/
    embeddings.py Embedding provider protocol and Ollama provider.
  services/
    ingestion.py   ingest_turn use case.
    retrieval.py   get_context use case.
    chunking.py    Text chunking helpers used by ingestion.
  utils/
    serialization.py    Response serialization helpers.
    text_processing.py  Title, tag, body, and wikilink helpers.
```

## Runtime Flow

### `ingest_turn`

`server.py` receives MCP tool args and builds an `IngestTurnInput`.

`MemoryService` delegates to `IngestionService.ingest_turn`, which then:

1. Evaluates the ingest policy from `metadata.ingest_reason` / `skip_memory`.
2. Returns `status=skipped` without writes when the turn is not durable memory.
3. Builds a durable memory body from user input and assistant output.
4. Creates a `memory_items` row with `type = note` and `status = candidate`.
5. Splits the body into chunks.
6. Embeds every chunk.
7. Inserts `memory_chunks`.
8. Normalizes metadata tags and upserts `tags`.
9. Inserts `memory_item_tags`.
10. Detects `[[wikilinks]]` in the body.
11. Resolves matching titles and inserts `memory_links`.
12. Inserts a `created` event into `memory_item_events`.
13. Returns an `ingest_turn.output` shaped response.

The current extraction strategy is intentionally simple: one interaction becomes one candidate note. Later, this can become LLM-assisted extraction without changing the MCP tool boundary.

### `get_context`

`server.py` receives MCP tool args and builds a `GetContextInput`.

`MemoryService` delegates to `RetrievalService.get_context`, which then:

1. Embeds the caller input.
2. Searches `memory_chunks` with pgvector cosine distance.
3. Joins matching chunks back to `memory_items`.
4. Deduplicates by memory item.
5. Sorts by best chunk score.
6. Writes `retrieved` events for returned items.
7. Optionally loads outgoing links and backlinks.
8. Builds `compact_context`.
9. Truncates `compact_context` to `max_context_chars`.
10. Returns a `get_context.output` shaped response.

The current version does not yet implement recent diary relevance, tag candidate boosting, typed link expansion, full-text search, or reranking. Those belong after the P0 write/read path is proven.

## Boundaries

### `server.py`

Keep this as the transport adapter. It should know about FastMCP and input/output argument shapes, but should not grow business logic.

Good responsibilities:

- Register MCP tools.
- Convert function args into Pydantic models.
- Instantiate service from settings.
- Return service results.

Avoid:

- SQL queries.
- Chunking decisions.
- Ranking logic.
- Provider-specific embedding code.

### `service.py`

This is a thin facade. It exists so `server.py` can depend on one object while the actual use cases live in smaller services.

Good responsibilities:

- Compose `IngestionService`.
- Compose `RetrievalService`.
- Keep the MCP adapter stable while internal services evolve.

Avoid:

- Raw SQL.
- FastMCP decorators.
- Provider-specific API calls.
- Use-case logic that belongs in a dedicated service.

### `services/ingestion.py`

This owns the `ingest_turn` use case.

Good responsibilities:

- Build candidate note body and title.
- Create candidate memory item.
- Create chunks and embeddings.
- Attach normalized tags.
- Resolve simple wikilinks.
- Write `created` events.

Avoid:

- Retrieval ranking.
- Daily consolidation.
- Long-term profile stability rules.

### `services/retrieval.py`

This owns the `get_context` use case.

Good responsibilities:

- Embed caller query.
- Search matching chunks.
- Deduplicate and rank memory items.
- Log `retrieved` events.
- Attach selected links.
- Build context response.

Avoid:

- Ingestion writes.
- Memory extraction.
- Tag normalization writes.

### `utils/serialization.py`

This keeps response shaping out of use-case code. It converts database dictionaries into output-schema-shaped dictionaries.

This is app-specific utility code, not a use-case service. If serialization grows into versioned API presentation logic later, it can move to a dedicated `presenters/` or `mappers/` package.

### `utils/text_processing.py`

This keeps deterministic string handling separate from orchestration code. It currently owns title creation, tag normalization, turn body construction, and wikilink detection.

This is utility code because it has no side effects and no use-case orchestration responsibility.

### `repository/`

This is the persistence adapter package. It owns SQL and pgvector-specific details, with
table-scoped files behind one `PostgresMemoryRepository` facade.

Good responsibilities:

- Insert and query P0 tables.
- Convert Python vectors to pgvector literals.
- Wrap JSON metadata for `jsonb`.
- Return plain dictionaries to the service layer.

Avoid:

- Deciding whether a memory should exist.
- Ranking policies beyond database sort needed for retrieval.
- LLM extraction or summarization.

### `providers/embeddings.py`

This owns the embedding provider boundary. The runtime provider calls Ollama embeddings; tests can inject deterministic fakes through the same `EmbeddingProvider` protocol.

If the embedding dimension changes, update both:

- `MEMORY_EMBEDDING_DIMENSION`
- a fresh database, or a migration that changes `memory_chunks.embedding` and re-embeds chunks

For an existing database, changing dimension requires a new migration and re-embedding existing chunks.

## Database Assumptions

The migration in `migrations/001_p0_schema.sql` follows the P0 DB spec:

- `memory_items`
- `memory_chunks`
- `memory_links`
- `tags`
- `memory_item_tags`
- `memory_item_events`

`memory_chunks.embedding` uses `vector(1024)` and an HNSW cosine index. The app assumes the runtime embedding provider returns the same dimension.

## What Is Intentionally Missing

These are intentionally not in the first skeleton:

- Real embedding provider.
- Daily maintenance worker.
- Candidate note consolidation.
- Diary generation.
- Profile memory stability detection.
- Full-text search.
- Reranking.
- Typed link expansion policy.
- HTTP transport.
- Auth / multi-user isolation.
- Migration runner.

They should be added once the local vertical slice is exercised end to end.

## Suggested Next Steps

1. Install dependencies with `uv sync --extra dev`.
2. Create a local PostgreSQL database with pgvector enabled.
3. Run `psql "$DATABASE_URL" -f migrations/001_p0_schema.sql`.
4. Start the server with `uv run personal-agent-memory`.
5. Call `ingest_turn` with a small interaction.
6. Call `get_context` with related input and inspect returned `compact_context`.
7. Add integration tests around the DB-backed vertical slice.
