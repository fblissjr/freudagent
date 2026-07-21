# FreudAgent

A data layer for agent systems, living inside the harness rather than wrapping
it. The harness orchestrates; this holds the schema, the context assembly, and
the governed knowledge the agent loads. Behavior comes from data — skills,
rules, findings — not from code.

Mostly a joke repo. The thesis is serious and it is not restated here:
`docs/data-flywheel.md` is the source of truth for the design, and the README is
the shorter version of it. The one term worth knowing before reading either is
the **grounding layer** — the governed data between raw sources and the agent,
with constraints at both ends and checked knowledge between them. This file is
conventions and a map, nothing more.

## Project Structure

```
src/freud_schema/
  cli.py             - CLI interface (freud-schema)
  keys.py            - Deterministic sha256/32 surrogate keys: dimension_key(), hash_diff()
  db.py              - DuckDB schema: 4 SCD-2 dims (tenant-scoped natural keys) + 5
                       registries (incl. dim_tenant, dim_event_type) + 11 facts (incl.
                       fact_event), 10 views, meta_load_log, meta_key_algorithm, CHECK
                       constraints, indexes. No sequences.
  tables.py          - Pydantic models + 20 enum classes (single source of truth)
  store.py           - CRUD with SCD-2 evolution + insert-time denormalization (ExperimentStore)
  discovery.py       - Transcript discovery (nested subagents/ layout; subagent identity
                       from the path, never the internal sessionId -- it's the parent's)
  ingest.py          - Ingest: transcript ingestion (idempotent by key construction) +
                       the IngestAdapter protocol (TranscriptAdapter, JsonlEventAdapter)
                       for the generic fact_event grain
  couch.py           - Analyze: SQL finding detectors; thresholds live here, never in view DDL
  materialize.py     - Compile: rule compiler with provenance; the privacy gate refuses
                       rather than degrades
  ops.py             - Shared write-op dispatch layer: CLI and mcp_server.py both call
                       these instead of ExperimentStore directly, so the two surfaces
                       cannot drift
  mcp_server.py      - Store-ops MCP server (M16): read-only `query` tool + gated write
                       tools; self-modification gate lives here (rule_add/skill_add force
                       non-compiling statuses; proposal_approve is the one
                       step only a person can do)
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
  synthetic/         - PUBLIC synthetic corpus (committed, all fictional; see its
                       README): SaaS exports, relational extracts, documents,
                       human feedback, unstructured streams, and JSONL event
                       streams shaped for `ingest events` -- dev/eval data for
                       the flywheel. Also: messy/ + drive_chaos/ (real-world
                       formats -- OCR, XML, ICS, SQL dumps, mbox, near-dup
                       drafts -- for structuring evals), time/ (page histories,
                       org/roadmap snapshots, policy supersession -- staleness),
                       and governance/ + external/ + eval/ (system-of-record and
                       source-authority registries, a DACI decision log, and
                       eval/conflicts.jsonl -- the conflict-resolution answer key
                       + eval/citation_edges.csv source-centrality graph). Volume
                       files regenerate deterministically via
                       scripts/generate_synthetic_data.py; documents are
                       hand-authored and cross-reference generated IDs
tests/
  conftest.py        - Shared fixtures (in-memory DuckDB store)
  test_schema.py     - Corpus, archetypes, harness composition
  test_experiment.py - Schema, store, context assembly, providers, CLI
  test_rlm.py        - RLM provider tests
  test_synthetic_data.py - Synthetic-corpus guards: generator determinism,
                       manifest/disk parity, cross-source references, event
                       streams ingest idempotently. Companion suites:
                       test_synthetic_internal.py (HRIS/ITSM/finance +
                       GL reconciliations), test_synthetic_granularity.py
                       (cross-grain rollups), test_synthetic_temporal.py
                       (snapshots/staleness), test_synthetic_conflicts.py
                       (conflict schema + resolution-rule vocab), and
                       test_citation_graph.py
  test_docs_inventory.py - Agent-facing docs must match code: every view, table,
                       enum value and record_source in db.py/tables.py appears in
                       schema.md and db-query.md, and no doc names a view that
                       does not exist
  (also) test_couch, test_events, test_evolve, test_ingest, test_ingest_events,
                       test_keys, test_materialize, test_mcp_server, test_tenancy,
                       test_schema_v017, test_store_v017 -- one per subsystem
skill/
  skill.md           - Routing document: CLI reference, and pointers into reference/
  reference/         - Deep references, opened on demand: schema, archetypes,
                       archetype patterns, context assembly, hierarchy, flywheel,
                       retrieval thesis, translation matrix, trace-capture (the
                       last one is a spec for an unbuilt capture path, not a
                       runnable procedure -- it says so at the top)
scripts/
  trace-hook.sh      - PostToolUse hook for automatic tool_call trace capture
  generate_synthetic_data.py - Deterministic generator for data/synthetic/
                       (fixed seed, fixed dates -- byte-identical re-runs)
  build_citation_graph.py - Derives data/synthetic/eval/citation_edges.csv
                       (corpus-wide ID mentions as from_path->to_id edges).
                       Standalone (scans the whole corpus on disk), not part
                       of generate(); run it after the generator, then rerun
                       the generator so MANIFEST re-inventories the CSV
docs/
  data-flywheel.md             - The detailed source of truth for the design. Vision, not
                                 a description of the code -- the code is one reference
                                 implementation of it. Generalized past this repo
  flywheel-failure-modes.md    - How a data flywheel fails, with what this repo
                                 does and does not defend against
  implementation-plan.md       - Milestones, schema deltas, definitions of done
  research-agent-data-representation.md - The literature and production practice
                                 this design was checked against
  assets/                      - Diagram SVGs for data-flywheel.md and the README
                                 (SMIL-animated, no <style> blocks -- they must
                                 render via <img> on GitHub)
  tutorial-arxiv-extraction.md - End-to-end extraction pipeline
  tutorial-rlm-provider.md     - RLM provider tutorial
  tutorial-flywheel.md         - Feedback loop end-to-end
  tutorial-cold-start.md       - Cold-start playbook: empty DB to turning flywheel
a2ui/                - DEPRECATED, unmaintained (see a2ui/README.md). Pre-v0.17
                       schema, no test coverage. Kept as a reference for the
                       rendering approach only; do not build on it
internal/            - Analysis docs, backlog, session logs (gitignored)
.claude/
  skills/            - Project-specific Claude Code skills (committed)
  rules/             - Rules the agent loads (committed). Files carrying the
                       compiled marker header are build output from dim_rule --
                       do NOT edit those; change the dimension row via proposal
                       and recompile. Unmarked files (model-delegation.md) are
                       hand-authored, backed by no row, and the reaper leaves
                       them alone
  agents/            - Pre-shaped delegation subagents (fast-executor,
                       task-coder), referenced by rules/model-delegation.md
  settings.local.json - Personal permissions (gitignored)
.githooks/pre-commit - Opt-in corpus + path-privacy guard. Enable once with
                       `git config core.hooksPath .githooks`
README.md            - The explainer and entry point; the short version of
                       docs/data-flywheel.md
ROADMAP.md           - What scales, what breaks, in what order
CHANGELOG.md         - Semver, no dates. Historical entries are a record; do not
                       edit them to match current conventions
LICENSE
.mcp.json            - MCP server config: freud-schema mcp-serve (the store-ops
                       connection holder for this project; committed)
```

