# FreudAgent

Mostly a joke repo.

Satirical experiment and meta-harness for data-driven agent orchestration, grounded in an inside joke of
Freudian archetypes. Not a framework, but a satirical test bed for answering: "Does declarative
data-driven orchestration produce measurably better results than code-driven workflow approaches?"

But still mostly a joke repo. Becoming less so over time though. Weird.

## Project Structure

```
src/freud_schema/
  models.py          - Pydantic models (FreudEntry, AgenticArchetype)
  archetypes.py      - Registry of 9 agentic archetypes (3x3 grid)
  harness.py         - Meta-harness for composing system prompts
  dataset.py         - JSONL data loading and querying
  cli.py             - CLI interface
  db.py              - DuckDB schema (7 tables), CHECK/FK constraints, DDL generation
  tables.py          - Pydantic models + enum classes (single source of truth for valid values)
  store.py           - CRUD operations with generic dict-based row conversion
  orchestrator.py    - Provider protocol, orchestrator loop + subagent runner
  rlm.py             - RLM provider: REPL engine, sandbox, source content loading
data/
  freud_schema.jsonl - 17 core entries from Freud's works
  freudagent.duckdb  - Experiment database (gitignored)
tests/
  test_schema.py     - Freud corpus, archetypes, harness composition
  test_experiment.py - DuckDB schema, store, orchestrator, providers
  test_rlm.py        - RLM provider, REPL loop, sandbox, source loading
skill/
  skill.md           - Claude Code skill definition
  reference/         - Archetype patterns, translation matrix
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
internal/            - Analysis docs, backlog, session logs (gitignored)
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
- Experiment tests use in-memory DuckDB (`:memory:`)
- No phantom dependencies -- only add to `pyproject.toml` what the code actually imports
- New tables must be added to the drop list in `reset_schema()` (order matters: drop dependents first)
- No migration path -- breaking schema changes use `reset_schema()` (experiment repo, no legacy data)
- DDL is stored as `list[str]` (one statement per element, no semicolon splitting)
- `freud-schema db ddl` prints full DDL for piping to `duckdb` CLI
- 8 enum classes in `tables.py` are the single source of truth for valid column values
- CHECK constraints and FK constraints are generated from enums and embedded in DDL
- Store uses `cursor.description` for column-name-keyed dicts (no positional indexing)
- All SQL queries use parameterized enum values (no hardcoded string literals)
- All CLI `--status`/`--scope`/`--type` args must have `choices=[e.value for e in EnumClass]`
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

The harness implements declarative agent orchestration: behavior comes from data
(skills, rules, sources), not code. The schema is the architecture.

| Table | Purpose |
|-------|---------|
| meta_schema_version | Tracks schema version for `db status` |
| skills | Declarative instructions loaded at runtime (domain + task_type + version) |
| sources | Raw artifacts to process (file paths, MIME types, metadata) |
| extractions | Structured output from agent runs (with validation status) |
| sessions | Logged agent executions (orchestrator + subagent, token tracking) |
| feedback | Human corrections on extractions (the flywheel signal) |
| rules | Constraints applied globally or per-domain (priority-ordered) |

### Schema Management

No migration path. For breaking changes, use `freud-schema db reset`.
`meta_schema_version` tracks the schema version for `db status`.
`init_schema()` uses `CREATE TABLE IF NOT EXISTS` (idempotent).
`reset_schema()` drops and recreates everything.

CLI workflow: `db init` -> `rule add` -> `skill add` -> `source add` -> `run` -> `extraction list/show/validate` -> `feedback add`

`--db` is a global flag on the root parser (before the subcommand). All handlers use it consistently.

Execution: `freud-schema run --domain D --task-type T [--model echo|anthropic|local] [--endpoint URL]`
Review: `freud-schema extraction list`, `extraction show N`, `extraction validate N`
Feedback: `freud-schema feedback add --extraction-id N --type T --correction '{...}'`
History: `freud-schema session list`

## Architecture Notes

Archetypes span two scopes:
- **Intra-agent** (`structural-triad`): roles within a single agent
- **Inter-agent** (`ephemeral`): hierarchical topology and ephemeral subagent lifecycle

The orchestrator uses archetype-composed system prompts for its own behavior.
Subagents use the progressive disclosure hierarchy: rules -> skill -> source -> task.
Model calls are pluggable via the `Provider` protocol (3 built-in: `EchoProvider`, `ClaudeProvider`,
`OpenAICompatProvider`; 1 wrapper: `RLMProvider`). The code is a thin loop; behavior is data.

`RLMProvider` wraps any inner provider with a Python REPL loop: the model writes code to
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
