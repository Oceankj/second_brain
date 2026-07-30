# MCP Resources

Resources 是 client 可讀取的 durable memory context。P0 的核心能力先放在 tools；resources 先定義設計方向，避免 retrieval tool 與 future read-only views 混在一起。

## P0 Position

P0 不要求一定實作 resources。若只實作 `get_context` 與 `ingest_turn`，系統仍然是有效的 MCP-first server。

當以下需求出現時，再把 resources 提升成正式 primitive：

- Client 需要瀏覽 memory item，而不是只讓 model retrieval。
- Client 需要直接讀取某天 diary、某個 note、某個 tag。
- Client UI 想呈現 backlinks、outgoing links 或 tag collections。

## Candidate Resources

### memory://items/{id}

讀取單一 memory item。

Returns:

- memory item body
- type/status/event date
- tags
- outgoing links
- backlinks

### memory://diary/{date}

讀取某一天的 diary entry。

Parameters:

- `date`: ISO date, for example `2026-07-30`

Returns:

- diary memory item
- related notes
- links

### memory://tags

列出 normalized tags。

Returns:

- tag name
- description
- usage count if available

### memory://tags/{name}/items

讀取某個 tag 底下的 memory items。

Returns:

- compact item list
- item status
- item type

## Resource Rules

- Resources should be read-only.
- Writes should go through tools.
- Resource content should stay compact enough for client preview.
- Large bodies can expose ranges or chunks later, but P0 can keep full item reads simple.
