# freudagent

<p align="center">
  <a href="assets/theman-medium.png">
    <img src="assets/theman-medium.png" alt="freud agent logo" width="400">
  </a>
  <br>
</p>


A meta-framework for declarative agent orchestration that lives INSIDE the harness
(Claude Code, Agent SDK), not outside it. Pure data layer: schema, context assembly,
prompt composition. The harness handles orchestration. FreudAgent handles data.

Mostly a joke repo. But the thesis is serious.

Last updated: 2026-07-21

## Start here

[The data flywheel](docs/data-flywheel.md) explains the whole design end to end,
in plain English with animated diagrams: how agent output becomes evidence, how
evidence becomes proposals, how a person approves them, and how approved changes
become the files the agent loads next time. It covers the generalized pattern,
not just this repo, and marks which parts are built and which are planned.

## Setup

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh

git clone https://github.com/fblissjr/freudagent.git
cd freudagent
uv sync --extra dev
```

## Tutorials

These are the hands-on path. For why any of it is shaped this way, read
Start here first.

New here? Start with the [end-to-end tutorial](docs/tutorial-arxiv-extraction.md) --
extracts structured data from an arxiv paper using the full pipeline. Covers the
why behind every step, not just the commands.

Then try the [RLM provider tutorial](docs/tutorial-rlm-provider.md) -- wraps any
model with a Python REPL loop for iterative, code-driven extraction of large inputs.

Then walk through the [flywheel tutorial](docs/tutorial-flywheel.md) -- the full
feedback loop (extract, review, correct, refine skill, re-extract, compare), then
the governed path in sections 9-16: run the detectors, draft a proposal from a
finding, approve it, and compile it with its provenance attached.

Starting a fresh deployment? The [cold-start tutorial](docs/tutorial-cold-start.md)
is the day-one playbook: seed corpus with staleness baselines, thin human-authored
skills, validate-everything gating, and the first turn of the flywheel.

## Usage

### CLI -- Freud Corpus

```bash
# Query the Freud corpus (17 core entries)
uv run freud-schema list-topics
uv run freud-schema search "wish"
uv run freud-schema term "Id"
```

### CLI -- Archetypes and Prompts

```bash
# List all 9 archetypes
uv run freud-schema list-archetypes

# Show a specific archetype
uv run freud-schema archetype structural-triad
uv run freud-schema archetype dream-work

# Generate a system prompt from a preset
uv run freud-schema prompt --preset careful-executor
uv run freud-schema prompt --preset hierarchical-orchestrator

# Generate a prompt from specific archetypes with task context
uv run freud-schema prompt structural-triad free-association fixation \
  --task "Explore this codebase and summarize the architecture"
```

### CLI -- Experiment Harness

Entity references (skill, source, rule, extraction, feedback, session, trace)
are sha256/32 hash keys (SHA-256, truncated to 32 hex chars), not integers.
Every command that takes one accepts a full key or a unique prefix,
git-short-hash style.

```bash
# 1. Initialize
uv run freud-schema db init

# 2. Set up: rules, skills, sources
uv run freud-schema rule add --name always-valid-json --content "Always output valid JSON" --scope global
uv run freud-schema skill add \
  --domain legal --task-type extraction \
  --content "Extract party names and dates from contracts" \
  --status active
uv run freud-schema source add --path ./contracts/sample.pdf --media-type application/pdf

# 3. Extract (via the harness -- Claude Code, Agent SDK, or programmatic API)
# The CLI manages data; the harness orchestrates extraction.
# See docs/tutorial-arxiv-extraction.md for the full workflow.

# 4. Review results
uv run freud-schema extraction list
uv run freud-schema extraction show <key-or-prefix>
uv run freud-schema session list

# 5. Validate or reject extractions
uv run freud-schema extraction validate <key-or-prefix> --by "reviewer"

# 6. Close the feedback loop
uv run freud-schema feedback add \
  --extraction-key <key-or-prefix> --type wrong_value \
  --correction '{"field": "party", "was": "X", "should_be": "Y"}' \
  --notes "Full legal name required" --by "reviewer"

# 7. View the flywheel signal
uv run freud-schema feedback list --skill-key <key-or-prefix> --aggregate

