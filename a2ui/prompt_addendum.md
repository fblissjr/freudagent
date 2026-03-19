# FreudAgent Data Shapes

When generating A2UI surfaces for FreudAgent, your data model will contain these entity types.
All tables use a dimensional model (dim_/fact_ naming). Fact tables carry denormalized
dimension attributes -- no joins needed for display.

## Extraction

An extraction is a structured output from an agent run (from `fact_extraction`).

| Field | Type | Notes |
|-------|------|-------|
| id | integer | Primary key |
| source_id | integer | Which source was processed (ref dim_source) |
| skill_id | integer | Which skill was used (ref dim_skill) |
| session_id | integer | Which execution produced this (ref fact_session) |
| source_path | string or null | Denormalized from dim_source |
| source_media_type | string or null | Denormalized from dim_source |
| skill_domain | string or null | Denormalized from dim_skill |
| skill_task_type | string or null | Denormalized from dim_skill |
| skill_version | integer or null | Denormalized from dim_skill |
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

A session is a logged agent execution (from `fact_session`).

| Field | Type | Notes |
|-------|------|-------|
| id | integer | Primary key |
| task_description | string | What the agent was asked to do |
| task_type | string | Domain category |
| parent_session_id | integer or null | Tree structure (orchestrator/subagent hierarchy) |
| agent_role | string | "orchestrator" or "subagent" |
| skill_id | integer or null | Which skill was used (ref dim_skill) |
| skill_domain | string or null | Denormalized from dim_skill |
| skill_task_type | string or null | Denormalized from dim_skill |
| skill_version | integer or null | Denormalized from dim_skill |
| context_loaded | object or null | What data was assembled |
| model_used | string | Model name (e.g., "claude-sonnet-4-6", "echo") |
| status | string | "running", "completed", or "failed" |
| result | object or null | Output + metadata |
| token_usage | object | {"input_tokens": N, "output_tokens": N} |
| sampled_session_ids | array or null | IDs used for pattern sampling |
| created_at | string or null | ISO datetime |
| completed_at | string or null | ISO datetime |

## Trace

A reasoning trace node within a session (from `fact_trace`).

| Field | Type | Notes |
|-------|------|-------|
| id | integer | Primary key |
| session_id | integer | Parent session |
| parent_trace_id | integer or null | Tree structure (null for top-level) |
| trace_type | string | decision_point, path_taken, path_discarded, insight, dead_end, subagent_spawn, tool_call, conclusion |
| depth | integer | Tree depth (0 = top-level) |
| sequence_order | integer | Order within depth |
| title | string | Short description |
| content | string or null | Extended description or body text |
| reasoning | string or null | Explanation (when non-obvious) |
| alternatives | object or null | Options considered |
| outcome | object or null | Result of this trace node |
| duration_ms | integer or null | Elapsed time |
| child_session_id | integer or null | Subagent session spawned |
| skill_id | integer or null | Denormalized from session |
| skill_domain | string or null | Denormalized from session |
| skill_task_type | string or null | Denormalized from session |
| created_at | string or null | ISO datetime |

## TraceFeedback

Human feedback on a specific trace node (from `fact_trace_feedback`).

| Field | Type | Notes |
|-------|------|-------|
| id | integer | Primary key |
| trace_id | integer | Which trace node |
| session_id | integer | Which session |
| feedback_type | string | path_correction, positive_signal, dead_end_confirmation, reasoning_error |
| content | string | Explanation |
| correction | object or null | Optional structured correction |
| created_by | string or null | Reviewer identifier |
| trace_type | string or null | Denormalized from fact_trace |
| trace_title | string or null | Denormalized from fact_trace |
| skill_id | integer or null | Denormalized from fact_trace |
| skill_domain | string or null | Denormalized from fact_trace |
| skill_task_type | string or null | Denormalized from fact_trace |
| created_at | string or null | ISO datetime |

## Skill

A skill is a declarative instruction set loaded at runtime (from `dim_skill`).

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