## Development

- Python >= 3.10, Pydantic >= 2.0, DuckDB >= 0.9, orjson >= 3.9
- Package manager: **uv** (always use `uv run`, `uv sync`, `uv pip`)
- Tests: `uv run pytest tests/`
- `[tool.pytest.ini_options]` in pyproject.toml anchors the rootdir -- without it, collection
  escapes into the parent directory (itself a Python project) and every test fails at import
- Install: `uv sync --extra dev` (includes the `mcp` extra so gate tests run)
- Optional: `uv sync --extra anthropic` (Claude API), `uv sync --extra local` (httpx),
  `uv sync --extra mcp` (store-ops MCP server, `freud-schema mcp-serve`)

## CLI Quick Reference

`--db` is a global flag (before the subcommand). Defaults to `data/freudagent.duckdb`.

Workflow: `db init` -> `rule add` -> `skill add` -> `source add` -> harness extracts -> `extraction list/show/validate` -> `feedback add` -> `skill add --version N` (SCD-2: the new version automatically closes the prior row; no manual deprecate step)

Full CLI reference is in `skill/skill.md`. Key commands:

- `freud-schema extraction list|show|validate|reject` (keys or unique prefixes, git-short-hash style)
- `freud-schema feedback add --extraction-key <key-or-prefix> --type T --correction '{...}'`
- `freud-schema skill add|list|deprecate|activate` (add supports `--version N`)
- `freud-schema session list|show`
- `freud-schema ingest transcripts [--project] [--since]` (idempotent; CLI-only, needs the DB lock)
- `freud-schema ingest events --root DIR [--stream-type] [--since]` (generic JSONL event streams -> fact_event, idempotent)
- `freud-schema couch run|list` (SQL detectors -> fact_finding, no model calls)
- `freud-schema proposal add|list|show|approve|reject` / `freud-schema compile --out DIR`
- `freud-schema mcp-serve` (store-ops MCP server over stdio; requires `uv sync --extra mcp`)

## DuckDB MCP

DuckDB is single-process -- only one connection per file. Exactly one process
may hold it during a Claude Code session, so the `freud-schema` CLI cannot
touch the same DB file while that connection is open.

**The store-ops server (`freud-schema mcp-serve`, configured in `.mcp.json`)
is the preferred connection holder** (implementation plan M16, landed
0.25.0). It exposes:

