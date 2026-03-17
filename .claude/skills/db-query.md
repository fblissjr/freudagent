---
name: db-query
description: Query the experiment harness DuckDB via the duckdb MCP server. Use when inspecting skills, sources, sessions, extractions, feedback, or rules data.
---

# db-query

Query the FreudAgent experiment harness database using the `duckdb` MCP server tools.

## When to use

- Inspecting experiment data (skills, sources, sessions, extractions, feedback, rules)
- Ad-hoc analysis of orchestrator runs
- Checking schema state or table contents
- Debugging extraction output or session status
- Verifying data integrity after code changes

## MCP tools available

The `duckdb` MCP server (mcp-server-motherduck) exposes these tools:

| Tool | Use for |
|------|---------|
| `execute_query` | Run any DuckDB SQL. Pass `sql` parameter. |
| `list_tables` | Show all tables in the database. |
| `list_columns` | Show columns of a specific table. Pass `table` parameter. |

## Schema (7 tables)

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `skills` | Declarative instructions | domain, task_type, version, status, content |
| `sources` | Raw artifacts to process | content_path, media_type, status |
| `sessions` | Logged agent executions | task_type, agent_role, status, model_used, parent_session_id |
| `extractions` | Structured output from runs | source_id, skill_id, session_id, output, validation_status |
| `feedback` | Human corrections | extraction_id, correction_type, correction |
| `rules` | Constraints (global or per-domain) | scope, domain, priority, content, status |
| `meta_schema_version` | Schema version tracking | version, description |

## Enum values (enforced by CHECK constraints)

| Column | Valid values |
|--------|-------------|
| skills.status | draft, active, deprecated |
| sources.status | active, archived |
| sessions.status | running, completed, failed |
| sessions.agent_role | orchestrator, subagent |
| extractions.validation_status | pending, validated, rejected |
| feedback.correction_type | field_mapping, wrong_value, missing_field, false_positive |
| rules.scope | global, domain-specific |
| rules.status | active, inactive |

## Common queries

**Recent sessions with status:**
```sql
SELECT id, agent_role, task_type, status, model_used, created_at
FROM sessions ORDER BY created_at DESC LIMIT 20
```

**Active skills:**
```sql
SELECT id, domain, task_type, version, status
FROM skills WHERE status = 'active'
```

**Extractions needing review:**
```sql
SELECT e.id, e.validation_status, e.confidence, s.content_path
FROM extractions e JOIN sources s ON e.source_id = s.id
WHERE e.validation_status = 'pending'
```

**Feedback flywheel signal:**
```sql
SELECT correction_type, COUNT(*) as cnt
FROM feedback GROUP BY correction_type ORDER BY cnt DESC
```

**Failed sessions:**
```sql
SELECT id, task_description, result, created_at
FROM sessions WHERE status = 'failed'
```

## FK relationships

```
skills.parent_skill_id    -> skills.id
sources.superseded_by     -> sources.id
sessions.parent_session_id -> sessions.id
sessions.skill_id         -> skills.id
extractions.source_id     -> sources.id
extractions.skill_id      -> skills.id
extractions.session_id    -> sessions.id
feedback.extraction_id    -> extractions.id
feedback.session_id       -> sessions.id
feedback.skill_id         -> skills.id
```

## Notes

- JSON columns (metadata, context_loaded, token_usage, result, output, correction) are queryable with DuckDB's JSON functions: `output->>'$.raw'`, `json_extract(metadata, '$.key')`
- The MCP server connects to `data/freudagent.duckdb` with read-write access
- For a fresh schema with CHECK + FK constraints, run `freud-schema db reset` first
- To get the DDL as standalone SQL: `freud-schema db ddl`
