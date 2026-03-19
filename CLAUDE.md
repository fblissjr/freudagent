# FreudAgent

Pure data layer for declarative agent orchestration. Lives INSIDE the harness
(Claude Code, Agent SDK), not outside it. Schema, context assembly, archetypes,
prompt composition. The harness orchestrates. FreudAgent provides data.

Mostly a joke repo. But the thesis is serious: agents are trees, not workflows.
The harness is the moat. Behavior comes from data (skills, rules, archetypes), not code.

## Project Structure

```
src/freud_schema/
  cli.py             - CLI interface (freud-schema)
  db.py              - DuckDB schema: 4 dim + 5 fact tables, 6 views, CHECK constraints, indexes
  tables.py          - Pydantic models + 12 enum classes (single source of truth)
  store.py           - CRUD operations with insert-time denormalization (ExperimentStore)
  orchestrator.py    - Context assembly, provider protocol, provider implementations
  harness.py         - Archetype composition into system prompts
  archetypes.py      - 9 archetypes in a 3x3 grid
  models.py          - Pydantic models (FreudEntry, AgenticArchetype)
  dataset.py         - JSONL data loading and querying
  rlm.py             - RLM provider: REPL engine, sandbox
data/
  freud_schema.jsonl - 17 core entries from Freud's works
  freudagent.duckdb  - Experiment database (gitignored)
tests/
  conftest.py        - Shared fixtures (in-memory DuckDB store)
  test_schema.py     - Corpus, archetypes, harness composition
  test_experiment.py - Schema, store, context assembly, providers, CLI
  test_rlm.py        - RLM provider tests
skill/
  skill.md           - L2: CLI reference, routing table to L3 references
  reference/         - L3: schema, archetypes, hierarchy, flywheel, retrieval thesis, trace-capture, etc.
scripts/
  trace-hook.sh      - PostToolUse hook for automatic tool_call trace capture
docs/
  tutorial-arxiv-extraction.md - End-to-end extraction pipeline
  tutorial-rlm-provider.md     - RLM provider tutorial
  tutorial-flywheel.md         - Feedback loop end-to-end
a2ui/                - MCP server + Lit client for A2UI visual surfaces
internal/            - Analysis docs, backlog, session logs (gitignored)
.claude/
  skills/            - Project-specific Claude Code skills (committed)
  settings.local.json - Personal permissions (gitignored)
```

## Development

- Python >= 3.10, Pydantic >= 2.0, DuckDB >= 0.9, orjson >= 3.9
- Package manager: **uv** (always use `uv run`, `uv sync`, `uv pip`)
- Tests: `uv run pytest tests/`
- Install: `uv sync --extra dev`
- Optional: `uv sync --extra anthropic` (Claude API), `uv sync --extra local` (httpx)

## CLI Quick Reference

`--db` is a global flag (before the subcommand). Defaults to `data/freudagent.duckdb`.

Workflow: `db init` -> `rule add` -> `skill add` -> `source add` -> harness extracts -> `extraction list/show/validate` -> `feedback add` -> `skill deprecate` -> `skill add --version N`

Full CLI reference is in `skill/skill.md`. Key commands:

- `freud-schema extraction list|show|validate|reject`
- `freud-schema feedback add --extraction-id N --type T --correction '{...}'`
- `freud-schema skill add|list|deprecate|activate` (add supports `--version N`)
- `freud-schema session list|show`

## DuckDB MCP

DuckDB is single-process -- only one connection per file. The MCP server holds it
during Claude Code sessions, so the `freud-schema` CLI cannot access the same DB file.

**Always use MCP tools for database access:**

- `mcp__duckdb__execute_query` -- Run any SQL (SELECT, INSERT, UPDATE, DELETE, DDL)
- `mcp__duckdb__list_tables` -- List all tables in the database
- `mcp__duckdb__list_columns` -- Show columns of a specific table

Do NOT shell out to `freud-schema` CLI for any command that touches the database --
every subcommand except `db ddl` opens a connection and will fail with a lock error.

