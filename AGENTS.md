# Repository Agent Instructions

## Shared memory: favor useful context

For this repository, use the personal memory MCP (`personcal_brain`, also called
second-brain) proactively. The user prefers a lower write threshold because too
little useful context has been reaching the memory system.

Write with `ingest_turn` when information could reasonably help a future agent
continue the conversation or work. Do not require every record to be a completed
task, a stable long-term fact, or knowledge already proven reusable across agents.
Useful records include:

- Meaningful intermediate progress, current blockers, and next steps.
- Approaches tried, their results, failure reasons, and directions ruled out.
- Tentative decisions and their reasons, including later changes that supersede
  earlier decisions.
- Substantive ideas, open questions, emerging preferences, and learning insights.
- Confirmed outcomes, explicit memory requests, and established preferences.

Record enough context to explain what the information concerns and why it matters.
Clearly distinguish user statements from agent suggestions, facts from hypotheses,
and completed work from plans. Preserve important limits such as unimplemented,
unverified, not deployed, or simulation only. When a decision changes, explicitly
identify which earlier decision it replaces.

Capture meaningful developments at natural checkpoints; do not wait until the
entire task is finished. Avoid storing every utterance or duplicating unchanged
records. Never store passwords, tokens, authorization codes, or other secrets;
skip pure greetings and storage acknowledgments.

Read with `get_context` when prior discussions, preferences, decisions, or history
could materially affect the work. Report a write as saved only after the MCP
confirms success, and distinguish candidate records from reviewed active memory.

These instructions govern agents working in this repository. They do not by
themselves change MCP server templates, prompts, or behavior in other repositories.
