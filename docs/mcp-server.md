# MCP Server Overview

Personal Agent Memory MCP 是一個 durable memory server。它提供外層 agent runtime 查詢、寫入、整理長期記憶的能力，但不接管外層 runtime 的 reasoning loop、近期對話管理或一般工具決策。

## Canonical Spec

本專案的 canonical API 文件由 MCP primitives 組成：

- Tools: model 可呼叫的操作，詳見 [mcp-tools.md](mcp-tools.md)。
- Link policy: retrieval expansion 與 ranking 使用 links 的方式，詳見 [mcp-links.md](mcp-links.md)。
- Resources: client 可讀取的 context data，詳見 [mcp-resources.md](mcp-resources.md)。
- Prompts: 可重用的 workflow template，詳見 [mcp-prompts.md](mcp-prompts.md)。
- JSON Schema: tool input/output schema，位於 [schemas](schemas)。

OpenAPI/Swagger 不是 canonical spec。若未來需要 HTTP gateway，應從 MCP tool schema 另外產生 adapter 文件。

## Runtime Boundary

外層 runtime 負責：

- 判斷是否需要 durable memory context。
- 呼叫 `get_context`。
- 執行推理與其他 tool calls。
- 在 turn 或 conversation 完成後呼叫 `ingest_turn`。
- 管理 recent chat 或短期 conversation state。

Memory MCP 負責：

- 搜尋 `note`、`diary`、`profile_memory`。
- 回傳 compact context bundle。
- 將 interaction 轉成 candidate memory。
- 維護 chunks、embeddings、tags、links。
- 透過 daily maintenance 合併、拆分、整理 notes，並建立 diary。

## Data Stores

P0 使用 PostgreSQL + pgvector。主要資料表見 [DB.md](../DB.md)：

- `memory_items`
- `memory_chunks`
- `memory_links`
- `tags`
- `memory_item_tags`

## Transport

P0 文件不綁定 transport。實作時可先支援 MCP stdio transport；若部署需求需要 remote access，再補 streamable HTTP 或 gateway adapter。

Transport 選擇不應改變 tool name、input schema 或 result shape。

## Memory Types

```text
note
diary
profile_memory
```

這三種 memory 共用 `memory_items` 形狀，用 `type` 區分。

## Item Status

```text
candidate -> active -> archived
```

- `candidate`: turn ingestion 後尚未整理或檢視的記憶。
- `active`: 經 review 或 daily consolidation 後可作為正式 retrieval source。
- `archived`: 已過期、重複、被合併或被取代的記憶。
