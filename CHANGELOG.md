# Changelog

## 0.24.0

M0 of the enterprise-scale implementation plan: the cold-start playbook and
the first maintenance detector. The flywheel now has a documented first turn
and a standing signal for when seed knowledge decays.

### Added

- couch.py: `stale_source` detector -- recomputes each active source's
  content hash and compares it to the baseline recorded at registration;
  emits one GLOBAL-scope finding per changed source, basename only in the
  summary (privacy rules apply). Registered with `detection_method = hybrid`:
  it reads the warehouse AND the filesystem, so the finding is not
  reproducible from the warehouse alone. Sources without a baseline hash and
  missing files are skipped.
- couch.py: `source_content_hash()` -- sha256 hexdigest of a source file's
  bytes (full digest; a content fingerprint, not a key), shared by the CLI
  baseline and the detector's recomputation.
- couch.py: `run_couch(include_filesystem=True)` -- False skips filesystem
  detectors for warehouse-only runs (CI, machines without the corpus).
- cli.py: `source add --hash` records the staleness baseline;
  `couch run --warehouse-only` skips filesystem detectors.
- docs/tutorial-cold-start.md: the day-one playbook -- seed corpus with
  staleness baselines, thin human-authored skills, validate-everything
  cold-start gating, typed corrections, first flywheel turn, and the first
  staleness finding. Linked from README.
- tests: TestStaleSource in test_couch.py (mutated/unchanged/no-baseline/
  missing-file/warehouse-only paths, hybrid registration, and a
  basename-only privacy assertion).

### Changed

- `_insert` in couch.py takes a scope parameter (default PROJECT) so
  non-project findings (stale_source is GLOBAL) share the one write path.


## 0.23.0

M2+M3 of the enterprise-scale implementation plan: key algorithm versioning
and tenancy in natural keys, landed as a single reset (per the M1 no-migrations
policy -- SHA-256 keys with the tenant component already in the natural key,
so the warehouse resets once, not twice).

### Added

- keys.py: `KEY_ALGORITHM = "sha256/32"` constant; `dimension_key()` and
  `hash_diff()` now hash with SHA-256, truncated to the first 32 hex chars
  (same length as the MD5 hex scheme they replace -- no column width or
  prefix-resolution changes).
- db.py: `meta_key_algorithm` (single-row, seeded with `KEY_ALGORITHM` at
  `init_schema()`) so a database self-describes its key scheme.
- db.py/tables.py/store.py: `dim_tenant` registry (append-only, mirrors
  `dim_project`), seeded with a `default` tenant at `init_schema()`.
  `ExperimentStore.ensure_tenant()`/`get_tenant()`/`list_tenants()` and the
  `tenant_key_for()` recipe.
- tables.py: `tenant_id: str = "default"` on `Skill`, `Rule`, `Source`,
  `SamplingConfig`; `tenant_key: str | None = None` denormalized onto every
  fact model.
- cli.py: global `--tenant` flag (default `"default"`), threaded into
  `skill add`, `rule add`, `source add`, `sampling-config add`, the
  `dim_skill` prefix-resolving handlers, and `compile`.
- `_SCHEMA_VERSIONS`: version 6, "sha256/32 keys, dim_tenant registry,
  tenant-scoped natural keys, meta_key_algorithm".
- Tests: `tests/test_tenancy.py` (two-tenant collision, default-tenant
  back-compat, `resolve_key` tenant scoping, `init_schema` seeds); golden
  sha256/32 key values and the `KEY_ALGORITHM` constant added to
  `tests/test_keys.py`.

### Changed

- The four SCD-2 dims' natural keys now lead with `tenant_id`: skill =
  `(tenant_id, domain, task_type)`, rule = `(tenant_id, name)`, source =
  `(tenant_id, content_path)`, sampling config = `(tenant_id, domain,
  task_type)`. Two tenants can hold the "same" entity without collision.
- store.py: `get_active_skill()`, `get_rules()`, `get_sampling_config()`,
  and `resolve_key()` (for the four tenant-keyed dims only) gained a
  `tenant_id` parameter, defaulting to `"default"` -- omitting it preserves
  pre-0.23 behavior exactly. `_resolve_skill_attrs()` additionally resolves
  the skill's `tenant_key`; the five skill-denormalizing fact inserts
  (session, trace, extraction, feedback, trace_feedback) set the fact's
  `tenant_key` from it when a skill is linked, else from the model's own
  `tenant_key` or the default tenant. `insert_derived_skill()` inherits the
  parent skill's `tenant_id`. `approve_proposal()` reads an optional
  `tenant_id` out of `target_natural_key`, defaulting to `"default"`.
- materialize.py: `compile_rules()` gained a `tenant_id` parameter
  (default `"default"`); compiles one tenant's rules per run.
- Docs (CLAUDE.md, skill/skill.md, skill/reference/schema.md,
  skill/reference/context-assembly.md, a2ui/prompt_addendum.md): MD5 ->
  sha256/32 throughout; schema.md/a2ui docs gained `dim_tenant` (and
  schema.md gained `meta_key_algorithm`) plus `tenant_id`/`tenant_key`
  column documentation.

### Notes

- No data migration, per the M1 policy: existing databases reset
  (`reset_schema()`) and re-ingest; deterministic keys make re-ingest
  idempotent, native test rows (skills, rules, feedback, proposals) are
  disposable and recreated as needed.
- `hash_diff()`/natural-key content fingerprints do not include `tenant_id`
  -- it is identity, not content, consistent with `domain`/`task_type`/
  `name`/`content_path` already being excluded from `hash_diff()`.

