---
name: db-query
description: Query the experiment harness DuckDB via MCP (store-ops server's read-only query tool, or a generic duckdb server). Use when inspecting skills, sources, sessions, traces, extractions, feedback, rules, findings, or proposals.
---

# db-query

Last updated: 2026-07-21

Query the FreudAgent experiment harness database via MCP.

## When to use

**Inside Claude Code — reads:** use the store-ops server's `query` tool
(`freud-schema mcp-serve`, configured in `.mcp.json` since v0.25/M16). It is
read-only by construction (single SELECT statement, parser-enforced; SHOW/
DESCRIBE/SUMMARIZE allowed). If a session is still connected to a generic
`duckdb` MCP server instead, `mcp__duckdb__execute_query` works for reads the
same way. Never shell out to the CLI while any MCP server holds the DB --
DuckDB is single-process and CLI commands fail with a lock error.

**Inside Claude Code — writes:** never raw SQL. Use the store-ops server's
write tools (`rule_add`, `skill_add`, `source_add`, `feedback_add`,
`finding_add`, `extraction_validate`/`reject`, `proposal_add`/`approve`/
`reject`, `couch_run`, `compile`, `ingest_transcripts`, `ingest_events`) --
each is a thin
wrapper over the store's one write path (validation, key recipes,
denormalization, lineage). On a generic duckdb server, use the CLI write
window instead (see CLAUDE.md's DuckDB MCP section).

**Outside Claude Code (scripts, CI, terminal):** use the `freud-schema` CLI.

Use this skill for:
- Inspecting experiment data (skills, sources, sessions, traces, extractions, feedback, rules, findings, proposals)
- Ad-hoc analysis of orchestrator runs and couch findings
- Checking schema state or table contents
- Debugging extraction output or session status
- Verifying data integrity after code changes

## How to use

Read via the store-ops `query` tool (preferred) or `mcp__duckdb__execute_query`:

```
query(sql="SELECT * FROM dim_skill WHERE status = 'active' AND is_current")
```

Keys are sha256/32 hashes (`keys.dimension_key()`: SHA-256 hexdigest truncated
to 32 chars), not sequences -- see "Key scheme" below. You should never need to
compute one by hand: the write tools and `ExperimentStore` derive keys
automatically. (The only sanctioned raw-INSERT fallback is the /couch skill's
appendix, for sessions stuck on a generic server.)

## MCP tools available

**Store-ops server (`freud-schema`, preferred -- .mcp.json):**

| Tool | Use for |
|------|---------|
| `query` | Read-only SQL: exactly one SELECT (WITH/FROM/SHOW/DESCRIBE/SUMMARIZE forms allowed); rows capped at 500. |
| `rule_add`, `skill_add` | Create entities in the NON-compiling status (inactive/draft) -- activation goes through the proposal flow. |
| `source_add`, `feedback_add`, `finding_add`, `extraction_validate`, `extraction_reject` | The corresponding store write, validated + lineage-stamped. |
| `proposal_add`, `proposal_approve`, `proposal_reject` | Evolve flow. `proposal_approve` is the human approval gate -- NEVER allowlist it. |
| `couch_run`, `compile`, `ingest_transcripts`, `ingest_events` | Pipeline operations in-session. |

**Generic `duckdb` server (legacy/alternative, reads only):**

| Tool | Use for |
|------|---------|
| `mcp__duckdb__execute_query` | SELECT queries. Do not use for writes -- see above. |
| `mcp__duckdb__list_tables` / `list_columns` | Schema inspection. |

## Schema: Meta-Harness Model (Kimball-style, schema version 7 / v0.26+)

### Key scheme

Every key is `dimension_key(*natural_key_parts)` -- SHA-256 hex of pipe-joined
parts truncated to 32 chars (`keys.KEY_ALGORITHM = "sha256/32"`), `NULL` mapped
to `"-1"`. No sequences. Replicate in raw SQL with
`substring(CAST(sha256(part1 || '|' || part2) AS VARCHAR), 1, 32)`. The four
SCD-2 dims' natural keys LEAD with `tenant_id` (skill = tenant|domain|task_type,
rule = tenant|name, source = tenant|content_path). `meta_key_algorithm` records
the active scheme. Full natural-key recipe per table is in
`skill/reference/schema.md`.

### SCD-2 dimensions (versioned reference data)

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `dim_skill` | Declarative instructions | tenant_id, domain, task_type, version, status, origin, content |
| `dim_source` | Raw artifacts to process | tenant_id, content_path, media_type, source_hash, status |
| `dim_rule` | Constraints (global or per-domain) | tenant_id, name, scope, domain, priority, content, status |
| `dim_sampling_config` | Prior run sampling settings | tenant_id, domain, task_type, strategy, max_samples |

