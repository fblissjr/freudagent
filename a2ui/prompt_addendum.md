# FreudAgent Data Shapes

Last updated: 2026-07-09 (M5: generic event grain)

When generating A2UI surfaces for FreudAgent, your data model will contain these entity types.
All tables use a dimensional model (dim_/fact_ naming). Fact tables carry denormalized
dimension attributes -- no joins needed for display. Keys are sha256/32 hash strings
(`keys.dimension_key()`), not integers -- render them truncated (e.g. first 8 chars)
the way the CLI does, never as a numeric id.

## Extraction

An extraction is a structured output from an agent run (from `fact_extraction`).

| Field | Type | Notes |
|-------|------|-------|
| extraction_key | string | Primary key (sha256/32 hash) |
| source_key | string | Which source was processed (ref dim_source) |
| skill_key | string | Which skill was used (ref dim_skill) |
| session_key | string | Which execution produced this (ref fact_session) |
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

A session is a logged agent execution (from `fact_session`) -- a native experiment
run or an ingested transcript, distinguished by `record_source`.

| Field | Type | Notes |
|-------|------|-------|
| session_key | string | Primary key (sha256/32 hash) |
| native_session_id | string or null | Claude Code session uuid for ingested transcripts; store-generated uuid for native runs |
| project_key | string or null | Which project this session belongs to (ref dim_project) |
| task_description | string or null | What the agent was asked to do (nullable -- ingested transcripts may not have one) |
| task_type | string or null | Domain category (nullable, same reason) |
| parent_session_key | string or null | Tree structure (orchestrator/subagent hierarchy) |
| agent_role | string | "orchestrator" or "subagent" |
| skill_key | string or null | Which skill was used (ref dim_skill) |
| skill_domain | string or null | Denormalized from dim_skill |
| skill_task_type | string or null | Denormalized from dim_skill |
| skill_version | integer or null | Denormalized from dim_skill |
| context_loaded | object or null | What data was assembled |
| model_used | string | Model name (e.g., "claude-sonnet-4-6", "echo") |
| status | string | "running", "completed", or "failed" |
| result | object or null | Output + metadata |
| token_usage | object | {"input_tokens": N, "output_tokens": N} |
| sampled_session_keys | array or null | Keys used for pattern sampling |
| record_source | string | "native", "transcript_ingest", "history_jsonl", or "derived" |
| created_at | string or null | ISO datetime |
| completed_at | string or null | ISO datetime |

## Trace

A reasoning trace node within a session (from `fact_trace`).

| Field | Type | Notes |
|-------|------|-------|
| trace_key | string | Primary key (sha256/32 hash) |
| session_key | string | Parent session |
| parent_trace_key | string or null | Tree structure (null for top-level) |
| trace_type | string | decision_point, path_taken, path_discarded, insight, dead_end, subagent_spawn, tool_call, conclusion |
| depth | integer | Tree depth (0 = top-level) |
| sequence_order | integer | Order within depth |
| title | string | Short description |
| content | string or null | Extended description or body text |
| reasoning | string or null | Explanation (when non-obvious) |
| alternatives | object or null | Options considered |
| outcome | object or null | Result of this trace node |
| duration_ms | integer or null | Elapsed time |
| child_session_key | string or null | Subagent session spawned |
| skill_key | string or null | Denormalized from session |
| skill_domain | string or null | Denormalized from session |
| skill_task_type | string or null | Denormalized from session |
| created_at | string or null | ISO datetime |

## TraceFeedback

Human feedback on a specific trace node (from `fact_trace_feedback`).

| Field | Type | Notes |
|-------|------|-------|
| trace_feedback_key | string | Primary key (sha256/32 hash) |
| trace_key | string | Which trace node |
| session_key | string | Which session |
| feedback_type | string | path_correction, positive_signal, dead_end_confirmation, reasoning_error |
| content | string | Explanation |
| correction | object or null | Optional structured correction |
| created_by | string or null | Reviewer identifier |
| trace_type | string or null | Denormalized from fact_trace |
| trace_title | string or null | Denormalized from fact_trace |
| skill_key | string or null | Denormalized from fact_trace |
| skill_domain | string or null | Denormalized from fact_trace |
| skill_task_type | string or null | Denormalized from fact_trace |
| created_at | string or null | ISO datetime |

