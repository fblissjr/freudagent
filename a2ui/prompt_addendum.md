# FreudAgent Data Shapes

When generating A2UI surfaces for FreudAgent, your data model will contain these entity types.

## Extraction

An extraction is a structured output from an agent run.

| Field | Type | Notes |
|-------|------|-------|
| id | integer | Primary key |
| source_id | integer | FK to sources table |
| skill_id | integer | FK to skills table |
| session_id | integer | FK to sessions table |
| confidence | float or null | 0.0-1.0, null if unknown |
| validation_status | string | "pending", "validated", or "rejected" |
| validated_by | string or null | Who validated |
| validated_at | string or null | ISO datetime |
| created_at | string or null | ISO datetime |
| output | object | The extracted data (varies by skill) |
| source | object or null | Nested source info (when enriched) |
| skill | object or null | Nested skill info (when enriched) |
| feedback | array | Feedback entries for this extraction |

## Session

A session is a logged agent execution.

| Field | Type | Notes |
|-------|------|-------|
| id | integer | Primary key |
| task_description | string | What the agent was asked to do |
| task_type | string | Domain category |
| parent_session_id | integer or null | FK for orchestrator/subagent hierarchy |
| agent_role | string | "orchestrator" or "subagent" |
| model_used | string | Model name (e.g., "claude-sonnet-4-6", "echo") |
| status | string | "running", "completed", or "failed" |
| token_usage | object | {"input_tokens": N, "output_tokens": N} |
| created_at | string or null | ISO datetime |
| completed_at | string or null | ISO datetime |

## Skill

A skill is a declarative instruction set loaded at runtime.

| Field | Type | Notes |
|-------|------|-------|
| id | integer | Primary key |
| domain | string | Domain name (e.g., "arxiv") |
| task_type | string | Task category (e.g., "extraction") |
| version | string | Skill version |
| status | string | "draft", "active", or "deprecated" |
| content_preview | string or null | First 200 chars of skill content |

## Feedback Summary

Aggregated feedback corrections by type.

| Field | Type | Notes |
|-------|------|-------|
| skill_id | integer or null | Scoped to skill, or null for all |
| by_type | object | {correction_type: count} |
| total | integer | Sum of all corrections |

## Dashboard Stats

Aggregated overview of the experiment harness.

```json
{
  "skills": {"total": 3, "active": 2},
  "extractions": {"total": 15, "pending": 5, "validated": 8, "rejected": 2},
  "sessions": {"total": 20, "recent": [...]},
  "feedback": {"total": 7}
}
```

## Design Guidelines

- Use data binding (`{"path": "/field"}`) for dynamic values, not hardcoded strings
- Use the List component with `itemTemplate` for repeating items (constant component count)
- Group related stats in Card components
- Use Row for horizontal layouts, Column for vertical
- Use Divider to separate sections
- Use variant "caption" for labels, "body" for values, "h1"-"h4" for headings
- Add Button actions for validate/reject/navigate operations
- Use status colors semantically: pending=warning, validated=success, rejected=error