## 0.22.0

M1 of the enterprise-scale implementation plan: reset-based schema
lifecycle, codified. Plus the planning-doc arc that produced it.

### Added

- `ROADMAP.md`: enterprise-scale roadmap generalized from a structural
  critique -- seven invariants worth preserving, seven phases of substrate
  work, explicitly scoped to a production descendant, not this repo.
- `docs/implementation-plan.md`: 15-milestone build plan (M0-M14) across
  six tracks, with dated research-review amendments and a risk register.
- `docs/research-agent-data-representation.md`: research pass over the 2026
  harness-engineering literature (ACE, MCE, Meta-Harness, Self-Harness,
  ScientistOne, Weng's harness post) and production practice, validating
  the files-as-truth + warehouse-as-catalog architecture; per-data-type
  representation guidance (code, diagrams, structured data, documents,
  logs); six adopted amendments.
- CLAUDE.md: **grounding layer** definition (constraints on one end,
  grounding data in the middle, verifiers and feedback on the other;
  warehouse = governed truth, compiled files = agent-facing form).
- CLAUDE.md: the no-migrations convention is now an explicit standing
  policy (owner decision, 2026-07-08) -- all warehouse data is disposable
  test/research data; never build migration machinery -- plus the standard
  schema-change recipe (edit DDL -> reset -> re-ingest -> recreate native
  test rows).
- `skill/reference/schema.md`: schema-change recipe note in Notes.

### Changed

- db.py: `_SCHEMA_VERSIONS` documented as a plain DDL changelog, NOT a
  migration ledger; module docstring cites the policy. No behavior change.

Quality pass over the Phase 0-3 code: a 4-angle cleanup review plus an 8-angle
correctness review, findings applied.

### Changed

- **Views use CREATE OR REPLACE** (was CREATE VIEW IF NOT EXISTS): view
  definition changes now reach existing databases instead of being silently
  pinned to the old definition forever.
- **One write path per fact table**: `insert_message`/`insert_tool_use` are
  thin delegators to the batch methods, so the column lists cannot drift
  (same principle as `_write_skill_row`, which both skill write paths now
  share). Batch inserts do one existing-key fetch per session and insert only
  the misses -- unchanged re-ingest drops from ~2min to ~5s. Batches raise on
  mixed-session input (the dedupe is per-session by design).
- `v_retry_loops` carries no threshold in the DDL; couch detectors own
  thresholds, parameterized through new store view-query methods
  (`query_retry_loops` etc. -- couch/materialize no longer touch private
  store helpers).
- `resolve_key(table, prefix)` drops the derivable `key_col` argument and
  escapes LIKE wildcards in prefixes; CLI resolution calls simplified
  accordingly.
- `load_run()` context manager owns the meta_load_log lifecycle for all
  operations and yields typed `LoadRunStats` (counter typos raise instead of
  silently logging zeros); failure rows now record counters accumulated
  before the error (per-file transactions make earlier writes durable).
- Canonical `ALL_TABLES`/`ALL_VIEWS` inventories in db.py drive
  `reset_schema()` and `db status`; an inventory test keeps both honest.
- SCD-2 insert guard shared across source/rule/sampling-config inserts;
  named key recipes (`session_key_for`, `message_key_for`) replace formula
  re-derivation in ingest.
- Test fixtures deduplicated to conftest; stale duplicate schema tests
  removed.

## 0.20.0

Phase 3 of the meta-harness plan: evolve + materialize. The loop is closed --
the first rule mined from real session history is compiled into this repo's
`.claude/rules/` with its full evidence chain.

### Added

- **Proposal lifecycle**: `approve_proposal` applies a pending proposal to its
  target dimension (rule evolve/create, skill version bump with data_derived
  origin, sampling config) as an SCD-2 evolution, recording
  resulting_dimension_key, reviewer, and timestamp. `reject_proposal` records
  the decision and changes nothing downstream. Pending-only guards on both.
  Approval is the one human atom -- nothing calls it automatically.
- **`rollback_dimension`**: close the current SCD-2 row, reopen the prior one.
  Symmetric with evolution, no destructive undo; recompile to propagate.
- **The compiler** (`materialize.py`): `compile --out DIR [--scope]` renders
  current active rules to `<name>.md` with a do-not-edit header, a source line
  (dimension key + effective_from), and a provenance footer naming the
  approving proposal and its evidence findings. Managed-file hygiene: files for
  deactivated rules are removed, but only files carrying the compiled marker --
  hand-written neighbors are never touched. Deterministic output.
- **Fail-closed privacy gate**: rendered files containing home-directory paths
  or the OS username are not written; the last good compile of a blocked rule
  survives; CLI exits nonzero on any block.
- CLI: `proposal add|list|show|approve|reject`, `compile`.
- `.claude/rules/no-identical-retries.md`: the first compiled rule, evidence:
  16 retry-loop findings mined from real transcripts across the project corpus.
- Tests: `test_evolve.py`, `test_materialize.py` (including planted-leak gate
  tests and rollback-then-recompile round-trip).

## 0.19.0

Phase 2 of the meta-harness plan: the couch. Analysis passes over the
warehouse produce typed, evidence-linked findings.

### Added

- **SQL finding detectors** (`couch.py` + 4 views: `v_retry_loops`,
  `v_tool_error_clusters`, `v_interruption_hotspots`, `v_permission_friction`).
  `freud-schema couch run` seeds the finding-type registry (4 SQL-detected +
  2 LLM-detected vocabularies) and records `fact_finding` rows with
  evidence session keys and occurrence counts. No model calls. Findings are
  append-only trend data keyed per run. Summaries are built from tool names,
  counts, and rates only -- never tool inputs, message text, paths, or URLs
  (scrubbed by construction, since findings feed the future compile step).
- `freud-schema couch list [--type]` to review findings.
- `/couch` skill (`.claude/skills/couch.md`): the LLM layer -- the harness
  judges user-correction patterns in scoped subagents and records findings
  via MCP, with non-negotiable privacy rules (describe the pattern, never
  quote the transcript).
- `project_key` conformed onto `fact_message` and `fact_tool_use` at ingest
  (dimensional fix: per-project finding views would otherwise need a
  fact-to-fact join through fact_session). Schema version 5.
- Tests: `test_couch.py` -- one fixture per finding pattern, each with a
  below-threshold neighbor asserting no false positives, plus a
  no-content-in-summaries privacy test.

## 0.18.0

Phase 1 of the meta-harness plan: sense. Claude Code's own session transcripts
become warehouse facts.

### Added

- **Transcript ingestion**: `freud-schema ingest transcripts [--root] [--project]
  [--since]`. One fact_session per transcript (root sessions as orchestrator,
  nested subagents linked via parent_session_key with agentType/description from
  their .meta.json sidecars), one fact_message per user/assistant entry, one
  fact_tool_use per tool_use block joined to its tool_result, dim_project from
  the session's cwd. Idempotent by key construction: re-running against
  unchanged files writes zero rows; a resumed session's grown file inserts only
  its new entries. All runs logged in meta_load_log.
- `discovery.py`: transcript discovery for the current nested layout
  (`<project>/<parent-uuid>/subagents/agent-<id>.jsonl` + sidecars), built fresh
  and verified against on-disk data.
- **Vendored ccutils parsers** (`vendor/ccutils_parsers/`): the typed transcript
  parser (12 discriminated entry types, Unknown* fallbacks, extra="allow") and
  the history.jsonl parser, with upstream commit provenance headers.
- Store: `transaction()` context manager (one transcript file per transaction),
  `count_rows()`, `update_session_progress()` (accumulating-snapshot updates
  with transcript-derived timestamps, not wall clock).
- Tests: `test_ingest.py` -- includes Phase 1's falsifiable milestone (idempotent
  re-ingest measured via meta_load_log counts) and incremental growth coverage.