## Message

One user/assistant transcript entry (from `fact_message`). Ingested-transcript
grain -- full detail, not a session-level summary.

| Field | Type | Notes |
|-------|------|-------|
| message_key | string | Primary key (sha256/32 hash) |
| session_key | string | Parent session |
| role | string | "user" or "assistant" |
| entry_uuid | string or null | Source transcript's own entry id |
| parent_uuid | string or null | Transcript threading |
| sequence_num | integer | Order within the session |
| occurred_at | string or null | ISO datetime, original transcript timestamp |
| content_text | string or null | Message text |
| has_thinking | boolean | Whether an extended-thinking block was present |
| stop_reason | string or null | Provider stop reason |
| input_tokens | integer or null | |
| output_tokens | integer or null | |
| is_meta | boolean | Harness-internal message (not user-visible) |
| is_sidechain | boolean | Part of a subagent/sidechain transcript |
| record_source | string | Almost always "transcript_ingest" |

## ToolUse

One tool_use content block, joined to its tool_result where present (from
`fact_tool_use`). No per-tool typed columns -- tool-specific detail is in
`tool_input`.

| Field | Type | Notes |
|-------|------|-------|
| tool_use_key | string | Primary key (sha256/32 hash) |
| session_key | string | Parent session |
| message_key | string or null | The message this tool_use block belongs to |
| tool_use_id | string or null | Provider's tool_use id (joins its tool_result) |
| tool_name | string | e.g., "Read", "Bash", "Edit" |
| tool_input | object or null | Tool call arguments |
| is_error | boolean or null | Tri-state: true/false from tool_result, null if no result yet |
| result_text | string or null | Tool result content |
| sequence_num | integer | Order within the session |
| occurred_at | string or null | ISO datetime |

## SessionFacet

One value of one behavioral facet for one session (from `fact_session_facets`,
EAV-shaped). Registry-validated against `dim_facet_type`.

| Field | Type | Notes |
|-------|------|-------|
| facet_row_key | string | Primary key (sha256/32 hash) |
| session_key | string | |
| facet_type_key | string or null | Denormalized dim_facet_type reference |
| facet_id | string | e.g., "verbosity", "hedging_rate" |
| prompt_version | integer | |
| value_text | string or null | Populated when the facet's output_type is "text" |
| value_numeric | float or null | Populated when output_type is "numeric" |
| value_bool | boolean or null | Populated when output_type is "bool" |
| value_json | object or array or null | Populated when output_type is "json" |
| is_fallback | boolean | Set when extraction failed and a default was used |
| extraction_metadata | object or null | Populator-specific detail |

## Finding

A detected pattern with its evidence (from `fact_finding`, a couch output).
Append-only -- re-running Analyze produces new rows.

| Field | Type | Notes |
|-------|------|-------|
| finding_key | string | Primary key (sha256/32 hash) |
| finding_type | string | Open vocabulary -- see FindingType below |
| finding_type_key | string | Denormalized dim_finding_type reference |
| scope | string | "project" or "global" |
| project_key | string or null | Denormalized dim_project reference |
| evidence_session_keys | array or null | Sessions supporting this finding |
| occurrence_count | integer or null | |
| summary | string | Human-readable, pre-scrubbed of paths/usernames |
| detected_at | string or null | ISO datetime |

## Proposal

A proposed dimension change (from `fact_proposal`, an evolve output), pending
until a human approves or rejects.

