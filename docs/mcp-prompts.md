# MCP Prompts

P0 沒有必要先實作 prompts。核心能力是 `get_context` 與 `ingest_turn`。

Prompts 適合在 workflow 穩定後加入，用來讓 client 或使用者明確觸發一段可重用流程。

## Candidate Prompts

### review_candidate_notes

協助使用者檢視尚未整理的 candidate notes，決定要合併、拆分、保留或 archive。

Possible arguments:

- `date`
- `tag`
- `limit`

### create_daily_diary

根據某一天的 interactions 與 candidate notes，建立 diary entry。

Possible arguments:

- `date`
- `token`

### normalize_tags

檢視低使用量、高相似度或 alias-like tags，提出合併建議。

Possible arguments:

- `limit`
- `dry_run`

## Prompt Rules

- Prompts should describe workflows, not replace tools.
- Any write action still needs route through MCP tools.
- Prompts should make review boundaries explicit when data may be merged, archived, or rewritten.
