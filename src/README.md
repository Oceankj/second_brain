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

目前 `embeddings.py` 使用 `HashEmbeddingProvider`，這是 deterministic local placeholder。它讓 migration、chunking、pgvector search、tool response shape 可以先跑通，不需要外部 API key。

之後接真實 embedding model 時，應該新增 provider 並符合這個 protocol：

```python
class EmbeddingProvider(Protocol):
    async def embed_text(self, text: str) -> list[float]:
        ...
```

不要把 OpenAI、local model 或其他 provider 的細節散落到 service/repository。

## Module Map

```text
personal_agent_memory/
  server.py       FastMCP app and tool handlers.
  config.py       Environment-backed runtime settings.
  schemas.py      Pydantic models matching docs/schemas JSON Schema intent.
  service.py      P0 use cases: ingest_turn and get_context.
  repository.py   PostgreSQL/pgvector persistence adapter.
  chunking.py     Text chunking helpers.
  embeddings.py   Embedding provider protocol and placeholder provider.
```

## Runtime Flow

### `ingest_turn`

`server.py` receives MCP tool args and builds an `IngestTurnInput`.

`MemoryService.ingest_turn` then:

1. Builds a durable memory body from user input and assistant output.
2. Creates a `memory_items` row with `type = note` and `status = candidate`.
3. Splits the body into chunks.
4. Embeds every chunk.
5. Inserts `memory_chunks`.
6. Normalizes metadata tags and upserts `tags`.
7. Inserts `memory_item_tags`.
8. Detects `[[wikilinks]]` in the body.
9. Resolves matching titles and inserts `memory_links`.
10. Inserts a `created` event into `memory_item_events`.
11. Returns an `ingest_turn.output` shaped response.

The current extraction strategy is intentionally simple: one interaction becomes one candidate note. Later, this can become LLM-assisted extraction without changing the MCP tool boundary.

### `get_context`

`server.py` receives MCP tool args and builds a `GetContextInput`.

`MemoryService.get_context` then:

1. Embeds the caller input.
2. Searches `memory_chunks` with pgvector cosine distance.
3. Joins matching chunks back to `memory_items`.
4. Deduplicates by memory item.
5. Sorts by best chunk score.
6. Writes `retrieved` events for returned items.
7. Optionally loads outgoing links and backlinks.
8. Builds `compact_context`.
9. Returns a `get_context.output` shaped response.

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

This is the application/use-case layer. It coordinates chunking, embedding, repository calls, serialization, and P0 workflow decisions.

Good responsibilities:

- Implement `ingest_turn` workflow.
- Implement `get_context` workflow.
- Normalize tags.
- Detect simple wikilinks.
- Build compact context.

Avoid:

- Raw SQL.
- FastMCP decorators.
- Provider-specific API calls.

### `repository.py`

This is the persistence adapter. It owns SQL and pgvector-specific details.

Good responsibilities:

- Insert and query P0 tables.
- Convert Python vectors to pgvector literals.
- Wrap JSON metadata for `jsonb`.
- Return plain dictionaries to the service layer.

Avoid:

- Deciding whether a memory should exist.
- Ranking policies beyond database sort needed for retrieval.
- LLM extraction or summarization.

### `embeddings.py`

This owns the embedding provider boundary. The placeholder provider is deterministic and local; production provider code should stay behind the same interface.

If the embedding dimension changes, update both:

- `MEMORY_EMBEDDING_DIMENSION`
- `migrations/001_p0_schema.sql`, currently `vector(1536)`

For an existing database, changing dimension requires a new migration and re-embedding existing chunks.

## Database Assumptions

The migration in `migrations/001_p0_schema.sql` follows the P0 DB spec:

- `memory_items`
- `memory_chunks`
- `memory_links`
- `tags`
- `memory_item_tags`
- `memory_item_events`

`memory_chunks.embedding` uses `vector(1536)` and an HNSW cosine index. The app assumes the runtime embedding provider returns the same dimension.

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
7. Replace `HashEmbeddingProvider` with a real embedding provider.
8. Add integration tests around the DB-backed vertical slice.
