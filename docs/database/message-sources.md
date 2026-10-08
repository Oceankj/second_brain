# Role-separated source notes

Implemented as an additive storage migration and a new `ingest_messages` API.
There is no `turn_id`. A conversation is scoped by authenticated user, `source`,
and `session_id`. A message has a stable `source_message_id`; caller-supplied
`sequence` is optional and is never inferred from insertion time.

## Schema comparison

| Concern | Legacy ingest_turn | New ingest_messages |
| --- | --- | --- |
| Source unit | One combined user/assistant body | One message per candidate note |
| Role | Embedded in body | user or assistant field |
| Record kind | New legacy writes: source/mixed; historical rows: unknown | source |
| Identity | No message deduplication | Unique user/source/session/message ID |
| Reply | No explicit relationship | replies_to, either role to either role |
| Classification | ingest_reason (why saved) | Separate content_kinds array (what it contains) |
| Atomicity | Existing legacy behavior | Whole batch, chunks, tags, events, links commit together |
| Retry | May create duplicates | Identical normalized payload reuses row; changed payload conflicts |

New columns on `memory_items`: record_kind, role, source, session_id,
source_message_id, sequence, source_timestamp, content_kinds, ingest_fingerprint.
The fingerprint is an internal retry check, never returned as public note content.
It covers the original message including reply target, timestamp, tags and supplied
classifications. Later classification of a stored row does not change its ingest fingerprint.
Source timestamps must include a time zone. Stored source text is exactly the submitted
body: the caller may supply a summary, so this is not a claim of verbatim conversation capture.

`content_kinds` permits any combination of event, thought, intention, including [].
There are no role-specific restrictions. It is not a replacement for ingest_reason.
Ingestion stores supplied classifications without invoking an LLM. Diary preparation
separately produces advisory classifications, described below.

`record_kind`: source / derived / unknown. Role on a derived item is null. Newly
created diaries and reviewed notes are derived. Reviewed notes inherit the union
of their sources' content kinds. Original source bodies are retained on archive.

## Relations

- replies_to: reply -> earlier source, same owner/source/session. Both role directions work.
- derived_from: derived note/diary -> evidence it used.
- references: general reference, including links to replacement notes.

Only ordinary references propagate onto replacement notes. Conversation links stay
on their original sources. Existing references are not globally reinterpreted.
SQL guards reject cross-user links, invalid conversation links and reply cycles.
Application imports serialize per conversation and reject cyclic batches.

## API

Available as authenticated MCP HTTP `ingest_messages` (memory:write), stdio
`ingest_messages` (token argument), and POST `/memory/messages` (Bearer token).

```json
{
  "source": "codex",
  "session_id": "conversation-123",
  "messages": [
    {
      "source_message_id": "a1",
      "role": "assistant",
      "body": "建議採用方案 A。",
      "timestamp": "2026-10-03T09:00:00-07:00",
      "sequence": 1,
      "ingest_reason": "decision"
    },
    {
      "source_message_id": "u2",
      "role": "user",
      "body": "好，就這樣做。",
      "timestamp": "2026-10-03T09:01:00-07:00",
      "sequence": 2,
      "reply_to_message_id": "a1",
      "ingest_reason": "decision",
      "content_kinds": ["thought", "intention"]
    }
  ]
}
```

A batch accepts 1–50 messages, including single-role batches and reverse input order.
Reply targets must exist in this batch or already exist in the same conversation.
Unknown targets fail the whole batch (REST 422); changed retries return 409. A replay
returns the existing item, including its current lifecycle status, not a new candidate.
`created_count` reports newly inserted rows; `links` reports newly inserted links.
A concurrent identical call can still incur embedding cost before discovering the replay.

## Review and retrieval

Role metadata survives vector/tag retrieval and is included in compact context.
Candidate review and diary generation load reply ancestors (including archived sources)
as read-only context. Ancestors are not extra candidates and are not new events for
the diary date. Explicit reply IDs are included with the evidence. Ancestors are bounded
at 50; oversized context fails explicitly. Independent diary generation now rejects
over-budget evidence rather than truncating qualifications. Diary preparation uses the extractive pipeline described below; model-proposed
classifications remain semantically unverified.

## Rollout and compatibility

1. Back up the database before schema deployment.
2. Apply migrations in file order. 006 adds link enum values and must commit before
   new values are used. 007 adds columns/indexes/guards and identifies existing diaries
   and candidate-review outputs as derived. Neither migration splits old bodies.
