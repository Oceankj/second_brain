# MCP Tools

P0 先實作兩個 tools：`get_context` 與 `ingest_turn`。

Runtime input contracts live in `src/personal_agent_memory/contracts/`. The JSON Schema files linked below are documentation snapshots for external readers and should be regenerated from the runtime contracts if they become machine-read by clients.

## get_context

根據使用者目前輸入，搜尋 durable memory stores，回傳精簡、可引用、可追溯的 context bundle。

```text
get_context(input, token, session_id?)
  -> load recent diary entries from the last 1-2 days
  -> check whether recent diary is relevant to input
  -> merge relevant diary context into retrieval context
  -> find related tags as retrieval signals
  -> run semantic retrieval over notes, diary, and profile_memory
  -> expand and rank candidates through typed links
  -> merge and deduplicate results
  -> log retrieval events for returned memory items
  -> enforce max_context_chars on compact_context
  -> return related durable memory context
```

Input schema:

- [get_context.input.schema.json](schemas/get_context.input.schema.json)

Output schema:

- [get_context.output.schema.json](schemas/get_context.output.schema.json)

### Behavior

- 預設搜尋 `note`、`diary`、`profile_memory`。
- Caller 必須提供 top-level `token`；server 會用 token 驗證並解析 user identity。
- Retrieval 會先用原始 input embedding 搜尋最近 N 天的 `diary` chunks，將分數達到 `memory.json` 門檻的 diary 視為 relevant。
- 若 caller 未提供 `diary_lookback_days`，server 使用 `memory.json` 的 `retrieval.recent_diary_lookback_days` 作為預設；caller 仍可逐次 override。
- 若 recent diary 相關，先把 diary context 併入 retrieval context，再進 semantic retrieval。
- Semantic retrieval 以 `memory_chunks` 的 pgvector search 為主，再 join 回 `memory_items`。
- Tag retrieval 會用 retrieval query embedding 搜尋 `tags.embedding`，再從超過 `retrieval.tag_retrieval_min_score` 的 tags 載入 tagged chunks。
- Tagged chunk score 使用 `tag_score * tag_retrieval_tag_weight + chunk_score * (1 - tag_retrieval_tag_weight)`；預設 tag 佔 0.4、chunk 佔 0.6。
- Tags 不在一般 `get_context` output 中 attach；tag match 只作為 retrieval signal 補候選 items。
- P0 links 只支援 `references`；server 會依內部 retrieval policy 從 top seed items 的 outgoing links 與 backlinks 找 linked candidates，詳見 [mcp-links.md](mcp-links.md)。
- Linked candidates 會先在自己的 lane 內 ranking，最多取 `retrieval.link_expansion_max_items` 則，再與 seed items 做 quota merge。
- Recent diary、tag candidates、semantic matches 與 link-expanded candidates 會合併、去重，再套用 status/user scope/limit。
- 回傳內容應該是相關 durable memory context，不負責 reasoning 或 answer generation。
- P0 會記錄 returned memory items 的 `retrieved` events，作為未來 hot/cold ranking 的 raw signals。
- 若 `include_chunks` 為 true，可以回傳命中的 chunk；預設應避免過量 token。
- `max_context_chars` 是 `compact_context` 的 server-side hard budget，預設 6000。超過時會截斷 `compact_context` 並回傳 `context_truncated=true`。
- `items` 保留結構化 provenance；外層 agent 應優先把 `compact_context` 放進 prompt，而不是直接 dump `items`。

### Side Effects

`get_context` 不會修改 memory content，但會寫入 `memory_item_events` 的 usage log。

### Example Call

```json
{
  "input": "我接下來要繼續整理 personal memory MCP 的資料模型",
  "token": "<memory-default-user-token>",
  "session_id": "codex-2026-07-30",
  "max_context_chars": 6000
}
```

## ingest_turn

把一次 interaction 轉成可保存的 memory source，建立帶有 `ingest_reason` 的 candidate memory item。

```text
ingest_turn(token, user_input, assistant_output, metadata)
  -> evaluate ingest policy from metadata
  -> extract candidate memories
  -> normalize tags
  -> create candidate memory_items
  -> store caller-provided ingest_reason on memory_items
  -> create memory_chunks and embeddings
  -> find or create tags
  -> create memory_item_tags
  -> detect links
  -> create memory_links
  -> log created / linked events
```

Input schema:

- [ingest_turn.input.schema.json](schemas/ingest_turn.input.schema.json)

Output schema:

- [ingest_turn.output.schema.json](schemas/ingest_turn.output.schema.json)

### Behavior

- Memory source 是完整 interaction，不只是 assistant output。
- Caller 必須提供 top-level `token`；server 會用 token 驗證並決定寫入的 `user_id`。
- P0 要求 caller 提供 `metadata.ingest_reason`，避免每輪 raw output 都無腦寫入 durable memory。
- 若不想寫入 durable memory，caller 不應呼叫 `ingest_turn`。
- 缺少 `metadata.ingest_reason` 是 invalid input，不會建立 memory item。
- 允許的 `ingest_reason` 是 `task_completed`、`explicit_memory_request`、`user_preference`、`stable_fact`、`personal_insight`、`decision`、`stable_artifact`、`manual_import`。
- P0 使用 deterministic routing：`ingest_turn` 不推論 reason；caller 提供 `metadata.ingest_reason` 後，server 將它寫入 `memory_items.ingest_reason`。
- 目前所有 accepted turns 都先建立 `note` candidate。`user_preference`、`stable_fact`、`personal_insight` 的後續用途由 daily maintenance tasks 根據 `ingest_reason` 判斷。
- `personal_insight` 表示使用者對自身思考、工作方式、需求或狀態的自我觀察；P0 先作為帶時間脈絡的 `note` candidate。
- P0 可以先產生 `candidate` memory item，不急著在主流程合併到既有 note。
- Canonical profile 不由 `ingest_turn` 直接更新；profile update task 會讀取當天 `status=candidate` 且 `ingest_reason=user_preference` 的 items，採用後再把 raw candidates archived。
- Daily diary 不依賴 enqueue queue；daily maintenance 直接讀取指定日期產生的 `memory_items` 與 `created` events，作為建立 diary entry 的素材。
- 當 `ingest_turn` 因明確 `[[wikilink]]` 建立新的 `memory_links` 時，會在被連到的 target item 上寫入 `linked_from_new_note` event，作為 audit trail 與未來 ranking signal。

### Side Effects

可能寫入或更新：

- `memory_items`
- `memory_chunks`
- `tags`
- `memory_item_tags`
- `memory_links`
- `memory_item_events`

不直接建立或更新 canonical profile。

### Example Call

```json
{
  "token": "<memory-default-user-token>",
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