# 8. Refine: deprecate v1, add v2 with fixes, re-extract via harness
uv run freud-schema skill deprecate <key-or-prefix>
uv run freud-schema skill add \
  --domain legal --task-type extraction \
  --content "Improved extraction instructions..." \
  --status active --version 2

# 9. Inspect session details
uv run freud-schema session show <key-or-prefix>

# Use a non-default database (--db is a global flag)
uv run freud-schema --db /tmp/test.duckdb db init

# Print full DDL (pipeable to duckdb CLI)
uv run freud-schema db ddl
uv run freud-schema db ddl | duckdb :memory:

# Nuclear option: drop and recreate all tables (destructive)
uv run freud-schema db reset
```

### Python API

```python
from freud_schema.harness import compose_preset, compose_system_prompt
from freud_schema.archetypes import get_archetype, search_archetypes

# Use a preset composition
prompt = compose_preset("careful-executor", task_context="Review this PR for bugs")

# Tree-shaped orchestrator with ephemeral subagents
prompt = compose_preset(
    "hierarchical-orchestrator",
    task_context="Decompose and execute a multi-step refactor",
)

# Pick specific archetypes
prompt = compose_system_prompt(
    ["structural-triad", "free-association", "fixation"],
    task_context="Explore this codebase",
)

# Look up individual archetypes
a = get_archetype("repetition-compulsion")
print(a.prompt_fragment)
```

## Archetypes (9, in a 3x3 grid)

| Category | Archetypes | Pattern |
|----------|-----------|---------|
| Structural | structural-triad, censor-gate, ephemeral | How agents are built |
| Behavioral | repetition-compulsion, pleasure-principle, dream-work | How agents decide |
| Diagnostic | free-association, freudian-slip, fixation | How agents explore and self-correct |

**Intra-agent** archetypes (e.g. `structural-triad`) define roles within a
single agent. **Inter-agent** archetypes (e.g. `ephemeral`) define topology
and lifecycle between agents.

## Presets (6)

| Preset | Archetypes | Use Case |
|--------|-----------|----------|
| `careful-executor` | structural-triad, censor-gate, repetition-compulsion, freudian-slip, pleasure-principle | Safety-first with loop detection |
| `creative-explorer` | free-association, dream-work, fixation | Exploratory reasoning |
| `iterative-refiner` | dream-work, pleasure-principle, freudian-slip | Feedback-driven refinement |
| `minimal-safe` | structural-triad, repetition-compulsion, pleasure-principle | Lightweight safety baseline |
| `hierarchical-orchestrator` | ephemeral, dream-work, fixation, pleasure-principle | Tree-shaped orchestrator with ephemeral subagents |
| `recursive-decomposer` | dream-work, free-association, fixation, pleasure-principle | RLM-aligned iterative decomposition |

## Experiment Harness

A Kimball-style dimensional model in DuckDB: 9 dimension tables (4 SCD Type 2 +
5 append-only registries), 11 fact tables, 10 analytical views. Behavior comes
from data (skills, rules, sources), not code. Keys are sha256/32 hash surrogates
(`keys.dimension_key()`), not sequences -- deterministic, so transcript
re-ingestion is idempotent. Fact tables carry denormalized dimension attributes
at insert time, eliminating joins, plus a lineage envelope (`record_source`,
`etl_run_id`). No FK constraints (store-layer validation instead). The CLI
exposes data operations (CRUD, review, feedback). Extraction is the harness's
job (Claude Code, Agent SDK).

Context assembly implements progressive disclosure:
**rules -> skill -> source -> task**.

| Table | Purpose |
|-------|---------|
| **SCD-2 Dimensions** | |
| `dim_skill` | Declarative instructions loaded at runtime (domain + task_type + version) |
| `dim_source` | Raw artifacts to process (file paths, MIME types, metadata) |
| `dim_rule` | Constraints applied globally or per-domain (priority-ordered), keyed by name |
| `dim_sampling_config` | Prior run sampling settings for pattern detection |
| **Registry Dimensions** | |
| `dim_project` | Conformed project dimension for cross-project queries |
| `dim_tenant` | Tenant registry -- natural keys on the four SCD-2 dims are tenant-scoped |
| `dim_facet_type` | Behavioral facet registry (tier, method, output type) |
| `dim_finding_type` | Open finding-type vocabulary (registry-validated, not an enum) |
| `dim_event_type` | Open event-type registry for the generic `fact_event` grain |
| **Facts** | |
| `fact_session` | Logged agent executions -- native runs or ingested transcripts (denormalized skill attrs, token tracking) |
| `fact_trace` | Reasoning trace tree nodes within a session |
| `fact_extraction` | Structured output from agent runs (with denormalized source/skill attrs) |
| `fact_feedback` | Human corrections on extractions (the flywheel signal) |
| `fact_trace_feedback` | Human feedback on specific trace nodes |
| `fact_message` | Transcript messages, full grain |
| `fact_tool_use` | Transcript tool_use/tool_result blocks |
| `fact_session_facets` | Behavioral facet values (EAV) |
| `fact_finding` | Detected patterns with evidence (couch output) |
| `fact_proposal` | Proposed dimension changes pending human review (evolve output) |
| `fact_event` | Generic ingested event grain -- any JSONL stream via `IngestAdapter`, not just transcripts |
| **Views** | |
| `v_feedback_by_skill` | Correction counts by skill + correction_type |
| `v_feedback_fields` | Field names mentioned in corrections by skill |
| `v_recurring_traces` | Traces that recur across sessions for a skill |
| `v_recurring_trace_feedback` | Trace feedback patterns across sessions |
| `v_skill_feedback_patterns` | Skills with feedback above threshold |
| `v_session_feedback_count` | Feedback count per session (for sampling) |
| `v_retry_loops` | Repeated identical tool calls within a session (couch detector) |
| `v_tool_error_clusters` | Tool error rates by project + tool (couch detector) |
| `v_interruption_hotspots` | Sessions with user-interrupted turns by project (couch detector) |
| `v_permission_friction` | Permission-denial clusters by project + tool (couch detector) |
| **Operational** | |
| `meta_schema_version` | Tracks schema version |
| `meta_load_log` | One row per ingest/compile run (row counts, status, errors) |
| `meta_key_algorithm` | Records the active key-hashing scheme so a database self-describes it |

Full column-level reference: `skill/reference/schema.md`.

## Project Structure

```
src/freud_schema/
  models.py          - Pydantic models (FreudEntry, AgenticArchetype)
  archetypes.py      - Registry of 9 agentic archetypes (3x3 grid)
  harness.py         - Meta-harness for composing system prompts
  dataset.py         - JSONL data loading and querying
  cli.py             - CLI interface (freud-schema)
  keys.py            - Deterministic sha256/32 surrogate keys: dimension_key(), hash_diff()
  db.py              - DuckDB schema: 4 SCD-2 dims + 5 registries + 11 facts, 10 views,
                       meta_load_log, meta_key_algorithm, CHECK constraints, indexes.
                       No sequences.
  tables.py          - Pydantic models + 20 enum classes (single source of truth for valid values)
  store.py           - CRUD with SCD-2 evolution + insert-time denormalization (ExperimentStore)
  discovery.py       - Transcript discovery (nested subagents/ layout; subagent identity
                       comes from the path, never the internal sessionId)
  ingest.py          - Ingest: transcript ingestion (idempotent by key construction) +
                       the IngestAdapter protocol (transcript and JSONL event adapters)
  couch.py           - Analyze: SQL finding detectors over the warehouse (no model calls)
  materialize.py     - Materialize: rule compiler with provenance + fail-closed privacy gate
  ops.py             - Shared write-op dispatch layer: CLI and mcp_server.py both call
                       these instead of ExperimentStore directly, so the two surfaces
                       cannot drift
  mcp_server.py      - Store-ops MCP server: read-only `query` tool + gated write tools;
                       self-modification gate lives here
  vendor/ccutils_parsers/ - Vendored transcript parsers, pinned upstream commit
  orchestrator.py    - Context assembly, provider protocol, provider implementations
  rlm.py             - RLM provider: REPL engine, sandbox, source content loading
