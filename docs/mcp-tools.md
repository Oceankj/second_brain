# MCP Tools

P0 先實作兩個 tools：`get_context` 與 `ingest_turn`。

## get_context

根據使用者目前輸入，搜尋 durable memory stores，回傳精簡、可引用、可追溯的 context bundle。

```text
get_context(input, user_id, session_id?)
  -> load recent diary entries from the last 1-2 days
  -> check whether recent diary is relevant to input
  -> merge relevant diary context into retrieval context
  -> find related tags as retrieval signals
  -> run semantic retrieval over notes, diary, and profile_memory
  -> expand and rank candidates through typed links
  -> merge and deduplicate results
  -> log retrieval events for returned memory items
  -> optionally include outgoing links and backlinks
  -> enforce max_context_chars on compact_context
  -> return related durable memory context
```

Input schema:

- [get_context.input.schema.json](schemas/get_context.input.schema.json)

Output schema:

- [get_context.output.schema.json](schemas/get_context.output.schema.json)

### Behavior

- 預設搜尋 `note`、`diary`、`profile_memory`。
- Retrieval 會先載入最近 1-2 天的 `diary`，判斷是否與當前 input 相關。
- 若 recent diary 相關，先把 diary context 併入 retrieval context，再進 semantic retrieval。
- Semantic retrieval 以 `memory_chunks` 的 pgvector search 為主，再 join 回 `memory_items`。
- Tags 不在一般 `get_context` output 中 attach；但 tag match 是重要 retrieval signal，可以補候選 items 或提升排名。
- P0 links 只支援 `references`，可用於 candidate expansion 與 backlinks，詳見 [mcp-links.md](mcp-links.md)。
- Recent diary、tag candidates、semantic matches 與 link-expanded candidates 需要合併、去重，再套用 status/user scope/limit。
- 回傳內容應該是相關 durable memory context，不負責 reasoning 或 answer generation。
- P0 會記錄 returned memory items 的 `retrieved` events，作為未來 hot/cold ranking 的 raw signals。
- 若 `include_links` 為 true，回傳 outgoing links 與 backlinks。
- 若 `include_chunks` 為 true，可以回傳命中的 chunk；預設應避免過量 token。
- `max_context_chars` 是 `compact_context` 的 server-side hard budget，預設 6000。超過時會截斷 `compact_context` 並回傳 `context_truncated=true`。
- `items` 保留結構化 provenance；外層 agent 應優先把 `compact_context` 放進 prompt，而不是直接 dump `items`。

### Side Effects

`get_context` 不會修改 memory content，但會寫入 `memory_item_events` 的 usage log。

### Example Call

```json
{
  "input": "我接下來要繼續整理 personal memory MCP 的資料模型",
  "user_id": "user-local",
  "session_id": "codex-2026-07-30",
  "diary_lookback_days": 2,
  "link_expansion_depth": 1,
  "max_context_chars": 6000,
  "limit": 10
}
```

## ingest_turn

把一次 interaction 轉成可保存的 memory source，再由系統判斷是否建立 note、diary material 或更新 profile memory。

```text
ingest_turn(user_input, assistant_output, metadata)
  -> evaluate ingest policy from metadata
  -> skip without writes when policy says this turn is not durable memory
  -> extract candidate memories
  -> normalize tags
  -> create candidate memory_items
  -> create memory_chunks and embeddings
  -> find or create tags
  -> create memory_item_tags
  -> detect links
  -> create memory_links
  -> log created / linked / diary mention events
  -> update profile_memory when stable
  -> enqueue diary material
```

Input schema:

- [ingest_turn.input.schema.json](schemas/ingest_turn.input.schema.json)

Output schema:

- [ingest_turn.output.schema.json](schemas/ingest_turn.output.schema.json)

### Behavior

- Memory source 是完整 interaction，不只是 assistant output。
- P0 要求 caller 提供 `metadata.ingest_reason`，避免每輪 raw output 都無腦寫入 durable memory。
- 若 `metadata.skip_memory=true`，或缺少 `metadata.ingest_reason`，`ingest_turn` 會回傳 `status=skipped` 並且不寫 DB。
- 允許的 `ingest_reason` 是 `task_completed`、`explicit_memory_request`、`user_preference`、`stable_fact`、`decision`、`stable_artifact`、`manual_import`。
- P0 可以先產生 `candidate` memory item，不急著在主流程合併到既有 note。
- Profile memory 只有在 evidence 足夠穩定時才更新。
- Diary material 可以先進入每日整理佇列，由 daily maintenance 建立 diary entry。

### Side Effects

可能寫入或更新：

- `memory_items`
- `memory_chunks`
- `tags`
- `memory_item_tags`
- `memory_links`
- `memory_item_events`

也可能 enqueue diary material，或建立/更新 `profile_memory`。

### Example Call

```json
{
  "user_input": "幫我整理一版 MCP-first 文件",
  "assistant_output": "已建立 mcp-server、mcp-tools、resources、prompts 與 schemas",
  "metadata": {
    "timestamp": "2026-07-30T13:45:00+08:00",
    "source": "codex",
    "app": "Codex Desktop",
    "session_id": "codex-2026-07-30",
    "ingest_reason": "task_completed",
    "tags": ["personal-memory", "mcp"]
  }
}
```
