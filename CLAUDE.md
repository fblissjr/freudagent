# FreudAgent

Pure data layer for declarative agent orchestration. Lives INSIDE the harness
(Claude Code, Agent SDK), not outside it. Schema, context assembly, archetypes,
prompt composition. The harness orchestrates. FreudAgent provides data.

Mostly a joke repo. But the thesis is serious: agents are trees, not workflows.
The harness is the moat. Behavior comes from data (skills, rules, archetypes), not code.

The data FreudAgent provides is the **grounding layer**: constraints on one end
(rules, activation conditions, policies), grounding data in the middle (validated
knowledge, evidence, provenance), and verifiers and feedback on the other (eval
gates, corrections, usage signals). The warehouse is its governed source of truth;
compiled files are its agent-facing form.

## Project Structure

```
src/freud_schema/
  cli.py             - CLI interface (freud-schema)
  keys.py            - Deterministic sha256/32 surrogate keys: dimension_key(), hash_diff()
  db.py              - DuckDB schema: 4 SCD-2 dims (tenant-scoped natural keys) + 4
                       registries (incl. dim_tenant) + 10 facts, 10 views, meta_load_log,
                       meta_key_algorithm, CHECK constraints, indexes. No sequences.
  tables.py          - Pydantic models + 20 enum classes (single source of truth)
  store.py           - CRUD with SCD-2 evolution + insert-time denormalization (ExperimentStore)
  discovery.py       - Transcript discovery (nested subagents/ layout; subagent identity
                       from the path, never the internal sessionId -- it's the parent's)
  ingest.py          - Sense: transcript ingestion, idempotent by key construction
  couch.py           - Analyze: SQL finding detectors; thresholds live here, never in view DDL
  materialize.py     - Materialize: rule compiler with provenance + fail-closed privacy gate
  vendor/ccutils_parsers/ - Vendored transcript parsers, pinned upstream commit --
                       do not edit here, sync from upstream
  orchestrator.py    - Context assembly, provider protocol, provider implementations
  harness.py         - Archetype composition into system prompts
  archetypes.py      - 9 archetypes in a 3x3 grid
  models.py          - Pydantic models (FreudEntry, AgenticArchetype)
  dataset.py         - JSONL data loading and querying
  rlm.py             - RLM provider: REPL engine, sandbox
data/
  freud_schema.jsonl - 17 core entries from Freud's works
  freudagent.duckdb  - Live warehouse incl. ingested personal transcripts (gitignored)
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
  tutorial-cold-start.md       - Cold-start playbook: empty DB to turning flywheel
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
- `[tool.pytest.ini_options]` in pyproject.toml anchors the rootdir -- without it, collection
  escapes into the parent directory (itself a Python project) and every test fails at import
- Install: `uv sync --extra dev`
- Optional: `uv sync --extra anthropic` (Claude API), `uv sync --extra local` (httpx)

## CLI Quick Reference

`--db` is a global flag (before the subcommand). Defaults to `data/freudagent.duckdb`.

Workflow: `db init` -> `rule add` -> `skill add` -> `source add` -> harness extracts -> `extraction list/show/validate` -> `feedback add` -> `skill add --version N` (SCD-2: the new version automatically closes the prior row; no manual deprecate step)

Full CLI reference is in `skill/skill.md`. Key commands:

- `freud-schema extraction list|show|validate|reject` (keys or unique prefixes, git-short-hash style)
- `freud-schema feedback add --extraction-key <key-or-prefix> --type T --correction '{...}'`
- `freud-schema skill add|list|deprecate|activate` (add supports `--version N`)
- `freud-schema session list|show`
- `freud-schema ingest transcripts [--project] [--since]` (idempotent; CLI-only, needs the DB lock)
- `freud-schema couch run|list` (SQL detectors -> fact_finding, no model calls)
- `freud-schema proposal add|list|show|approve|reject` / `freud-schema compile --out DIR`

## DuckDB MCP

DuckDB is single-process -- only one connection per file. The MCP server holds it
during Claude Code sessions, so the `freud-schema` CLI cannot access the same DB file.

**Always use MCP tools for database access:**

- `mcp__duckdb__execute_query` -- Run any SQL (SELECT, INSERT, UPDATE, DELETE, DDL)
- `mcp__duckdb__list_tables` -- List all tables in the database
- `mcp__duckdb__list_columns` -- Show columns of a specific table

Do NOT shell out to `freud-schema` CLI for any command that touches the database --
every subcommand except `db ddl` opens a connection and will fail with a lock error.

- `execute_query` accepts multi-statement SQL.
- Lock workaround for CLI-only ops (ingest, compile): run them against a scratch DB
  file, then `ATTACH` it read-only from the MCP connection and `INSERT INTO` the live
  tables -- deterministic keys make the copy idempotent.

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
- 20 enum classes in `tables.py` are the single source of truth; CHECK constraints generated from them
- `finding_type` is deliberately NOT an enum: open vocabulary, registry-validated against `dim_finding_type` in the store (new finding types are rows, not code)
- No FK constraints (DuckDB can't CASCADE anyway) -- existence validated in store layer
- Fact tables carry denormalized dimension attributes populated at insert time
- 10 analytical views replace complex aggregation queries (no N+1 patterns); couch views are consumed only through the store's `query_*` methods
- Prior run context uses `_SIGNAL_TRACE_TYPES` to filter traces -- only decision_point, dead_end, insight, conclusion, subagent_spawn appear in system prompts. Don't add tool_call/path_taken/path_discarded.
- Providers: dynamic imports inside `__init__`, raise `ImportError` with install hint
- `get_provider()` is the only provider factory

### Store / DB
- All DB access through `ExperimentStore` methods -- never `store.con.execute` directly
- Store uses `cursor.description` for column-name-keyed dicts (no positional indexing)
- All SQL uses parameterized enum values (no hardcoded string literals)
- Keys: SHA-256/32 hash surrogates via `keys.dimension_key()` (sha256 hexdigest truncated
  to 32 chars; `keys.KEY_ALGORITHM` names the scheme, recorded in `meta_key_algorithm`).
  Entity keys from natural keys, tenant-leading on the four SCD-2 dims (skill =
  tenant|domain|task_type, rule = tenant|name, source = tenant|content_path). Ingested
  facts get deterministic keys (idempotent re-ingest); native facts get uuid-salted keys
- Naming: `etl_run_id` = lineage (joins `meta_load_log`); `session_key` = harness session.
  `session_id` is banned from DDL
- SCD-2 dims: changes close the current row and insert a new one; rows never mutate.
  Query current state with `is_current`. Facts are append-only EXCEPT `fact_session`
  (accumulating snapshot: status/result/completed_at update in place)
- Denormalization: use `_resolve_skill_attrs()` for skill lookups on fact inserts. Don't `_require()` + `get_skill()` separately -- the denormalization fetch validates existence as a side effect
- Existence validation: only use `_require()` when no denormalization fetch covers that reference (e.g., session_key on extractions has no denormalization)
- Views: `CREATE OR REPLACE` only -- `IF NOT EXISTS` pins stale definitions in existing DBs
- `ALL_TABLES`/`ALL_VIEWS` in db.py are the canonical inventories (`reset_schema()`,
  `db status`, and the inventory test consume them) -- register new tables/views there
- One write path per table: single-row inserts delegate to batch methods; batch inserts
  are single-session (guarded)
- New ingest/analysis operations wrap in `store.load_run()` (typed LoadRunStats -> meta_load_log)
- Reference keys via the named recipes (`session_key_for`, `message_key_for`) -- never
  re-derive dimension_key formulas at call sites
- After `store.insert_*()`, use `model.model_copy(update={"<table>_key": new_key})` instead of re-fetching
- No migration path, by explicit policy (owner decision, 2026-07-08): this is a research
  repo, never prod. All warehouse data is disposable test/research data -- breaking schema
  changes use `reset_schema()` + re-ingest (deterministic keys make re-ingest idempotent).
  Do NOT build migration machinery or data-preservation paths. Git history of code and
  git-tracked artifacts is the only history that matters. If this ever changes, the owner
  will say so explicitly.
- Standard schema-change recipe: edit DDL in db.py (register new tables in `ALL_TABLES`
  and the `reset_schema()` drop list, new views in `ALL_VIEWS`, bump `_SCHEMA_VERSIONS`
  on breaking change) -> reset (`db reset` from the CLI, or `reset_schema()`'s DDL via
  `execute_query` when the MCP server holds the lock) -> `ingest transcripts` ->
  `couch run` -> recreate whatever native test rows (skills/rules/feedback/proposals)
  the current experiment needs
- New tables must be added to `reset_schema()` drop list (order matters: dependents first)
- DDL stored as `list[str]` (one statement per element, no semicolon splitting)

### Privacy
- `data/freudagent.duckdb` holds personal transcript content -- gitignored, and transcript
  text must never be quoted into committed files, commit messages, or finding summaries
- Finding summaries and compiled artifacts are clean by construction (tool names, counts,
  rates only); `compile`'s privacy gate is fail-closed, not advisory

### CLI
- `--status`/`--scope`/`--type` args must use `choices=[e.value for e in EnumClass]`
- Handlers that modify by key resolve prefixes via `store.resolve_key()` first and `sys.exit(1)` on no-match/ambiguity
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
