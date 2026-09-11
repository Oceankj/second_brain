[\[en\]](README.md)

# Personal Agent Memory MCP
這個專案的目標是建立一個可被 agent runtime 使用的 personal memory MCP server。

它本身不負責完整的 agent loop，也不負責一般 tool using 的決策；這些應該由 Dify、Codex、Claude Desktop 或其他外層 agent runtime 負責。本專案專注在長期記憶的讀取、寫入、整理與連結。

## Quick Start

這條流程只涵蓋本機啟動：安裝依賴、啟動 PostgreSQL + pgvector，預設 embedding provider 為 Ollama，套 schema、啟動 stdio MCP server。

安裝依賴：

```bash
uv sync --extra dev
```

如果在 Codex sandbox 裡遇到 `~/.cache/uv` 權限問題，可以把 cache 放在 repo 內：

```bash
UV_CACHE_DIR=.uv-cache uv sync --extra dev
```

準備本機環境設定：

```bash
cp .env.example .env
```

準備 memory 行為設定：

```bash
cp memory.example.json memory.json
```

預設使用本機 Ollama embeddings。`.env` 主要保存 runtime environment、service connection 與 secrets，例如 `DATABASE_URL`、`MEMORY_DEFAULT_USER_TOKEN`、Cloudflare API credentials。`DATABASE_URL` 是 MCP runtime 實際使用的 database；`LOCAL_POSTGRES_*` 只用來設定本機 Docker Compose database。

```dotenv
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/personal_agent_memory
LOCAL_POSTGRES_DB=personal_agent_memory
LOCAL_POSTGRES_USER=postgres
LOCAL_POSTGRES_PASSWORD=postgres
LOCAL_POSTGRES_PORT=5432
MEMORY_REST_API_ENABLED=false
MEMORY_DEFAULT_USER_TOKEN=replace-with-a-random-token-at-least-32-chars
CLOUDFLARE_ACCOUNT_ID=
CLOUDFLARE_API_TOKEN=
```

非 secret 的 memory 行為參數放在 `memory.json`，包含 chunking、retrieval、embedding provider selector 與 summary provider：

```json
{
  "database": {
    "pool_min_size": 1,
    "pool_max_size": 10,
    "pool_timeout_seconds": 30
  },
  "chunking": {
    "max_chars": 1800,
    "overlap_chars": 200
  },
  "embedding": {
    "provider": "ollama",
    "dimension": 1024,
    "ollama": {
      "model": "qwen3-embedding:0.6b",
      "base_url": "http://localhost:11434",
      "timeout_seconds": 30
    },
    "cloudflare": {
      "model": "@cf/baai/bge-large-en-v1.5",
      "account_id_env": "CLOUDFLARE_ACCOUNT_ID",
      "api_token_env": "CLOUDFLARE_API_TOKEN",
      "timeout_seconds": 30
    }
  },
  "summary": {
    "provider": "cloudflare",
    "source_max_chars": 24000,
    "cloudflare": {
      "model": "@cf/meta/llama-3.1-8b-instruct-fp8",
      "account_id_env": "CLOUDFLARE_ACCOUNT_ID",
      "api_token_env": "CLOUDFLARE_API_TOKEN",
      "timeout_seconds": 60,
      "max_tokens": 1200,
      "temperature": 0.2
    }
  },
  "daily_diary": {
    "timezone": "America/Los_Angeles"
  },
  "retrieval": {
    "recent_diary_lookback_days": 2,
    "recent_diary_max_items": 3,
    "recent_diary_min_score": 0.72,
    "recent_diary_max_chars": 2000,
    "tag_retrieval_min_score": 0.72,
    "tag_retrieval_max_tags": 5,
    "tag_retrieval_tag_weight": 0.4,
    "link_expansion_max_items": 3,
    "link_expansion_source_limit": 5,
    "link_expansion_source_weight": 0.4
  }
}
```

預設會讀取 repo root 的 `memory.json`。部署時如果要使用不同 config 檔，可以設定：

```dotenv
MEMORY_CONFIG_PATH=/app/config/memory.production.json
```

`qwen3-embedding:0.6b` 預設搭配目前 schema 的 1024 維向量；如果改成其他模型或維度，DB schema 的 `memory_chunks.embedding vector(1024)` 也要一起調整。

Migration 會讀 `memory.json` 的 `embedding.dimension` 來建立 fresh database 的 vector 欄位。既有 database 不會被重跑 migration 自動改維度；換模型維度時需要 fresh DB 或另寫 migration。

