# TODO

Ideas below are intentionally not P0. They are useful, but the first version should stay small enough to build and test.

## Schema Ideas

- Add `summary` to `memory_items` for quick previews and retrieval reranking.
- Add `metadata jsonb` to `memory_items` once provenance or source-specific fields are concrete.
- Add `memory_sources` to track source app, conversation id, turn ids, and raw evidence.
- Add `anchor_text` and `context` to `memory_links` for precise link previews and highlighted references.
- Add `tag_aliases` as a separate table if similar tags start appearing repeatedly.
- Add `confidence` to `memory_item_tags` if tag assignment needs ranking or review.
- Add `memory_item_stats` or `memory_item_rankings` as a derived rollup/cache for hot/cold memory signals.

Example:

```sql
create table memory_item_stats (
  memory_item_id uuid primary key references memory_items(id) on delete cascade,
  retrieval_count integer not null default 0,
  used_count integer not null default 0,
  linked_count integer not null default 0,
  last_retrieved_at timestamptz,
  last_used_at timestamptz,
  heat_score numeric not null default 0,
  importance_score numeric not null default 0,
  algorithm_version text not null default 'v0',
  calculated_at timestamptz not null default now(),
  features jsonb,
  updated_at timestamptz not null default now()
);
```

## Hot/Cold Memory Ideas

- Keep `type` for memory kind: `note`, `diary`, `profile_memory`.
- Track hot/cold as operational ranking metadata, not as note type.
- Use `memory_item_events` as the source of truth for future hot/cold scoring.
- Separate `heat_score` from `importance_score`.
- `heat_score` should represent recent activity and decay over time.
- `importance_score` should represent longer-term importance, manual pinning, or high-confidence system judgment.
- Avoid rich-get-richer loops where retrieved notes become hotter only because they were retrieved.
- Weight `retrieved` lower than stronger signals like `used_in_answer`, `linked_from_new_note`, `mentioned_in_diary`, or `manually_pinned`.

## Retrieval Ideas

- Combine pgvector semantic search with PostgreSQL full-text search.
- Add reranking after chunk retrieval.
- Return backlinks and outgoing links as part of the context bundle.
- Add source/provenance snippets when returning memory context.
- Add recency weighting for diary entries.
- Add profile memory priority weighting.
- Use `heat_score` and `importance_score` as retrieval ranking references.
- Consider a ranking formula that combines semantic score, diary context boost, tag match boost, typed link boost, heat boost, importance boost, and staleness penalty.

## Maintenance Jobs

- Normalize tags during daily tasks.
- Merge highly similar candidate notes.
- Split notes that exceed the chosen length or complexity limit.
- Repair links after note merge or split.
- Generate daily diary entries from the day's interactions.
- Mark candidate notes as `active` after consolidation.
- Archive stale or superseded notes.
- Update memory heat by decaying old `heat_score`, adding recent usage signals, boosting notes linked from recent diary, and cooling notes not used recently.

## Product Decisions To Revisit

- Decide whether `create notes` should run per turn or once per conversation.
- Decide note length limits: token count, character count, or semantic section count.
- Decide how many repeated signals are needed before updating `profile_memory`.
- Decide which tag operations need user confirmation.
- Decide whether raw conversation logs are needed as `conversation_events`.
- Decide which events count as hot/cold signals and their weights.
- Decide whether `importance_score` can be automatically assigned, manually pinned, or both.