Claude Code IS the harness. Orchestration happens natively (Agent tool, Read tool,
MCP tools). The CLI exposes data operations (CRUD on skills/sources/rules/feedback/
extractions/sessions, corpus queries, archetype commands) but not execution pipelines.

**Outside Claude Code (scripts, CI, terminal):** Use the `freud-schema` CLI for data management.

Schema docs: `.claude/skills/db-query.md`

## Conventions

### Code
- Models: Pydantic v2 (`model_validate`, `model_dump`), `Field(default_factory=list)` for lists
- JSON: **orjson** (not json)
- Enums: construct with members (`SkillStatus.ACTIVE`), never bare strings
- 12 enum classes in `tables.py` are the single source of truth; CHECK constraints generated from them
- No FK constraints (DuckDB can't CASCADE anyway) -- existence validated in store layer
- Fact tables carry denormalized dimension attributes populated at insert time
- 6 analytical views replace complex aggregation queries (no N+1 patterns)
- Prior run context uses `_SIGNAL_TRACE_TYPES` to filter traces -- only decision_point, dead_end, insight, conclusion, subagent_spawn appear in system prompts. Don't add tool_call/path_taken/path_discarded.
- Providers: dynamic imports inside `__init__`, raise `ImportError` with install hint
- `get_provider()` is the only provider factory

### Store / DB
- All DB access through `ExperimentStore` methods -- never `store.con.execute` directly
- Store uses `cursor.description` for column-name-keyed dicts (no positional indexing)
- All SQL uses parameterized enum values (no hardcoded string literals)
- Denormalization: use `_resolve_skill_attrs()` for skill lookups on fact inserts. Don't `_require()` + `get_skill()` separately -- the denormalization fetch validates existence as a side effect
- Existence validation: only use `_require()` when no denormalization fetch covers that reference (e.g., session_id on extractions has no denormalization)
- New views must be added to `reset_schema()` drop list (before tables) and to `_ALL_DDL`
- After `store.insert_*()`, use `model.model_copy(update={"id": new_id})` instead of re-fetching
- No migration path -- breaking changes use `reset_schema()` (experiment repo, no legacy data)
- New tables must be added to `reset_schema()` drop list (order matters: dependents first)
- DDL stored as `list[str]` (one statement per element, no semicolon splitting)

### CLI
- `--status`/`--scope`/`--type` args must use `choices=[e.value for e in EnumClass]`
- Handlers that modify by ID must check existence first and `sys.exit(1)` if not found
- CLI exposes data operations only -- no execution/orchestration commands (harness's job)

### Tests
- Module-scoped `entries` fixture for JSONL (no repeated `load_entries()`)
- In-memory DuckDB (`:memory:`) for store tests, `tmp_path` for CLI end-to-end tests
- `ExperimentStore` in tests must use `with` blocks or explicit `.close()` (matches CLI handlers)

### Versioning
- Version must stay in sync across `pyproject.toml`, `skill/skill.md` frontmatter, and `CHANGELOG.md`
- No phantom dependencies -- only add to `pyproject.toml` what the code actually imports

### Documentation (skill/reference/)
- schema.md omits `NOT NULL`/`DEFAULT`/`created_at`/`updated_at` boilerplate for readability -- this is intentional
- schema.md column order is logical grouping, not DDL order -- don't "fix" it to match db.py
- schema.md Common Queries use string literals (example SQL for MCP users) -- the "no hardcoded strings" convention applies to store.py, not doc examples
- schema.md Enum Values table must list every column with a CHECK constraint
- prompt_addendum.md (a2ui/) is LLM context for A2UI surface generation -- keep types/columns in sync with schema.md

## Internal Docs

All in `internal/` (gitignored). Read before proposing new work.

- `BACKLOG.md` -- known gaps, deferred work. Check here before suggesting features. Mark items DONE with version when resolved.
- `log/` -- session logs
- `flywheel_decomposition.json` -- 12-atom decomposition mapping to Agent SDK primitives
