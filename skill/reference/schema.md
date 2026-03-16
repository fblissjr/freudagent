# DuckDB Schema Reference

Full schema for the 7-table experiment harness. Use the `duckdb` MCP tools for ad-hoc queries.

## Tables

### meta_schema_version
Tracks schema version for `db status`. Seeded with version 1 on `init_schema()`.

### skills
Declarative instructions loaded at runtime. One active version per domain/task_type pair.

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| domain | VARCHAR NOT NULL | e.g., "insurance", "legal" |
| task_type | VARCHAR NOT NULL | e.g., "extraction", "validation" |
| version | INTEGER DEFAULT 1 | Incremented on skill evolution |
| content | VARCHAR NOT NULL | Markdown instructions |
| metadata | JSON | Optional structured config |
| parent_skill_id | INTEGER FK -> skills | Previous version lineage |
| status | VARCHAR | draft, active, deprecated |

### sources
Raw artifacts to process (file paths, MIME types).

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| content_path | VARCHAR NOT NULL | File path or object store reference |
| media_type | VARCHAR NOT NULL | MIME type (application/pdf, text/plain) |
| metadata | JSON | Optional domain metadata |
| source_hash | VARCHAR | Content fingerprint for dedup |
| status | VARCHAR | active, archived |
| superseded_by | INTEGER FK -> sources | Version chain |

### rules
Constraints applied globally or per-domain, priority-ordered.

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| scope | VARCHAR | global, domain-specific |
| domain | VARCHAR | NULL for global rules |
| priority | INTEGER DEFAULT 0 | Higher = loaded first |
| content | VARCHAR NOT NULL | Rule text (markdown) |
| status | VARCHAR | active, inactive |

### sessions
Logged agent executions (orchestrator and subagent).

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| task_description | VARCHAR NOT NULL | Human-readable description |
| task_type | VARCHAR NOT NULL | Matches skill task_type |
| parent_session_id | INTEGER FK -> sessions | Tree structure |
| agent_role | VARCHAR | orchestrator, subagent |
| skill_id | INTEGER FK -> skills | Which skill was used |
| context_loaded | JSON | What data was assembled |
| model_used | VARCHAR | Provider model name |
| token_usage | JSON | {input_tokens, output_tokens} |
| status | VARCHAR | running, completed, failed |
| result | JSON | Output + metadata |

### extractions
Structured output from processing a source with a skill.

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| source_id | INTEGER FK -> sources | What was processed |
| skill_id | INTEGER FK -> skills | What instructions were used |
| session_id | INTEGER FK -> sessions | Which execution produced this |
| output | JSON NOT NULL | The structured data produced |
| confidence | DOUBLE | Optional model confidence |
| validation_status | VARCHAR | pending, validated, rejected |
| validated_by | VARCHAR | Human reviewer identifier |

### feedback
Human corrections on extractions -- the flywheel signal.

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| extraction_id | INTEGER FK -> extractions | What was corrected |
| session_id | INTEGER FK -> sessions | Context of the correction |
| skill_id | INTEGER FK -> skills | Which skill to refine |
| correction | JSON NOT NULL | {field: {before, after}} |
| correction_type | VARCHAR | field_mapping, wrong_value, missing_field, false_positive |
| notes | VARCHAR | Human explanation |
| created_by | VARCHAR | Reviewer identifier |

## Enum Values (enforced by CHECK constraints)

| Column | Valid Values |
|--------|-------------|
| skills.status | draft, active, deprecated |
| sources.status | active, archived |
| sessions.status | running, completed, failed |
| sessions.agent_role | orchestrator, subagent |
| extractions.validation_status | pending, validated, rejected |
| feedback.correction_type | field_mapping, wrong_value, missing_field, false_positive |
| rules.scope | global, domain-specific |
| rules.status | active, inactive |

## FK Relationships

```
skills.parent_skill_id     -> skills.id
sources.superseded_by      -> sources.id
sessions.parent_session_id -> sessions.id
sessions.skill_id          -> skills.id
extractions.source_id      -> sources.id
extractions.skill_id       -> skills.id
extractions.session_id     -> sessions.id
feedback.extraction_id     -> extractions.id
feedback.session_id        -> sessions.id
feedback.skill_id          -> skills.id
```

## Common Queries

```sql
-- Active skills
SELECT id, domain, task_type, version FROM skills WHERE status = 'active';

-- Extractions needing review
SELECT e.id, e.validation_status, s.content_path
FROM extractions e JOIN sources s ON e.source_id = s.id
WHERE e.validation_status = 'pending';

-- Feedback flywheel signal
SELECT correction_type, COUNT(*) as cnt
FROM feedback GROUP BY correction_type ORDER BY cnt DESC;

-- Session tree (parent + children)
SELECT id, agent_role, task_type, status, parent_session_id
FROM sessions ORDER BY created_at DESC LIMIT 20;

-- Token usage by model
SELECT model_used, SUM(json_extract(token_usage, '$.input_tokens')::int) as input_tok,
       SUM(json_extract(token_usage, '$.output_tokens')::int) as output_tok
FROM sessions WHERE token_usage IS NOT NULL
GROUP BY model_used;
```

## Notes

- JSON columns are queryable with DuckDB JSON functions: `output->>'$.raw'`, `json_extract(metadata, '$.key')`
- For a fresh schema: `freud-schema db reset`
- For standalone DDL: `freud-schema db ddl | duckdb :memory:`
