# FreudAgent

A meta-framework for declarative agent orchestration that lives INSIDE the harness
(Claude Code, Agent SDK), not outside it. Pure data layer: schema, context assembly,
prompt composition. The harness handles orchestration. FreudAgent handles data.

Mostly a joke repo. But the thesis is serious.

## Thesis

Agents are trees, not workflows. The harness is the moat. Build inside it with data
and structure, don't wrap it.

- **The meta-framework is inside the harness, not outside it.** FreudAgent doesn't
  orchestrate -- the harness does. FreudAgent provides what the harness needs: skills,
  rules, sources, archetypes, and assembled context.
- **Every handoff is where it breaks.** Pipelines (A -> B -> C) degrade context at
  each hop. Trees return through the parent, preserving integrity.
- **Behavior comes from data, not code.** The schema IS the architecture. Skills are
  instructions, rules are constraints, archetypes are behavioral shaping -- all data.

## What FreudAgent Provides (the data layer)

- **7-table DuckDB schema**: skills, sources, extractions, sessions, feedback, rules,
  meta_schema_version
- **Context assembly**: `assemble_runner_context()` implements progressive disclosure
  (rules -> skill -> source -> task)
- **9 Freudian archetypes** in a 3x3 grid (composable prompt fragments)
- **6 presets** (archetype compositions for common agent patterns)
- **CLI** for data management and inspection (`freud-schema`)
- **Test providers** for verifying context assembly (echo, plus optional Claude/local/RLM)

## What FreudAgent Does NOT Provide (the harness's job)

- Orchestration (task decomposition, routing, looping)
- Agent lifecycle (spawning, scoping, cleanup)
- Execution decisions (which subagent for which task)

The CLI `run` command is a **test utility** that proves context assembly works.
It calls a provider once per source. It is not orchestration.

## Progressive Disclosure Hierarchy

| Level | What | FreudAgent Example |
|-------|------|-------------------|
| L1 | Always loaded | CLAUDE.md, skill frontmatter, rules |
| L2 | Loaded on match | `skill/skill.md` body (CLI reference, workflow) |
| L3 | Loaded on demand | `skill/reference/*.md` (schema, archetypes, hierarchy, flywheel, retrieval thesis) |

This applies to FreudAgent's own skill structure: the frontmatter triggers on
activation keywords, the body routes to references, references provide depth.

## How the Harness Consumes FreudAgent

| Harness | How |
|---------|-----|
| Claude Code | skill.md as L2, references as L3, DuckDB via MCP/CLI |
| Agent SDK | 12 flywheel atoms map to agents/tools/handoffs |
| CLI test utility | `freud-schema run` verifies context assembly with pluggable providers |

## Project Structure

```
src/freud_schema/
  models.py          - Pydantic models (FreudEntry, AgenticArchetype)
  archetypes.py      - Registry of 9 agentic archetypes (3x3 grid)
  harness.py         - Meta-harness for composing system prompts
  dataset.py         - JSONL data loading and querying
  cli.py             - CLI interface
  db.py              - DuckDB schema (7 tables), CHECK/FK constraints, DDL generation
  tables.py          - Pydantic models + enum classes (single source of truth)
  store.py           - CRUD operations with generic dict-based row conversion
  orchestrator.py    - Context assembly, provider protocol, test utility
  rlm.py             - RLM provider: REPL engine, sandbox, source content loading
data/
  freud_schema.jsonl - 17 core entries from Freud's works
  freudagent.duckdb  - Experiment database (gitignored)
tests/
  test_schema.py     - Freud corpus, archetypes, harness composition
  test_experiment.py - DuckDB schema, store, context assembly, providers
  test_rlm.py        - RLM provider, REPL loop, sandbox, source loading
skill/
  skill.md              - L2: routing document (CLI reference, workflow)
  reference/
    schema.md           - L3: DuckDB schema, enums, FK relationships
    archetypes.md       - L3: 3x3 grid, presets, prompt composition
    context-assembly.md - L3: Progressive disclosure layers
    hierarchy.md        - L3: Tree architecture, harness mapping
    flywheel.md         - L3: Feedback loop, 12 atoms, correction flow
    archetype_patterns.md - L3: Detailed patterns with examples
    translation_matrix.md - L3: German-English term mapping
    retrieval-thesis.md   - L3: Progressive disclosure rationale, skills as retrieval
a2ui/
  server.py          - MCP server (stdio + HTTP modes)
  bridge.py          - A2UI v0.9 structural validator
  queries.py         - Data access layer (ExperimentStore -> dicts)
  adapter.py         - v0.9-to-v0.8 message translator for @a2ui/lit
  providers.py       - A2UI LLM providers (echo, Claude, Gemini)
  prompt.py          - System prompt assembly from skill files
  prompt_addendum.md - FreudAgent data shapes for LLM context
  client/            - Vite + Lit client (builds to static/)
  tests/             - Adapter, bridge, provider tests
docs/
  tutorial-arxiv-extraction.md - End-to-end tutorial using an arxiv paper
  tutorial-rlm-provider.md     - RLM provider tutorial: REPL loop, sub-calls, presets
  tutorial-flywheel.md         - Flywheel tutorial: feedback loop end-to-end
internal/            - Analysis docs, backlog, session logs (gitignored)
.claude/
  skills/            - Project-specific Claude Code skills (committed)
  settings.local.json - Personal permission settings (gitignored)
```

