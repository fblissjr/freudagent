# DuckDB Schema Reference

Last updated: 2026-07-21

Full schema for the FreudAgent experiment harness (meta-harness model).
Use the store-ops server's `query` tool for ad-hoc queries (a generic `duckdb`
MCP server works too if that's what's connected). See
`.claude/skills/db-query.md` for common query patterns and enum values.

## Design Principles

- **No FK constraints.** DuckDB cannot CASCADE, so existence validation runs in
  the store layer via `_require()` (or a denormalization fetch that validates as a
  side effect). Orphaned keys are impossible in practice because all writes go
  through `ExperimentStore`.
- **sha256/32 hash surrogate keys, no sequences.** Every key is
  `keys.dimension_key(...)` -- a SHA-256 hex hash of pipe-joined natural-key
  parts, truncated to 32 chars (`None` maps to a `"-1"` sentinel; same length
  as the MD5 hex scheme it replaced in v0.23). Keys are deterministic: any
  consumer can compute a row's key without a lookup. This is what makes
  transcript re-ingestion idempotent -- re-ingesting the same file recomputes
  the same keys and skips rows that already exist. `meta_key_algorithm`
  records the active scheme (`sha256/32`) so a database self-describes it.
- **SCD Type 2 on the four core dimensions** (`dim_skill`, `dim_source`, `dim_rule`,
  `dim_sampling_config`). An attribute change closes the current row
  (`effective_to`, `is_current = false`) and inserts a new current row. Rows never
  mutate. `updated_at` does not exist -- `effective_from`/`effective_to` carry that
  information. Since v0.23 (M3) their natural keys lead with `tenant_id`, so two
  tenants can hold the "same" entity without collision.
- **Registry dimensions, no SCD-2** (`dim_project`, `dim_tenant`, `dim_facet_type`,
  `dim_finding_type`, `dim_event_type`, `dim_feedback_origin`). Append-only reference data whose identity
  doesn't evolve the way a skill's or rule's content does.
- **Lineage envelope on every fact table**: `record_source` (CHECK-constrained
  allowlist: `native`, `transcript_ingest`, `history_jsonl`, `event_ingest`,
  `derived`) and `etl_run_id` (joins `meta_load_log`). Every row declares where
  it came from.
- **Denormalized fact tables.** Fact tables carry dimension attributes
  (`skill_domain`, `source_path`, etc.) at insert time. Eliminates fact-to-fact joins.
- **Analytical views.** 10 views replace complex aggregation queries and N+1 patterns.

## Key Scheme

Every key is `dimension_key(*parts)` -- SHA-256 hex of the pipe-joined parts,
truncated to 32 chars (`keys.KEY_ALGORITHM = "sha256/32"`). This table is the
natural-key recipe per entity (see `insert_*` methods in `store.py` for the
authoritative source). The four core SCD-2 dims lead with `tenant_id` (v0.23,
M3) -- a tenant scopes identity, so `dim_skill` for `("team-a", "x", "y")` and
`("team-b", "x", "y")` are different rows:

| Table | Natural key | Notes |
|-------|-------------|-------|
| `dim_skill` | `(tenant_id, domain, task_type)` | All SCD-2 versions of a skill share this key |
| `dim_source` | `(tenant_id, content_path)` | |
| `dim_rule` | `(tenant_id, name)` | `name` is also the compile target filename |
| `dim_sampling_config` | `(tenant_id, domain, task_type)` | NULL-safe (global configs have both NULL) |
| `dim_project` | `(project_path,)` | |
| `dim_tenant` | `(tenant_id,)` | Not itself tenant-scoped -- it's the tenant registry |
| `dim_facet_type` | `(facet_id, prompt_version)` | Bumping the prompt version adds a row, never overwrites |
| `dim_finding_type` | `(finding_type,)` | |
| `dim_event_type` | `(event_type,)` | Open vocabulary, mirrors `dim_finding_type` |
| `fact_session` | `(record_source, native_session_id)` | Re-ingesting the same transcript resolves to the same key |
| `fact_trace` | `(session_key, depth, sequence_order, title)` | Deterministic -- bulk re-imports of the same trace buffer are idempotent |
| `fact_extraction` | `(session_key, source_key, uuid4())` | uuid-salted: a native event, intrinsically unique, never re-ingested |
| `fact_feedback` | `(extraction_key, uuid4())` | uuid-salted |
| `fact_trace_feedback` | `(trace_key, uuid4())` | uuid-salted |
| `fact_message` | `(session_key, entry_uuid)` | Falls back to a random uuid if `entry_uuid` is absent |
| `fact_tool_use` | `(session_key, tool_use_id)` | Falls back to a random uuid if `tool_use_id` is absent |
| `fact_session_facets` | `(session_key, facet_id, prompt_version)` | |
| `fact_finding` | `(finding_type, scope, project_key, summary, etl_run_id)` | |
| `fact_proposal` | `(target_dimension, target_key, uuid4())` | uuid-salted |
| `fact_event` | `(stream_key, native_event_id)` | `stream_key = dimension_key(record_source, native_stream_id)`, the generalization of `session_key` |