data/
  freud_schema.jsonl - 17 core entries from Freud's works
  freudagent.duckdb  - Experiment database (gitignored)
  papers/            - Local paper/source corpora registered as dim_source rows (gitignored)
  synthetic/         - PUBLIC synthetic corpus (committed, all fictional): SaaS exports,
                       relational extracts, documents, feedback, unstructured streams,
                       JSONL event streams, plus messy/time/governance/external/eval
                       subsets for structuring, staleness, and conflict-resolution evals
tests/
  conftest.py               - Shared fixtures (in-memory DuckDB store)
  test_schema.py            - Freud corpus, archetypes, harness composition
  test_experiment.py        - DuckDB schema, store, context assembly, providers
  test_keys.py              - dimension_key()/hash_diff() determinism and NULL-safety
  test_schema_v017.py       - v0.17 DDL: SCD-2 columns, lineage envelope, new tables
  test_store_v017.py        - v0.17 store: SCD-2 evolution, registries, resolve_key
  test_rlm.py               - RLM provider, REPL loop, sandbox, source loading
  test_ingest.py            - Transcript ingestion idempotency
  test_ingest_events.py     - Generic JSONL event-stream ingestion (fact_event)
  test_events.py            - fact_event grain and dim_event_type registry
  test_couch.py             - SQL finding detectors
  test_evolve.py            - Proposal drafting and approval (SCD-2 versioning)
  test_materialize.py       - Rule compiler, provenance footers, privacy gate
  test_mcp_server.py        - Store-ops MCP server, self-modification gate
  test_tenancy.py           - Tenant-scoped natural keys and --tenant CLI scope
  test_citation_graph.py    - Corpus-wide citation edge derivation
  test_synthetic_data.py    - Synthetic-corpus guards: generator determinism, manifest
                              parity, cross-source references, event-stream ingest
  test_synthetic_internal.py    - HRIS/ITSM/finance + GL reconciliations
  test_synthetic_granularity.py - Cross-grain rollups
  test_synthetic_temporal.py    - Snapshots/staleness
  test_synthetic_conflicts.py   - Conflict schema + resolution-rule vocab
