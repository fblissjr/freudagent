# Trace Capture: Standard Operating Procedure

Last updated: 2026-07-07

Instructions for capturing reasoning traces during extraction runs. Tool-call
traces are captured automatically by the PostToolUse hook (`scripts/trace-hook.sh`).
Reasoning traces are recorded via SQL using the DuckDB MCP tools.

Keys are MD5 hashes (`keys.dimension_key()`), not sequences -- there is no
`RETURNING id` auto-increment to rely on. `fact_session.session_key` and
`fact_trace.trace_key` are `NOT NULL` with no default, so raw SQL inserts must
compute them explicitly. Replicate `dimension_key()` with DuckDB's `md5()`:
`md5(part1 || '|' || part2 || ...)` -- verified equivalent to the Python
implementation for the same inputs. `RETURNING` still works to hand the computed
key back to the caller in the same statement.

## Session lifecycle

1. **Start**: Insert a session record via `mcp__duckdb__execute_query` at the
   beginning of each run. `native_session_id` is required (`NOT NULL`) -- for a
   native run with no externally-supplied session id, generate one with
   DuckDB's `uuid()`. Record the returned `session_key` for all subsequent
   trace inserts.

   ```sql
   INSERT INTO fact_session (session_key, native_session_id, task_description,
                              task_type, agent_role, status, record_source)
   SELECT md5('native' || '|' || sid), sid, 'Extract metadata from arxiv paper',
          'extraction', 'orchestrator', 'running', 'native'
   FROM (SELECT uuid()::VARCHAR AS sid)
   RETURNING session_key
   ```

   The key recipe is `session_key = dimension_key(record_source, native_session_id)`
   -- see `skill/reference/schema.md` for the full natural-key table.

2. **Self-report reasoning** at key decision points by inserting trace records.
   `trace_key = dimension_key(session_key, depth, sequence_order, title)`:

   ```sql
   INSERT INTO fact_trace (trace_key, session_key, trace_type, depth,
                            sequence_order, title, reasoning, alternatives)
   VALUES (
     md5('<session_key>' || '|' || '0' || '|' || '0' || '|' || 'Focus on methodology first'),
     '<session_key>', 'decision_point', 0, 0, 'Focus on methodology first',
     'Section 3 is the core contribution',
     '{"options": ["methodology", "results", "full scan"], "selected": "methodology"}'
   )
   ```

   Trace types to use:
   - `decision_point` -- when choosing between alternatives
   - `insight` -- when discovering something useful
   - `dead_end` -- when a path leads nowhere
   - `path_taken` / `path_discarded` -- recording explored vs rejected paths
   - `conclusion` -- when synthesizing a final finding
   - `subagent_spawn` -- when delegating to a subagent (populate `child_session_key`)

3. **End**: Load hook-captured tool_call traces from the JSONL buffer, then
   complete the session:

   ```sql
   UPDATE fact_session
   SET status = 'completed', result = '{"raw": "...output..."}', completed_at = current_timestamp
   WHERE session_key = '<session_key>'
   ```

## What to trace (4-6 calls per run)

Focus on **observable reasoning events** that a human reviewer would find useful:

- Major decisions: "Chose methodology section over full scan because..."
- Dead ends: "Abstract lacks training hyperparameters, need appendix"
- Insights: "Paper uses custom notation -- extract definitions first"
- Alternative paths: what you considered but rejected, and why

## What NOT to trace

- Every tool call (the hook handles those automatically)
- Routine formatting or output assembly
- Internal uncertainty (only trace decisions that affect the extraction)

Full transcript capture (every message and tool call, not just self-reported
reasoning) lives in `fact_message` and `fact_tool_use` -- a different pipeline
(transcript ingestion, `record_source = transcript_ingest`) at a different grain.
This SOP is about the smaller set of human-reviewable reasoning traces in
`fact_trace`, not a replacement for full transcript capture.

## Trace fields

| Field | When to populate | Example |
|-------|-----------------|---------|
| `title` | Always (required) | "Focus on methodology first" |
| `reasoning` | When non-obvious | "Section 3 is the core contribution" |
| `alternatives` | At decision points | `{"options": ["methodology", "results"]}` |
| `outcome` | When actionable | `{"pages_read": 5, "text_length": 12400}` |
| `depth` | For nested decisions | 0 for top-level, 1+ for sub-decisions |
| `duration_ms` | When measurable | Elapsed time for this step |

## Example trace sequence

Substitute `<session_key>` with the key returned from the session-start insert.

```sql
-- decision_point: focus strategy
INSERT INTO fact_trace (trace_key, session_key, trace_type, depth, sequence_order, title, reasoning, alternatives)
VALUES (
  md5('<session_key>' || '|' || '0' || '|' || '0' || '|' || 'Focus on methodology first'),
  '<session_key>', 'decision_point', 0, 0,
  'Focus on methodology first',
  'Section 3 titled ''Model Architecture'' is the core contribution',
  '{"options": ["methodology", "results", "full scan"], "selected": "methodology"}'
);

-- dead_end: abstract insufficient
INSERT INTO fact_trace (trace_key, session_key, trace_type, depth, sequence_order, title, outcome, reasoning)
VALUES (
  md5('<session_key>' || '|' || '0' || '|' || '1' || '|' || 'Abstract lacks training hyperparameters'),
  '<session_key>', 'dead_end', 0, 1,
  'Abstract lacks training hyperparameters',
  '{"reason": "Abstract only mentions BLEU scores, not batch size/lr/epochs"}',
  'Need to look at Section 5.3 or appendix instead'
);

-- insight: notation discovery
INSERT INTO fact_trace (trace_key, session_key, trace_type, depth, sequence_order, title, reasoning)
VALUES (
  md5('<session_key>' || '|' || '0' || '|' || '2' || '|' || 'Custom notation for attention dimensions'),
  '<session_key>', 'insight', 0, 2,
  'Custom notation for attention dimensions',
  'Paper uses d_k, d_v, d_model consistently -- without notation, extracted dimensions are ambiguous'
);

-- conclusion
INSERT INTO fact_trace (trace_key, session_key, trace_type, depth, sequence_order, title, outcome)
VALUES (
  md5('<session_key>' || '|' || '0' || '|' || '3' || '|' || 'Methodology extraction complete'),
  '<session_key>', 'conclusion', 0, 3,
  'Methodology extraction complete',
  '{"fields_extracted": 8, "confidence": "high", "gaps": ["training schedule"]}'
);
```

## Querying traces

```sql
-- Full trace tree for a session
SELECT trace_key, depth, sequence_order, trace_type, title, reasoning, skill_domain
FROM fact_trace WHERE session_key = '<session_key>'
ORDER BY depth, sequence_order;

-- Recurring dead ends for a skill (via view)
SELECT * FROM v_recurring_traces
WHERE skill_key = '<skill_key>' AND trace_type = 'dead_end' AND occurrence_count >= 2
ORDER BY occurrence_count DESC;
```
