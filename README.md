# Personal Agent Memory MCP

這個專案的目標是建立一個可被 agent runtime 使用的 personal memory MCP server。

它本身不負責完整的 agent loop，也不負責一般 tool using 的決策；這些應該由 Dify、Codex、Claude Desktop 或其他外層 agent runtime 負責。本專案專注在長期記憶的讀取、寫入、整理與連結。

## Quick Start

這條流程只涵蓋本機啟動：安裝依賴、啟動 PostgreSQL + pgvector 與 Ollama、套 schema、啟動 stdio MCP server。

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

預設使用本機 Ollama embeddings：

```dotenv
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBEDDING_MODEL=qwen3-embedding:0.6b
MEMORY_EMBEDDING_DIMENSION=1024
```

`.env` 主要保存 runtime environment 與 service connection，例如 `DATABASE_URL`、`OLLAMA_BASE_URL`、`OLLAMA_EMBEDDING_MODEL`。非 secret 的 memory 行為參數放在 `memory.json`，例如 chunking：

```json
{
  "chunking": {
    "max_chars": 1800,
    "overlap_chars": 200
  }
}
```

`qwen3-embedding:0.6b` 預設搭配目前 schema 的 1024 維向量；如果改成其他模型或維度，DB schema 的 `memory_chunks.embedding vector(1024)` 也要一起調整。

Migration 會讀 `.env` 的 `MEMORY_EMBEDDING_DIMENSION` 來建立 fresh database 的 vector 欄位。既有 database 不會被重跑 migration 自動改維度；換模型維度時需要 fresh DB 或另寫 migration。

可以從 migration output 確認實際傳入值：

```bash
MEMORY_EMBEDDING_DIMENSION=777 scripts/db/migrate.sh
```

如果 env override 有生效，會看到：

```text
Using embedding_dimension=777
```

啟動本機 infra：

```bash
scripts/infra/up.sh
```

這會啟動 PostgreSQL + pgvector、Ollama，並 pull `.env` 裡的 embedding model。你也可以直接用 `docker compose up -d` 起服務；第一次 pull model 會花比較久。

套用 P0 database schema：

```bash
scripts/db/migrate.sh
```

啟動 stdio MCP server 給外層 agent runtime：

```bash
uv run personal-agent-memory
```

預設的 Docker Compose database URL 是：

```text
postgresql://postgres:postgres@localhost:5432/personal_agent_memory
```

預設的 Ollama URL 是：

```text
http://localhost:11434
```

如果你已經有自己的 Docker PostgreSQL 或其他 local PostgreSQL，這個 Compose service 不是必要的；把 `DATABASE_URL` 指到你的 database，然後用你的 migration 流程套 [migrations/001_p0_schema.sql](migrations/001_p0_schema.sql)。細節見 [scripts/db/README.md](scripts/db/README.md)。

## Verification

檢查 DB extensions、tables 與欄位：

```bash
scripts/db/doctor.sh
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

這個 smoke test 需要本機 Ollama 正在執行，且 `.env` 裡的 `OLLAMA_EMBEDDING_MODEL` 已可用。

這個 smoke test 會：

- 連到 `DATABASE_URL` 檢查必要 tables 與 `memory_link_type` enum。
- 呼叫 Ollama `/api/embed`，確認 embedding model 可用且維度符合設定。
- 用 MCP stdio client 啟動 `personal_agent_memory.server`。
- `list_tools` 檢查 `ingest_turn` / `get_context`。
- 呼叫帶有 `metadata.ingest_reason` 的 `ingest_turn`，透過 Ollama embeddings 寫入一筆 smoke memory。
- 呼叫帶有 `max_context_chars` 的 `get_context`，透過 Ollama embeddings + pgvector retrieval 確認至少回傳一筆 item。

## Documentation Shape

這個 repo 採用 MCP-first 文件架構。Canonical spec 是 MCP primitives 與 JSON Schema，不是 Swagger/OpenAPI。

- [MCP server overview](docs/mcp-server.md)
- [MCP tools](docs/mcp-tools.md)
- [MCP link policy](docs/mcp-links.md)
- [MCP resources](docs/mcp-resources.md)
- [MCP prompts](docs/mcp-prompts.md)
- [Lifecycle diagrams](docs/lifecycle.md)
- [Database schema](DB.md)
- [Future ideas](TODO.md)

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

目前實作骨架採用 Python FastMCP，入口在 `src/personal_agent_memory/server.py`。

目前 runtime 使用 `src/personal_agent_memory/providers/embeddings.py` 的 Ollama embeddings provider。測試若需要 deterministic embeddings，應在 test code 裡注入 fake provider，不走 production server 設定。

Runtime settings 由 `.env` 與 optional `memory.json` 組成；`memory.json` 用於非 secret 的 memory behavior settings。

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

每次對話結束或每次 turn 完成後，外層 agent 只有在符合 ingest policy 時才應呼叫 `ingest_turn` 建立 raw-ish 的 candidate note。P0 要求 `metadata.ingest_reason` 明確說明寫入原因；沒有原因時 server 會回傳 `skipped` 並且不寫 DB。

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
