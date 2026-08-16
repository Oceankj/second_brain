# MCP Link Policy

Links are edges between memory items. They are not just display backlinks; they can shape retrieval expansion, ranking, provenance, and maintenance.

P0 stores only explicit reference links in `memory_links`:

```text
source_id -> target_id
link_type
```

Backlinks are queried by filtering `target_id`; two-way display does not require writing two rows.

## Link Types

| link_type | Meaning | Retrieval Use | Maintenance Use |
| --- | --- | --- | --- |
| `references` | Source directly mentions or depends on target. | Light expansion and visible backlinks. | Preserve when merging/splitting notes. |

Future link types such as `expands`, `derived_from`, `same_topic`, `contradicts`, and `supersedes` should wait until the retrieval or maintenance code has concrete behavior for them.

## Retrieval Rules

1. Start from seed candidates from diary relevance, tag matches, and semantic search.
2. Expand links up to `link_expansion_depth`.
3. For P0, only `references` can add neighbors to the candidate set.
4. Deduplicate after expansion.
5. Apply status, user scope, type filters, and final limit.

## Output Rules

`get_context` may use links internally even when `include_links` is false.

When `include_links` is true, return only selected links that explain or help navigate the returned items. The result should not dump the full graph.