## 0.17.0

Phase 0 of the meta-harness plan (see internal plan doc): the schema realigned
to the star-schema reference pattern so transcript ingestion (Phase 1) can be
idempotent by construction.

### Changed

- **MD5 hash surrogate keys everywhere** (`keys.dimension_key`), replacing all
  9 sequences and integer ids. Entity keys are deterministic from natural keys:
  skills = (domain, task_type), sources = content_path, rules = name, sampling
  configs = (domain, task_type). Every model field renamed `id` -> `<table>_key`;
  all cross-references renamed (`skill_id` -> `skill_key`, `session_id` ->
  `session_key`, etc.). `session_id` no longer exists anywhere in the DDL:
  `etl_run_id` is the lineage identifier, `session_key` the harness session.
- **SCD Type 2 on all four core dimensions** (`effective_from`/`effective_to`/
  `is_current`/`hash_diff`): attribute changes close the current row and insert
  a new one; rows never mutate; `updated_at` dropped. `insert_source`/`insert_rule`
  are idempotent on identical re-adds and evolve on change. Skill status changes
  (activate/deprecate) are SCD-2 evolutions. Skill versions are monotonic per
  entity.
- **Rules are keyed by a new required `name`** (also the future compile target
  filename `.claude/rules/<name>.md`).
- **fact_session unified across origins**: one row per harness session, native
  experiment run or ingested transcript, distinguished by `record_source`
  (CHECK-constrained allowlist). `task_description`/`task_type` now nullable;
  new `native_session_id`, `project_key` columns. Documented as an accumulating
  snapshot fact (status/result update in place; all other facts append-only).
- CLI id arguments become keys with git-style unique-prefix resolution
  (`store.resolve_key`); `rule add` requires `--name`.
- Schema version 3 -> 4. Breaking change via `reset_schema()`, no migration.

### Added

- `keys.py`: `dimension_key()` / `hash_diff()` -- deterministic, NULL-safe key
  generation; the primitive Phase 1's idempotent re-ingest guarantee builds on.
- **8 new tables**: `dim_project` (conformed project dimension), `dim_facet_type`
  + `fact_session_facets` (facet registry, EAV), `dim_finding_type` (open
  finding vocabulary -- registry-validated in the store, deliberately no CHECK
  enum), `fact_message` + `fact_tool_use` (transcript grain, deterministic keys,
  skip-if-exists inserts), `fact_finding` (couch outputs, evidence-linked),
  `fact_proposal` (evolve outputs, pending/approved/rejected lifecycle), plus
  `meta_load_log` (one row per ingest/compile run).
- Lineage envelope on every fact: `record_source` + `etl_run_id`; load-run
  lifecycle methods (`start_load_run`/`complete_load_run`).
- New enums: `RecordSource`, `ProposalStatus`, `TargetDimension`, `FindingScope`,
  `FacetMethod`, `FacetOutputType`, `DetectionMethod`, `MessageRole`.
- New store methods: project/facet-type/finding-type registries, message/tool-use
  inserts, findings, proposals, `resolve_key` prefix resolution.
- Tests: `test_keys.py`, `test_schema_v017.py`, `test_store_v017.py`.
- `[tool.pytest.ini_options]` anchoring rootdir (test collection previously
  escaped the repo and broke against an unrelated parent directory).

## 0.16.1

