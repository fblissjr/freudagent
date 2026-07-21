# Implementation Plan: Executing the Roadmap

Last updated: 2026-07-09

This is the concrete build plan for [ROADMAP.md](../ROADMAP.md). The roadmap
says *what* and *why*; this document says *how*, against this codebase as it
exists — which modules change, which tables are added, which store methods
appear, what the CLI grows, and what "done" means for each milestone.

The target, restated once: a system that cold-starts a knowledge base from an
empty warehouse, then compounds it through a data flywheel — agents doing the
modeling, transformation, and maintenance; humans governing every change;
skills updating dynamically and loading through progressive disclosure. What
the milestones collectively build is the **grounding layer** (see ROADMAP):
constraints on one end, grounding data in the middle, verifiers and feedback
on the other.

## Ground Rules (apply to every milestone)

These are the existing conventions that every milestone must uphold. They are
restated here because several milestones are large enough to tempt shortcuts.

1. **The library never calls models.** Evals, embeddings, and LLM-layer
   analysis are computed *by the harness*; the library assembles inputs,
   scores deterministically, and records results. Any milestone that seems to
   need a model call inside `src/freud_schema/` is mis-scoped — split it into
   a data op (library) and an execution step (harness/skill).
2. **One write path per table**, all access through `ExperimentStore`, no raw
   `con.execute` at call sites, `cursor.description`-keyed dicts, and
   parameterized enum values.
3. **New enums live in `tables.py`**; CHECK constraints are generated from
   them. Open vocabularies (finding types, event types, redaction patterns)
   are registry rows, never enums.
4. **New tables register in `ALL_TABLES`** (dependency order — dependents
   first) and new views in `ALL_VIEWS`; views are `CREATE OR REPLACE` only.
5. **Every ingest/analysis operation wraps in `store.load_run()`** so lineage
   stays total.
6. **Keys come from named recipes** (`session_key_for`, `message_key_for`,
   and the new recipes each milestone adds) — never re-derived inline.
7. **Docs ship with code**: `skill/reference/schema.md` (including the enum
   table), `skill/skill.md` CLI reference, `CHANGELOG.md`, and the version
   sync across `pyproject.toml` / skill frontmatter. Each milestone is a
   version bump.
8. **Tests per convention**: `:memory:` DuckDB for store tests, `tmp_path`
   for CLI end-to-end, stores in `with` blocks.

## Milestone Map

| # | Milestone | Roadmap phase | Size | Depends on | Status |
|---|-----------|--------------|------|------------|--------|
| M1 | Reset-based schema lifecycle (policy) | 1 | S | — | DONE 0.22.0 |
| M0 | Cold-start playbook + staleness detector | 0 | S | M1 | DONE 0.24.0 |
| M2 | Key algorithm versioning (SHA-256) | 1 | M | M1 | DONE 0.23.0 |
| M3 | Tenancy in natural keys | 1 | M | M1, M2 | DONE 0.23.0 |
| M4 | Store split + backend protocol | 1 | L | M1–M3 | — |
| M5 | Generic event grain + ingest adapters | 2 | M | M1–M3 | DONE 0.26.0 |
| M6 | Ingest-time redaction | 2 | M | M5 | — |
| M7 | Principals and authorization | 2 | M | M1, M3 | — |
| M8 | Hybrid retrieval layer | 3 | L | M1, M3 | — |
| M9 | Activation conditions with teeth | 3 | S | M8 | — |
| M10 | Scoped materialization + drift check | 3 | S | M3 | — |
| M11 | Cases, watermarks, incremental detection | 4 | L | M1, M5 | — |
| M12 | Review queue and conflict handling | 4 | M | M7, M11 | — |
| M13 | Verification gate + flywheel health | 5 | L | M11, M12 | — |
| M14 | Serving layer + widened feedback | 6 | L | M8, M10, M13 | — |
| M15 | Dream-work: periodic consolidation passes | 4/6 | M | M8, M11 | — |
| M16 | Store-ops MCP server (in-session writes) | 6 | M | M1–M3 | DONE 0.25.0 |

Shipped milestones carry the version that landed them (see CHANGELOG.md for
the full record). As-shipped deltas from the specs below, all minor: M0's
stale_source summaries carry the basename only (no age), findings are
GLOBAL-scope with an empty evidence-session list (the source key lives in
the summary), and the skip flag shipped as `couch run --warehouse-only`.
M2+M3 landed as one reset as planned; implementation additionally fixed
`approve_proposal`'s inline skill-key derivation (pre-tenancy formula) —
the named-recipe convention exists precisely to prevent that class of bug.
The first real reset-and-rebuild (2026-07-09: 174,779 transcript entries →
127,495 rows, ~2m17s, 34 findings) validated the M1 recipe end to end.

The first full flywheel turn also ran 2026-07-09 (pre-registered in
`internal/research/`): SQL findings → LLM couch judgment → three
evidence-linked rule proposals → owner approval → compile with provenance
footers. Retroactive verification of the earliest compiled rule was
directional but underpowered (identical-retry sessions 1.5% before → 0/64
after; re-measure at ~200 post-rule sessions). The turn's friction log
feeds M11 (auto-denial filtering), M13 (session-denominated verify
windows, health views), and M16 (which it motivated).