Writing raw SQL (MCP tools, not the store layer)? Replicate `dimension_key()` with
DuckDB's `sha256()`: `substring(sha256(part1 || '|' || part2 || ...), 1, 32)`,
substituting `'-1'` for any NULL part. Verified equivalent to
`keys.dimension_key()` for the same inputs.

## SCD-2 Columns (dim_skill, dim_source, dim_rule, dim_sampling_config)

Shared block, identical across the four core dimensions:

| Column | Type | Notes |
|--------|------|-------|
| effective_from | TIMESTAMP | Row's start of validity |
| effective_to | TIMESTAMP | NULL while `is_current` |
| is_current | BOOLEAN | TRUE for exactly one row per entity key |
| hash_diff | VARCHAR | Content fingerprint (`keys.hash_diff()`); unchanged content on re-add is a no-op |
| record_source | VARCHAR | Lineage allowlist, see below |
| created_at | TIMESTAMP | Row insert time |

Query current state with `WHERE is_current`; query history with
`ORDER BY effective_from`.

## Lineage Envelope (fact tables)

`_lineage_cols()` in db.py applies this block to fact tables only:

| Column | Type | Notes |
|--------|------|-------|
| tenant_key | VARCHAR | Denormalized `dim_tenant` reference (since v0.23/M3). Resolved from the linked skill's tenant when a skill is denormalized onto the fact, else from the model's own `tenant_key` or the default tenant |
| record_source | VARCHAR | `native`, `transcript_ingest`, `history_jsonl`, `event_ingest`, `derived` |
| etl_run_id | VARCHAR | Joins `meta_load_log`; NULL for rows not part of a tracked run. |
| created_at | TIMESTAMP | Row insert time |

Registry dimensions carry a narrower version of this envelope: just
`record_source` and `created_at` -- no `tenant_key`, no `etl_run_id`.

## Dimension Tables (SCD Type 2)

### dim_skill
Declarative instructions loaded at runtime. Entity key: `(tenant_id, domain, task_type)`.

| Column | Type | Notes |
|--------|------|-------|
| skill_key | VARCHAR | `dimension_key(tenant_id, domain, task_type)` |
| tenant_id | VARCHAR DEFAULT 'default' | Scopes identity (v0.23/M3) -- two tenants can hold the same (domain, task_type) |
| domain | VARCHAR NOT NULL | e.g., "insurance", "arxiv" |
| task_type | VARCHAR NOT NULL | e.g., "extraction", "validation" |
| version | INTEGER DEFAULT 1 | Monotonic per entity -- a new insert must exceed the current version |
| content | VARCHAR NOT NULL | Markdown instructions |
| metadata | JSON | Optional structured config |
| parent_skill_key | VARCHAR | Links derived skills to their parent |
| status | VARCHAR | draft, active, deprecated |
| origin | VARCHAR | human_authored, data_derived |
| activation_conditions | JSON | Optional conditions for derived skills |
| *SCD-2 columns* | | See above |

Status changes (activate/deprecate) are SCD-2 evolutions, not in-place updates --
they close the current row and insert a copy with the new status.

### dim_source
Raw artifacts to process. Entity key: `(tenant_id, content_path)`.

| Column | Type | Notes |
|--------|------|-------|
| source_key | VARCHAR | `dimension_key(tenant_id, content_path)` |
| tenant_id | VARCHAR DEFAULT 'default' | Scopes identity (v0.23/M3) |
| content_path | VARCHAR NOT NULL | File path or object store reference |
| media_type | VARCHAR NOT NULL | MIME type (application/pdf, text/plain) |
| metadata | JSON | Optional domain metadata |
| source_hash | VARCHAR | Content fingerprint for dedup |
| status | VARCHAR | active, archived |
| superseded_by_key | VARCHAR | Points to replacement source (versioning) |
| *SCD-2 columns* | | See above |

`insert_source` is idempotent: re-adding an identical source (same `hash_diff`) is
a no-op; a changed one evolves the SCD-2 row.

### dim_rule
Constraints applied globally or per-domain, priority-ordered. Entity key: `(tenant_id, name)`.