### Fixed

- **README.md**: Experiment Harness section updated from stale 7-table description to
  dimensional model (4 dim + 5 fact tables, 6 views). Project Structure updated with
  current file descriptions, added missing directories (scripts/, a2ui/, internal/).
- **skill/reference/schema.md**: Column-level fixes -- dim_sampling_config domain/task_type
  now nullable with parameters/status columns, dim_skill adds parent_skill_id/activation_conditions,
  dim_source adds superseded_by, fact_trace adds parent_trace_id/content (reordered for
  tree-structure clarity), fact_extraction adds validated_at, fact_trace_feedback renames
  notes->content and adds correction/skill_task_type, fact_feedback adds skill_version/source_path.
  Enum Values table now includes dim_sampling_config.status.
- **a2ui/prompt_addendum.md**: Removed stale FK language, added denormalized fields to
  Extraction and Session entities, added Trace and TraceFeedback data shapes.

## 0.16.0

### Changed

- **Dimensional model redesign** (Kimball-style): all tables renamed to `dim_*` (reference
  data) and `fact_*` (event data). Fact tables carry denormalized dimension attributes
  at insert time, eliminating all fact-to-fact joins.
- **6 analytical views** replace complex Python aggregation: `v_feedback_by_skill`,
  `v_feedback_fields`, `v_recurring_traces`, `v_recurring_trace_feedback`,
  `v_skill_feedback_patterns`, `v_session_feedback_count`. N+1 query patterns eliminated.
- `aggregate_feedback`, `get_recurring_traces`, `get_recurring_trace_feedback`,
  `get_skills_with_feedback_patterns` rewritten as view-backed single queries
- `sample_prior_sessions` HIGH_FEEDBACK strategy uses `v_session_feedback_count` view
  instead of correlated subquery
- Schema version 2 -> 3 (dimensional model)

### Added

- Insert-time denormalization: `insert_session` populates `skill_domain/skill_task_type/skill_version`,
  `insert_trace` populates skill attrs from session, `insert_extraction` populates source
  and skill attrs, `insert_feedback` populates skill and source attrs,
  `insert_trace_feedback` populates trace and skill attrs
- Session skill attribute caching in store for bulk trace inserts
- **Store-level existence validation** (`_require` helper): all fact insert methods validate
  required references exist before insert (replaces FK enforcement). Raises `ValueError`
  with clear message for orphaned references.
- **Prior run trace filtering**: `_format_prior_runs` now only includes signal-bearing traces
  (decision_point, dead_end, insight, conclusion, subagent_spawn). Skips tool_call,
  path_taken, path_discarded to avoid blowing up context with mechanical detail.
  Shows summary count ("3 of 50" format).

### Removed

- **FreudAgent MCP server** (`mcp_server.py`, `freud-mcp` entry point, `fastmcp` dependency):
  70% of tools were 1:1 SQL mappings the duckdb MCP already handles; views solve the rest.
  Access data via duckdb MCP + views (Claude Code) or CLI (terminal).
- All 15 FK REFERENCES clauses (DuckDB can't enforce CASCADE anyway; existence
  validation done in store layer)
- PRIMARY KEY on dimension and fact tables (sequences still guarantee unique IDs)

## 0.15.0

### Added

- **Run traces** (`traces` table): hierarchical reasoning trace nodes attached to
  sessions. 8 trace types: decision_point, path_taken, path_discarded, insight,
  dead_end, subagent_spawn, tool_call, conclusion. Tree structure via parent_trace_id.
- **Trace feedback** (`trace_feedback` table): human feedback on specific trace nodes.
  4 feedback types: path_correction, positive_signal, dead_end_confirmation, reasoning_error.
- **Sampling configs** (`sampling_configs` table): per-domain/task-type prior run
  sampling configuration. 5 strategies: recent, random, stratified_outcome,
  stratified_feedback, high_feedback.
- **Prior run injection**: `assemble_runner_context()` accepts `prior_runs` and
  `include_feedback_summary` parameters. Prior runs formatted as interpretable
  system prompt blocks with traces, feedback, and outcomes.
- **Skill evolution**: `origin` field (human_authored/data_derived) and
  `activation_conditions` JSON on skills. `insert_derived_skill()` tracks provenance.
  Pattern detection: `get_skills_with_feedback_patterns()`, `get_recurring_traces()`,
  `get_recurring_trace_feedback()`.
- **FreudAgent MCP server** (`freud-mcp`): typed MCP tools wrapping ExperimentStore.
  30+ tools for sessions, traces, extractions, feedback, sampling, pattern detection,
  and raw SQL escape hatch. Replaces generic DuckDB MCP server.
- **PostToolUse hook** (`scripts/trace-hook.sh`): automatic tool_call trace capture
  to JSONL buffer. `bulk_import_traces` MCP tool loads buffer into DB at session end.
- **Trace capture reference** (`skill/reference/trace-capture.md`): instructions for
  Claude on self-reporting reasoning traces during extraction runs.
- **Schema hardening**: UNIQUE constraint on skills `(domain, task_type, version)`,
  16 indexes across all tables, enhanced `aggregate_feedback` with field-level detail
  and optional examples.
- **Temporal queries**: `list_sessions` and `list_extractions` accept `created_after`
  and `created_before` date range filters. `list_sessions` adds `skill_id` filter.
- **Rich retrieval**: `get_extraction_with_feedback()`, `get_session_with_context()`,
  `get_sessions_with_context()` for joined data access.
- **Store methods**: `sample_prior_sessions()` (5 strategies), `get_active_sub_skills()`,
  `insert_derived_skill()`, `delete_session_traces()`, 10 trace/trace-feedback CRUD methods.
