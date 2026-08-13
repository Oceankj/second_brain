# Personal Agent Memory MCP

這個專案的目標是建立一個可被 agent runtime 使用的 personal memory MCP server。

它本身不負責完整的 agent loop，也不負責一般 tool using 的決策；這些應該由 Dify、Codex、Claude Desktop 或其他外層 agent runtime 負責。本專案專注在長期記憶的讀取、寫入、整理與連結。

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

P0 只負責三類 durable memory：

- `note`: 明確的知識、想法、專案筆記、可被重複引用的資訊。
- `diary`: 時間序的日記式整理，記錄當天關注的目標、使用者的自我發現，以及根據對話內容形成的第三方觀察。
- `profile_memory`: 穩定的使用者偏好、長期事實、常見工作方式、價值觀與限制。

暫時不把 `recent chat` 當作本系統的核心資料庫。近期對話脈絡通常由外層 runtime 自己管理。未來如果需要 audit trail，可以另外加入 raw `conversation_events`，但不讓它成為主要 retrieval 來源。

## P0 MCP Primitives

P0 先實作 tools：

- `get_context`: 根據目前任務輸入搜尋 durable memory，回傳 compact context bundle。
- `ingest_turn`: 把一次 interaction 轉成候選 memory，並處理 tags、links、profile/diary material。

P0 schema 也會記錄 `memory_item_events`。這是 hot/cold memory 的 raw event log；分數與 ranking 演算法可以之後再從 log 重算。

Resources 與 prompts 先作為 MCP-first 設計邊界記錄；是否進入 P0 實作，以工具穩定後再決定。

## FastMCP Skeleton

目前實作骨架採用 Python FastMCP，入口在 `src/personal_agent_memory/server.py`。

先安裝依賴：

```bash
uv sync --extra dev
```

建立 P0 database schema：

```bash
psql "$DATABASE_URL" -f migrations/001_p0_schema.sql
```

啟動 stdio MCP server：

```bash
DATABASE_URL="postgresql://localhost:5432/personal_agent_memory" uv run personal-agent-memory
```

第一版先用 deterministic hash embedding provider，讓 ingestion 與 pgvector retrieval 的 vertical slice 可以本機跑通。之後接真實 embedding model 時，替換 `src/personal_agent_memory/embeddings.py` 的 provider 即可。

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

每次對話結束或每次 turn 完成後，`ingest_turn` 可以先建立 raw-ish 的 candidate note。它不一定馬上合併到既有 note，避免在對話主流程中做太重的整理。

每天結束、準備關掉 app、或 app init 時發現有日期缺少 summary，就執行 daily tasks：

- update notes
- create diary
- normalize tags
- repair / update links

Daily maintenance 會把候選 notes 和當天 interactions 整理成更穩定的 active memory，並生成 diary entry。

## Open Questions

- `create notes` 是每個 turn 都建立，還是每段 conversation 結束後建立一批 candidate notes？
- note 的長度上限要用 token、字數，還是 semantic sections 數量判斷？
- profile_memory 什麼時候可以更新？需要幾次重複 evidence 才算穩定？
- tag 合併是否需要人工確認，還是允許低風險自動合併？