可以從 migration output 確認實際傳入值：

```bash
scripts/db/migrate.sh
```

如果 `memory.json` 設定 `embedding.dimension` 為 1024，會看到：

```text
Using embedding_dimension=1024
```

啟動本機 infra：

```bash
scripts/infra/up.sh
```

這會啟動 PostgreSQL + pgvector。如果 `memory.json` 的 `embedding.provider` 是 `ollama`，也會啟動 Ollama 並 pull `embedding.ollama.model`；如果是 `cloudflare`，則略過 Ollama。

套用 P0 database schema：

```bash
scripts/db/migrate.sh
```

`scripts/db/migrate.sh` 會套用到本機 Docker Compose database。如果要套用到 `DATABASE_URL` 指向的 database，例如 Supabase，使用：

```bash
scripts/db/migrate_url.sh
```

啟動 stdio MCP server 給外層 agent runtime：

```bash
uv run personal-agent-memory
```

啟動部署用 unified HTTP server，同一個 process 同時提供 `/mcp` remote MCP 與 REST maintenance routes：

```bash
uv run personal-agent-memory-http
```

REST routes 預設關閉；需要先設定 `MEMORY_REST_API_ENABLED=true`。Remote MCP HTTP 預設也關閉；需要在 `memory.json` 設定 `mcp_http.enabled=true`。`personal-agent-memory-http` 需要兩者都開啟。stdio MCP tools 使用 top-level `token` argument；HTTP REST routes 使用 `Authorization: Bearer <token>` 或 `X-Memory-Token` header；remote MCP 使用 `Authorization: Bearer <token>` transport auth，不需要在 tool arguments 再傳 token。Token 只以 hash 形式寫入 DB。

建立每日 diary：

```bash
curl -X POST http://127.0.0.1:8000/maintenance/daily-diary \
  -H "Authorization: Bearer $MEMORY_DEFAULT_USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"date":"2026-09-08","dry_run":false}'
```

這個 endpoint 會用 `daily_diary.timezone` 將指定日期換算成查詢範圍，讀該日期的 non-archived, non-diary memory items，呼叫 `memory.json` 的 `summary.provider` 產生 diary body，建立 `type=diary` 的 active memory item，再替 diary 建 chunks / embeddings / references links / `mentioned_in_diary` events。`dry_run=true` 會呼叫 summary provider 產生預覽，但不寫入 DB。若當天已經有未 archived diary，預設回傳 `already_exists`；`force=true` 會 archive 舊 diary 並重建。

Remote MCP HTTP 的 `memory.json` 設定範例：

```json
{
  "mcp_http": {
    "enabled": true,
    "host": "127.0.0.1",
    "port": 8001,
    "path": "/mcp",
    "public_url": "http://127.0.0.1:8001",
    "allowed_hosts": ["127.0.0.1:*", "localhost:*", "[::1]:*"],
    "allowed_origins": [
      "http://127.0.0.1:*",
      "http://localhost:*",
      "http://[::1]:*"
    ],
    "max_request_body_size": 4194304
  }
}
```

部署注意事項：

- GitHub Action daily diary 排程建議打 REST endpoint，不需要繞 MCP。
- Remote MCP 適合給遠端 agent runtime 讀寫 memory；不要裸開到 public internet。
- Render/container 部署使用 `personal-agent-memory-http`，同一個 instance 同時服務 `/mcp` 和 `/maintenance/daily-diary`。第一版 Render Docker 操作手冊見 [deploy/render/README.md](deploy/render/README.md)。
- 如果只在本機或 tunnel 後面測試，維持 `host=127.0.0.1`。
- 如果部署在 container/VPS 需要對外 bind，可把 `host` 改成 `0.0.0.0`，但 `public_url` 必須改成實際 HTTPS 網域，例如 `https://memory.example.com`。
- `allowed_hosts` 要包含 client 實際送出的 Host header；放在 reverse proxy 後面時通常是你的公開網域。
- `allowed_origins` 要包含瀏覽器型 MCP client 的 origin；純 server-to-server client 也建議保持收斂。
- production 必須放在 TLS/reverse proxy/Cloudflare Access/Tailscale/SSH tunnel 這類邊界後面，並搭配 rate limit 與 access log。
- Bearer token 使用既有 user token 規則，也就是 `MEMORY_DEFAULT_USER_TOKEN` 或 DB 裡已 seed 的 token；不要把 provider API keys 當成 MCP auth token。