| Column | Type | Notes |
|--------|------|-------|
| rule_key | VARCHAR | `dimension_key(tenant_id, name)` |
| tenant_id | VARCHAR DEFAULT 'default' | Scopes identity (v0.23/M3); `compile_rules()` compiles one tenant's rules per run |
| name | VARCHAR NOT NULL | Stable identity; also the compile target filename (`.claude/rules/<name>.md`) |
| scope | VARCHAR | global, domain-specific |
| domain | VARCHAR | NULL for global rules |
| priority | INTEGER DEFAULT 0 | Higher = loaded first |
| content | VARCHAR NOT NULL | Rule text (markdown) |
| status | VARCHAR | active, inactive |
| *SCD-2 columns* | | See above |

`name` became required in v0.17.0 -- rules previously had no stable identity
beyond their row id, which made deterministic keying impossible. `rule add` now
requires `--name`.

### dim_sampling_config
Prior run sampling settings for pattern detection. Entity key:
`(tenant_id, domain, task_type)`, NULL-safe.

| Column | Type | Notes |
|--------|------|-------|
| config_key | VARCHAR | `dimension_key(tenant_id, domain, task_type)` |
| tenant_id | VARCHAR DEFAULT 'default' | Scopes identity (v0.23/M3) |
| domain | VARCHAR | Skill domain (NULL for global configs) |
| task_type | VARCHAR | Skill task type (NULL for global configs) |
| strategy | VARCHAR | recent, random, stratified_outcome, stratified_feedback, high_feedback |
| parameters | JSON | Strategy-specific config (NOT NULL, defaults to {}) |
| max_samples | INTEGER | Sample count limit |
| status | VARCHAR | active, inactive (reuses `RuleStatus`) |
| *SCD-2 columns* | | See above |

## Registry Dimensions (append-only, no SCD-2)

These are lookup tables, not versioned entities -- new rows widen the vocabulary,
existing rows are never evolved.

### dim_project
Conformed project dimension -- what makes cross-project queries a `GROUP BY`
instead of a cross-database merge. Entity key: `(project_path,)`.

| Column | Type | Notes |
|--------|------|-------|
| project_key | VARCHAR | `dimension_key(project_path)` |
| project_path | VARCHAR NOT NULL | Filesystem path identifying the project |
| project_name | VARCHAR | Human-readable label |
| first_seen_at | TIMESTAMP | When this project was first registered |
| record_source | VARCHAR | Lineage |
| created_at | TIMESTAMP | |

### dim_tenant
Conformed tenant dimension (v0.23/M3) -- what makes the four core SCD-2 dims
tenant-scoped instead of single-namespace. Entity key: `(tenant_id,)`.
Seeded with a `default` tenant at `init_schema()`.

| Column | Type | Notes |
|--------|------|-------|
| tenant_key | VARCHAR | `dimension_key(tenant_id)` |
| tenant_id | VARCHAR NOT NULL | e.g., "default", "team-a" |
| display_name | VARCHAR | Human-readable label |
| record_source | VARCHAR | Lineage |
| created_at | TIMESTAMP | |

### dim_facet_type
Registry row for a behavioral facet. Entity key: `(facet_id, prompt_version)`.

| Column | Type | Notes |
|--------|------|-------|
| facet_type_key | VARCHAR | `dimension_key(facet_id, prompt_version)` |
| facet_id | VARCHAR NOT NULL | e.g., "verbosity", "hedging_rate" |
| tier | INTEGER DEFAULT 1 | Facet grouping tier |
| method | VARCHAR | computed, regex, llm, cluster |
| output_type | VARCHAR | text, numeric, bool, json |
| prompt_text | VARCHAR | LLM prompt used to derive the facet, if `method = llm` |
| prompt_version | INTEGER DEFAULT 1 | Bumping this adds a new registry row |
| description | VARCHAR | |
| record_source | VARCHAR | Lineage |
| created_at | TIMESTAMP | |

Adding a facet is a row plus a populator, not a schema migration.

### dim_feedback_origin
Registry row for one producer of feedback: a named person, a specific model
version, a usage signal, a downstream system. Entity key: `(origin_id,)`.

| Column | Type | Notes |
|--------|------|-------|
| feedback_origin_key | VARCHAR | `dimension_key(origin_id)` |
| origin_id | VARCHAR NOT NULL | Open vocabulary -- register new producers as rows |
| origin_kind | VARCHAR NOT NULL | human, model, usage_signal, downstream_system, unspecified. CHECK-constrained |
| description | VARCHAR | |
| record_source | VARCHAR | Lineage |
| created_at | TIMESTAMP | |