- **CLI commands**: `trace list|show|patterns`, `trace-feedback add|list`,
  `sampling-config add|list`, `skill patterns`. `skill list` shows origin column.
  `db status` shows all 10 tables.
- 45 new tests covering all new tables, constraints, store methods, context assembly,
  and CLI commands.

### Changed

- Schema version 1 -> 2 (10 tables, up from 7)
- `aggregate_feedback` returns `list[dict]` with correction_type, count, fields, examples
  (was `list[tuple[str, int]]`)
- `Session` model adds `sampled_session_ids: list[int] | None`
- `Skill` model adds `origin: SkillOrigin` and `activation_conditions: dict | None`
- `list_skills` accepts `origin` and `parent_skill_id` filters
- `_json()` helper widened to accept `dict | list | None`
- pyproject.toml: version 0.15.0, `freud-mcp` script entry point, `mcp` optional extra

## 0.14.0

### Removed

- **`freud-schema run` CLI command** -- orchestration belongs to the harness, not
  the data layer. Use Claude Code (MCP tools + Agent tool) or Agent SDK for extraction.
- `run_single()` from orchestrator module
- `_handle_run` CLI handler and `run` subparser
- 8 tests for removed orchestration code; 1 test rewritten to insert session directly

## 0.13.2

### Fixed

- **DuckDB lock detection**: `connect()` catches `IOException` on locked database files
  and raises a clear message directing users to MCP tools instead of raw traceback
- **Connection lifecycle**: `ExperimentStore` now supports context manager protocol
  (`with ExperimentStore(...) as store:`). All 8 CLI handlers use `with` blocks --
  previously leaked connections.

### Changed

- **DuckDB MCP routing docs**: CLAUDE.md, db-query skill, skill.md, and arxiv tutorial
  now explicitly state that CLI cannot access the DB while MCP server is active.
  MCP tools are the primary interface during Claude Code sessions.

## 0.13.1

### Added

- **CLI: `skill deprecate <id>` and `skill activate <id>`** -- expose existing store
  methods for skill lifecycle management
- **CLI: `session show <id>`** -- display full session details including context loaded,
  token usage, and result JSON
- **CLI: `--version` flag on `skill add`** -- specify skill version (default: 1) for
  flywheel v1/v2 comparisons
- **Retrieval thesis** (`skill/reference/retrieval-thesis.md`): architecture note
  connecting FreudAgent's L1/L2/L3 hierarchy to the progressive disclosure thesis
- **Flywheel tutorial** (`docs/tutorial-flywheel.md`): end-to-end walkthrough of the
  feedback loop -- extract, review, correct, refine skill, re-extract, compare
- **Claude Code native path** (step 6b in arxiv tutorial): documents how Claude Code
  consumes the data layer natively vs the CLI test utility
- 6 new tests: skill deprecate/activate CLI, session show, skill version roundtrip,
  nonexistent ID error handling for deprecate/activate/session show

## 0.13.0

### Changed

- **Pure data layer**: Removed orchestration from library. FreudAgent is now strictly
  a data layer (schema, context assembly, providers). Orchestration is the harness's job.
- CLI `run` command simplified to single-shot execution (`run_single()`) -- test utility,
  not orchestrator
- CLAUDE.md rewritten to position FreudAgent as a meta-framework inside the harness
- `skill/` restructured to demonstrate L1/L2/L3 progressive disclosure hierarchy
  - `skill.md` rewritten as L2 routing document
  - 5 new L3 reference files: schema, archetypes, context-assembly, hierarchy, flywheel

### Removed

- `run_task()`, `run_subtask()`, `run_simple()` from orchestrator module
- `TaskPlan`, `Subtask` Pydantic models from tables module
- 13 orchestration tests replaced by direct context assembly + provider tests

## 0.12.0

### Added

- **RLM (Recursive Language Model) provider**: inference-time scaffold that treats
  the user's prompt as a Python REPL variable, enabling iterative code-based
  exploration of large inputs
  - `rlm.py` -- `RLMProvider`, REPL engine, system prompt, source content loading
  - `RLMProvider` wraps any inner provider with a multi-turn REPL loop: the model
    writes code to probe, slice, and transform input via a persistent namespace
  - `llm_query()` function injected into REPL namespace for recursive sub-calls
  - `FINAL()`/`FINAL_VAR()` termination functions for explicit answer delivery
  - Sandboxed execution: restricted builtins (no `open`, `import`, `exec`),
    per-iteration timeout via `signal.alarm`, output truncation
  - Source content loading: `load_source_content()` reads text/JSON files directly,
    attempts `pdftotext` for PDFs, degrades gracefully for unsupported types
  - Source tag parsing: `<source>` XML tags in user messages trigger automatic
    content loading into the `context` variable
  - RLM metadata in session results: iteration count, sub-query count, per-iteration
    trace (code length, stdout/stderr length, termination action)
- **`complete_chat()` method** on `OpenAICompatProvider` and `ClaudeProvider`:
  multi-turn message history support for RLM and other iterative patterns.
  Backward-compatible -- `complete()` remains the required protocol method.
- **`recursive-decomposer` preset**: dream-work + free-association + fixation +
  pleasure-principle, mapping RLM behaviors to Freudian archetypes
- `metadata` field on `CompletionResult` for provider-specific structured data
- CLI flags: `--max-iterations` (REPL iteration limit), `--sub-model` (provider
  for `llm_query()` sub-calls)
