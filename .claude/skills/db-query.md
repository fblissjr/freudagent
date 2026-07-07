---
name: db-query
description: Query the experiment harness DuckDB via the duckdb MCP server. Use when inspecting skills, sources, sessions, traces, extractions, feedback, or rules data.
---

# db-query

Last updated: 2026-07-07

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
mcp__duckdb__execute_query(sql="SELECT * FROM dim_skill WHERE status = 'active' AND is_current")
mcp__duckdb__execute_query(sql="INSERT INTO dim_rule (rule_key, name, scope, content, priority, hash_diff) VALUES (md5('global-rule'), 'global-rule', 'global', 'Rule text', 10, 'x')")
```

Keys are MD5 hashes (`keys.dimension_key()`), not sequences -- see "Key scheme"
below. Raw SQL inserts must compute the key themselves; `ExperimentStore` does
this automatically.

## MCP tools available

The `duckdb` MCP server (mcp-server-motherduck) exposes these tools:

| Tool | Use for |
|------|---------|
| `mcp__duckdb__execute_query` | Run any DuckDB SQL (SELECT, INSERT, UPDATE, DELETE, DDL). Pass `sql` parameter. |
| `mcp__duckdb__list_tables` | Show all tables in the database. |
| `mcp__duckdb__list_columns` | Show columns of a specific table. Pass `table` parameter. |

## Schema: Meta-Harness Model (Kimball-style, v0.17.0)

### Key scheme

Every key is `dimension_key(*natural_key_parts)` -- MD5 hex of pipe-joined parts,
`NULL` mapped to `"-1"`. No sequences. Replicate in raw SQL with
`md5(part1 || '|' || part2)`. Full natural-key recipe per table is in
`skill/reference/schema.md`.

### SCD-2 dimensions (versioned reference data)

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `dim_skill` | Declarative instructions | domain, task_type, version, status, origin, content |
| `dim_source` | Raw artifacts to process | content_path, media_type, status |
| `dim_rule` | Constraints (global or per-domain) | name, scope, domain, priority, content, status |
| `dim_sampling_config` | Prior run sampling settings | domain, task_type, strategy, max_samples |

All four carry `effective_from`, `effective_to`, `is_current`, `hash_diff` --
query current rows with `WHERE is_current`. An attribute change closes the old
row and inserts a new one; rows never mutate.

### Registry dimensions (append-only, no SCD-2)

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `dim_project` | Conformed project dimension | project_path, project_name |
| `dim_facet_type` | Behavioral facet registry | facet_id, prompt_version, method, output_type |
| `dim_finding_type` | Open finding-type vocabulary | finding_type, detection_method |

`dim_finding_type` validates `fact_finding.finding_type` in the store layer --
that column has no CHECK constraint, by design (new finding types are rows, not
enum edits).

### Fact tables (event data with denormalized attributes)

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `fact_session` | Logged agent executions (native + ingested) | native_session_id, project_key, agent_role, status, skill_key, skill_domain |
| `fact_trace` | Reasoning trace tree nodes | session_key, trace_type, depth, title, skill_key, skill_domain |
| `fact_extraction` | Structured output from runs | source_key, source_path, skill_key, skill_domain, validation_status |
| `fact_feedback` | Human corrections on extractions | extraction_key, correction_type, skill_key, skill_domain, source_key |
| `fact_trace_feedback` | Human feedback on traces | trace_key, feedback_type, trace_type, trace_title, skill_key |
| `fact_message` | Transcript messages (full grain) | session_key, role, entry_uuid, sequence_num |
| `fact_tool_use` | Transcript tool_use blocks | session_key, tool_use_id, tool_name, is_error |
| `fact_session_facets` | Behavioral facet values (EAV) | session_key, facet_id, prompt_version |
| `fact_finding` | Detected patterns (couch output) | finding_type, scope, project_key, summary |
| `fact_proposal` | Proposed dimension changes (evolve output) | target_dimension, target_key, status |

Every fact table carries a lineage envelope: `record_source` (CHECK-constrained:
native, transcript_ingest, history_jsonl, derived) and `etl_run_id` (joins
`meta_load_log`).

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
| `meta_schema_version` | Schema version tracking (version, description). Currently version 4. |
| `meta_load_log` | One row per ingest/compile run: etl_run_id, operation, status, row counts |

## Enum values (enforced by CHECK constraints)

| Column | Valid values |
|--------|-------------|
| dim_skill.status | draft, active, deprecated |
| dim_skill.origin | human_authored, data_derived |
| dim_source.status | active, archived |
| dim_rule.scope | global, domain-specific |
| dim_rule.status | active, inactive |
| dim_sampling_config.strategy | recent, random, stratified_outcome, stratified_feedback, high_feedback |
| dim_sampling_config.status | active, inactive |
| dim_facet_type.method | computed, regex, llm, cluster |
| dim_facet_type.output_type | text, numeric, bool, json |
| dim_finding_type.detection_method | sql, llm, hybrid |
| fact_session.status | running, completed, failed |
| fact_session.agent_role | orchestrator, subagent |
| fact_trace.trace_type | decision_point, path_taken, path_discarded, insight, dead_end, subagent_spawn, tool_call, conclusion |
| fact_extraction.validation_status | pending, validated, rejected |
| fact_trace_feedback.feedback_type | path_correction, positive_signal, dead_end_confirmation, reasoning_error |
| fact_feedback.correction_type | field_mapping, wrong_value, missing_field, false_positive |
| fact_message.role | user, assistant |
| fact_finding.scope | project, global |
| fact_proposal.target_dimension | dim_skill, dim_rule, dim_sampling_config |
| fact_proposal.status | pending, approved, rejected |
| record_source (every dim_*/fact_*/meta_* table) | native, transcript_ingest, history_jsonl, derived |

`fact_finding.finding_type` has NO CHECK constraint -- open vocabulary,
registry-validated against `dim_finding_type`.

## Common queries

**Recent sessions with denormalized skill info:**
```sql
SELECT session_key, agent_role, task_type, status, skill_domain, skill_task_type, model_used, created_at
FROM fact_session ORDER BY created_at DESC LIMIT 20
```

**Active skills (current row only):**
```sql
SELECT skill_key, domain, task_type, version, status, origin
FROM dim_skill WHERE status = 'active' AND is_current
```

**Trace tree for a session:**
```sql
SELECT trace_key, depth, sequence_order, trace_type, title, reasoning, skill_domain
FROM fact_trace WHERE session_key = ?
ORDER BY depth, sequence_order
```

**Extractions with denormalized source info (no join needed):**
```sql
SELECT extraction_key, validation_status, confidence, source_path, skill_domain, skill_task_type
FROM fact_extraction
WHERE validation_status = 'pending'
```

**Feedback flywheel signal (via view):**
```sql
SELECT * FROM v_feedback_by_skill WHERE skill_key = ?
```

**Recurring dead ends (via view, no join needed):**
```sql
SELECT * FROM v_recurring_traces
WHERE skill_key = ? AND trace_type = 'dead_end' AND occurrence_count >= 2
ORDER BY occurrence_count DESC
```

**Skills needing attention (via view):**
```sql
SELECT DISTINCT skill_key, skill_domain, skill_task_type, total_feedback
FROM v_skill_feedback_patterns WHERE total_feedback >= 3
```

**Transcript messages for a session:**
```sql
SELECT role, sequence_num, content_text, has_thinking
FROM fact_message WHERE session_key = ? ORDER BY sequence_num
```

**Pending proposals awaiting review:**
```sql
SELECT proposal_key, target_dimension, proposed_version, status
FROM fact_proposal WHERE status = 'pending'
```

## Design notes

- No FK constraints (DuckDB can't CASCADE anyway). Existence validation done in the store layer.
- Fact tables carry denormalized dimension attributes (skill_domain, source_path, etc.) populated at insert time. This eliminates fact-to-fact joins.
- Views replace N+1 query patterns and complex Python aggregation code.
- SCD-2 dimensions (`dim_skill`, `dim_source`, `dim_rule`, `dim_sampling_config`) never mutate -- an attribute change closes the current row and inserts a new one. Always filter `WHERE is_current` unless you specifically want history.
- JSON columns (metadata, context_loaded, token_usage, result, output, correction, alternatives, outcome, activation_conditions, sampled_session_keys, tool_input, value_json, target_natural_key) are queryable with DuckDB's JSON functions: `output->>'$.raw'`, `json_extract(metadata, '$.key')`
- No UNIQUE constraints -- entity identity and version monotonicity are enforced by the store layer (`insert_skill` rejects a version that doesn't exceed the current one), not the DDL.
- The MCP server connects to `data/freudagent.duckdb` with read-write access
- To get the DDL as standalone SQL: `freud-schema db ddl` (this is the one CLI DB command that does NOT open a connection)
