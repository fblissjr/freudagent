# Reasoning traces: what to capture

Last updated: 2026-07-21

## Status: derivation works, nothing drives it automatically

Read this before anything else in this file.

What exists:

- `fact_message.thinking_text` keeps each turn's reasoning verbatim, captured at
  ingest for every run (schema v10).
- `reasoning_list` (MCP) / `store.list_reasoning_messages()` returns the messages
  whose reasoning has not been derived yet -- the queue.
- `trace_add` (MCP) / `ops.trace_add()` writes one typed trace, wrapped in its
  own `load_run`, with `record_source = derived`.
- Every derived trace carries `source_message_key`, so the structured claim can
  be checked against the reasoning it came from.

What does not exist: any pass that runs this over the warehouse on its own. Today
someone has to ask. That is the remaining half.

### Derived, not self-reported -- and the difference is the design

These write the same table, so it is easy to collapse them. Do not.

Self-reporting is an agent narrating its own reasoning while it works. It exists
only when someone turned it on, it degrades whenever reporting is not
load-bearing for the agent's own task, and it is missing for exactly the run you
later wanted to look at. The design rules this out: the trail is meant to be
"recorded by default rather than switched on when someone suspects a problem,
because you never suspect in time".

Derivation is a later pass over `thinking_text`, which was captured whether
anyone was curious or not. It is independent of the run it describes, it covers
everything captured, and it can be redone tomorrow with a better prompt without
losing anything -- re-deriving the same message converges on the same rows
rather than duplicating them, because the key is
`(source_message_key, sequence_order)` and not the title. A model will not word a
title the same way twice; a title-keyed row would duplicate the corpus on every
pass while looking like it found new material.

So `scripts/trace-hook.sh` stays unwired. It captures `tool_call` events the
agent emits about itself, which is the self-reporting shape.

### How to run a derivation pass

1. `reasoning_list` for the queue (optionally scoped to one session).
2. Read each `thinking_text` and decide what it actually contains -- often
   nothing worth structuring, which is a valid answer.
3. `trace_add` per step found, with `sequence_order` placing them within the
   turn, `source_message_key` naming the evidence, and `reasoning` carrying the
   why rather than restating the title.

Earlier versions of this file gave raw-SQL insert recipes. They were removed
rather than repaired: they computed keys with `md5()`, and keys have been
sha256/32 since v0.23, so an agent following them wrote rows keyed against
nothing the store computes -- silently, with no error at write time. Writes go
through store ops.

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