docs/
  tutorial-arxiv-extraction.md - End-to-end arxiv extraction pipeline
  tutorial-rlm-provider.md     - RLM provider: REPL loop, sub-calls, presets
  tutorial-flywheel.md         - Flywheel tutorial: feedback loop end-to-end
  tutorial-cold-start.md       - Cold-start playbook: empty DB to turning flywheel
  data-flywheel.md             - The data flywheel end to end, in plain English
  implementation-plan.md       - Milestones, schema deltas, definitions of done
  research-agent-data-representation.md - Research review validating the roadmap
  assets/                       - Diagrams referenced by data-flywheel.md (SVG)
skill/
  skill.md              - L2: routing document (CLI reference, workflow)
  reference/
    schema.md           - L3: Dimensional model, denormalization, views
    archetypes.md       - L3: 3x3 grid, presets, prompt composition
    context-assembly.md - L3: Progressive disclosure layers
    hierarchy.md        - L3: Tree architecture, harness mapping
    flywheel.md         - L3: Feedback loop, 12 atoms, correction flow
    archetype_patterns.md - L3: Detailed patterns with examples
    translation_matrix.md - L3: German-English term mapping
    retrieval-thesis.md   - L3: Progressive disclosure rationale
    trace-capture.md      - L3: Self-reporting reasoning traces
scripts/
  trace-hook.sh                - PostToolUse hook for automatic trace capture
  generate_synthetic_data.py   - Deterministic generator for data/synthetic/
  build_citation_graph.py      - Derives data/synthetic/eval/citation_edges.csv
a2ui/                 - MCP server + Lit client for A2UI visual surfaces
internal/             - Analysis docs, backlog, session logs (gitignored)
.claude/
  skills/            - Project-specific Claude Code skills (db-query.md, couch.md)
  rules/             - Compiled rule output from dim_rule (committed; do not edit by hand)
  settings.local.json - Personal permissions (gitignored)
.mcp.json             - MCP server config: freud-schema mcp-serve (committed)
```

## Development

```bash
uv sync --extra dev
uv run pytest tests/ -v
```

Core dependencies: pydantic >= 2.0, duckdb >= 0.9, orjson >= 3.9.

Optional dependencies:
```bash
uv sync --extra anthropic   # Claude API
uv sync --extra local       # OpenAI-compatible endpoints (httpx)
uv sync --extra mcp         # Store-ops MCP server (freud-schema mcp-serve)
```

## License

MIT
