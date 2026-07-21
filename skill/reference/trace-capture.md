# Reasoning traces: what to capture

Last updated: 2026-07-21

## Status: there is no write path yet

Read this before anything else in this file. Reasoning traces are a schema and a
read surface with nothing writing to them.

- `fact_trace` exists and `TraceType` carries all eight types.
- `store.insert_trace()` has no callers outside `tests/`.
- There is no `trace add` CLI command and no store-op MCP tool for traces.
- Transcript ingest records messages and tool calls only. It reduces thinking
  blocks to a boolean and keeps no content.
- `scripts/trace-hook.sh` captures `tool_call` events to a JSONL buffer, needs
  opt-in hook configuration, and has no loader to hand that buffer to.

Earlier versions of this file gave raw-SQL insert recipes. They have been removed
rather than repaired. They computed keys with `md5()`, and keys have been
sha256/32 since v0.23 — an agent following them wrote rows keyed against nothing
the store computes, with no error at write time, silently breaking idempotent
re-ingest and prefix resolution. They also routed writes through a generic DuckDB
MCP server, which the store-ops server replaced. Writes go through store ops; see
`.claude/skills/db-query.md`.

What remains here is the part that stays true regardless of mechanism: what a
reasoning trace should contain. Treat it as the spec for the capture path when it
gets built, not as instructions you can follow today.

## Why this matters more than its size suggests

A person can only give useful feedback on something they can evaluate, and
evaluating an outcome alone does not tell you where it went wrong. The reasoning
trail is what makes a run interpretable rather than merely scored: which path was
chosen, what was considered and rejected, where the approach changed. That is
also what makes deviation legible — an agent that departs from the guidance it
was given, and gets a better result, is a process-improvement signal rather than
a defect, but only if the departure was recorded.

## What to trace

Observable reasoning events a human reviewer would find useful. Four to six per
run is the right order of magnitude.

- major decisions, with the alternatives that were live at the time
- dead ends, and what ruled them out
- insights that changed the approach
- paths considered and rejected, and why

## What not to trace

- every tool call — that is a different grain, captured separately
- routine formatting or output assembly
- internal uncertainty that did not affect what happened

## Trace types

| Type | Use when |
|---|---|
| `decision_point` | choosing between alternatives |
| `insight` | discovering something that changes the approach |
| `dead_end` | a path leads nowhere |
| `path_taken` / `path_discarded` | recording explored against rejected paths |
| `conclusion` | synthesizing a final finding |
| `subagent_spawn` | delegating to a subagent, with `child_session_key` populated |

Note that `_SIGNAL_TRACE_TYPES` in `orchestrator.py` admits only
`decision_point`, `dead_end`, `insight`, `conclusion` and `subagent_spawn` into
prior-run context. `tool_call`, `path_taken` and `path_discarded` are recorded
but not replayed into a system prompt.

## Fields

| Field | When to populate | Example |
|---|---|---|
| `title` | always, required | "Focus on methodology first" |
| `reasoning` | when the choice is non-obvious | "Section 3 is the core contribution" |
| `alternatives` | at decision points | `{"options": ["methodology", "results"]}` |
| `outcome` | when actionable | `{"pages_read": 5, "text_length": 12400}` |
| `depth` | for nested decisions | 0 for top level, 1+ for sub-decisions |
| `duration_ms` | when measurable | elapsed time for this step |

## This is not transcript capture

Full transcript capture — every message and every tool call — lives in
`fact_message` and `fact_tool_use`, written by transcript ingestion with
`record_source = transcript_ingest`. That is a different pipeline at a different
grain, and it works today.

`fact_trace` is the smaller set of human-reviewable reasoning events. It is not a
replacement for transcript capture, and transcript capture is not a substitute
for it: the transcript records what happened, not why.

## Reading traces

These are read-only and valid today, for whatever rows exist.

```sql
-- full trace tree for a session
SELECT trace_key, depth, sequence_order, trace_type, title, reasoning, skill_domain
FROM fact_trace WHERE session_key = '<session_key>'
ORDER BY depth, sequence_order;

-- recurring dead ends for a skill
SELECT * FROM v_recurring_traces
WHERE skill_key = '<skill_key>' AND trace_type = 'dead_end' AND occurrence_count >= 2
ORDER BY occurrence_count DESC;
```