3. Deploy the matching server code. Queries now require the new columns.
4. Move callers to ingest_messages and provide stable IDs. Existing ingest_turn callers
   continue to create one mixed source note; they do not gain deduplication automatically.
5. Verify an identical new-API retry has created_count=0; verify a user reply can point
   to an assistant source; check source role is present in retrieved context.

Output schemas gain source metadata and two additional link enum values. Consumers
with closed schemas must update validators. The old input shape and one-item behavior
remain supported. No model is used to guess/split historical sources or infer reply links.

For rollback, disable new-message writers and restore the previous application while
retaining additive columns/data. Do not drop columns or enum values containing new
sources; old consumers must tolerate new link values, or remain stopped until updated.
A pre-deployment backup is the full rollback option, but restoring it loses subsequent
writes: export those writes first. No production migration is run by development tests.

## Extractive diary preparation (extractive-v1)

Both diary entry points now use the same `prepare_diary` pipeline. Each source is
classified independently; explicit reply ancestors are supplied only as context.
The model returns block IDs, zero or more content kinds, and keep/omit suggestions.
It does not generate diary prose. Original source sections are rendered in their
original language with an attribution label. There is no final whole-day LLM rewrite.

The first version deliberately retains every substantive source section. A model's
omit suggestion is recorded but overridden: schema-valid JSON does not prove a
semantic omission safe. Only exact storage receipts and standalone save requests
matched by deterministic rules are excluded. Legacy envelopes are split only when
there is one recognizable User/Assistant delimiter; explicit role fields take precedence.

Preview responses include `preparation` (replacing the old `summary_prompt` field):
source hashes, original Python string offsets, source text, proposed classifications,
effective dispositions, excluded ranges, reply-context IDs and validation status.
Classification status `structure_valid` means only schema and ID coverage passed;
`semantic_validation` remains `not_performed`. Classifications are advisory and are
not written back to source notes or user profiles. No classification restricts roles.

Invalid model output, provider failures, or a source exceeding the per-call character
budget retain the complete original section with a specific fallback status. No
truncation or automatic retry is performed. If all sources are bookkeeping, standalone
diary creation returns skipped/no_substantive_content; review creates no empty diary.

Created diary event metadata stores the preparation version and evidence mapping
without copying the source bodies. Token usage records each actual classification call
as diary_classification; an oversized source performs no model call. This increases
call count and may increase latency/cost compared with one daily generation call.
This is a provenance-preserving extractive review, not a polished narrative summary.
Candidate note merge/split generation remains a separate, existing model operation.

## Selective work summaries (selective-summary-v2)

The classifier now proposes presentation=work_report or verbatim. Operational reports
can be shortened to one or two sentences (180 characters maximum, plus preserved scope clauses); personal material
remains an attributed original excerpt. Personal ingest reasons (user_preference,
personal_insight, stable_fact, explicit_memory_request) prevent accidental compression.
Routing is content-based, not restricted to one speaker role.

A work summary keeps the result, principal decision and completion boundaries while
omitting paths, IDs, test counts and implementation mechanics. It cites one or more
valid evidence blocks; it need not cite a request omitted in favor of the result.
The original blocks, offsets and hashes remain in the preparation report. Unknown
classification labels are reported as unrecognized_kinds and excluded from actual kinds.
Missing/duplicate block IDs in the classification plan still fail validation.

A separate model call checks factual support and scope. Rejected, malformed, oversized,
or failed summaries fall back to the original excerpts. A successful check is explicitly
labeled model_reviewed, with semantic_validation=model_review_only: the same model's
review is not independent proof of correctness. No classification is written to source notes.
No whole-day rewrite follows; each work source is summarized independently.

Usage stages: diary_classification, diary_work_summary, diary_work_review. Each source
can therefore incur three calls; personal sources require only classification. Preview
and saved event metadata record the selected presentation and compression/fallback status.

Explicit non-execution clauses recognized by deterministic rules (for example,
"No application submitted or fit evaluation performed.") are appended verbatim if absent
from the short summary. This protects known forms independently of the model reviewer;
it is not an exhaustive detector of all qualifications. English scope clauses may remain
English. Summaries containing job IDs or code paths fall back. Work summaries retain the source
language to avoid mistranslating English product names. Incidental job IDs are removed
only from compression input; original evidence remains untouched.

Summary generation now needs only the summary text; source block IDs default to the
current source's blocks and are bound by code. Optional returned IDs are validated.
One bounded repair call is allowed for malformed or overlong summary JSON; subsequent
failure falls back. These repair calls are also recorded as diary_work_summary. No
unbounded retry loop or whole-day rewrite is used.
