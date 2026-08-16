# Database Schema

這份文件記錄 personal agent memory system 的第一版資料庫設計。

系統應該使用 PostgreSQL 搭配 `pgvector`。原因是這個系統同時需要 relational structure、graph-like links、tag normalization、full-text search 與 semantic search。

## P0 Tables

P0 目前聚焦在六張 tables：

- `memory_items`
- `memory_chunks`
- `memory_links`
- `tags`
- `memory_item_tags`
- `memory_item_events`

## memory_items

儲存最上層的 memory objects。

Diary entries、一般 notes、profile memories 應該共用這張 table。它們本質上都是有 identity、status、timestamps、links、tags 與 chunks 的 durable text。

使用 `type`，不要使用 `is_diary`。這樣未來可以自然擴充，不會被二元的 note/diary 分類綁住。

```sql
create type memory_item_type as enum (
  'note',
  'diary',
  'profile_memory'
);

create type memory_item_status as enum (
  'candidate',
  'active',
  'archived'
);

create table memory_items (
  id uuid primary key default gen_random_uuid(),
  type memory_item_type not null,
  title text not null,
  body text not null,
  status memory_item_status not null default 'candidate',
  event_date date,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
```

### 欄位說明

- `type`: 區分 `note`、`diary`、`profile_memory`。
- `status`: 一開始是 `candidate`；經過 review 或 daily consolidation 後變成 `active`。
- `event_date`: 主要給 diary entries 使用。一般 notes 與 profile memories 可以是 null。
- `body`: 儲存這個 memory item 的 canonical full text。

P0 先不要加入 `summary` 或 `metadata`。等 retrieval 或 provenance 真的有具體需求時再補。

## memory_chunks

儲存從 `memory_items` 產生出來、可被搜尋的 chunks。

Embeddings 應該放在 chunks 上，而不是直接放在 `memory_items` 上。原因是長 notes 與 diary entries 可能需要多個 embeddings。

```sql
create table memory_chunks (
  id uuid primary key default gen_random_uuid(),
  memory_item_id uuid not null references memory_items(id) on delete cascade,
  chunk_index integer not null,
  content text not null,
  embedding vector(1536) not null,
  token_count integer,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (memory_item_id, chunk_index)
);
```

### 欄位說明

- `chunk_index`: 保留 chunk 在 parent memory item 裡的順序。
- `content`: 實際被拿去 embedding 與 semantic search 的文字。
- `embedding`: pgvector embedding，用於 retrieval。
- `token_count`: 用於 token budgeting 與未來 re-chunking。如果尚未計算，可以是 null。

Vector dimension 應該要跟選定的 embedding model 一致。`1536` 只是 placeholder；如果 embedding model 使用不同 dimension，需要調整。

## memory_links

儲存 memory items 之間的 directed links。

Two-way links 不需要真的存兩筆。存一條 directed edge，backlinks 用 `target_id` 反查即可。

```sql
create type memory_link_type as enum (
  'references'
);

create table memory_links (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references memory_items(id) on delete cascade,
  target_id uuid not null references memory_items(id) on delete cascade,
  link_type memory_link_type not null default 'references',
  created_at timestamptz not null default now(),
  unique (source_id, target_id, link_type),
  check (source_id <> target_id)
);
```

### 欄位說明

- `source_id`: 包含 reference 的 note、diary entry 或 profile memory。
- `target_id`: 被連到的 memory item。
- `link_type`: P0 只支援 `references`，表示 source 直接提到或依賴 target。

P0 先不要加 `anchor_text` 或 `context`。它們之後可以用於精準 hover preview、highlight link 位置，以及解釋為什麼有這條 link。

### Link Type 用法

- `references`: source 直接提到或依賴 target。用於輕量 retrieval expansion 與可見 backlinks。

`expands`、`derived_from`、`same_topic`、`contradicts`、`supersedes` 先留到 P1。等 retrieval policy、maintenance workflow 或 human review 真的需要這些語意時再加入。

## tags

儲存 normalized tags。

Tags 和 links 分工不同。Tags 提供廣義分類；links 表達 memory items 之間的具體關係。

```sql
create table tags (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  description text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
```

### 欄位說明

- `name`: canonical tag name。
- `description`: 定義這個 tag 的使用邊界。可以由 LLM 產生，之後再人工調整。