## Development

- Python >= 3.10, Pydantic >= 2.0, DuckDB >= 0.9, orjson >= 3.9
- Package manager: **uv** (always use `uv run`, `uv sync`, `uv pip`)
- Tests: `uv run pytest tests/`
- Install: `uv sync --extra dev`
- Optional provider deps: `uv sync --extra anthropic` (Claude API), `uv sync --extra local` (httpx for OpenAI-compat)

## Conventions

- Models use Pydantic v2 (`model_validate`, `model_dump`)
- List fields use `Field(default_factory=list)`, never bare `[]` defaults
- Data stored as JSONL (one JSON object per line) for Freud corpus
- Experiment data stored in DuckDB (7-table schema)
- JSON serialization: **orjson** (not json)
- Archetype names use kebab-case: `structural-triad`, `dream-work`
- Categories use the `ArchetypeCategory` enum (3 categories: STRUCTURAL, BEHAVIORAL, DIAGNOSTIC)
- `related_archetypes` must be bidirectional: if A lists B, B must list A
- Tests use a module-scoped `entries` fixture for JSONL data (no repeated `load_entries()` calls)
- Experiment tests use in-memory DuckDB (`:memory:`) for store-level tests, `tmp_path` for CLI end-to-end tests
- No phantom dependencies -- only add to `pyproject.toml` what the code actually imports
- New tables must be added to the drop list in `reset_schema()` (order matters: drop dependents first)
- No migration path -- breaking schema changes use `reset_schema()` (experiment repo, no legacy data)
- DDL is stored as `list[str]` (one statement per element, no semicolon splitting)
- `freud-schema db ddl` prints full DDL for piping to `duckdb` CLI
- Version must stay in sync across `pyproject.toml`, `skill/skill.md` frontmatter, and `CHANGELOG.md`
- 8 enum classes in `tables.py` are the single source of truth for valid column values
- CHECK constraints and FK constraints are generated from enums and embedded in DDL
- All DB access goes through `ExperimentStore` methods -- never use `store.con.execute` directly
- After `store.insert_*()`, use `model.model_copy(update={"id": new_id})` instead of re-fetching from DB
- Construct Pydantic models with enum members (`SkillStatus.ACTIVE`), not string literals (`"active"`)
- Store uses `cursor.description` for column-name-keyed dicts (no positional indexing)
- All SQL queries use parameterized enum values (no hardcoded string literals)
- All CLI `--status`/`--scope`/`--type` args must have `choices=[e.value for e in EnumClass]`
- CLI handlers that modify a record by ID must check existence first and `sys.exit(1)` if not found
- For ad-hoc DB queries, use the `duckdb` MCP tools -- do not write Python scripts
- Providers use dynamic imports (`anthropic`, `httpx`) -- import inside `__init__`, raise `ImportError` with install hint
- New providers implement the `Provider` protocol (required: `complete(system, user) -> CompletionResult`; optional: `complete_chat(messages) -> CompletionResult` for multi-turn)
- `get_provider()` is the only factory -- add new provider names there, not ad-hoc constructors
- RLM providers (`rlm`, `rlm-anthropic`) wrap an inner provider with a REPL loop; `complete_chat()` preferred, fallback to flattened single-turn

## Archetypes (9, in a 3x3 grid)

