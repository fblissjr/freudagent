# /derive-traces -- structure captured reasoning into typed traces

Last updated: 2026-07-21

Ingest keeps each turn's reasoning verbatim in `fact_message.thinking_text`
(schema v10). This pass reads that reasoning and turns it into typed
`fact_trace` rows -- decision points, dead ends, insights, conclusions -- that
later steps can aggregate and a person can judge.

Like `/couch`, this is the harness doing judgment the library cannot. The queue
and the write path are store-ops tools; you are the intelligence between them.
There is no code loop that calls a model, by the same rule that keeps model
calls out of the couch's SQL layer: orchestration is the harness's job.

## Derivation, not self-reporting

This is the one thing to hold onto. You are reading reasoning that was already
captured, for every run, whether anyone was curious at the time or not. You are
NOT asking an agent to narrate a run as it happens.

The difference is the whole reason this pass exists. A self-reported trail is
present only when someone remembered to turn it on, thins out whenever reporting
is not load-bearing for the agent's own task, and is absent for exactly the run
you later wanted to inspect. A derived trail is none of those things: it covers
everything captured, it is independent of the run it describes, and it can be
redone tomorrow with a better prompt.

So work only from `reasoning_list`. Do not prompt a live agent to produce traces
about its current session.

## Workflow

1. **Pull the queue.** `reasoning_list` returns messages whose reasoning has not
   been derived yet (the default), so the pass runs incrementally over a
   warehouse that keeps growing:

   ```
   reasoning_list(limit=50)                       # everything pending
   reasoning_list(session_key=<key>, limit=50)    # one session
   ```

   Each row is `{message_key, session_key, sequence_num, occurred_at,
   thinking_text}`.

2. **Read each `thinking_text` and decide what it actually contains.** Often the
   honest answer is nothing worth structuring -- a turn that just did the obvious
   thing has no decision point. Deriving a trace from it would be invention, the
   same failure the design warns about for forced task breakdown. Skip it.

   When a turn does carry structure, it usually carries more than one step: a
   dead end tried first, then the decision that followed.

3. **Judge in scoped subagents** for a large queue (tree topology, a batch of
   messages per subagent). Each subagent returns, per message, the list of steps
   it found: a `trace_type`, a one-line `title`, and the `reasoning` (the why,
   not a restatement of the title).

4. **Write each step back** with `trace_add`:

   ```
   trace_add(
       session_key=<session_key>,
       source_message_key=<message_key>,   # required: names the evidence
       trace_type="decision_point",        # or dead_end, insight, conclusion, ...
       title="Chose the narrow fix over the refactor",
       sequence_order=0,                   # 0,1,2... to place several steps in one turn
       reasoning="refactor was out of scope for the ticket",
   )
   ```

   The tool wraps its own `meta_load_log` row (`operation = 'trace_derive'`),
   writes `record_source = derived`, and validates that
   `source_message_key` exists. Nothing to do by hand.

   `trace_type` is one of: `decision_point`, `path_taken`, `path_discarded`,
   `insight`, `dead_end`, `subagent_spawn`, `tool_call`, `conclusion`.

## Re-running is safe

A derived trace keys on `(source_message_key, sequence_order)`, not on the
title. Re-run the pass with a better prompt and it converges on the same rows
instead of duplicating -- you will not word a title identically twice, and a
title-keyed row would duplicate the whole corpus on every pass while looking
like it found new material. So it is always safe to re-derive; improving the
prompt does not mean cleaning up after the old one.

## Privacy rules (non-negotiable)

`thinking_text` is the most sensitive column in the warehouse: unrehearsed, and
never written for an audience. It stays in the gitignored DB. What you derive
from it must be clean by construction, because traces can feed later steps that
compile to committed files:

- `title` and `reasoning` describe the shape of the decision, they do not quote
  the reasoning. "Chose the narrow fix over the refactor" -- not the model's
  words.
- No absolute paths, usernames, machine names, URLs, or secrets in any field.
  The evidence is reachable through `source_message_key`; a reviewer with DB
  access can always drill down to the raw reasoning.
- If a step cannot be described without identifying content, do not derive it.

## What this does not do

It does not run itself. Someone -- a person, or a scheduled agent -- has to start
a pass. Wiring a recurring driver (read the queue on a cadence, judge, write
back) is the remaining piece, and it belongs in the harness, not the library.
