# Trace Capture: Standard Operating Procedure

Last updated: 2026-03-18

Instructions for capturing reasoning traces during extraction runs. Tool-call
traces are captured automatically by the PostToolUse hook (`scripts/trace-hook.sh`).
Reasoning traces are recorded via SQL using the DuckDB MCP tools.

## Session lifecycle

1. **Start**: Insert a session record via `mcp__duckdb__execute_query` at the
   beginning of each run. Record the returned `id` for all subsequent trace inserts.

   ```sql
   INSERT INTO fact_session (task_description, task_type, agent_role, status)
   VALUES ('Extract metadata from arxiv paper', 'extraction', 'orchestrator', 'running')
   RETURNING id
   ```

2. **Self-report reasoning** at key decision points by inserting trace records:

   ```sql
   INSERT INTO fact_trace (session_id, trace_type, depth, sequence_order, title, reasoning, alternatives)
   VALUES (?, 'decision_point', 0, 0, 'Focus on methodology first',
           'Section 3 is the core contribution',
           '{"options": ["methodology", "results", "full scan"], "selected": "methodology"}')
   ```

   Trace types to use:
   - `decision_point` -- when choosing between alternatives
   - `insight` -- when discovering something useful
   - `dead_end` -- when a path leads nowhere
   - `path_taken` / `path_discarded` -- recording explored vs rejected paths
   - `conclusion` -- when synthesizing a final finding
   - `subagent_spawn` -- when delegating to a subagent (populate `child_session_id`)

3. **End**: Load hook-captured tool_call traces from the JSONL buffer
   (`bulk_import` via CLI if running outside Claude Code), then complete the session:

   ```sql
   UPDATE fact_session
   SET status = 'completed', result = '{"raw": "...output..."}', completed_at = current_timestamp
   WHERE id = ?
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

```sql
-- decision_point: focus strategy
INSERT INTO fact_trace (session_id, trace_type, depth, sequence_order, title, reasoning, alternatives)
VALUES (1, 'decision_point', 0, 0,
  'Focus on methodology first',
  'Section 3 titled ''Model Architecture'' is the core contribution',
  '{"options": ["methodology", "results", "full scan"], "selected": "methodology"}');

-- dead_end: abstract insufficient
INSERT INTO fact_trace (session_id, trace_type, depth, sequence_order, title, outcome, reasoning)
VALUES (1, 'dead_end', 0, 1,
  'Abstract lacks training hyperparameters',
  '{"reason": "Abstract only mentions BLEU scores, not batch size/lr/epochs"}',
  'Need to look at Section 5.3 or appendix instead');

-- insight: notation discovery
INSERT INTO fact_trace (session_id, trace_type, depth, sequence_order, title, reasoning)
VALUES (1, 'insight', 0, 2,
  'Custom notation for attention dimensions',
  'Paper uses d_k, d_v, d_model consistently -- without notation, extracted dimensions are ambiguous');

-- conclusion
INSERT INTO fact_trace (session_id, trace_type, depth, sequence_order, title, outcome)
VALUES (1, 'conclusion', 0, 3,
  'Methodology extraction complete',
  '{"fields_extracted": 8, "confidence": "high", "gaps": ["training schedule"]}');
```

## Querying traces

```sql
-- Full trace tree for a session
SELECT id, depth, sequence_order, trace_type, title, reasoning, skill_domain
FROM fact_trace WHERE session_id = ?
ORDER BY depth, sequence_order;

-- Recurring dead ends for a skill (via view)
SELECT * FROM v_recurring_traces
WHERE skill_id = ? AND trace_type = 'dead_end' AND occurrence_count >= 2
ORDER BY occurrence_count DESC;
```