預設的 Docker Compose database URL 是：

```text
postgresql://postgres:postgres@localhost:5432/personal_agent_memory
```

`ollama` embedding provider 預設的 URL 是：

```text
http://localhost:11434
```

如果你已經有自己的 Docker PostgreSQL 或其他 local PostgreSQL，這個 Compose service 不是必要的；把 `DATABASE_URL` 指到你的 database，然後用你的 migration 流程套 [migrations/001_p0_schema.sql](migrations/001_p0_schema.sql)。細節見 [scripts/db/README.md](scripts/db/README.md)。

## Verification

檢查 DB extensions、tables 與欄位：

```bash
scripts/db/doctor.sh
```

如果要檢查 `DATABASE_URL` 指向的 database，例如 Supabase，使用：

```bash
scripts/db/doctor_url.sh
```

跑單元測試與 lint：

```bash
uv run pytest
uv run ruff check .
```

跑真實 MCP tool-call smoke test：

```bash
uv run python scripts/smoke_test.py
```

這個 smoke test 需要 `memory.json` 指定的 embedding provider 可用。`ollama` 模式需要本機 Ollama 正在執行且模型已 pull；`cloudflare` 模式需要 `.env` 裡有 `CLOUDFLARE_ACCOUNT_ID` 與 `CLOUDFLARE_API_TOKEN`。

這個 smoke test 會：

- 連到 `DATABASE_URL` 檢查必要 tables 與 `memory_link_type` enum。
- 呼叫目前設定的 embedding provider，確認 embedding model 可用且維度符合設定。
- 用 MCP stdio client 啟動 `personal_agent_memory.server`。
- `list_tools` 檢查 `ingest_turn` / `get_context`。
- 呼叫帶有 `metadata.ingest_reason` 的 `ingest_turn`，透過目前設定的 embeddings 寫入一筆 smoke memory。
- 呼叫帶有 `max_context_chars` 的 `get_context`，透過目前設定的 embeddings + pgvector retrieval 確認至少回傳一筆 item。

## Documentation Shape

這個 repo 採用 MCP-first 文件架構。Runtime 使用 `src/personal_agent_memory/contracts/` 的 Pydantic models 作為實際 contract；`docs/schemas/` 目前是對外文件用的 JSON Schema snapshot，不會被 runtime 讀取。之後若需要 machine-readable runtime schema，應由 Pydantic models 產生，避免手維護兩份 spec。

- [MCP server overview](docs/mcp-server.md)
- [MCP tools](docs/mcp-tools.md)
- [MCP link policy](docs/mcp-links.md)
- [MCP resources](docs/mcp-resources.md)
- [MCP prompts](docs/mcp-prompts.md)
- [Lifecycle diagrams](docs/lifecycle.md)
- [Database schema](docs/database/schema.md)
- [Future ideas](docs/roadmap/TODO.md)

OpenAPI/Swagger 只適合未來如果要做 HTTP gateway 或 REST adapter 時另外生成；目前不作為主文件。

## Scope

P0 只負責三類 durable text：

- `note`: 明確的知識、想法、專案筆記、可被重複引用的資訊。
- `diary`: 時間序的日記式整理，記錄當天關注的目標、使用者的自我發現，以及根據對話內容形成的第三方觀察。
- `profile_memory`: 保留給可被 retrieval 的 profile-derived memory；canonical user profile 本身由獨立 Markdown profile 維護。

暫時不把 `recent chat` 當作本系統的核心資料庫。近期對話脈絡通常由外層 runtime 自己管理。未來如果需要 audit trail，可以另外加入 raw `conversation_events`，但不讓它成為主要 retrieval 來源。

## P0 MCP Primitives

P0 先實作 tools：

- `get_context`: 根據目前任務輸入搜尋 durable memory，回傳 compact context bundle。
- `ingest_turn`: 把一次 interaction 轉成候選 memory，並處理 `ingest_reason`、tags 與 links。

P0 schema 也會記錄 `memory_item_events`。這是 hot/cold memory 的 raw event log；分數與 ranking 演算法可以之後再從 log 重算。

Resources 與 prompts 先作為 MCP-first 設計邊界記錄；是否進入 P0 實作，以工具穩定後再決定。

## FastMCP Skeleton

目前實作骨架採用 Python FastMCP。`src/personal_agent_memory/server/` 只保留兩個公開入口，其餘檔案都是內部 adapter 或 wiring：