| Category | Archetypes | Pattern |
|----------|-----------|---------|
| Structural | structural-triad, censor-gate, ephemeral | How agents are built |
| Behavioral | repetition-compulsion, pleasure-principle, dream-work | How agents decide |
| Diagnostic | free-association, freudian-slip, fixation | How agents explore and self-correct |

## Presets (6)

- `careful-executor` -- safety-first with loop detection and termination
- `creative-explorer` -- exploratory reasoning with resource awareness
- `iterative-refiner` -- feedback-driven refinement with diagnostic analysis
- `minimal-safe` -- lightweight safety baseline
- `hierarchical-orchestrator` -- tree-shaped orchestrator with ephemeral subagents
- `recursive-decomposer` -- RLM-aligned: condensation, exploration, attention, completion

## Experiment Harness (7-table schema)

The schema IS the architecture. Behavior comes from data (skills, rules, sources), not code.

| Table | Purpose |
|-------|---------|
| meta_schema_version | Tracks schema version for `db status` |
| skills | Declarative instructions loaded at runtime (domain + task_type + version) |
| sources | Raw artifacts to process (file paths, MIME types, metadata) |
| extractions | Structured output from agent runs (with validation status) |
| sessions | Logged agent executions (token tracking) |
| feedback | Human corrections on extractions (the flywheel signal) |
| rules | Constraints applied globally or per-domain (priority-ordered) |

### Schema Management

No migration path. For breaking changes, use `freud-schema db reset`.
`meta_schema_version` tracks the schema version for `db status`.
`init_schema()` uses `CREATE TABLE IF NOT EXISTS` (idempotent).
`reset_schema()` drops and recreates everything.

CLI workflow: `db init` -> `rule add` -> `skill add` -> `source add` -> `run` -> `extraction list/show/validate` -> `feedback add` -> `skill deprecate` -> `skill add --version N`

`--db` is a global flag on the root parser (before the subcommand). All handlers use it consistently.

Test execution: `freud-schema run --domain D --task-type T [--model echo|anthropic|local|rlm|rlm-anthropic] [--endpoint URL] [--max-iterations N] [--sub-model NAME]`
Review: `freud-schema extraction list`, `extraction show N`, `extraction validate N`
Feedback: `freud-schema feedback add --extraction-id N --type T --correction '{...}'`
Skill lifecycle: `freud-schema skill deprecate N`, `skill activate N`
History: `freud-schema session list`, `session show N`

## Architecture Notes

The code is a thin data layer; behavior is data:
- `assemble_runner_context()` in `orchestrator.py` -- core context assembly
- `compose_preset()` in `harness.py` -- archetype composition
- `ExperimentStore` in `store.py` -- all CRUD operations
- `get_provider()` in `orchestrator.py` -- provider factory
- `run_single()` in `orchestrator.py` -- test utility (single-shot, not orchestration)

Archetypes span two scopes:
- **Intra-agent** (`structural-triad`): roles within a single agent
- **Inter-agent** (`ephemeral`): hierarchical topology and ephemeral subagent lifecycle

RLMProvider wraps any inner provider with a Python REPL loop: the model writes code to
probe, slice, and transform its input, can recursively call itself via `llm_query()`, and
terminates with `FINAL()`/`FINAL_VAR()`. Sandboxed by default (restricted builtins, timeout).
Use `--model rlm` (local MLX) or `--model rlm-anthropic` (Claude API).

## DuckDB MCP Server

The `duckdb` MCP server (mcp-server-motherduck) is configured for this project.
It connects to `data/freudagent.duckdb` with read-write access.

Use the MCP tools for ad-hoc queries instead of writing Python scripts:
- `execute_query` -- run any DuckDB SQL
- `list_tables` -- show all tables
- `list_columns` -- show columns of a table

The `db-query` skill (`.claude/skills/db-query.md`) documents the schema,
enum values, FK relationships, and common queries. Use it when inspecting
experiment data.

For a standalone SQL file: `freud-schema db ddl | duckdb :memory:`

## Internal Docs

All in `internal/` (gitignored). Read these before proposing new work.

- `BACKLOG.md` -- known gaps, deferred work, north star architecture. Check here before
  suggesting features; many are already documented or explicitly deferred.
- `log/` -- session logs tracking what was done and why per working session
- `research/` -- discussion transcripts and analysis docs from the meta-framework thesis
- `flywheel_decomposition.json` -- 12-atom decomposition of the feedback flywheel,
  maps to Agent SDK primitives. Referenced by BACKLOG.md for the Agent SDK harness adapter.