**Deliberately half-open.** `origin_id` is open for the same reason
`finding_type` is: which person or which model version is discovered by running
the loop. `origin_kind` is closed, because it is the column filters are written
against -- "exclude model-derived rows from this measurement", "hold a
human-only slice". An open vocabulary there fails silently, one writer recording
`llm` and another `model` while the exclusion filter misses rows and looks like
it worked. Adding a kind means measurement code must handle it.

### dim_finding_type
Registry row for a finding vocabulary entry. Entity key: `(finding_type,)`.

| Column | Type | Notes |
|--------|------|-------|
| finding_type_key | VARCHAR | `dimension_key(finding_type)` |
| finding_type | VARCHAR NOT NULL | Open vocabulary -- see note below |
| description | VARCHAR | |
| detection_method | VARCHAR | sql, llm, hybrid |
| record_source | VARCHAR | Lineage |
| created_at | TIMESTAMP | |

**`finding_type` has no CHECK constraint, by design.** Every other closed set in
this schema (statuses, scopes, roles) is a CHECK constraint generated from a
Python enum in `tables.py`. `finding_type` is deliberately excluded: it is open
vocabulary, registry-validated against `dim_finding_type` in the store layer
(`insert_finding` raises `ValueError` if the type isn't registered first). New
domains seed their finding types as data -- a row insert -- not a DDL change or
an enum edit. This is the same reasoning that keeps skills and rules as data
instead of code.

### dim_event_type
Registry row for an event vocabulary entry (M5) -- the generalization of
`dim_finding_type` for the generic event grain. Entity key: `(event_type,)`.

| Column | Type | Notes |
|--------|------|-------|
| event_type_key | VARCHAR | `dimension_key(event_type)` |
| event_type | VARCHAR NOT NULL | Open vocabulary -- see note below |
| description | VARCHAR | |
| schema_hint | JSON | Optional shape hint for this event type's payload |
| record_source | VARCHAR | Lineage |
| created_at | TIMESTAMP | |

**`event_type` has no CHECK constraint, by design** -- same reasoning as
`finding_type` above: `fact_event.event_type` is registry-validated against
`dim_event_type` in the store layer (`insert_events` raises `ValueError` if a
type isn't registered first). Any `IngestAdapter` widens the vocabulary by
inserting a row, never by editing an enum.

## Fact Tables (event data with denormalized attributes)

### fact_session
One row per harness session -- a native experiment run or an ingested transcript.
Unified across origins (`record_source` distinguishes them). Accumulating
snapshot fact: `status`/`result`/`completed_at` update in place as the session
progresses; every other fact table is append-only. Entity key:
`(record_source, native_session_id)`.

| Column | Type | Notes |
|--------|------|-------|
| session_key | VARCHAR | `dimension_key(record_source, native_session_id)` |
| native_session_id | VARCHAR NOT NULL | Claude Code session uuid for ingested transcripts; store-generated uuid for native runs |
| project_key | VARCHAR | Denormalized reference to `dim_project` |
| task_description | VARCHAR | Nullable -- ingested transcripts may not have one |
| task_type | VARCHAR | Nullable, same reason |
| parent_session_key | VARCHAR | Tree structure (no FK constraint) |
| agent_role | VARCHAR | orchestrator, subagent |
| skill_key | VARCHAR | Which skill was used |
| skill_domain | VARCHAR | Denormalized from `dim_skill` at insert |
| skill_task_type | VARCHAR | Denormalized from `dim_skill` at insert |
| skill_version | INTEGER | Denormalized from `dim_skill` at insert |
| context_loaded | JSON | What data was assembled |
| model_used | VARCHAR | Provider model name |
| token_usage | JSON | {input_tokens, output_tokens} |
| status | VARCHAR | running, completed, failed |
| result | JSON | Output + metadata |
| sampled_session_keys | JSON | Keys used for pattern sampling |
| completed_at | TIMESTAMP | Set by `complete_session()` |
| *lineage columns* | | See above |

`session_id` does not exist anywhere in this schema. `native_session_id` is the
harness/transcript identifier; `etl_run_id` is the ingestion-run identifier;
`session_key` is the surrogate key. Don't conflate the three.

### fact_trace
Reasoning trace tree nodes within a session.

| Column | Type | Notes |
|--------|------|-------|
| trace_key | VARCHAR | `dimension_key(session_key, depth, sequence_order, title)` |
| session_key | VARCHAR NOT NULL | Parent session (no FK constraint) |
| parent_trace_key | VARCHAR | Tree structure (NULL for top-level) |
| trace_type | VARCHAR | decision_point, path_taken, path_discarded, insight, dead_end, subagent_spawn, tool_call, conclusion |
| depth | INTEGER DEFAULT 0 | Tree depth (0 = top-level) |
| sequence_order | INTEGER DEFAULT 0 | Order within depth |
| title | VARCHAR NOT NULL | Short description |
| content | VARCHAR | Extended description or body text |
| reasoning | VARCHAR | Explanation (when non-obvious) |
| alternatives | JSON | Options considered |
| outcome | JSON | Result of this trace node |
| duration_ms | INTEGER | Elapsed time |
| child_session_key | VARCHAR | Subagent session spawned |
| skill_key | VARCHAR | Denormalized from session at insert |
| skill_domain | VARCHAR | Denormalized from session at insert |
| skill_task_type | VARCHAR | Denormalized from session at insert |
| *lineage columns* | | See above |

### fact_extraction
Structured output from processing a source with a skill.

| Column | Type | Notes |
|--------|------|-------|
| extraction_key | VARCHAR | `dimension_key(session_key, source_key, uuid4())` |
| source_key | VARCHAR NOT NULL | What was processed |
| skill_key | VARCHAR NOT NULL | What instructions were used |
| session_key | VARCHAR NOT NULL | Which execution produced this |
| source_path | VARCHAR | Denormalized from `dim_source` at insert |
| source_media_type | VARCHAR | Denormalized from `dim_source` at insert |
| skill_domain | VARCHAR | Denormalized from `dim_skill` at insert |
| skill_task_type | VARCHAR | Denormalized from `dim_skill` at insert |
| skill_version | INTEGER | Denormalized from `dim_skill` at insert |
| output | JSON NOT NULL | The structured data produced |
| confidence | DOUBLE | Optional model confidence |
| validation_status | VARCHAR | pending, validated, rejected |
| validated_at | TIMESTAMP | When validation occurred |
| validated_by | VARCHAR | Human reviewer identifier |
| *lineage columns* | | See above |

### fact_feedback
Human corrections on extractions -- the flywheel signal.

| Column | Type | Notes |
|--------|------|-------|
| feedback_key | VARCHAR | `dimension_key(extraction_key, uuid4())` |
| extraction_key | VARCHAR NOT NULL | What was corrected |
| session_key | VARCHAR NOT NULL | Context of the correction |
| skill_key | VARCHAR NOT NULL | Which skill to refine |
| source_key | VARCHAR | Denormalized from `fact_extraction` at insert |
| skill_domain | VARCHAR | Denormalized from `dim_skill` at insert |
| skill_task_type | VARCHAR | Denormalized from `dim_skill` at insert |
| skill_version | INTEGER | Denormalized from `dim_skill` at insert |
| source_path | VARCHAR | Denormalized from `fact_extraction` at insert |
| correction | JSON NOT NULL | {field: {before, after}} |
| feedback_origin_key | VARCHAR | Points at `dim_feedback_origin`; NULL when unattributed |
| origin_kind | VARCHAR NOT NULL | Denormalized from the registry at insert, so excluding model-derived rows never needs a join. Defaults to `unspecified` -- never to `human`, which would contaminate the slice everything is measured against |
| correction_type | VARCHAR | field_mapping, wrong_value, missing_field, false_positive |
| notes | VARCHAR | Human explanation |
| created_by | VARCHAR | Reviewer identifier |
| *lineage columns* | | See above |

### fact_trace_feedback
Human feedback on trace nodes.

| Column | Type | Notes |
|--------|------|-------|
| trace_feedback_key | VARCHAR | `dimension_key(trace_key, uuid4())` |
| trace_key | VARCHAR NOT NULL | Which trace node |
| session_key | VARCHAR NOT NULL | Which session |
| feedback_type | VARCHAR | path_correction, positive_signal, dead_end_confirmation, reasoning_error |
| content | VARCHAR NOT NULL | Explanation |
| correction | JSON | Optional structured correction |
| created_by | VARCHAR | Reviewer identifier |
| trace_type | VARCHAR | Denormalized from `fact_trace` at insert |
| trace_title | VARCHAR | Denormalized from `fact_trace` at insert |
| skill_key | VARCHAR | Denormalized from `fact_trace` at insert |
| skill_domain | VARCHAR | Denormalized from `fact_trace` at insert |
| skill_task_type | VARCHAR | Denormalized from `fact_trace` at insert |
| *lineage columns* | | See above |

### fact_message
One user/assistant entry in a transcript. Full grain from day one -- user-correction
detection is structurally impossible at session-level aggregation.
Ingestion-scale table: deterministic keys, skip-if-exists inserts.

| Column | Type | Notes |
|--------|------|-------|
| message_key | VARCHAR | `dimension_key(session_key, entry_uuid or uuid4())` |
| session_key | VARCHAR NOT NULL | Parent session |
| role | VARCHAR NOT NULL | user, assistant |
| entry_uuid | VARCHAR | Source transcript's own entry id, if any |
| parent_uuid | VARCHAR | Transcript threading |
| sequence_num | INTEGER DEFAULT 0 | Order within the session |
| occurred_at | TIMESTAMP | Original transcript timestamp |
| content_text | VARCHAR | Message text |
| has_thinking | BOOLEAN DEFAULT FALSE | Whether an extended-thinking block was present |
| stop_reason | VARCHAR | Provider stop reason |
| input_tokens | INTEGER | |
| output_tokens | INTEGER | |
| is_meta | BOOLEAN DEFAULT FALSE | Harness-internal message (not user-visible) |
| is_sidechain | BOOLEAN DEFAULT FALSE | Part of a subagent/sidechain transcript |
| *lineage columns* | | See above -- defaults to `record_source = transcript_ingest` |

### fact_tool_use
One tool_use content block, joined to its tool_result where present. Deliberately
no per-tool typed columns -- tool-specific detail stays in `tool_input`.
Ingestion-scale table: deterministic keys, skip-if-exists inserts.

| Column | Type | Notes |
|--------|------|-------|
| tool_use_key | VARCHAR | `dimension_key(session_key, tool_use_id or uuid4())` |
| session_key | VARCHAR NOT NULL | Parent session |
| message_key | VARCHAR | The message this tool_use block belongs to |
| tool_use_id | VARCHAR | Provider's tool_use id (joins its tool_result) |
| tool_name | VARCHAR NOT NULL | e.g., "Read", "Bash", "Edit" |
| tool_input | JSON | Tool call arguments |
| is_error | BOOLEAN | Tri-state: True/False from tool_result, NULL if no result yet |
| result_text | VARCHAR | Tool result content |
| sequence_num | INTEGER DEFAULT 0 | Order within the session |
| occurred_at | TIMESTAMP | Original transcript timestamp |
| *lineage columns* | | See above -- defaults to `record_source = transcript_ingest` |

### fact_session_facets
EAV fact: one value of one facet for one session. Registry-validated -- the
`(facet_id, prompt_version)` pair must exist in `dim_facet_type` before insert.

| Column | Type | Notes |
|--------|------|-------|
| facet_row_key | VARCHAR | `dimension_key(session_key, facet_id, prompt_version)` |
| session_key | VARCHAR NOT NULL | |
| facet_type_key | VARCHAR | Denormalized `dim_facet_type` reference |
| facet_id | VARCHAR NOT NULL | |
| prompt_version | INTEGER DEFAULT 1 | |
| value_text | VARCHAR | Populated when `output_type = text` |
| value_numeric | DOUBLE | Populated when `output_type = numeric` |
| value_bool | BOOLEAN | Populated when `output_type = bool` |
| value_json | JSON | Populated when `output_type = json` |
| is_fallback | BOOLEAN DEFAULT FALSE | Set when extraction failed and a default was used |
| extraction_metadata | JSON | Populator-specific detail |
| *lineage columns* | | See above -- defaults to `record_source = derived` |

### fact_finding
A couch output: one detected pattern with its evidence. Append-only --
re-running Analyze produces new rows, so trends work for free.

| Column | Type | Notes |
|--------|------|-------|
| finding_key | VARCHAR | `dimension_key(finding_type, scope, project_key, summary, etl_run_id)` |
| finding_type | VARCHAR NOT NULL | Open vocabulary -- no CHECK, see `dim_finding_type` above |
| finding_type_key | VARCHAR NOT NULL | Denormalized `dim_finding_type` reference |
| scope | VARCHAR | project, global |
| project_key | VARCHAR | Denormalized `dim_project` reference |
| evidence_session_keys | JSON | Sessions supporting this finding |
| occurrence_count | INTEGER | |
| summary | VARCHAR NOT NULL | Human-readable; must be pre-scrubbed of paths/usernames (compile is fail-closed) |
| detected_at | TIMESTAMP | |
| *lineage columns* | | See above -- defaults to `record_source = derived` |

### fact_proposal
An evolve output: one proposed dimension change, pending until a human approves
or rejects. Approval creates the new SCD-2 row and records it in
`resulting_dimension_key`.

| Column | Type | Notes |
|--------|------|-------|
| proposal_key | VARCHAR | `dimension_key(target_dimension, target_key, uuid4())` |
| target_dimension | VARCHAR NOT NULL | dim_skill, dim_rule, dim_sampling_config -- genuinely closed, see notes below |
| target_key | VARCHAR | Entity key of the dim row to evolve; NULL for new entities |
| target_natural_key | JSON | Natural key parts, for proposals targeting a not-yet-existing entity |
| proposed_content | VARCHAR NOT NULL | |
| proposed_version | INTEGER | |
| status | VARCHAR | pending, approved, rejected |
| evidence_finding_keys | JSON | Findings that justify this proposal |
| resulting_dimension_key | VARCHAR | Set on approval |
| reviewed_by | VARCHAR | |
| review_notes | VARCHAR | Why the reviewer decided as they did. Rejection rate is a health measure; the rate without the reason cannot tell a gate catching real problems from one objecting to wording |
| reviewed_at | TIMESTAMP | |
| *lineage columns* | | See above -- defaults to `record_source = derived` |

`target_dimension` is a closed enum (unlike `finding_type`): a new member means
the evolve loop learned to modify a new kind of rule-bearing dimension, which is
a code change by definition, not a data change.

### fact_event
The generic event grain (M5) -- the generalization of `fact_message`/
`fact_tool_use` for non-transcript sources. Any enterprise event stream
ingests through this table via an `IngestAdapter` (`ingest.py`); transcripts
keep their richer typed projection instead of also landing here -- typed
tables are for sources rich enough to deserve them. Ingestion-scale table:
deterministic keys, skip-if-exists inserts, loaded via the spill-to-JSON bulk
insert path (`_bulk_insert_json`, shared with `fact_message`/`fact_tool_use`).

| Column | Type | Notes |
|--------|------|-------|
| event_key | VARCHAR | `dimension_key(stream_key, native_event_id or uuid4())` |
| stream_key | VARCHAR NOT NULL | `dimension_key(record_source, native_stream_id)` -- the generalization of `session_key`, via `stream_key_for()` |
| native_event_id | VARCHAR | Source stream's own event id, if any |
| event_type | VARCHAR NOT NULL | Open vocabulary -- no CHECK, see `dim_event_type` above |
| occurred_at | TIMESTAMP | |
| actor | VARCHAR | |
| payload | JSON | Adapter-parsed event payload |
| content_text | VARCHAR | Extracted searchable text, if any |
| signature | VARCHAR | Optional normalized template signature (amendment 6's `mask_signature()` hook) |
| sequence_num | INTEGER DEFAULT 0 | Order within the stream |
| *lineage columns* | | See above -- defaults to `record_source = event_ingest` |

Indexed on `(stream_key, occurred_at)` and `(event_type)`.

## Analytical Views

| View | Purpose |
|------|---------|
| `v_feedback_by_skill` | Correction counts by skill + correction_type |
| `v_feedback_fields` | Field names mentioned in corrections by skill |
| `v_recurring_traces` | Traces that recur across sessions for a skill |
| `v_recurring_trace_feedback` | Trace feedback patterns across sessions |
| `v_skill_feedback_patterns` | Skills with feedback above threshold |
| `v_session_feedback_count` | Feedback count per session (for HIGH_FEEDBACK sampling) |
| `v_retry_loops` | Same tool called with the same input repeatedly in one session (attempts + error counts, couch's retry-loop detector base) |
| `v_tool_error_clusters` | Per-project, per-tool error rates (uses, errors, error_pct, error session keys -- couch's tool-error-cluster detector base) |
| `v_interruption_hotspots` | Mid-turn user interruptions per project (`[Request interrupted by user...]` messages -- couch's interruption-hotspot detector base) |
| `v_permission_friction` | Permission denials per project+tool (tool errors whose result text mentions permission/denial -- couch's permission-friction detector base) |

The four couch views carry no thresholds in the DDL -- `couch.py`'s detectors
own those, passed as parameters into the store's `query_*` methods.

## Enum Values (enforced by CHECK constraints)

| Column | Valid Values |
|--------|-------------|
| dim_skill.status | draft, active, deprecated |
| dim_feedback_origin.origin_kind | human, model, usage_signal, downstream_system, unspecified |
| fact_feedback.origin_kind | human, model, usage_signal, downstream_system, unspecified |
| dim_skill.origin | human_authored, data_derived |
| dim_source.status | active, archived |
| dim_rule.scope | global, domain-specific |
| dim_rule.status | active, inactive |
| dim_sampling_config.strategy | recent, random, stratified_outcome, stratified_feedback, high_feedback |
| dim_sampling_config.status | active, inactive |
| dim_facet_type.method | computed, regex, llm, cluster |
| dim_facet_type.output_type | text, numeric, bool, json |
| dim_finding_type.detection_method | sql, llm, hybrid |
| fact_session.agent_role | orchestrator, subagent |
| fact_session.status | running, completed, failed |
| fact_trace.trace_type | decision_point, path_taken, path_discarded, insight, dead_end, subagent_spawn, tool_call, conclusion |
| fact_extraction.validation_status | pending, validated, rejected |
| fact_feedback.correction_type | field_mapping, wrong_value, missing_field, false_positive |
| fact_trace_feedback.feedback_type | path_correction, positive_signal, dead_end_confirmation, reasoning_error |
| fact_message.role | user, assistant |
| fact_finding.scope | project, global |
| fact_proposal.target_dimension | dim_skill, dim_rule, dim_sampling_config |
| fact_proposal.status | pending, approved, rejected |
| meta_load_log.status | running, completed, failed (shares `SessionStatus`) |
| **record_source** (every dim_*, fact_*, and meta_* table) | native, transcript_ingest, history_jsonl, event_ingest, derived |

**`fact_finding.finding_type` and `fact_event.event_type` are deliberately absent
from this table.** Neither has a CHECK constraint -- see the "Registry
Dimensions" section above for why.

## Operational

| Table | Purpose |
|-------|---------|
| `meta_schema_version` | Schema version tracking (version, description). Seeded on `db init`. Currently version 7. |
| `meta_load_log` | One row per ingest/compile run. `start_load_run()` opens a row and returns `etl_run_id`; `complete_load_run()` closes it with row counts and an optional error. |
| `meta_key_algorithm` | Single-row self-description of the active key scheme (`algorithm`, `recorded_at`). Seeded with `keys.KEY_ALGORITHM` (`sha256/32`) on `db init`. |

## Common Queries

```sql
-- Active skills (current row only)
SELECT skill_key, domain, task_type, version, origin
FROM dim_skill WHERE status = 'active' AND is_current;

-- Skill version history (SCD-2: every row for one entity)
SELECT version, status, effective_from, effective_to, is_current
FROM dim_skill WHERE skill_key = 'a1b2c3...' ORDER BY effective_from;

-- Extractions needing review (no join needed -- source_path is denormalized)
SELECT extraction_key, validation_status, source_path, skill_domain, skill_task_type
FROM fact_extraction WHERE validation_status = 'pending';

-- Feedback flywheel signal (via view)
SELECT * FROM v_feedback_by_skill WHERE skill_key = 'a1b2c3...';

-- Session tree
SELECT session_key, agent_role, task_type, status, skill_domain, parent_session_key
FROM fact_session ORDER BY created_at DESC LIMIT 20;

-- Token usage by model
SELECT model_used,
       SUM(json_extract(token_usage, '$.input_tokens')::int) as input_tok,
       SUM(json_extract(token_usage, '$.output_tokens')::int) as output_tok
FROM fact_session WHERE token_usage IS NOT NULL
GROUP BY model_used;

-- Skills needing attention (via view)
SELECT DISTINCT skill_key, skill_domain, skill_task_type, total_feedback
FROM v_skill_feedback_patterns WHERE total_feedback >= 3;

-- Transcript messages for a session (fact_message, full grain)
SELECT role, sequence_num, content_text, has_thinking
FROM fact_message WHERE session_key = 'a1b2c3...' ORDER BY sequence_num;

-- Tool call counts for a session
SELECT tool_name, COUNT(*) as calls
FROM fact_tool_use WHERE session_key = 'a1b2c3...'
GROUP BY tool_name ORDER BY calls DESC;

-- Findings detected so far
SELECT finding_key, finding_type, summary, occurrence_count
FROM fact_finding WHERE scope = 'project' ORDER BY detected_at DESC;

-- Proposals pending human review
SELECT proposal_key, target_dimension, proposed_version, status
FROM fact_proposal WHERE status = 'pending';

-- Events for one stream, in order (fact_event, generic event grain)
SELECT event_type, occurred_at, actor, content_text
FROM fact_event WHERE stream_key = 'a1b2c3...' ORDER BY occurred_at;

-- Load run health (ingestion/compile runs)
SELECT operation, status, rows_read, rows_written, rows_skipped, error
FROM meta_load_log ORDER BY started_at DESC LIMIT 10;
```

## Notes

- JSON columns queryable with DuckDB JSON functions: `output->>'$.raw'`, `json_extract(metadata, '$.key')`
- For standalone DDL: `freud-schema db ddl` (the one `db` subcommand that does NOT open a connection)
- For a fresh schema: `freud-schema db reset`
- CLI commands that take a key argument accept a full key or a unique prefix
  (git-short-hash style), resolved via `store.resolve_key()`
- Schema changes never migrate data (explicit policy -- see CLAUDE.md): edit the DDL in
  db.py, reset, re-ingest. Deterministic keys make re-ingest idempotent; native rows
  (skills, rules, feedback, proposals) are disposable test data, recreated as needed