- `query(sql)` -- read-only. Enforced at the parser level
  (`mcp_server.classify_readonly`): exactly one SELECT statement, no
  INSERT/UPDATE/DELETE/DDL/ATTACH/COPY/PRAGMA, no multi-statement input.
  Ad-hoc analysis keeps its full SQL surface within that constraint.
- Store-op tools for every write (`rule_add`, `skill_add`, `source_add`,
  `feedback_add`, `finding_add`, `extraction_validate`, `extraction_reject`,
  `proposal_add`, `proposal_reject`, `couch_run`, `compile`,
  `ingest_transcripts`, `ingest_events`) -- each a thin wrapper over
  `ops.py`, which is the same dispatch layer the CLI calls, so the two
  surfaces cannot drift.
- **The self-modification gate**: `rule_add`/`skill_add` always create the
  non-compiling status (rules: `inactive`; skills: `draft`) regardless of
  what a caller asks for -- a session cannot make a rule or skill load into
  its own future context by calling these tools directly. The only path to
  activation is `proposal_add` -> `proposal_approve`.
- `proposal_approve` is how approval reaches a person: **never allowlist
  it** in permissions config, at any scope. Every call must surface the
  harness's permission prompt -- that prompt IS the approval. `reviewed_by`
  is a required argument, not optional.
- No tool exposes `db reset`, `db ddl`, or any raw-write escape hatch.

**Migration note**: if this project's `.mcp.json` still lists a generic
`duckdb` MCP server entry (e.g. from a user-level config), disable it for
this project once the store-ops server is connected -- two servers holding
the same file is the lock conflict this section used to be about. Until a
session has switched over, the old write-window rules still apply:

- Native-row writes through a **generic duckdb MCP server**: open a **CLI
  write window** -- disconnect that server (`/mcp`), run the `freud-schema`
  commands, reconnect.
- The `/couch` skill's raw-INSERT exception is retired: `finding_add`
  (CLI or the MCP tool) is the one write path for findings now, LLM-judged
  or SQL-detected alike. `.claude/skills/couch.md` keeps the old raw-SQL
  recipe as a fallback appendix for sessions still on a generic server.

**Still true for any raw connection** (the store-ops server's `query` tool
included, since it shares the store's connection): `execute_query`-style
calls accept multi-statement SQL, and each call is ONE transaction. Keep
catalog changes (DROP/CREATE of tables and indexes) in separate calls from
each other and from data loads -- batching drops + creates + copies in one
call (or using `COPY FROM DATABASE` / `IMPORT DATABASE`, which are
single-transaction) trips DuckDB's index dependency tracking on a
long-lived connection ("Could not commit creation of dependency" -- hit for
real, 2026-07-09). Lock workaround for CLI-only ops when no MCP server is
in play (ingest, compile): run them against a scratch DB file, then
`ATTACH` it read-only from the MCP connection and `INSERT INTO` the live
tables -- deterministic keys make the copy idempotent. For a full
reset-and-rebuild, `EXPORT DATABASE (FORMAT PARQUET)` the scratch DB, then
replay on the live connection in separate calls: creates, then indexes,
then `read_parquet` loads.

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
  on breaking change) -> reset via a CLI window (`db reset`; the store-ops server has
  no reset/DDL tool BY DESIGN -- disconnect it first, reconnect after) ->
  `ingest transcripts` -> `couch run` -> recreate native rows. Two sharp edges:
  (1) re-seed active rules into dim_rule BEFORE anything compiles, or the reaper
  deletes their compiled files (strip the marker header/provenance footer from each
  compiled .md for content); (2) reset wipes proposal/finding provenance -- expected,
  not a bug; footers survive only in compiled files and git history
- New tables must be added to `reset_schema()` drop list (order matters: dependents first)
- DDL stored as `list[str]` (one statement per element, no semicolon splitting)

### Privacy
- `data/freudagent.duckdb` holds personal transcript content -- gitignored, and transcript
  text must never be quoted into committed files, commit messages, or finding summaries
- Finding summaries and compiled artifacts are clean by construction (tool names, counts,
  rates only); `compile`'s privacy gate refuses rather than degrades — it is not advisory

### CLI
- `--status`/`--scope`/`--type` args must use `choices=[e.value for e in EnumClass]`
- Handlers that modify by key resolve prefixes via `store.resolve_key()` first and `sys.exit(1)` on no-match/ambiguity
- CLI exposes data operations only -- no execution/orchestration commands (harness's job)
- CLI output is human-oriented: scripts must capture keys from each command's own
  stdout, never scrape `list` output (no --json; learned 2026-07-09 when a scripted
  approval loop half-ran. M16's store-ops MCP tools are the structured surface)

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
- prompt_addendum.md (a2ui/) is frozen along with the rest of a2ui/ -- it is no longer kept in sync with schema.md

## Internal Docs

All in `internal/` (gitignored). Read before proposing new work.

- `BACKLOG.md` -- known gaps, deferred work. Check here before suggesting features. Mark items DONE with version when resolved.
- `log/` -- session logs
- `flywheel_decomposition.json` -- twelve-step decomposition mapping to Agent SDK primitives
