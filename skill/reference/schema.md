# DuckDB Schema Reference

Last updated: 2026-03-18

Full schema for the FreudAgent experiment harness (v0.16.0 dimensional model).
Use the `duckdb` MCP tools for ad-hoc queries. See `.claude/skills/db-query.md`
for common query patterns and enum values.

## Design Principles

- **No FK constraints.** DuckDB cannot CASCADE, so existence validation runs in
  the store layer via `_require()`. Orphaned IDs are impossible in practice because
  all writes go through `ExperimentStore`.
- **Denormalized fact tables.** Fact tables carry dimension attributes (skill_domain,
  source_path, etc.) at insert time. Eliminates fact-to-fact joins.
- **Analytical views.** 6 views replace complex aggregation queries and N+1 patterns.

## Dimension Tables (reference data)

### dim_skill
Declarative instructions loaded at runtime. One active version per domain/task_type pair.

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| domain | VARCHAR NOT NULL | e.g., "insurance", "arxiv" |
| task_type | VARCHAR NOT NULL | e.g., "extraction", "validation" |
| version | INTEGER DEFAULT 1 | Incremented on skill evolution |
| content | VARCHAR NOT NULL | Markdown instructions |
| metadata | JSON | Optional structured config |
| parent_skill_id | INTEGER | Links derived skills to their parent |
| status | VARCHAR | draft, active, deprecated |
| origin | VARCHAR | human_authored, data_derived |
| activation_conditions | JSON | Optional conditions for derived skills |

UNIQUE constraint on `(domain, task_type, version)`.

### dim_source
Raw artifacts to process (file paths, MIME types).

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| content_path | VARCHAR NOT NULL | File path or object store reference |
| media_type | VARCHAR NOT NULL | MIME type (application/pdf, text/plain) |
| metadata | JSON | Optional domain metadata |
| source_hash | VARCHAR | Content fingerprint for dedup |
| status | VARCHAR | active, archived |

### dim_rule
Constraints applied globally or per-domain, priority-ordered.

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| scope | VARCHAR | global, domain-specific |
| domain | VARCHAR | NULL for global rules |
| priority | INTEGER DEFAULT 0 | Higher = loaded first |
| content | VARCHAR NOT NULL | Rule text (markdown) |
| status | VARCHAR | active, inactive |

### dim_sampling_config
Prior run sampling settings for pattern detection.

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| domain | VARCHAR | Skill domain (NULL for global configs) |
| task_type | VARCHAR | Skill task type (NULL for global configs) |
| strategy | VARCHAR | recent, random, stratified_outcome, stratified_feedback, high_feedback |
| max_samples | INTEGER | Sample count limit |

## Fact Tables (event data with denormalized attributes)

### fact_session
Logged agent executions (orchestrator and subagent).

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| task_description | VARCHAR NOT NULL | Human-readable description |
| task_type | VARCHAR NOT NULL | Matches skill task_type |
| parent_session_id | INTEGER | Tree structure (no FK constraint) |
| agent_role | VARCHAR | orchestrator, subagent |
| skill_id | INTEGER | Which skill was used |
| skill_domain | VARCHAR | Denormalized from dim_skill at insert |
| skill_task_type | VARCHAR | Denormalized from dim_skill at insert |
| skill_version | INTEGER | Denormalized from dim_skill at insert |
| context_loaded | JSON | What data was assembled |
| model_used | VARCHAR | Provider model name |
| token_usage | JSON | {input_tokens, output_tokens} |
| status | VARCHAR | running, completed, failed |
| result | JSON | Output + metadata |
| sampled_session_ids | JSON | IDs used for pattern sampling |

### fact_trace
Reasoning trace tree nodes within a session.

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| session_id | INTEGER NOT NULL | Parent session (no FK constraint) |
| trace_type | VARCHAR | decision_point, path_taken, path_discarded, insight, dead_end, subagent_spawn, tool_call, conclusion |
| depth | INTEGER DEFAULT 0 | Tree depth (0 = top-level) |
| sequence_order | INTEGER DEFAULT 0 | Order within depth |
| parent_trace_id | INTEGER | Tree structure (NULL for top-level) |
| title | VARCHAR NOT NULL | Short description |
| content | VARCHAR | Extended description or body text |
| reasoning | VARCHAR | Explanation (when non-obvious) |
| alternatives | JSON | Options considered |
| outcome | JSON | Result of this trace node |
| duration_ms | INTEGER | Elapsed time |
| child_session_id | INTEGER | Subagent session spawned |
| skill_id | INTEGER | Denormalized from session at insert |
| skill_domain | VARCHAR | Denormalized from session at insert |
| skill_task_type | VARCHAR | Denormalized from session at insert |