All four carry `effective_from`, `effective_to`, `is_current`, `hash_diff` --
query current rows with `WHERE is_current`. An attribute change closes the old
row and inserts a new one; rows never mutate.

### Registry dimensions (append-only, no SCD-2)

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `dim_project` | Conformed project dimension | project_path, project_name |
| `dim_tenant` | Tenant registry (default seeded at init) | tenant_id, display_name |
| `dim_facet_type` | Behavioral facet registry | facet_id, prompt_version, method, output_type |
| `dim_finding_type` | Open finding-type vocabulary | finding_type, detection_method |
| `dim_event_type` | Open event-type vocabulary (M5) | event_type, schema_hint |

`dim_finding_type` validates `fact_finding.finding_type` in the store layer --
that column has no CHECK constraint, by design (new finding types are rows, not
enum edits). `dim_event_type` validates `fact_event.event_type` the same way.

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
| `fact_event` | Generic event grain (M5, non-transcript sources) | stream_key, native_event_id, event_type, occurred_at, payload |

Every fact table carries a lineage envelope: `tenant_key` (denormalized
`dim_tenant` reference), `record_source` (CHECK-constrained: native,
transcript_ingest, history_jsonl, event_ingest, derived) and `etl_run_id`
(joins `meta_load_log`).

### Analytical views (replace complex store queries)

| View | Purpose |
|------|---------|
| `v_feedback_by_skill` | Correction counts by skill + correction_type |
| `v_feedback_fields` | Field names mentioned in corrections by skill |
| `v_recurring_traces` | Traces that recur across sessions for a skill |
| `v_recurring_trace_feedback` | Trace feedback patterns across sessions |
| `v_skill_feedback_patterns` | Skills with feedback above threshold |
| `v_session_feedback_count` | Feedback count per session (for HIGH_FEEDBACK sampling) |
| `v_retry_loops` | Identical-input tool-call loops per session (couch detector base) |
| `v_tool_error_clusters` | Per-project tool error rates (couch detector base) |
| `v_interruption_hotspots` | Mid-turn user interruptions per project (couch detector base) |
| `v_permission_friction` | Permission denials per project+tool (couch detector base) |

Couch views carry NO thresholds -- couch.py's detectors own them; consume the
views through the store's `query_*` methods, never re-derive thresholds.

### Operational

| Table | Purpose |
|-------|---------|
| `meta_schema_version` | Schema DDL changelog (version, description). Currently version 7. NOT a migration ledger -- schema changes reset + re-ingest (see CLAUDE.md policy). |
| `meta_key_algorithm` | Active key scheme (sha256/32), seeded at init. |
| `meta_load_log` | One row per ingest/couch/compile run: etl_run_id, operation, status, row counts |

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
| meta_load_log.status | running, completed, failed (shares `SessionStatus`) |
| record_source (every dim_*/fact_*/meta_* table) | native, transcript_ingest, history_jsonl, event_ingest, derived |

`fact_finding.finding_type` and `fact_event.event_type` have NO CHECK
constraint -- open vocabulary, registry-validated against `dim_finding_type`
and `dim_event_type` respectively.

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

**Events for one stream, in order (fact_event, M5's generic event grain):**
```sql
SELECT event_type, occurred_at, actor, content_text
FROM fact_event WHERE stream_key = ? ORDER BY occurred_at
```

## Design notes

- No FK constraints (DuckDB can't CASCADE anyway). Existence validation done in the store layer.
- Fact tables carry denormalized dimension attributes (skill_domain, source_path, etc.) populated at insert time. This eliminates fact-to-fact joins.
- Views replace N+1 query patterns and complex Python aggregation code.
- SCD-2 dimensions (`dim_skill`, `dim_source`, `dim_rule`, `dim_sampling_config`) never mutate -- an attribute change closes the current row and inserts a new one. Always filter `WHERE is_current` unless you specifically want history.
- JSON columns (metadata, context_loaded, token_usage, result, output, correction, alternatives, outcome, activation_conditions, sampled_session_keys, tool_input, value_json, target_natural_key) are queryable with DuckDB's JSON functions: `output->>'$.raw'`, `json_extract(metadata, '$.key')`
- No UNIQUE constraints -- entity identity and version monotonicity are enforced by the store layer (`insert_skill` rejects a version that doesn't exceed the current one), not the DDL.
- The store-ops MCP server (`freud-schema mcp-serve`, .mcp.json) holds the single connection: reads via its parser-enforced read-only `query` tool, writes via its store-op tools only. A generic duckdb server, if connected instead, has raw read-write access -- treat it as read-only by convention and use the CLI write window for writes.
- To get the DDL as standalone SQL: `freud-schema db ddl` (this is the one CLI DB command that does NOT open a connection)
