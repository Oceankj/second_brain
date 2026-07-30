# MCP Link Policy

Links are typed edges between memory items. They are not just display backlinks; they shape retrieval expansion, ranking, provenance, and maintenance.

P0 stores links in `memory_links`:

```text
source_id -> target_id
link_type
```

Backlinks are queried by filtering `target_id`; two-way display does not require writing two rows.

## Link Types

| link_type | Meaning | Retrieval Use | Maintenance Use |
| --- | --- | --- | --- |
| `references` | Source directly mentions or depends on target. | Light expansion and visible backlinks. | Preserve when merging/splitting notes. |
| `expands` | Target adds detail to source. | Expand when seed is relevant and deeper context is useful. | Good split signal when a note gets too broad. |
| `derived_from` | Source was created from target. | Lower-priority expansion for provenance. | Preserve source/evidence history. |
| `same_topic` | Items discuss the same area. | Ranking boost, not automatic broad expansion. | Merge candidate signal. |
| `contradicts` | Items disagree or contain conflicting claims. | Include only when one side is already relevant, so caller can see conflict. | Review signal; should not auto-merge. |
| `supersedes` | Source replaces target. | Prefer source; target is mostly provenance. | Archive or de-prioritize superseded target. |

## Retrieval Rules

1. Start from seed candidates from diary relevance, tag matches, and semantic search.
2. Expand links up to `link_expansion_depth`.
3. Apply link policy by type:
   - `references`, `expands`: can add neighbors to the candidate set.
   - `same_topic`: mostly boosts ranking; avoid flooding results.
   - `derived_from`: add only when provenance is useful or result count is low.
   - `contradicts`: add only if the source or target is already strongly relevant.
   - `supersedes`: prefer the superseding item and de-prioritize the older item.
4. Deduplicate after expansion.
5. Apply status, user scope, type filters, and final limit.

## Output Rules

`get_context` may use links internally even when `include_links` is false.

When `include_links` is true, return only selected links that explain or help navigate the returned items. The result should not dump the full graph.