- `rlm` and `rlm-anthropic` provider names in `get_provider()` factory
- 33 new tests: parsing, sandboxed execution, source loading, REPL loop,
  termination, token aggregation, multi-turn, preset integration, orchestrator pipeline

### Changed

- `OpenAICompatProvider.complete()` now delegates to `complete_chat()` internally
- `run_subtask()` merges `CompletionResult.metadata` into session result JSON

## 0.11.0

### Added

- **LLM-generated A2UI surfaces**: replaced static Python surface templates with
  runtime LLM generation (Claude, Gemini, or echo fallback)
  - `adapter.py` -- v0.9-to-v0.8 message translator for `@a2ui/lit` renderer
    (component restructuring, property mapping, typed data model conversion)
  - `providers.py` -- `A2UIProvider` protocol with 3 implementations:
    `EchoA2UIProvider`, `ClaudeA2UIProvider`, `GeminiA2UIProvider`
  - `prompt.py` -- system prompt assembly from skill files + component catalog +
    FreudAgent data shapes + few-shot examples
  - `prompt_addendum.md` -- FreudAgent entity descriptions for LLM context
- **Lit client** (`a2ui/client/`): Vite + Lit app using `@a2ui/lit` renderer
  - `src/app.ts` -- main app component with nav, provider selector, surface rendering
  - `src/api.ts` -- HTTP client for compose + action endpoints
  - `src/theme.ts` -- dark theme for `@a2ui/lit`
  - Builds to `a2ui/static/` (replaces old vanilla JS client)
- **Provider parameter** on `compose_surface` tool -- select LLM at request time
- **Free-form surface requests** -- no more hardcoded surface enum; LLM generates any layout
- 38 new tests: adapter (28), providers (10)

### Changed

- `compose_surface` now uses LLM pipeline: provider -> bridge validate -> adapter convert
- `queries.py` simplified: `model_dump(mode='json')` replaces 5 manual `*_to_dict` functions
- `server.py` serves built Lit app as static files via Starlette `StaticFiles`
- `pyproject.toml` updated: `anthropic` and `google-genai` optional deps, updated py-modules

### Removed

- `surfaces.py` -- 370 lines of hand-built component trees replaced by LLM generation
- `tests/test_surfaces.py` -- tests for deleted surfaces
- `static/index.html` -- vanilla JS renderer replaced by Lit client build output

## 0.10.0

### Added

- **A2UI integration** (`a2ui/`): visual surfaces for the experiment harness via A2UI v0.9 protocol
  - `server.py` -- MCP server with stdio (Claude Desktop) and HTTP (standalone web) modes
  - `bridge.py` -- structural A2UI validator (version, message types, component topology,
    JSON Pointer syntax, circular ref detection); optional `a2ui-agent` upgrade path
  - `queries.py` -- data access layer wrapping `ExperimentStore` for A2UI data models
  - `surfaces.py` -- 5 A2UI surface templates: extraction card, extraction list,
    session timeline, feedback summary, dashboard
  - `static/index.html` -- standalone web client with vanilla JS A2UI renderer
    (Text, Column, Row, Card, Button, Icon, Divider, Image, TextField, Tabs),
    SSE consumer, action sender, dark theme
- **5 MCP tools**: `render_a2ui`, `compose_surface`, `list_extractions`,
  `show_extraction`, `dashboard`
- **Interactivity**: validate/reject extractions from the web UI via POST actions,
  feedback submission
- **A2UI List component** in extraction list surface -- constant component count
  regardless of item count (data-driven via `itemTemplate`)
- **Session timeline grouping** -- children appear under their parent session,
  visually indented by depth level
- 34 tests: bridge validation (17), surface template validity (17)

### Changed

- Store uses a cached singleton connection (one DuckDB connection per server
  lifetime, not per tool call)
- Removed dead SSE infrastructure from web client (REST-only transport for now)
- Dropped `sse-starlette` dependency
- Shared `conftest.py` for test fixtures

## 0.9.0

### Added

- **Provider protocol**: `Provider` (protocol class) and `CompletionResult` (dataclass) replace
  the old `ModelCall` callable. Providers return structured responses with token counts and model info.
- **3 built-in providers**:
  - `EchoProvider` -- pipeline verification (replaces `EchoModel`)
  - `ClaudeProvider` -- Anthropic SDK, extracts `input_tokens`, `output_tokens`, `model` from response
  - `OpenAICompatProvider` -- any OpenAI-compatible endpoint via httpx (heylookitsanllm, llama.cpp, vLLM, Ollama)
- `get_provider()` factory: `"echo"`, `"anthropic"`, `"local"` with `model_name` and `base_url` params
- CLI `--endpoint` flag for local provider base URL
- CLI `--model local` option
- `token_usage` parameter on `store.complete_session()` -- set at completion time from provider response
- 4 new tests: token usage population, model_used from response, OpenAI-compat request format, get_provider local

### Changed

- `Session.token_usage` is now populated from provider responses (was always None)
- `Session.model_used` is set from the actual model in the response, not just the caller's string
- All `model_fn` parameters renamed to `provider` across orchestrator, CLI, and tests
- `run_subtask`, `run_task`, `run_simple` accept `provider: Provider` instead of `model_fn: ModelCall`

### Removed

- `ModelCall` protocol, `EchoModel` class, `get_model()` factory, `_call_anthropic` closure

## 0.8.0

### Added

- **8 enum classes** in `tables.py` as single source of truth for valid column values:
  `SkillStatus`, `SourceStatus`, `SessionStatus`, `AgentRole`, `ValidationStatus`,
  `CorrectionType`, `RuleScope`, `RuleStatus`
