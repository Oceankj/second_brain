# Database Schema

This document records the first-pass database design for the personal agent memory system.

The system should use PostgreSQL with `pgvector`, because the data model needs relational structure, graph-like links, tag normalization, full-text search, and semantic search in the same database.

## P0 Tables

P0 focuses on six tables:

- `memory_items`
- `memory_chunks`
- `memory_links`
- `tags`
- `memory_item_tags`
- `memory_item_events`

## memory_items

Stores the top-level memory objects.

Diary entries, normal notes, and profile memories should share this table. They are the same core object shape: durable text with identity, status, timestamps, links, tags, and chunks.

Use `type` instead of `is_diary` so the model can grow beyond a binary note/diary split.

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

### Field Notes

- `type`: distinguishes `note`, `diary`, and `profile_memory`.
- `status`: starts as `candidate`; becomes `active` after review or daily consolidation.
- `event_date`: mainly used by diary entries. Normal notes and profile memories can leave it null.
- `body`: stores the canonical full text of the item.

Do not add `summary` or `metadata` in P0. They can be added later when there is a concrete retrieval or provenance need.

## memory_chunks

Stores searchable chunks derived from `memory_items`.

Embeddings should live on chunks, not directly on `memory_items`, because long notes and diary entries may need multiple embeddings.

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

### Field Notes

- `chunk_index`: preserves chunk order inside the parent memory item.
- `content`: the exact text embedded for semantic search.
- `embedding`: pgvector embedding for retrieval.
- `token_count`: useful for budgeting and future re-chunking, but can be null if not calculated yet.

The vector dimension should match the embedding model. `1536` is a placeholder and should be changed if the selected embedding model uses a different dimension.

## memory_links

Stores directed links between memory items.

Two-way links do not need two rows. Store one directed edge, then query backlinks by filtering `target_id`.

```sql
create type memory_link_type as enum (
  'references',
  'expands',
  'derived_from',
  'same_topic',
  'contradicts',
  'supersedes'
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

### Field Notes

- `source_id`: the note, diary entry, or profile memory that contains the reference.
- `target_id`: the linked memory item.
- `link_type`: describes how retrieval and maintenance should use the edge.

Do not add `anchor_text` or `context` in P0. Those are useful later for precise hover previews, highlighted link positions, and explaining why a link exists.

### Link Type Usage

- `references`: source directly mentions or depends on target. Use for light retrieval expansion and visible backlinks.
- `expands`: target adds detail to source. Use when the seed item is relevant and the caller may need deeper context.
- `derived_from`: source was created from target. Use for provenance and lower-priority expansion back to evidence.
- `same_topic`: items discuss the same area. Use as a ranking boost and maintenance merge signal, but avoid blindly returning every neighbor.
- `contradicts`: items disagree or supersede each other's claims. Use to surface conflict only when one side is already relevant.
- `supersedes`: source replaces target. Prefer the superseding item during retrieval; keep target mostly for provenance/backlinks.

## tags

Stores normalized tags.

Tags are separate from links. Tags provide broad classification; links express concrete relationships between memory items.

```sql
create table tags (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  description text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
```

### Field Notes

- `name`: canonical tag name.
- `description`: defines the tag boundary. This can be generated by an LLM and edited later.

Do not add aliases in P0. If alias handling becomes necessary, add a separate `tag_aliases` table instead of storing aliases in a `text[]` column.

## memory_item_tags

Join table between memory items and tags.

```sql
create table memory_item_tags (
  memory_item_id uuid not null references memory_items(id) on delete cascade,
  tag_id uuid not null references tags(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (memory_item_id, tag_id)
);
```

## memory_item_events

Stores usage and lifecycle events for memory items.

This is the raw fact table for future hot/cold ranking. P0 should capture events, but it does not need to decide the final heat algorithm yet. Future ranking tables can be recalculated from this log.

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

### Field Notes

- `event_type`: what happened to this memory item.
- `source`: source app or runtime, such as `codex`, `dify`, or `claude-desktop`.
- `session_id`: optional conversation/session id for grouping events.
- `metadata`: flexible event details, such as retrieval score, rank, query hash, link id, or manual reason.

Do not add `heat_score` or `importance_score` in P0. Those are derived ranking values and should be computed later from event history.

## P0 Retrieval Shape

Typical context retrieval should:

1. Load recent `diary` items by `event_date`, usually the last 1-2 days.
2. Check whether those diary entries are relevant to the current input.
3. If relevant, merge diary context into the retrieval context.
4. Find matching tags and load tagged memory items as retrieval candidates or ranking signals.
5. Search `memory_chunks` with pgvector using the merged retrieval context.
6. Join semantic matches back to `memory_items`.
7. Expand or rerank candidates according to typed `memory_links`.
8. Merge candidates, deduplicate, and apply type/status/user scope/limit.
9. Optionally include selected outgoing links and backlinks from `memory_links`.
10. Insert `retrieved` events for returned memory items.
11. Return related durable memory context to the caller.

Tags are useful retrieval references, but normal context retrieval does not need to attach tags to the returned context.

## P0 Write Shape

Typical memory ingestion should:

1. Create a `memory_items` row with `status = 'candidate'`.
2. Chunk the body into `memory_chunks`.
3. Generate embeddings for each chunk.
4. Find or create normalized tags.
5. Insert `memory_item_tags`.
6. Detect explicit `[[wikilinks]]` or model-suggested references.
7. Insert `memory_links`.
8. Insert `created`, `linked_from_new_note`, or `mentioned_in_diary` events where applicable.

## Indexes

P0 should include indexes for common retrieval paths.

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

Add the pgvector index after choosing the embedding model and distance metric.

Example:

```sql
create index memory_chunks_embedding_idx
on memory_chunks
using hnsw (embedding vector_cosine_ops);
```