```text
server/
  entrypoints/
    stdio.py         local stdio MCP entrypoint
    http.py          deployable unified HTTP entrypoint
  adapters/
    mcp_http.py      streamable HTTP MCP adapter setup
    rest.py          REST route handlers for health/users/maintenance
  auth/
    transport.py     MCP HTTP bearer token verifier
  tools/
    memory.py        shared MCP tool-to-service handlers
  dependencies.py    settings/repository/provider/service wiring
```

部署用 unified HTTP adapter 位於 `src/personal_agent_memory/server/entrypoints/http.py`，同一個 process 同時提供 `/mcp` remote MCP 與 REST maintenance routes。公開 HTTP 啟動入口只使用 unified HTTP server。

目前 runtime 使用 `memory.json` 的 `embedding.provider` 在 `src/personal_agent_memory/providers/embeddings.py` 裡的 Ollama 與 Cloudflare embeddings provider 之間切換。測試若需要 deterministic embeddings，應在 test code 裡注入 fake provider，不走 production server 設定。

Daily diary summary 由獨立的 `SummaryProvider` layer 負責，目前支援 Cloudflare Workers AI，和 `EmbeddingProvider` 分開。Cloudflare embedding 與 summary 可以共用 `.env` 裡的 `CLOUDFLARE_ACCOUNT_ID` / `CLOUDFLARE_API_TOKEN`。

Runtime settings 由 `.env` 與 optional `memory.json` 組成；`memory.json` 用於非 secret 的 memory behavior settings，`.env` 只放 database、tokens 與 provider credentials。

## Memory Source

Memory source 不是只有 model output，而是整個 interaction：

```text
memory source = user input + assistant output + timestamp + app/source + optional tags
```

## Linking And Tags

所有 notes 與 diary entries 應該支援像 Obsidian 一樣的 two-way links。

- `[[note title]]` 或穩定 `note_id` 的 wikilink。
- 每張 note / diary entry 保存 outgoing links。
- 系統可反查 backlinks。
- diary entry 可以連到當天提到或使用過的重要 notes。
- note merge / split 時需要保留 link history 或 redirect，避免舊連結失效。

Tags 負責分類，links 負責具體關聯。建立新 note 前應該先搜尋現有 tag，優先重用既有 tag，避免產生意思相近的新 tag。

## Update Timing

每次對話結束或每次 turn 完成後，外層 agent 只有在符合 ingest policy 時才應呼叫 `ingest_turn` 建立 raw-ish 的 candidate note。P0 要求 `metadata.ingest_reason` 明確說明寫入原因；沒有原因是 invalid input，不會建立 memory item。

MVP 允許的 `ingest_reason`：

- `task_completed`
- `explicit_memory_request`
- `user_preference`
- `stable_fact`
- `personal_insight`
- `decision`
- `stable_artifact`
- `manual_import`

P0 使用 deterministic routing：`ingest_turn` 不推論 reason，而是信任 caller 提供的 `metadata.ingest_reason`。目前所有 accepted turns 都先建立 `note` candidate，並把 `ingest_reason` 寫在 `memory_items` 上。Daily maintenance 再依 reason 分工：

- 整理 notes：讀取當天 `status=candidate` 且 `ingest_reason in stable_fact / personal_insight` 的 items。
- 生成 daily note：讀取當天所有 memory items。
- 更新 profile：讀取當天 `status=candidate` 且 `ingest_reason=user_preference` 的 items，更新 canonical profile 的 system-observed 區，並把已採用的 candidates archived。

`get_context` 會用 `max_context_chars` 對 `compact_context` 做 server-side hard budget，避免外層 agent 一次拿太多 memory 塞進 prompt。預設是 6000 chars。

每天結束、準備關掉 app、或 app init 時發現有日期缺少 summary，就可以分別執行 daily tasks：

- review notes
- create daily note / diary
- update profile
- normalize tags
- repair / update links

Daily maintenance 會把候選 notes 和當天 interactions 整理成更穩定的 active memory，並生成 diary entry。

## Open Questions

- `create notes` 是每個 turn 都建立，還是每段 conversation 結束後建立一批 candidate notes？
- note 的長度上限要用 token、字數，還是 semantic sections 數量判斷？
- profile_memory 什麼時候可以更新？需要幾次重複 evidence 才算穩定？
- tag 合併是否需要人工確認，還是允許低風險自動合併？
