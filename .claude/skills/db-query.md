---
name: db-query
description: Query the experiment harness DuckDB via the duckdb MCP server. Use when inspecting skills, sources, sessions, traces, extractions, feedback, or rules data.
---

# db-query

Query the FreudAgent experiment harness database using the `duckdb` MCP server tools.

## When to use

**Inside Claude Code (this session):** Always use `mcp__duckdb__execute_query` for
all database reads AND writes. Never shell out to `freud-schema` CLI for DB
operations -- DuckDB is single-process, and the MCP server already holds the
connection. CLI commands will fail with a lock error.

**Outside Claude Code (scripts, CI, terminal):** Use the `freud-schema` CLI.

Use this skill for:
- Inspecting experiment data (skills, sources, sessions, traces, extractions, feedback, rules)
- Ad-hoc analysis of orchestrator runs
- Checking schema state or table contents
- Debugging extraction output or session status
- Verifying data integrity after code changes
- **All INSERT/UPDATE/DELETE operations** during Claude Code sessions

## How to use

The primary interface is `mcp__duckdb__execute_query`. Pass any valid DuckDB SQL:

```
mcp__duckdb__execute_query(sql="SELECT * FROM dim_skill WHERE status = 'active'")
mcp__duckdb__execute_query(sql="INSERT INTO dim_rule (scope, content, priority) VALUES ('global', 'Rule text', 10)")
```

## MCP tools available

The `duckdb` MCP server (mcp-server-motherduck) exposes these tools:

| Tool | Use for |
|------|---------|
| `mcp__duckdb__execute_query` | Run any DuckDB SQL (SELECT, INSERT, UPDATE, DELETE, DDL). Pass `sql` parameter. |
| `mcp__duckdb__list_tables` | Show all tables in the database. |
| `mcp__duckdb__list_columns` | Show columns of a specific table. Pass `table` parameter. |

## Schema: Dimensional Model (Kimball-style)

### Dimension tables (reference data)

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `dim_skill` | Declarative instructions | domain, task_type, version, status, origin, content |
| `dim_source` | Raw artifacts to process | content_path, media_type, status |
| `dim_rule` | Constraints (global or per-domain) | scope, domain, priority, content, status |
| `dim_sampling_config` | Prior run sampling settings | domain, task_type, strategy, max_samples |

### Fact tables (event data with denormalized attributes)

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `fact_session` | Logged agent executions | task_type, agent_role, status, skill_id, skill_domain, skill_task_type |
| `fact_trace` | Reasoning trace tree nodes | session_id, trace_type, depth, title, skill_id, skill_domain |
| `fact_extraction` | Structured output from runs | source_id, source_path, skill_id, skill_domain, validation_status |
| `fact_feedback` | Human corrections on extractions | extraction_id, correction_type, skill_id, skill_domain, source_id |
| `fact_trace_feedback` | Human feedback on traces | trace_id, feedback_type, trace_type, trace_title, skill_id |

### Analytical views (replace complex store queries)

| View | Purpose |
|------|---------|
| `v_feedback_by_skill` | Correction counts by skill + correction_type |
| `v_feedback_fields` | Field names mentioned in corrections by skill |
| `v_recurring_traces` | Traces that recur across sessions for a skill |
| `v_recurring_trace_feedback` | Trace feedback patterns across sessions |
| `v_skill_feedback_patterns` | Skills with feedback above threshold |
| `v_session_feedback_count` | Feedback count per session (for HIGH_FEEDBACK sampling) |

### Operational

| Table | Purpose |
|-------|---------|
| `meta_schema_version` | Schema version tracking (version, description) |

## Enum values (enforced by CHECK constraints)

| Column | Valid values |
|--------|-------------|
| dim_skill.status | draft, active, deprecated |
| dim_skill.origin | human_authored, data_derived |
| dim_source.status | active, archived |
| fact_session.status | running, completed, failed |
| fact_session.agent_role | orchestrator, subagent |
| fact_trace.trace_type | decision_point, path_taken, path_discarded, insight, dead_end, subagent_spawn, tool_call, conclusion |
| fact_extraction.validation_status | pending, validated, rejected |
| fact_trace_feedback.feedback_type | path_correction, positive_signal, dead_end_confirmation, reasoning_error |
| fact_feedback.correction_type | field_mapping, wrong_value, missing_field, false_positive |
| dim_rule.scope | global, domain-specific |
| dim_rule.status | active, inactive |
| dim_sampling_config.strategy | recent, random, stratified_outcome, stratified_feedback, high_feedback |

## Common queries

**Recent sessions with denormalized skill info:**
```sql
SELECT id, agent_role, task_type, status, skill_domain, skill_task_type, model_used, created_at
FROM fact_session ORDER BY created_at DESC LIMIT 20
```

**Active skills:**
```sql
SELECT id, domain, task_type, version, status, origin
FROM dim_skill WHERE status = 'active'
```

**Trace tree for a session:**
```sql
SELECT id, depth, sequence_order, trace_type, title, reasoning, skill_domain
FROM fact_trace WHERE session_id = ?
ORDER BY depth, sequence_order
```

**Extractions with denormalized source info (no join needed):**
```sql
SELECT id, validation_status, confidence, source_path, skill_domain, skill_task_type
FROM fact_extraction
WHERE validation_status = 'pending'
```

**Feedback flywheel signal (via view):**
```sql
SELECT * FROM v_feedback_by_skill WHERE skill_id = ?
```

**Recurring dead ends (via view, no join needed):**
```sql
SELECT * FROM v_recurring_traces
WHERE skill_id = ? AND trace_type = 'dead_end' AND occurrence_count >= 2
ORDER BY occurrence_count DESC
```

**Skills needing attention (via view):**
```sql
SELECT DISTINCT skill_id, skill_domain, skill_task_type, total_feedback
FROM v_skill_feedback_patterns WHERE total_feedback >= 3
```

## Design notes

- No FK constraints (DuckDB can't CASCADE anyway). Existence validation done in the store layer.
- Fact tables carry denormalized dimension attributes (skill_domain, source_path, etc.) populated at insert time. This eliminates fact-to-fact joins.
- Views replace N+1 query patterns and complex Python aggregation code.
- JSON columns (metadata, context_loaded, token_usage, result, output, correction, alternatives, outcome, activation_conditions, sampled_session_ids) are queryable with DuckDB's JSON functions: `output->>'$.raw'`, `json_extract(metadata, '$.key')`
- UNIQUE constraint on dim_skill `(domain, task_type, version)` prevents duplicate skill versions
- The MCP server connects to `data/freudagent.duckdb` with read-write access
- To get the DDL as standalone SQL: `freud-schema db ddl` (this is the one CLI DB command that does NOT open a connection)