P0 不加 aliases。如果未來真的需要 alias handling，應該新增獨立的 `tag_aliases` table，而不是把 aliases 存成 `text[]`。

## memory_item_tags

Memory items 與 tags 的 join table。

```sql
create table memory_item_tags (
  memory_item_id uuid not null references memory_items(id) on delete cascade,
  tag_id uuid not null references tags(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (memory_item_id, tag_id)
);
```

## memory_item_events

儲存 memory items 的 usage 與 lifecycle events。

這是未來 hot/cold ranking 的 raw fact table。P0 應該先捕捉 events，但不需要決定最終 heat algorithm。未來 ranking tables 可以從這份 event log 重新計算。

```sql
create type memory_item_event_type as enum (
  'created',
  'retrieved',
  'shown',
  'used_in_answer',
  'linked_from_new_note',
  'mentioned_in_diary',
  'manually_pinned',
  'manually_demoted',
  'archived',
  'restored'
);

create table memory_item_events (
  id uuid primary key default gen_random_uuid(),
  memory_item_id uuid not null references memory_items(id) on delete cascade,
  event_type memory_item_event_type not null,
  source text,
  session_id text,
  metadata jsonb,
  occurred_at timestamptz not null default now()
);
```

### 欄位說明

- `event_type`: 這個 memory item 發生了什麼事。
- `source`: 來源 app 或 runtime，例如 `codex`、`dify`、`claude-desktop`。
- `session_id`: optional conversation/session id，用於 grouping events。
- `metadata`: 彈性事件細節，例如 retrieval score、rank、query hash、link id 或 manual reason。

P0 不加 `heat_score` 或 `importance_score`。它們是 derived ranking values，之後應該從 event history 計算。

## P0 Retrieval Shape

典型 context retrieval 流程：

1. 根據 `event_date` 載入近期 `diary` items，通常是最近 1-2 天。
2. 判斷這些 diary entries 是否與當前 input relevant。
3. 如果 relevant，把 diary context merge 進 retrieval context。
4. 找 matching tags，並把 tagged memory items 作為 retrieval candidates 或 ranking signals。
5. 使用合併後的 retrieval context，透過 pgvector 搜尋 `memory_chunks`。
6. 將 semantic matches join 回 `memory_items`。
7. 根據 typed `memory_links` expansion 或 rerank candidates。
8. Merge candidates、deduplicate，並套用 type/status/user scope/limit。
9. 視需要加入精選 outgoing links 與 backlinks。
10. 對回傳的 memory items 寫入 `retrieved` events。
11. 回傳 durable memory context 給 caller。

Tags 是有用的 retrieval references，但一般 context retrieval 不一定要把 tags 附在最終回傳內容中。

## P0 Write Shape

典型 memory ingestion 流程：

1. 建立 `memory_items` row，並設 `status = 'candidate'`。
2. 將 `body` 切成 `memory_chunks`。
3. 替每個 chunk 產生 embeddings。
4. 找到或建立 normalized tags。
5. 寫入 `memory_item_tags`。
6. 偵測明確的 `[[wikilinks]]` 或 model-suggested references。
7. 寫入 `memory_links`。
8. 視情況寫入 `created`、`linked_from_new_note` 或 `mentioned_in_diary` events。

## Indexes

P0 應該包含常見 retrieval paths 需要的 indexes。

```sql
create index memory_items_type_idx on memory_items(type);
create index memory_items_status_idx on memory_items(status);
create index memory_items_event_date_idx on memory_items(event_date);

create index memory_chunks_item_idx on memory_chunks(memory_item_id);
create index memory_links_source_idx on memory_links(source_id);
create index memory_links_target_idx on memory_links(target_id);
create index memory_item_tags_tag_idx on memory_item_tags(tag_id);
create index memory_item_events_item_idx on memory_item_events(memory_item_id);
create index memory_item_events_type_idx on memory_item_events(event_type);
create index memory_item_events_occurred_at_idx on memory_item_events(occurred_at);
```

選定 embedding model 與 distance metric 後，再加入 pgvector index。

範例：

```sql
create index memory_chunks_embedding_idx
on memory_chunks
using hnsw (embedding vector_cosine_ops);
```