### fact_extraction
Structured output from processing a source with a skill.

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| source_id | INTEGER | What was processed |
| skill_id | INTEGER | What instructions were used |
| session_id | INTEGER | Which execution produced this |
| source_path | VARCHAR | Denormalized from dim_source at insert |
| source_media_type | VARCHAR | Denormalized from dim_source at insert |
| skill_domain | VARCHAR | Denormalized from dim_skill at insert |
| skill_task_type | VARCHAR | Denormalized from dim_skill at insert |
| skill_version | INTEGER | Denormalized from dim_skill at insert |
| output | JSON NOT NULL | The structured data produced |
| confidence | DOUBLE | Optional model confidence |
| validation_status | VARCHAR | pending, validated, rejected |
| validated_by | VARCHAR | Human reviewer identifier |

### fact_feedback
Human corrections on extractions -- the flywheel signal.

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| extraction_id | INTEGER | What was corrected |
| session_id | INTEGER | Context of the correction |
| skill_id | INTEGER | Which skill to refine |
| source_id | INTEGER | Denormalized from fact_extraction at insert |
| skill_domain | VARCHAR | Denormalized from dim_skill at insert |
| skill_task_type | VARCHAR | Denormalized from dim_skill at insert |
| skill_version | INTEGER | Denormalized from dim_skill at insert |
| source_path | VARCHAR | Denormalized from fact_extraction at insert |
| correction | JSON NOT NULL | {field: {before, after}} |
| correction_type | VARCHAR | field_mapping, wrong_value, missing_field, false_positive |
| notes | VARCHAR | Human explanation |
| created_by | VARCHAR | Reviewer identifier |

### fact_trace_feedback
Human feedback on trace nodes.

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| trace_id | INTEGER NOT NULL | Which trace node |
| session_id | INTEGER | Which session |
| feedback_type | VARCHAR | path_correction, positive_signal, dead_end_confirmation, reasoning_error |
| content | VARCHAR NOT NULL | Explanation |
| correction | JSON | Optional structured correction |
| created_by | VARCHAR | Reviewer identifier |
| trace_type | VARCHAR | Denormalized from fact_trace at insert |
| trace_title | VARCHAR | Denormalized from fact_trace at insert |
| skill_id | INTEGER | Denormalized from fact_trace at insert |
| skill_domain | VARCHAR | Denormalized from fact_trace at insert |
| skill_task_type | VARCHAR | Denormalized from fact_trace at insert |

## Analytical Views

| View | Purpose |
|------|---------|
| `v_feedback_by_skill` | Correction counts by skill + correction_type |
| `v_feedback_fields` | Field names mentioned in corrections by skill |
| `v_recurring_traces` | Traces that recur across sessions for a skill |
| `v_recurring_trace_feedback` | Trace feedback patterns across sessions |
| `v_skill_feedback_patterns` | Skills with feedback above threshold |
| `v_session_feedback_count` | Feedback count per session (for HIGH_FEEDBACK sampling) |

## Enum Values (enforced by CHECK constraints)

| Column | Valid Values |
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

## Operational

| Table | Purpose |
|-------|---------|
| `meta_schema_version` | Schema version tracking (version, description). Seeded on `db init`. |

## Common Queries

```sql
-- Active skills
SELECT id, domain, task_type, version, origin
FROM dim_skill WHERE status = 'active';

-- Extractions needing review (no join needed -- source_path is denormalized)
SELECT id, validation_status, source_path, skill_domain, skill_task_type
FROM fact_extraction WHERE validation_status = 'pending';

-- Feedback flywheel signal (via view)
SELECT * FROM v_feedback_by_skill WHERE skill_id = ?;

-- Session tree
SELECT id, agent_role, task_type, status, skill_domain, parent_session_id
FROM fact_session ORDER BY created_at DESC LIMIT 20;

-- Token usage by model
SELECT model_used,
       SUM(json_extract(token_usage, '$.input_tokens')::int) as input_tok,
       SUM(json_extract(token_usage, '$.output_tokens')::int) as output_tok
FROM fact_session WHERE token_usage IS NOT NULL
GROUP BY model_used;

-- Skills needing attention (via view)
SELECT DISTINCT skill_id, skill_domain, skill_task_type, total_feedback
FROM v_skill_feedback_patterns WHERE total_feedback >= 3;
```

## Notes

- JSON columns queryable with DuckDB JSON functions: `output->>'$.raw'`, `json_extract(metadata, '$.key')`
- For standalone DDL: `freud-schema db ddl` (the one CLI command that does NOT open a connection)
- For a fresh schema: `freud-schema db reset`