| Field | Type | Notes |
|-------|------|-------|
| proposal_key | string | Primary key (sha256/32 hash) |
| target_dimension | string | "dim_skill", "dim_rule", or "dim_sampling_config" |
| target_key | string or null | Entity key of the dim row to evolve; null for new entities |
| target_natural_key | object or null | Natural key parts, for proposals targeting a not-yet-existing entity |
| proposed_content | string | |
| proposed_version | integer or null | |
| status | string | "pending", "approved", or "rejected" |
| evidence_finding_keys | array or null | Findings that justify this proposal |
| resulting_dimension_key | string or null | Set on approval |
| reviewed_by | string or null | |
| reviewed_at | string or null | ISO datetime |

## Event

A generic ingested event (from `fact_event`) -- the generalization of Message/
ToolUse for non-transcript sources (M5). Any enterprise event stream ingests
through this grain via an IngestAdapter; transcripts keep their richer typed
projection instead.

| Field | Type | Notes |
|-------|------|-------|
| event_key | string | Primary key (sha256/32 hash) |
| stream_key | string | Which stream this event belongs to (ref the source's own identity) |
| native_event_id | string or null | Source stream's own event id, if any |
| event_type | string | Open vocabulary -- see EventType below |
| occurred_at | string or null | ISO datetime |
| actor | string or null | |
| payload | object or null | Adapter-parsed event payload |
| content_text | string or null | Extracted searchable text, if any |
| signature | string or null | Optional normalized template signature |
| sequence_num | integer | Order within the stream |

## EventType

Registry row for an event vocabulary entry (from `dim_event_type`). New event
types are rows here, never enum edits -- the generalization of FindingType.

| Field | Type | Notes |
|-------|------|-------|
| event_type_key | string | Primary key (sha256/32 hash) |
| event_type | string | Open vocabulary |
| description | string or null | |
| schema_hint | object or null | Optional shape hint for this event type's payload |

## Project

A conformed project dimension (from `dim_project`) -- what makes cross-project
queries a group-by instead of a cross-database merge.

| Field | Type | Notes |
|-------|------|-------|
| project_key | string | Primary key (sha256/32 hash) |
| project_path | string | Filesystem path identifying the project |
| project_name | string or null | Human-readable label |
| first_seen_at | string or null | ISO datetime |

## Tenant

A conformed tenant dimension (from `dim_tenant`) -- what scopes skills, rules,
sources, and sampling configs to a namespace instead of a single global one.

| Field | Type | Notes |
|-------|------|-------|
| tenant_key | string | Primary key (sha256/32 hash) |
| tenant_id | string | e.g., "default", "team-a" |
| display_name | string or null | Human-readable label |

## FacetType

Registry row for a behavioral facet (from `dim_facet_type`). Bumping
`prompt_version` adds a row, never overwrites.

| Field | Type | Notes |
|-------|------|-------|
| facet_type_key | string | Primary key (sha256/32 hash) |
| facet_id | string | |
| tier | integer | Facet grouping tier |
| method | string | "computed", "regex", "llm", or "cluster" |
| output_type | string | "text", "numeric", "bool", or "json" |
| prompt_text | string or null | LLM prompt used to derive the facet, if method is "llm" |
| prompt_version | integer | |
| description | string or null | |

## FindingType

Registry row for a finding vocabulary entry (from `dim_finding_type`). New
finding types are rows here, never enum edits or DDL changes.

| Field | Type | Notes |
|-------|------|-------|
| finding_type_key | string | Primary key (sha256/32 hash) |
| finding_type | string | Open vocabulary |
| description | string or null | |
| detection_method | string | "sql", "llm", or "hybrid" |

## Skill

A skill is a declarative instruction set loaded at runtime (from `dim_skill`).

| Field | Type | Notes |
|-------|------|-------|
| skill_key | string | Primary key (sha256/32 hash) |
| tenant_id | string | Scopes identity, default "default" (ref dim_tenant) |
| domain | string | Domain name (e.g., "arxiv") |
| task_type | string | Task category (e.g., "extraction") |
| version | integer | Skill version |
| status | string | "draft", "active", or "deprecated" |
| content_preview | string or null | First 200 chars of skill content |

## Feedback Summary

Aggregated feedback corrections by type.

| Field | Type | Notes |
|-------|------|-------|
| skill_key | string or null | Scoped to skill, or null for all |
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