- **CHECK constraints** on all enum-like columns in DuckDB DDL (generated from Python enums)
- **10 FK constraints** enforcing referential integrity across all 6 tables
- `get_sources_by_ids()` bulk fetch method on `ExperimentStore` (eliminates N+1 in orchestrator)
- `get_ddl()` public function and `freud-schema db ddl` CLI command -- prints full DDL
  with CHECK + FK constraints for piping to `duckdb` CLI
- Generic `_fetchone`/`_fetchall` helpers on `ExperimentStore` -- uses `cursor.description`
  to build dicts by column name with automatic JSON deserialization via type detection
- 11 new tests: enum validation (5), CHECK constraint, FK constraint, prior results flow-through,
  all-subtasks-fail session state, exception session state, subtask named fields

### Changed

- `Subtask.skill_query: dict` replaced with `skill_domain: str` + `skill_task_type: str`
  (eliminates `.get("domain", "")` calls, gives IDE completion + type checking)
- All Pydantic model fields updated from bare `str` to enum types
- `store.py` method signatures typed: `complete_session(status: SessionStatus)`,
  `update_validation(status: ValidationStatus)`, `list_skills(status: SkillStatus)`, etc.
- CLI `choices=` derived from enum classes instead of hardcoded lists (also adds missing `deprecated` to skill status)
- `run_simple()` and all orchestrator code uses enum values for Session/Extraction construction
- All SQL string literals (`'active'`, `'deprecated'`, `'global'`) replaced with parameterized
  enum values -- zero hardcoded strings bypass the enum authority

### Removed

- Migration v2 infrastructure (`_MIGRATIONS`, `_run_migrations`, `_restore_migration_data`) --
  experiment repo, no legacy data, breaking changes are fine
- 6 `_row_to_*` positional-index methods in `store.py` -- replaced by generic dict conversion
  that is column-order-agnostic and auto-detects JSON columns from DuckDB type metadata

### Fixed

- **Prior results silently dropped**: `subtask.context and prior_results` gate removed --
  `subtask.context` was never set, so dependent subtasks never received upstream results
- **Session state lies**: orchestrator session now marked `"failed"` when all subtasks fail;
  `try/except/finally` ensures sessions never stay `"running"` after exceptions
- **Pydantic model mutation**: `extraction.id = ext_id` replaced with `store.get_extraction(ext_id)`
- **Source N+1 in context assembly**: `assemble_runner_context` uses `get_sources_by_ids()` bulk fetch

## 0.7.0

### Added

- **Archetype preset wiring**: archetypes are no longer decorative -- they flow into execution
  - `--preset` flag on `freud-schema run` composes archetype system prompt into context
  - `assemble_runner_context()` accepts optional `preset` param
  - `run_simple()` and `run_task()` propagate preset through the full pipeline
  - `freud-schema run --domain D --task-type T --preset careful-executor --model echo` shows archetypes in output