M16 landed 0.25.0 as planned, with one interpretive call in `query`'s
gate: the spec allowed `EXPLAIN` "if duckdb types it separately and it
wraps a SELECT." Measured against `duckdb.extract_statements()`, `EXPLAIN
<anything>` always types as `StatementType.EXPLAIN` with no exposed
handle on the wrapped statement's type, and `EXPLAIN ANALYZE <write>`
actually executes the wrapped statement (that's how it collects runtime
stats) -- so honoring the wrapping clause would have required parsing the
SQL text a second time to guess what followed `EXPLAIN`, or trusting the
caller. `classify_readonly()` took the spec's own fallback instead:
SELECT only, unconditionally. `EXPLAIN` is rejected by the same path as
every other non-SELECT statement type.

M5 landed 0.26.0 bundled with the fresh-ingest speed optimization from the
risk register (the M1-recipe risk row anticipated doing both together).
As-shipped deltas from the spec: `fact_event` does not carry a denormalized
`event_type_key` column the way `fact_finding` carries `finding_type_key`
-- the spec's own column list for `fact_event` omitted it, and open-vocabulary
validation (the actual point of the registry) works the same without the
denormalized reference. `TranscriptAdapter` conforms to `IngestAdapter`'s
shape (its `discover`/`parse` reuse `discover_sessions`/`iter_typed_entries`
and produce genuine `RawEvent`s per transcript entry) but `ingest_transcripts()`
does not route through it -- the direct path stays untouched, so the existing
transcript test suite carries zero regression risk. The JSON-spill bulk
insert (`ExperimentStore._bulk_insert_json`) now backs `insert_messages`,
`insert_tool_uses`, and `insert_events`; row-content equivalence with the old
per-row `executemany` path is asserted against literal expected values
(`tests/test_events.py`) rather than by keeping both code paths live, per the
task's own "your choice" clause. Measured on a synthetic 50k-row fixture:
~0.09s for the spill+`read_json` path vs. ~55s for `executemany` (~600x) --
see CHANGELOG.md for the reproducible benchmark shape.

Sizes are relative (S ≈ days, M ≈ a week, L ≈ multiple weeks of focused
work). The order within tracks matters. Track C (M8–M10) can start once the
storage track lands; Track D additionally needs M5 and M7 from Track B
(see the dependency column). The two tracks then proceed in parallel.

Rationale for the orderings: M1 precedes everything because it fixes the
change mechanism every later milestone uses (schema changes = code + reset +
re-ingest; never a data migration — see the CLAUDE.md policy). M2/M3 (keys,
tenancy) still come early because entity identity is baked into every key:
with reset-based changes the cost of deferring them isn't a rekey migration
but re-creating accumulated native test data (feedback, proposals), which
grows with time.

---

## Track A — Storage

### M1. Reset-based schema lifecycle (no migrations — by policy)

**Goal**: codify that this repo never migrates data. Owner decision
(2026-07-08, recorded in CLAUDE.md): this is a research repo, never prod;
all warehouse data is disposable test/research data; git history of code
and git-tracked artifacts is the only history that matters. Schema changes
ship as **code + `reset_schema()` + re-ingest** — no migration machinery,
no data-preservation paths, until the owner explicitly says otherwise.

**Changes**
- CLAUDE.md carries the policy (done alongside this plan revision).
- Document the standard schema-change recipe in the DB conventions: edit
  DDL in db.py (registering new tables in `ALL_TABLES` and the reset drop
  list) → `db reset` → `ingest transcripts` → `couch run` → recreate any
  native test rows the work needs. Deterministic keys make the re-ingest
  half idempotent and cheap; native rows (feedback, proposals) are test
  data and are recreated, not preserved.
- `_SCHEMA_VERSIONS` in db.py continues as a plain changelog of what the
  current DDL is (bump on breaking change), not a migration ledger.

**Tests**: none beyond the existing inventory test — every DB is always
freshly created at the latest schema, so schema drift between databases
cannot exist by construction.

**Done when**: CLAUDE.md carries the policy, the change recipe is
documented, and no milestone below references a data migration. (A
production descendant reintroduces forward migrations as its first
storage task — that requirement lives in ROADMAP Phase 1, not here.)

### M0. Cold-start playbook + staleness detector

**Goal**: a documented, partially-automated day-one sequence for a fresh
deployment, plus the first maintenance detector (cold-started knowledge
decays fastest).

**Changes**
- `docs/tutorial-cold-start.md`: the bootstrap sequence as a walkthrough —
  `db init`; register the seed corpus (`source add` per document); author
  seed rules and v1 skills by hand (`origin=human_authored`); harness runs
  extraction over the seed corpus; **all** cold-start output routes through
  `extraction validate|reject` (untrusted until promoted); first feedback,
  first aggregate, first proposal. Ends with the flywheel turning once.
- Staleness detector in `couch.py`: `_detect_stale_sources` — for every
  current active `dim_source` whose `content_path` exists, recompute the
  content hash and compare to `source_hash`; emit a `stale_source` finding
  (evidence: the source key, summary built from path basename + age only —
  privacy rules apply). Registered with `detection_method = hybrid` — the
  existing enum member fits: the detector reads both the warehouse
  (registered sources) and the filesystem (current bytes), so it is neither
  pure SQL nor LLM, and a `stale_source` finding is not reproducible from
  the warehouse alone. Because hashing reads the filesystem, it runs in
  `run_couch()` but is skippable via parameter for warehouse-only runs.
- `source add` gains `--hash` (compute and store `source_hash` at
  registration) so the detector has a baseline; tutorial uses it.

**Tests**: register a source with hash, mutate the file, `run_couch` →
exactly one `stale_source` finding; unchanged file → zero.

**Done when**: a new operator can go from empty DB to one full flywheel turn
using only the tutorial, and a mutated seed document surfaces as a finding.

### M2. Key algorithm versioning

**Goal**: replace MD5 with truncated SHA-256 before data accumulates, and
make the algorithm itself versioned so this never has to be a crisis again.

**Changes**
- `keys.py`: `dimension_key()` and `hash_diff()` switch to
  `hashlib.sha256(...).hexdigest()[:32]`. Same length as MD5 hex — no column
  or prefix-resolution changes. Add module constant `KEY_ALGORITHM =
  "sha256/32"` and record it in a new `meta_key_algorithm` single-row table
  (created at `init_schema`) so a database self-describes its key scheme.
- **No rekey migration** — per M1 policy, existing databases are reset and
  re-ingested. M2 and M3 land together as one reset (SHA-256 keys with the
  tenant component already in the natural key) so the warehouse is reset
  once, not twice. Native test rows are recreated as needed.

**Tests**
- Golden test: known natural keys → expected sha256/32 values.
- Fresh DB → ingest a fixture corpus → re-ingest the same corpus →
  `rows_written=0` (idempotency holds under the new algorithm).

**Done when**: golden tests pass, re-ingest of an unchanged corpus reports
`rows_written=0`, and no MD5 call remains in `src/`.

### M3. Tenancy in natural keys

**Goal**: entity identity stops being single-namespace. Two teams can hold a
skill for the same `(domain, task_type)` or a rule with the same name without
collision, and conflicting knowledge is handled by scoping.

**Changes**
- `tables.py`: new `Tenant` model; `tenant_id: str = "default"` field on
  `Skill`, `Rule`, `Source`, `SamplingConfig`; facts gain denormalized
  `tenant_key` populated at insert (extending the existing denormalization
  pattern — `_resolve_skill_attrs` also returns tenant).
- New registry `dim_tenant` (append-only, like `dim_project`):
  `tenant_key = dimension_key(tenant_id)`, `tenant_id`, `display_name`.
  The `default` tenant is seeded at `init_schema`; no backfill — existing
  databases reset per M1 policy.
- Natural keys grow a leading tenant component: skill =
  `tenant|domain|task_type`, rule = `tenant|name`, source =
  `tenant|content_path`. M2 and M3 land together as a single reset (SHA-256
  keys with the tenant component included), which is why M3 rides
  immediately behind M2 — the warehouse is reset once, not twice.
- Store: `ensure_tenant()`, tenant parameter (default `"default"`) threaded
  through `insert_*`, `get_active_skill`, `get_rules`, `resolve_key`
  (prefix resolution scopes to tenant), and the aggregate/query methods.
- CLI: global `--tenant` flag beside `--db`; omitting it preserves today's
  behavior exactly.
- `materialize.compile_rules` gains a tenant parameter (compile one tenant's
  rules into one output tree).

**Tests**: two tenants, identical skill natural keys, both active, no
collision; `get_active_skill` returns per-tenant; default-tenant round trip
matches pre-M3 behavior (back-compat test).

**Done when**: the full existing test suite passes untouched under the
default tenant, and the two-tenant collision test passes.

### M4. Store split + backend protocol

**Priority note (2026-07-09, owner-flagged)**: M4 is now the least urgent
Track A item and should slide behind M11 → M13. Its original pain — the
single-file lock choreography — was mostly absorbed by M16 (the store-ops
server holds the one connection and the write surface lives in-session);
what remains (multi-writer concurrency, retention separation, backend
swap) is enterprise-descendant territory. Nothing downstream blocks on it
except M15's retention hook (`prune_telemetry`), which can ship standalone
if M15 arrives first. Dependency order in the map is unchanged — this is
scheduling guidance, not a dependency edit.

**Goal**: break the single-file, single-process wall. The knowledge store
(small, precious, forever) and the telemetry warehouse (high-volume,
sensitive, retention-bound) become separable, and the storage engine becomes
swappable behind the store layer.

**Changes — staged in two sub-milestones**

*M4a — logical split (DuckDB only)*
- Classify tables: **knowledge** = SCD-2 dims, registries, `fact_proposal`,
  `fact_feedback`, `fact_trace_feedback`, `fact_extraction`, eval tables
  (M13); **telemetry** = `fact_session`, `fact_message`, `fact_tool_use`,
  `fact_trace`, `fact_session_facets`, `fact_finding`, `fact_event` (M5),
  cases (M11), watermarks; `meta_*` exists in both.
- `ExperimentStore` accepts two connections (or one, aliased — the default
  stays a single file so nothing breaks for the single-operator case).
  `ALL_TABLES` gains a store-affinity map used by `db status`, backup
  tooling, and retention.
- Cross-store denormalization gets a defined protocol: `_resolve_skill_attrs`
  reads `dim_skill` (knowledge store) during telemetry-fact inserts, so the
  store resolves attributes on the knowledge connection **first**, then opens
  the telemetry transaction and inserts. No cross-connection transaction is
  attempted; a resolution failure aborts before any telemetry write, so
  facts are never written with unresolved attributes.
- Retention hooks: `store.prune_telemetry(before: datetime)` deletes
  telemetry facts older than a horizon, wrapped in `load_run` (knowledge
  tables are never pruned).

*M4b — backend protocol*
- New module `src/freud_schema/backend.py`: `StorageBackend` protocol —
  `connect`, `transaction`, `execute`, plus the dialect seams that actually
  differ: JSON extraction, list aggregation (`LIST(DISTINCT ...)` /
  `FILTER`), and upsert form. The DuckDB backend is the reference
  implementation extracted from current code.
- The engine-specific analytical views (`v_retry_loops` etc.) move their SQL
  into backend-owned definitions; `ALL_VIEWS` stays the canonical inventory,
  DDL comes from the active backend.
- Optional extra `postgres` (psycopg): knowledge-store backend first —
  it is the transactional, multi-writer side and the smaller SQL surface.
  Telemetry stays DuckDB/parquet until scale demands otherwise.
- The provider-style dynamic-import convention applies: importing the
  Postgres backend without the extra installed raises `ImportError` with an
  install hint.

**Tests**: the store test suite runs parameterized over backends (DuckDB
always; Postgres behind a marker/env so CI without a server skips);
split-store test proves a knowledge write and telemetry write land in their
respective stores and cross-store references (denormalized attributes, not
joins — the schema already avoids cross-table joins by design) still work.

**Done when**: `ExperimentStore` runs green on a two-file split and on
Postgres-knowledge + DuckDB-telemetry, and no module outside `backend.py`
contains engine-conditional SQL.

---

## Track B — Ingest, redaction, identity

### M5. Generic event grain + ingest adapters

**Goal**: agent transcripts become one source among many. Any enterprise
event stream ingests through the same idempotent, lineage-stamped path.

**Changes**
- New registry `dim_event_type` (open vocabulary, like `dim_finding_type`):
  `event_type`, `description`, `schema_hint JSON`.
- New table `fact_event`: `event_key` (deterministic:
  `dimension_key(stream_key, native_event_id)`), `tenant_key`, `stream_key`
  (the generalization of session_key — a named recipe `stream_key_for(
  record_source, native_stream_id)` mirrors `session_key_for`),
  `event_type`, `occurred_at`, `actor`, `payload JSON`, `content_text`
  (extracted searchable text), lineage envelope. Registered in `ALL_TABLES`;
  indexed on `(stream_key, occurred_at)` and `event_type`.
- `ingest.py` refactor: an `IngestAdapter` protocol —
  `discover(root, since) -> list[SourceUnit]` and
  `parse(unit) -> Iterator[RawEvent]` — with the current transcript logic
  becoming `TranscriptAdapter` (it continues to write the typed
  message/tool-use tables *and* nothing else changes about it; typed tables
  are projections for sources rich enough to deserve them).
- Second reference adapter `JsonlEventAdapter`: newline-delimited events with
  `{id, type, timestamp, actor, payload}` — the smallest possible proof that
  a non-transcript stream flows end-to-end into `fact_event` idempotently.
- `RecordSource` enum grows `event_ingest`; CLI:
  `ingest events --root DIR [--stream-type T] [--since]`.

**Tests**: JSONL fixture ingests; re-ingest writes zero rows; grown file
writes only the delta; `meta_load_log` numbers match; couch detectors are
unaffected (they read the typed tables).

**Done when**: a synthetic event stream round-trips with idempotency
verified from `meta_load_log`, using no transcript-specific code.

### M6. Ingest-time redaction

**Goal**: the warehouse becomes clean by construction. The compile-time
privacy gate demotes to the backstop it was always meant to be.

**Changes**
- New module `src/freud_schema/redact.py`:
  - `Scanner` protocol: `scan(text) -> list[Span]` (span = start, end,
    pattern id). Built-ins: secret shapes (cloud access keys, bearer/OAuth
    tokens, private key blocks, connection strings with credentials),
    home-directory paths and OS username (shared with — extracted from —
    `materialize._find_leaks` so there is one definition), email addresses.
  - Custom patterns as data: new registry `dim_redaction_pattern`
    (`pattern_id`, `regex`, `replacement_class`, enabled) — enterprise
    deployments add their own without code changes.
  - `redact(text) -> (clean_text, hits)`: spans replaced with typed
    placeholders (`[REDACTED:secret.aws_key]`), hits carry pattern ids and
    counts only — never the matched text.
- Ingest integration: every free-text field bound for the warehouse
  (`content_text`, `result_text`, `tool_input` string values, `payload`
  leaves, task descriptions) passes through `redact()` inside the adapters,
  before keys or rows are computed. Rows record `redaction_count`.
  Fail-closed: a scanner exception quarantines the unit (skipped, counted in
  `rows_skipped`, logged in `meta_load_log.error`) rather than ingesting raw.
- Aggregate visibility: a `redaction_hit` deterministic finding (counts per
  pattern per project — pattern ids and counts only) so heavy leak sources
  surface for review.
- The materialize gate stays untouched — defense in depth.

**Tests**: fixture transcript seeded with fake secrets → warehouse contains
placeholders and zero raw matches (grep the whole DB dump); idempotency
survives (keys derive from uuids, not content); scanner-crash path
quarantines and reports.

**Done when**: the seeded-secret test passes against both adapters and the
redaction pattern registry round-trips through the CLI.

### M7. Principals and authorization

**Goal**: actors become identities; approval becomes a permissioned action;
scoping becomes enforceable.

**Changes**
- New registries: `dim_principal` (`principal_id`, `display_name`,
  `kind` enum: human | agent | service) and `dim_grant`
  (`principal_key`, `action` enum: approve | propose | validate | ingest |
  serve_read | serve_feedback, `tenant_key`, optional `domain`).
- `tables.py`: `PrincipalKind` and `GrantAction` enums; models.
- Store: `ensure_principal`, `add_grant`, `check_grant(principal, action,
  tenant, domain) -> bool`. Enforcement is **opt-in by configuration** — a
  `meta_policy` table keyed by `(tenant_key, policy_name)`, introduced here
  with a single default-tenant row (`strict_identity`, default false) so the
  single-operator mode keeps working with free-text names. M13 reuses the
  same shape for per-tenant eval policy rows — the grain is per-tenant from
  day one, no later grain change. When strict:
  `approve_proposal`/`reject_proposal` require `reviewed_by` to resolve to a
  principal holding `approve` for the proposal's tenant; `update_validation`
  requires `validate`; violations raise before any write.
- Actor columns (`created_by`, `reviewed_by`, `validated_by`) keep their
  VARCHAR type but store principal_ids when strict — no destructive column
  schema churn, one behavior flag.
- CLI: `principal add|list`, `grant add|list`, `policy set strict-identity
  on|off`.

**Tests**: strict mode — approval by an ungranted principal raises and
writes nothing; permissive mode matches current behavior byte-for-byte;
grants scope by tenant (approver in tenant A cannot approve tenant B).

**Done when**: the strict-mode denial test passes and the permissive-mode
back-compat test proves zero behavior change by default.

---

## Track C — Retrieval

### M8. Hybrid retrieval layer

**Goal**: L2 "loaded on match" becomes real when matches are semantic. One
ranked query surface over every knowledge unit.

**Changes**
- New module `src/freud_schema/retrieval.py`:
  - **Unit registry**: what is retrievable = current active skills and rules,
    validated extractions, and findings (open cases join the corpus as a
    post-M11 wiring task — not an M8 dependency) — each contributing
    `(unit_key, unit_kind, tenant_key, domain, title, body)` via store
    queries (no new tables for the corpus; retrieval reads the dims/facts).
  - **Lexical index**: DuckDB FTS extension (`PRAGMA create_fts_index`) over
    a materialized `retrieval_corpus` table rebuilt by `reindex()` (wrapped
    in `load_run`; rebuild is idempotent and cheap at knowledge-store scale —
    the corpus is skills/rules/validated knowledge, not telemetry).
  - **Vector index (optional)**: `Embedder` protocol following the provider
    convention — dynamic import, `ImportError` with install hint, *no model
    calls in the default path*. Embeddings are computed by whatever the
    deployment provides (harness-side batch, or a local model via the
    `local` extra) and stored in a `retrieval_embedding` table
    (`unit_key`, `model_id`, `vector FLOAT[]`); similarity via the VSS
    extension when present, brute-force cosine below a corpus-size threshold
    so the feature works with zero extensions installed.
  - **Fusion**: `retrieve(query, *, tenant, kinds=None, domain=None, k=10)`
    — reciprocal-rank fusion of lexical and (when available) vector
    rankings, with deterministic boosts: current+active over historical,
    validated over pending. Returns units with scores and kind tags.
- Store: thin `store.retrieve(...)` delegating to the module (keeps the
  "all access through the store" rule for consumers).
- CLI: `retrieve "query" [--kind skill|rule|extraction|case] [--k N]` and
  `retrieval reindex`.

**Tests**: FTS-only path (no embedder installed): seeded corpus, query hits
the right skill above the wrong one; kind and tenant filters; reindex
idempotency; brute-force cosine path with a fake embedder fixture.

**Done when**: retrieval returns correct ranked results with zero optional
dependencies installed, and the embedder path is exercised by a fake in
tests.

### M9. Activation conditions with teeth

**Goal**: `dim_skill.activation_conditions` stops being a stub; skill
selection becomes ranked retrieval instead of exact `(domain, task_type)`
match.

**Changes**
- Define the JSON contract (documented in `schema.md`):
  `{"keywords": [...], "domains": [...], "task_types": [...],
  "min_score": float}` — all optional; absent conditions mean "eligible,
  rank by retrieval alone".
- `orchestrator.py`: new `select_skills(store, task_text, *, tenant, k=3)` —
  candidate set from `store.retrieve(task_text, kinds=["skill"])`,
  filtered by each candidate's conditions (keyword/domain/task-type
  predicates evaluated in Python, deterministic), returned ranked with
  scores.
- `assemble_runner_context()` grows an alternative entry: pass `task_text`
  without `skill_key` → top-selected skill is loaded, and the chosen
  skill/score lands in the returned context metadata so the harness (and
  `fact_session.context_loaded`) records *why* this skill was picked —
  routing decisions become auditable like everything else.
- `skill add --conditions '{...}'` CLI passthrough (validated against the
  contract).

**Tests**: three skills with overlapping keywords, task text selects the
right one; `min_score` excludes weak matches (falls back to exact-match
lookup); explicit `skill_key` bypasses selection unchanged.

**Done when**: context assembly with only task text selects and loads the
correct skill and records the routing decision.

### M10. Scoped materialization + drift check

**Goal**: L1 stays bounded at any rule count; compiled output verifiably
matches the warehouse.

**Changes**
- `materialize.py`:
  - Output tree by scope: `out/<name>.md` for `scope=global` (bounded —
    compile *warns* past a configurable global-rule count budget),
    `out/domains/<domain>/<name>.md` for domain rules. Same markers, same
    managed-file hygiene per directory, same fail-closed privacy gate.
  - A generated bounded index `out/INDEX.md` (compiled marker, lists domains
    and rule names only) — the always-loaded surface stays small; domain
    files load on demand.
  - Renderer/IO split: `render_rule(store, rule) -> str` becomes public and
    pure; `compile_rules` handles filesystem. M14's second target reuses the
    renderer pattern.
- `compile --check`: renders everything in memory, diffs against the output
  directory, prints per-file added/removed/changed, exits nonzero on drift —
  the CI gate that compiled state matches current dimensions.

**Tests**: domain rules land in domain dirs; hand-written files survive
everywhere; `--check` green after compile, red after a dimension edit, red
after manual tampering with a managed file.

**Done when**: a CI job (documented in the tutorial) can enforce
warehouse ↔ artifact consistency with one command.

---

## Track D — Lifecycle and review

### M11. Cases, watermarks, incremental detection

**Goal**: findings stop being an append-only firehose. Recurrence is
recognized, state is tracked, detectors run incrementally, and "what is new"
is the default human entry point.

**Changes**
- `tables.py`: `CaseStatus` enum (open | triaged | addressed | verified |
  closed) and `Case` model.
- New table `fact_case` — an accumulating snapshot in the `fact_session`
  pattern (facts stay append-only except accumulating snapshots and
  review-state updates such as `fact_proposal`'s status fields):
  - `case_key = dimension_key(tenant_key, finding_type, scope, project_key,
    signature)` where `signature` is the finding's stable discriminator
    (e.g. tool name for retry loops) — new named recipe `case_key_for(...)`.
  - `status`, `first_seen_at`, `last_seen_at`, `total_occurrences`,
    `run_count`, `addressed_by_proposal_key`, `verified_at`, lineage.
- `couch.py`: detectors gain a `signature` per finding; `run_couch()` upserts
  cases (new → open; existing → bump `last_seen_at`/counts; `closed` cases
  that recur **reopen** — regression is a state transition, not a duplicate
  row). `fact_finding` gains `case_key` (findings remain the append-only
  evidence trail; cases are the stateful view over them).
- New table `meta_watermark` (`detector`, `tenant_key`, `last_occurred_at`,
  `etl_run_id`): detectors filter their base queries to
  `occurred_at > watermark` and advance it inside the same transaction.
  Full-rescan stays available (`couch run --full`) for after-backfill use.
- Detector precision (felt input, first flywheel turn): permission_friction
  must distinguish user-judgment denials from headless auto-denials
  ("prompts unavailable" result_text signature) — an entire finding was
  environmental noise. Filter lands with the watermark rework.
- Thresholds as data: `dim_finding_type` gains `parameters JSON`
  (schema change via reset, per M1 policy); `run_couch` reads per-type
  parameters with the module
  constants as defaults — per-tenant/per-domain tuning is a row edit.
- Proposal linkage: `approve_proposal` (given evidence findings) marks the
  findings' cases `addressed` with the proposal key — the flywheel's
  evolve step now moves case state automatically.
- CLI: `couch cases [--status open]`, `case show|triage|close <key>`,
  `couch new` (cases opened or reopened since the previous run).
- Views: `v_case_summary` (per type/project: open count, oldest, recurrence
  after address — the "did the rule work" query becomes a view).

**Tests**: two consecutive `run_couch` calls over unchanged data → second
run opens zero cases (the dedup guarantee); new occurrences bump the
existing case; closed case recurring → reopened; watermark advance proven by
row-count deltas; `--full` rescan does not duplicate cases.

**Done when**: the "second run opens zero new cases" test passes and case
state transitions are exercised end-to-end via CLI.

### M12. Review queue and conflict handling

**Goal**: the human approval atom survives volume. Triage, assignment, and
conflict detection around the existing proposal table.

**Changes**
- `fact_proposal` gains `priority INTEGER`, `risk` enum (low | medium |
  high), `assigned_to`, `conflicts_with_key` (schema change via reset, per
  M1 policy; all nullable).
- Store: `insert_proposal` detects an existing *pending* proposal targeting
  the same `(target_dimension, natural key)` → stamps `conflicts_with_key`
  on the new one (both stay pending; a human resolves by rejecting one —
  conflicting truths across tenants don't collide at all because tenancy is
  in the natural key, per M3).
  `queue_proposals(tenant, assigned_to=None)` orders by risk desc, priority
  desc, age; `assign_proposal(key, principal)`.
- Auto-approval as policy, not code: a `GrantAction.auto_approve` grant
  (M7) scoped to tenant+domain allows a *service principal* to approve
  proposals whose `risk = low` — the gate check in `approve_proposal`
  enforces the risk ceiling. Default: no such grants exist; everything stays
  human.
- CLI: `proposal queue [--assigned-to]`, `proposal assign <key> --to P`,
  `proposal add --risk R --priority N`.

**Tests**: conflict stamped when second pending proposal targets the same
entity; queue ordering; auto-approve grant approves low-risk and refuses
medium; strict-identity interplay (M7 gates still hold).

**Done when**: two conflicting proposals surface as a conflict in the queue
and the auto-approve ceiling test passes.

---

## Track E — Verification

### M13. Verification gate + flywheel health

**Goal**: the flywheel's missing fourth phase. Candidate knowledge versions
are tested against held-out validated history before approval can
materialize; the loop's health becomes measurable.

**Design note**: the no-orchestration rule shapes this milestone more than
any other. The *library* assembles holdout sets, scores candidate outputs
deterministically, records runs, and enforces the gate. The *harness* (a
project skill, an SDK workflow, CI) executes the candidate skill against the
holdout inputs — that's where model calls live.

**Changes**
- New tables:
  - `fact_eval_run`: `eval_run_key`, `proposal_key`, `skill_key`,
    `candidate_version`, `baseline_version`, `holdout_spec JSON` (extraction
    keys used), `metrics JSON` (per-field accuracy, exact-match rate,
    regression fields), `status` enum (running | passed | failed), reviewer
    fields, lineage.
  - `fact_eval_result` (optional per-item detail): `eval_run_key`,
    `extraction_key`, `field_diffs JSON`, `matched BOOLEAN`.
- Store:
  - `build_holdout(skill_key, *, proposal_key, limit,
    exclude_feedback_sessions=True)` — returns two splits. **Held-in** is
    derived from the proposal's evidence chain (evidence findings → their
    cases' evidence sessions → those sessions' validated extractions for the
    target skill); **held-out** is general validated history. Both exclude
    items whose corrections fed the candidate (no training-on-test), and an
    empty held-in set fails the gate rather than passing vacuously.
  - `score_extraction(candidate_output, validated_output) -> FieldScore` —
    deterministic field-level comparison (exact / normalized / missing /
    spurious), pure function, unit-testable in isolation.
  - `start_eval_run` / `record_eval_result` / `complete_eval_run` (computes
    aggregate metrics, sets passed/failed against thresholds stored in
    per-tenant `meta_policy` rows — the `(tenant_key, policy_name)` table
    M7 introduces: minimum held-in improvement, maximum held-out
    regression).
  - **The gate**: `approve_proposal` — when policy `require_eval` is on for
    the target dimension — requires a `passed` eval run referencing the
    proposal; otherwise raises before any write. Fail-closed like the
    privacy gate: no eval, no approval, last good version keeps serving.
- Case verification (closing M11's loop): a scheduled `couch verify` pass
  checks `addressed` cases — if the case's detector reports no recurrence
  since `addressed` + a configurable quiet window — denominated in ACTIVE
  SESSIONS, not days (felt input: P1's verify measurement was underpowered
  at 64 post-rule sessions; days say nothing about power) — transition to
  `verified`;
  recurrence reopens (already handled by M11).
- Views: `v_flywheel_health` — per skill version: extraction count,
  correction rate, time-to-validation; per rule: case recurrence after
  address. The "is the loop compounding or spinning" query.
- CLI: `eval holdout --skill <key>` (emits the holdout spec as JSON for the
  harness to execute), `eval record` (ingests the harness's candidate
  outputs and scores them), `eval show <key>`, `policy set require-eval on`.
- Docs: `skill/reference/flywheel.md` Phase 4 atoms marked implemented, with
  the harness-side execution documented as a project skill recipe;
  `docs/tutorial-flywheel.md` extended with the gated approve.

**Tests**: holdout excludes feedback-linked items; held-in membership
derives from the proposal's evidence chain and an empty held-in split fails
the gate; scoring function golden tests (every diff class); gate blocks
approval without a passed run and admits with one; held-in improvement and
held-out regression thresholds each flip pass→fail; `v_flywheel_health`
numbers match hand computation on a fixture.

**Done when**: the flywheel tutorial's approve step fails without an eval
and succeeds with one, entirely via CLI + fixture outputs (no model calls in
CI).

---

## Track F — Serving

### M14. Serving layer + widened feedback

**Goal**: humans become first-class consumers of the same governed data —
compiled knowledge artifacts, a query API, and feedback/usage signals that
feed the same flywheel.

**Changes**
- **Second materialize target** — `materialize.compile_knowledge(store,
  out_dir, *, tenant)`: renders human-readable pages per knowledge unit
  (skills with their current content and version history summary; validated
  extractions grouped by domain), same compiled markers, provenance footers,
  managed-file hygiene, and privacy gate as rules. Output is a static tree —
  deployable to any static host or docs system; the knowledge base humans
  read is build output.
- **Widened feedback grain**:
  - `tables.py`: `UnitFeedbackType` enum (outdated | incorrect | unclear |
    helpful | gap) — document-level, complementing the field-level
    `CorrectionType`.
  - New table `fact_unit_feedback`: `target_key` (any dim key),
    `target_kind`, `feedback_type`, `notes`, `created_by`, tenant, lineage.
  - New table `fact_usage`: `unit_key`, `unit_kind`, `action` enum
    (retrieved | viewed | resolved), `principal`, `occurred_at`, lineage —
    passive signal, append-only, telemetry-store affinity (M4a), covered by
    retention.
  - Couch detector `_detect_unit_feedback_pressure`: units crossing
    feedback thresholds (from `dim_finding_type.parameters`) open cases —
    human feedback enters the *same* case → proposal → approve → compile →
    verify loop as machine-detected patterns. This is the milestone's point:
    one flywheel, two signal sources.
- **Serving API** — optional extra `serve` (FastAPI + uvicorn), new module
  `src/freud_schema/serve.py`, deliberately thin:
  - `GET /retrieve?q=&kind=&k=` → `store.retrieve` (M8).
  - `GET /unit/{key}` → rendered unit + provenance.
  - `POST /feedback` → `fact_unit_feedback` (requires `serve_feedback`
    grant when strict identity is on); every retrieve/view logs `fact_usage`.
  - **No dimension writes.** The API reads knowledge and accepts signals;
    evolution still goes through proposals. Auth is a pluggable dependency
    (header-principal resolution against `dim_principal`; real SSO is a
    deployment concern in front of it).
  - CLI: `serve --host --port` (guarded by the extra, ImportError hint).
- Retrieval boost hook (closing the loop with M8): `retrieve()` gains an
  optional usage-signal boost (units frequently `resolved` rank higher) —
  deterministic, computed from `fact_usage` aggregates.

**Tests**: compiled knowledge tree markers/provenance/gate; unit feedback →
threshold → case opened (end-to-end store test); API tests via FastAPI test
client behind the extra marker (retrieve, feedback write, usage logged,
dimension-write endpoints do not exist); usage boost changes ranking on a
fixture.

**Done when**: a human-readable knowledge tree compiles from a seeded
warehouse; a feedback POST eventually surfaces as an open case in `couch
cases`; and the API cannot mutate a dimension by construction.

---

## Track G — Consolidation

### M15. Dream-work: periodic consolidation passes (added 2026-07-09)

**Why**: event-driven detection and human-triggered flywheel turns are not
enough — between turns, the warehouse and its derived structures degrade on
their own. Findings accumulate near-duplicates; denormalized fact attributes
drift from dims that have since evolved; the retrieval corpus and its
indexes fall behind current rows; staleness baselines age; telemetry
outgrows its retention horizon. A knowledge system that only reacts never
reorganizes. This is the "memory lifecycle as core intelligence" challenge
from the research review, and what the agent-memory literature runs as
offline consolidation ("sleep-time compute"). Here it gets the name the
repo was always going to give it: **dream-work** — condensation,
displacement, secondary revision.

**What exists as the seed**: every operation below is an idempotent data op
the library already half-has — case upserts (M11), `retrieval.reindex()`
(M8), the stale_source detector (M0), `prune_telemetry` (M4a),
`load_run()` lineage for all of it.

**Changes**
- One entry point, `run_dreamwork(store, *, passes=None)` in a new
  `dreamwork.py`, each pass wrapped in its own `load_run` (operation names
  `dreamwork_<pass>`), all idempotent and watermark-aware:
  - **Condensation** (dedup/merge): fold near-duplicate findings into their
    cases (M11's upsert applied retroactively across historical runs);
    merge redundant unit feedback onto the same target (M14).
  - **Displacement** (re-linking): refresh denormalized attributes on facts
    whose source dimensions evolved since insert (skill attrs, tenant);
    emit a dangling-reference report as findings rather than failing.
  - **Secondary revision** (metadata refresh): rebuild the retrieval corpus
    and indexes (M8); recompute source staleness baselines' findings (M0);
    refresh flywheel-health aggregates (M13).
  - **Retention**: `prune_telemetry` past the configured horizon (M4a) —
    knowledge tables never pruned.
- CLI: `maintain run [--pass NAME]` — runs all passes or one.
- **Scheduling stays in the harness** (no-orchestration rule): Claude Code
  cron/hooks, CI schedules, or OS cron invoke `maintain run` on whatever
  cadence fits. The library ships operations that are safe at any
  frequency; it never ships a scheduler. Anything in a pass that needs
  judgment (e.g. semantic merge of near-duplicate knowledge) is an LLM-layer
  job for the harness, exactly like the couch's LLM detectors — the
  library's passes stay deterministic.

**Tests**: run-twice idempotency per pass (second run writes zero rows);
each pass individually invocable; lineage rows present per pass.

**Done when**: `maintain run` twice in a row reports zero writes on the
second run, and a scheduled invocation (documented harness recipe, e.g.
Claude Code cron) keeps a live warehouse consolidated without human
triggering.

## Track H — Harness write surface

### M16. Store-ops MCP server (added 2026-07-09)

**Why**: the lock conventions optimized for read-analysis and made the write
half of the flywheel second-class — native-row writes (rules, proposals,
approvals, compile) need a disconnect-the-MCP-server dance, and the LLM
couch layer writes findings via raw SQL with hand-derived keys, bypassing
the one-write-path guarantee. That is misaligned with the thesis: Claude
Code IS the harness, and the harness writes during sessions. Surfaced by
the first real flywheel turn (2026-07-09), which also caught the couch
skill's key recipe still saying md5 — exactly the drift raw-SQL write
paths breed.

**What exists as the seed**: every operation is already a store method with
validation, key recipes, denormalization, and load_run lineage. The CLI is
a thin argparse layer over them; an MCP server is the same thinness with a
different transport.

**Changes**
- New module `src/freud_schema/mcp_server.py` behind an optional extra
  (`mcp`), started via `freud-schema mcp-serve --db PATH`. It holds the
  single DuckDB connection (replacing the generic duckdb MCP server in
  `.mcp.json`) and exposes:
  - `query(sql)` — read-only (SELECT/DESCRIBE only; writes rejected), so
    ad-hoc analysis keeps its full SQL surface.
  - Store-op tools mirroring the CLI's data operations: `rule_add`,
    `skill_add`, `source_add`, `feedback_add`, `finding_add` (retiring the
    couch skill's raw-INSERT exception), `proposal_add` / `proposal_approve`
    / `proposal_reject`, `extraction_validate`, `compile`, `couch_run`.
    Each is a thin wrapper over the existing store method — no new write
    logic, same validation, same lineage.
  - `ingest_transcripts` — the one CLI-only op left, now in-session.
- CLI handlers and MCP tools share one dispatch layer so the surfaces
  cannot drift (same principle as the batch-delegating single write path).
- CLAUDE.md's DuckDB MCP section rewrites to: reads via `query`, writes via
  store-op tools, no write window, no exceptions.
- The library still never calls models; this server is data ops only.

**Tests**: handler-level round trips against `:memory:` (each tool → store
method → row present); the read-only `query` tool rejects
INSERT/UPDATE/DELETE/DDL; a full flywheel-turn script (rule add → proposal
→ approve → compile) passes through tools alone.

**Risk — self-modification without the human atom** (identified
2026-07-09, before build): an in-session agent with direct `rule_add` /
`skill_add` tools can write rules that load into its own future sessions,
bypassing the proposal → human-approval flow entirely. The CLI has the
same bypass, but a human runs the CLI; MCP tools are agent-invoked. Gate
design, non-negotiable: (a) `rule_add`/`skill_add` tools accept only
`status=draft` (drafts don't compile — activation requires the proposal
flow); (b) `proposal_approve` is never allowlisted — it must surface the
harness permission prompt every single time, making the approval click
the human atom's transport; (c) the read-only `query` tool enforces
read-only via statement classification AND rejects multi-statement input
(CTE/ATTACH/COPY smuggling is a known bypass class — test it explicitly);
(d) `db reset` and other destructive ops are not exposed as tools at all.

**Done when**: a Claude Code session connected only to the store-ops server
completes a full flywheel turn with zero raw-SQL writes and zero MCP
disconnects — and the gate tests prove an agent cannot activate a rule
without a human-confirmed approval.

## Cross-Cutting Workstreams

These don't get milestone numbers; they get enforced at every milestone.

- **Schema docs**: every table/column/enum change lands in
  `skill/reference/schema.md` (respecting its intentional omissions and
  logical column ordering) and the a2ui `prompt_addendum.md` sync.
- **Inventory tests**: the existing `ALL_TABLES`/`ALL_VIEWS` inventory test
  is the tripwire for forgotten registrations — every milestone adding
  tables must extend it (and add new tables to the `reset_schema()` drop
  list, dependents first).
- **Privacy discipline**: every new free-text surface (case summaries, eval
  metrics, unit feedback notes in compiled output, API responses) inherits
  the counts-and-names-only rule; the M6 scanners run over compiled output
  in the existing gate.
- **Versioning**: one minor version per milestone, CHANGELOG entry, version
  sync across the three locations. No phantom dependencies — `postgres`,
  `serve`, embedder backends are extras added only when their milestone
  lands.
- **Backlog hygiene**: items in the internal backlog that a milestone
  resolves get marked DONE with the version, per existing convention.

## Risks and Mitigations

| Risk | Where | Mitigation |
|------|-------|------------|
| Backend split (M4) stalls on dialect drift | Analytical views, JSON ops | Postgres scope limited to the knowledge store (small SQL surface); telemetry stays DuckDB; parameterized backend test matrix |
| FTS/VSS extension availability varies by platform | M8 | Lexical index required, vector optional; brute-force cosine fallback; zero-extension test path in CI |
| Eval gate (M13) creates approval friction that tempts bypass | Human workflow | Gate is per-tenant policy, off by default until holdout sets exist; `require_eval` turns on per dimension; auto-approve stays risk-capped |
| Case signatures too coarse/fine → dedup fails | M11 | Signature is per-detector and versioned in `dim_finding_type.parameters`; changing it opens new cases rather than corrupting old ones |
| Serving API becomes a second write path | M14 | API writes only feedback/usage facts; dimension mutations have no endpoint; enforced by tests that assert the route table |
| Reset-and-rebuild via the locked MCP connection wedges DuckDB's catalog dependency tracking (hit 2026-07-09) | M1 recipe, any reset while the MCP server holds the DB | One transaction per `execute_query` call: creates, indexes, and data loads as separate calls; never `COPY FROM DATABASE`/`IMPORT DATABASE` on the long-lived connection (single-transaction). Full recipe in CLAUDE.md's DuckDB MCP section |
| ~~Fresh full ingest costs minutes~~ RESOLVED 0.26.0 | M1 recipe at scale | Spill-to-JSONL + `read_json` landed with M5: ~600x on the insert loop, live rebuild 2m17s → 13.6s wall |
| In-session write tools enable agent self-modification (rules that load into the agent's own future sessions) with the human atom bypassed | M16 | Gate design in M16: add-tools are draft/inactive-only (never compiled), `proposal_approve` never allowlisted (harness permission prompt = the human atom's transport), read-only `query` enforced at the parser level with multi-statement rejection, no destructive tools exposed |
| Read-only SQL classification bypassed via CTE/ATTACH/COPY/PRAGMA smuggling | M16 `query` tool | Parser-level statement extraction (single statement, SELECT-type only), explicit bypass-attempt tests in the suite |

## Research-Review Amendments (2026-07-08)

A pre-execution research pass ([research-agent-data-representation.md](research-agent-data-representation.md))
confirmed the architecture and produced six amendments. They modify the
milestones above as follows; where an amendment conflicts with earlier text
in this document, the amendment wins. Paper-sourced details cited below are
author-claimed (verified abstracts and author READMEs, not full texts) —
see the research doc's sourcing note.

1. **M11 — root-cause-typed findings.** `fact_finding`/`fact_case` gain
   `terminal_cause`, `causal_status`, and `mechanism` fields. SQL detectors
   leave them null (symptoms); the LLM analysis layer fills them (mechanisms).
   Mechanism never enters the case signature — case identity is fixed at
   detection time, and mechanism is an enrichment attribute on the
   case/finding. Signature definitions change only by a deliberate version
   bump in `dim_finding_type.parameters`, which opens new cases by design.
   Source:
   Self-Harness (arXiv:2606.09498) failure-record structure — surface-identical
   failures can have different causal mechanisms.
2. **M13 — two-sided eval gate.** `build_holdout` produces held-in and
   held-out splits; `complete_eval_run` passes only on held-in improvement
   AND held-out non-regression. Held-in membership is derived, not
   hand-tagged: proposal → evidence findings → their cases' evidence
   sessions → those sessions' validated extractions for the target skill;
   an empty held-in set fails the gate (fail-closed). M13's body reflects
   this. Source: Self-Harness acceptance rule.
3. **M12/M13 — typed evidence links.** Proposal evidence references become
   `{key, claim_kind}` pairs — claim kinds live in an open-vocabulary
   registry seeded with four: **reference** (the cited row exists and
   supports the statement — ScientistOne's citation claim adapted to
   internal evidence), **numerical**, **methodological**, and
   **conclusion**. The approval path verifies each claim kind against its
   cited rows before the gate.
   Source: ScientistOne (arXiv:2605.26340) Chain-of-Evidence.
4. **M9 — selection operators as data.** Activation conditions are the
   first step of an MCE-style ρ/F split (arXiv:2601.21557): skill content
   (ρ) and selection/retrieval/composition operators (F) both versioned,
   both evolvable via proposals. M9 reserves only the top-level `operators`
   key name in the JSON contract, and M9's validator **rejects any use of
   it** (fail-closed) until a later milestone defines the operator registry
   and semantics — the name is reserved so skills never squat on it, but no
   shape is guessed in advance.
5. **M8 — retrieval priority reordered.** Required core at M8 ship time =
   lexical search plus structured-metadata ranking over data that exists
   then (current/active and validation-status boosts). Eval-score boosts
   (M13) and usage-signal boosts (M14) wire into the same fusion when those
   milestones land — each gains that integration task; they are later
   enhancements to M8's ranking, not M8 dependencies, so the milestone
   map's dependency column is unchanged and M14's "optional usage-signal
   boost" is that task. Embeddings stay optional and move last in the
   fusion order. Rationale: both the meta-context literature and production
   harnesses select via structured metadata and agentic lexical search
   first; embeddings earn their place only for large fuzzy corpora.
6. **M5/M14 — storage split made explicit.** M5's adapter protocol gains
   an optional template-mining normalization step (Drain-style signatures
   for log-shaped streams) so high-volume variable text collapses to stable
   signatures before storage. M14's compiled knowledge artifacts carry YAML
   frontmatter (routing metadata: type, title, description, tags) and
   agent-authored diagrams compile as diagrams-as-code (Mermaid/D2), never
   raster.

## What This Plan Deliberately Does Not Do

Consistent with the roadmap's non-goals: no orchestration engine, no
scheduler, no workflow runtime — the harness decomposes, routes, loops, and
runs anything that needs a model. No data migrations, ever, in this repo —
warehouse data is disposable by policy (CLAUDE.md); schema changes reset
and re-ingest, and only a production descendant would reintroduce
migration machinery. No removal of the human approval atom —
every automation added here (auto-approve grants, case auto-verify, eval
gates) narrows what humans must look at; none widens what machines may
change. And no universal ontology: every vocabulary added in this plan
(event types, redaction patterns, thresholds, eval policies) is rows, not
code.
