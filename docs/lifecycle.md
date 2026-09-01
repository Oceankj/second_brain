# Personal Agent Memory Lifecycle

這份文件描述 Personal Agent Memory MCP 自己負責的生命週期。核心邊界是：本系統不負責 reasoning、不負責完整 agent loop、不負責一般工具決策；它只負責根據輸入吐出相關 durable memory，並在 interaction 結束後接收資料進行保存與整理。

## System Boundary

```mermaid
flowchart LR
  caller["User or outer agent runtime"] --> memoryMcp["Personal Agent Memory MCP"]
  memoryMcp --> durableContext["Related durable memory context"]
  durableContext --> caller

  caller -. "Reasoning, answer generation, tool decisions happen outside this system" .-> outside["Outer runtime boundary"]
```

## Durable Context Lookup Lifecycle

```mermaid
flowchart TD
  request["get_context(input, token, session_id?)"] --> validate["Validate token and request"]
  validate --> recentDiary["Load recent diary entries from last 1-2 days"]
  recentDiary --> diaryRelevant{"Diary chunk score above threshold?"}
  diaryRelevant -- "Yes" --> mergeDiary["Merge input with relevant diary context"]
  diaryRelevant -- "No" --> baseContext["Use original input as retrieval context"]

  mergeDiary --> embedQuery["Create retrieval query embedding"]
  baseContext --> embedQuery
  embedQuery --> tagHints["Find related tags by embedding"]
  tagHints --> tagCandidates["Load tagged chunks with weighted tag/chunk score"]

  embedQuery --> searchChunks["Search memory_chunks with pgvector"]
  searchChunks --> joinItems["Join matching memory_items"]
  joinItems --> seedSet["Build initial candidate set"]
  tagCandidates --> seedSet
  seedSet --> linkPolicy["Rank seeds, expand typed links, and rank linked candidates"]
  linkPolicy --> filterItems["Quota-merge, deduplicate, and filter by type, status, user scope, and limit"]
  filterItems --> logRetrieval["Insert retrieved events"]
  logRetrieval --> includeLinks{"include_links?"}

  includeLinks -- "Yes" --> loadLinks["Include selected outgoing links and backlinks"]
  includeLinks -- "No" --> compact["Build compact context bundle"]
  loadLinks --> compact

  compact --> response["Return related durable memory"]
```

Notes:

- Tags are not attached during normal durable context lookup.
- Tags are still important retrieval references: matched tags can add candidate memory items or boost ranking, but they do not need to be returned.
- Recent diary entries are checked with embedding similarity before RAG because they carry short-term life/work context that semantic search may miss.
- If recent diary is relevant, it becomes part of the retrieval context before semantic search.
- P0 links only support `references`, which can affect candidate expansion and backlinks.
- `get_context` should return relevant memory, not perform reasoning over that memory.

## Ingestion Lifecycle

```mermaid
flowchart TD
  ingest["ingest_turn(token, user_input, assistant_output, metadata)"] --> source["Validate token and build memory source"]
  source --> extract["Extract candidate memories"]
  extract --> normalizeTags["Normalize candidate tags"]

  normalizeTags --> noteCandidate["Create candidate memory_items"]
  noteCandidate --> chunk["Chunk memory item body"]
  chunk --> embed["Generate embeddings"]
  embed --> saveChunks["Insert memory_chunks"]

  normalizeTags --> findTags["Find or create tags"]
  findTags --> itemTags["Insert memory_item_tags"]

  noteCandidate --> detectLinks["Detect wikilinks or suggested references"]
  detectLinks --> saveLinks["Insert memory_links"]

  saveChunks --> done["Turn ingestion complete"]
  itemTags --> done
  saveLinks --> done
  saveLinks --> logWriteEvents["Insert created or linked events"]
  logWriteEvents --> done
```

## Daily Notes Review Lifecycle

```mermaid
flowchart TD
  trigger{"Daily notes review trigger"}
  trigger --> collect["Load today's candidate memory_items where ingest_reason is stable_fact or personal_insight"]

  collect --> updateNotes["Update notes"]
  updateNotes --> findSimilar["Find similar notes by tags, links, embedding, title, body"]
  findSimilar --> mergeOrSplit{"Merge or split needed?"}
  mergeOrSplit -- "Merge" --> merge["Merge notes and preserve provenance"]
  mergeOrSplit -- "Split" --> split["Split oversized notes into focused notes"]
  mergeOrSplit -- "No" --> keep["Keep candidate shape"]

  merge --> repairLinks["Repair and update two-way links"]
  split --> repairLinks
  keep --> repairLinks

  repairLinks --> normalize["Normalize tags"]
  normalize --> activate["Mark reviewed notes as active"]
  activate --> archive["Archive stale or superseded items when appropriate"]
  archive --> done["Daily notes review complete"]
```

## Daily Note Creation Lifecycle

```mermaid
flowchart TD
  trigger{"Daily note trigger"}
  trigger --> collect["Load today's memory_items and created events"]
  collect --> diary["Create daily note / diary entry"]
  diary --> diaryLinks["Link diary to important memory_items"]
  diaryLinks --> diaryEvents["Insert mentioned_in_diary events"]
  diaryEvents --> done["Daily note creation complete"]
```

## Profile Update Lifecycle

```mermaid
flowchart TD
  trigger{"Profile update trigger"}
  trigger --> collect["Load today's candidate memory_items where ingest_reason is user_preference"]
  collect --> updateProfile["Update canonical profile system-observed section"]
  updateProfile --> archive["Archive consumed user_preference candidates"]
  archive --> done["Profile update complete"]
```

## Memory Item Status

```mermaid
stateDiagram-v2
  [*] --> candidate: ingest_turn creates item
  candidate --> active: review or daily consolidation
  candidate --> archived: stale, duplicate, or superseded
  active --> archived: superseded by merge or no longer useful
  archived --> active: manual restore
```

## Retrieval Shape

```mermaid
sequenceDiagram
  participant Caller as User or outer runtime
  participant MCP as Memory MCP
  participant DB as PostgreSQL + pgvector

  Caller->>MCP: get_context(input, token, session_id?)
  MCP->>DB: load recent diary entries by event_date
  DB-->>MCP: recent diary candidates
  MCP->>MCP: check diary relevance and merge context if useful
  MCP->>DB: find matching tags and tagged memory_items
  MCP->>DB: vector search memory_chunks using merged retrieval context
  DB-->>MCP: tagged candidates and matching chunks
  MCP->>DB: join matching memory_items
  MCP->>DB: load typed links from top seed items for candidate expansion
  MCP->>MCP: rank linked candidates, quota-merge, and deduplicate results
  MCP->>DB: insert retrieved memory_item_events
  MCP->>DB: optionally load outgoing links and backlinks
  MCP-->>Caller: related durable memory context
```

## Write Shape

```mermaid
sequenceDiagram
  participant Caller as User or outer runtime
  participant MCP as Memory MCP
  participant DB as PostgreSQL + pgvector

  Caller->>MCP: ingest_turn(token, user_input, assistant_output, metadata)
  MCP->>MCP: extract candidate memories
  MCP->>MCP: normalize tags
  MCP->>DB: insert memory_items(status=candidate)
  MCP->>MCP: chunk body and generate embeddings
  MCP->>DB: insert memory_chunks
  MCP->>DB: find or create tags
  MCP->>DB: insert memory_item_tags
  MCP->>MCP: detect wikilinks or suggested references
  MCP->>DB: insert memory_links
  MCP->>DB: insert memory_item_events
  MCP-->>Caller: accepted ingestion summary
```