- **Skill rewrite**: `skill/skill.md` rewritten as a Claude Code data layer skill
  - Documents full CLI workflow: setup, data management, extraction, review, feedback
  - Reflects harness-agnostic architecture (FreudAgent feeds the harness, doesn't wrap it)
- 4 new tests: preset context assembly, preset in run_simple, no-preset baseline, invalid preset error

### Changed

- Promoted deferred `compose_preset` import to top-level in `orchestrator.py`
- Removed dead `orchestrator_preset` parameter from `run_task()` (was only logged, never used)
- Bumped `pyproject.toml` version to 0.7.0
- Backlog rewritten to reflect multi-harness north star and the inside/outside architectural pivot
  - Identifies orchestrator.py's API wrapper as the wrong pattern
  - Documents Provider protocol design (not implemented)
  - Documents harness adapter designs: Claude Code skill, Agent SDK workflow, MLX local
  - References flywheel decomposition JSON for Agent SDK mapping

## 0.6.1

### Added

- **Schema versioning**: `meta_schema_version` table tracks applied schema versions
  - Idempotent migration infrastructure (`_MIGRATIONS` list in `db.py`)
  - `get_schema_version()` query function
  - `db status` now displays current schema version
  - Pattern adopted from agent-state: replaces destructive-only schema evolution with safe, incremental migrations

## 0.6.0

### Added

- **`run` command**: Execute the orchestrator against database contents
  - `freud-schema run --domain D --task-type T` processes all active sources
  - `--source-id N` (repeatable) to target specific sources
  - `--model echo` (default) shows assembled context for pipeline verification
  - `--model anthropic` calls Claude API (requires `anthropic` SDK)
  - `--task` for additional task context
- **`extraction` commands**: `list`, `show`, `validate`, `reject`
- **`session list`**: View execution history (orchestrator + subagent sessions)
- **`feedback add`**: Close the flywheel loop with corrections on extractions
  - `--extraction-id`, `--type`, `--correction` (JSON), `--notes`, `--by`
- `EchoModel` -- built-in model for pipeline verification without API keys
- `get_model()` factory for model callables (echo, anthropic)
- `run_simple()` -- convenience function: skill + sources -> extractions
- 7 new tests for EchoModel, get_model, run_simple, end-to-end echo pipeline

### Changed

- `--db` moved from per-subparser to global root argument (all commands now use same DB)
- `feedback` CLI restructured to use subparsers: `feedback list` (was top-level), `feedback add` (new)
  - Old: `freud-schema feedback --skill-id 1 --aggregate`
  - New: `freud-schema feedback list --skill-id 1 --aggregate`
- `EchoModel` returns compact JSON; display layer handles formatting (eliminates double serialize)
- N+1 source lookups in `_handle_run` and `extraction list` replaced with bulk fetch + map
- Extracted `_print_json()` helper for duplicated JSON display logic
- `feedback add` uses `args.extraction_id` directly instead of `ext.id` (type-safe)

## 0.5.0

### Added

- **Experiment harness**: 6-table DuckDB schema for declarative agent orchestration
  - `skills` -- domain-specific instructions loaded at runtime
  - `sources` -- raw artifacts (file paths, MIME types)
  - `extractions` -- structured output with validation status
  - `sessions` -- logged agent executions with token tracking
  - `feedback` -- human corrections (the flywheel signal)
  - `rules` -- global and domain-specific constraints
- `db.py` -- DuckDB connection management and schema DDL
- `tables.py` -- Pydantic models for all 6 tables + TaskPlan/Subtask
- `store.py` -- ExperimentStore with typed CRUD operations, retrieval queries, feedback aggregation
- `orchestrator.py` -- Thin orchestrator loop + subagent runner with pluggable model calls
  - `assemble_runner_context()` -- progressive disclosure hierarchy (rules -> skill -> source -> task)
  - `run_subtask()` -- execute a single subtask with context assembly and session logging
  - `run_task()` -- process a TaskPlan respecting dependency order
- CLI commands: `db init|reset|status`, `skill add|list`, `source add|list`, `rule add|list`, `feedback`
- 18 new tests for schema, store CRUD, context assembly, orchestrator, and error handling
- DuckDB files added to .gitignore

### Changed

- Merged `progressive-refiner` preset into `iterative-refiner` (identical after archetype simplification)
- Presets reduced from 6 to 5
- CLI `export` command now uses orjson instead of json
- pyproject.toml: added duckdb, orjson dependencies; bumped to 0.5.0; updated description

## 0.4.0

### Changed

- **Aggressive archetype simplification: 19 -> 9** in a clean 3x3 grid
- ArchetypeCategory enum reduced from 6 categories to 3: STRUCTURAL, BEHAVIORAL, DIAGNOSTIC
- All 6 presets updated to reference new archetype names

### Added

- `ephemeral` archetype (merges `dream-element` + `psychic-apparatus`)
- `pleasure-principle` archetype (merges `pleasure-reality` + `death-drive`)
- `dream-work` archetype (merges `condensation` + `displacement` + `secondary-revision`)
- `freudian-slip` archetype (merges `parapraxis-monitor` + `resistance-detector`)
- `fixation` archetype (merges `cathexis` + `sublimation`)
- Tests for merged archetypes (verify each merge captures source concepts)
- 3x3 grid test (3 categories, 3 archetypes each)

### Removed

- 10 archetypes absorbed into merges or cut entirely
- Cut entirely (concepts absorbed into system-level design, not individual archetypes):
  `nachtraglichkeit`, `working-through`, `transference`, `topographic-hierarchy`
- Merged away: `condensation`, `displacement`, `secondary-revision`, `dream-element`,
  `psychic-apparatus`, `pleasure-reality`, `death-drive`, `parapraxis-monitor`,
  `resistance-detector`, `cathexis`, `sublimation`
- 3 obsolete ArchetypeCategory values: OBSERVATION, COMMUNICATION, RESOURCE_MANAGEMENT

## 0.3.1

### Changed

- Updated README.md to reflect current state: 19 archetypes, 17 entries, 6 presets
- Added architectural scopes section (intra-agent vs inter-agent)
- Added `hierarchical-orchestrator` and `progressive-refiner` to preset table
- Added `related_archetypes` usage and new preset examples to Python API section

## 0.3.0

### Added

- 5 new archetypes (14 -> 19): `psychic-apparatus`, `topographic-hierarchy`, `dream-element`, `nachtraglichkeit`, `secondary-revision`
- `related_archetypes` field on `AgenticArchetype` model (backward-compatible, default empty list)
- 3 new JSONL entries (14 -> 17): Interpretation of Dreams Ch. VII, Project for a Scientific Psychology, Letter 52/Mystic Writing Pad
- 2 new presets: `hierarchical-orchestrator`, `progressive-refiner`
- 5 new translation matrix entries: Nachtraglichkeit, Sekundare Bearbeitung, Bahnung, Wunderblock, Psychischer Apparat
- Archetype pattern reference entries for all 5 new archetypes
- Tests for new archetypes, presets, related_archetypes validation, and new JSONL entries

### Changed

- Updated `cathexis` description to reference RAM hierarchy and precise investment over diffuse attention
- Updated `structural-triad` description to clarify intra-agent scope vs `psychic-apparatus` inter-agent scope
- Skill activation keywords expanded (hierarchical, orchestrator, ephemeral, context tiering, nachtraglichkeit, topographic)
- `related_archetypes` enforced as bidirectional: `condensation`, `death-drive`, `working-through` now reference back to their counterparts
- `search_archetypes` now searches `prompt_fragment` in addition to other text fields
- CLAUDE.md updated to reflect current counts and presets

### Fixed

- Stray character in `pyproject.toml` dev dependencies
- Unused `json` import in `dataset.py`
- Removed phantom `duckdb` dependency (declared but never imported)
- Inconsistent mutable defaults on `FreudEntry` (`[]` -> `Field(default_factory=list)`)
- Redundant test functions (`test_new_archetypes_exist`, `test_new_presets`) merged into existing tests
- Repeated `load_entries()` disk reads in tests replaced with module-scoped fixture

## 0.2.0

- Initial agentic overlay: 14 archetypes, 4 presets, meta-harness, CLI

## 0.1.0

- Core schema: 14 JSONL entries, Pydantic models, dataset queries
