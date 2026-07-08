# Implementation Plan: Executing the Roadmap

Last updated: 2026-07-08

This is the concrete build plan for [ROADMAP.md](../ROADMAP.md). The roadmap
says *what* and *why*; this document says *how*, against this codebase as it
exists — which modules change, which tables are added, which store methods
appear, what the CLI grows, and what "done" means for each milestone.

The target, restated once: a system that cold-starts a knowledge base from an
empty warehouse, then compounds it through a data flywheel — agents doing the
modeling, transformation, and maintenance; humans governing every change;
skills updating dynamically and loading through progressive disclosure.

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

| # | Milestone | Roadmap phase | Size | Depends on |
|---|-----------|--------------|------|------------|
| M1 | Reset-based schema lifecycle (policy) | 1 | S | — |
| M0 | Cold-start playbook + staleness detector | 0 | S | M1 |
| M2 | Key algorithm versioning (SHA-256) | 1 | M | M1 |
| M3 | Tenancy in natural keys | 1 | M | M1, M2 |
| M4 | Store split + backend protocol | 1 | L | M1–M3 |
| M5 | Generic event grain + ingest adapters | 2 | M | M1–M3 |
| M6 | Ingest-time redaction | 2 | M | M5 |
| M7 | Principals and authorization | 2 | M | M1, M3 |
| M8 | Hybrid retrieval layer | 3 | L | M1, M3 |
| M9 | Activation conditions with teeth | 3 | S | M8 |
| M10 | Scoped materialization + drift check | 3 | S | M3 |
| M11 | Cases, watermarks, incremental detection | 4 | L | M1, M5 |
| M12 | Review queue and conflict handling | 4 | M | M7, M11 |
| M13 | Verification gate + flywheel health | 5 | L | M11, M12 |
| M14 | Serving layer + widened feedback | 6 | L | M8, M10, M13 |

Sizes are relative (S ≈ days, M ≈ a week, L ≈ multiple weeks of focused
work). The order within tracks matters. Track C (M8–M10) can start once the
substrate track lands; Track D additionally needs M5 and M7 from Track B
(see the dependency column). The two tracks then proceed in parallel.

Rationale for the orderings: M1 precedes everything because it fixes the
change mechanism every later milestone uses (schema changes = code + reset +
re-ingest; never a data migration — see the CLAUDE.md policy). M2/M3 (keys,
tenancy) still come early because entity identity is baked into every key:
with reset-based changes the cost of deferring them isn't a rekey migration
but re-creating accumulated native test data (feedback, proposals), which
grows with time.

---

## Track A — Substrate

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
substrate task — that requirement lives in ROADMAP Phase 1, not here.)

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

**Goal**: break the single-file, single-process wall. The knowledge store
(small, precious, forever) and the telemetry warehouse (high-volume,
sensitive, retention-bound) become separable, and the storage engine becomes
swappable behind the store layer.

**Changes — staged in two sub-milestones**

*M4a — logical split (DuckDB only)*
- Classify tables: **knowledge** = SCD-2 dims, registries, `fact_proposal`,
  `fact_feedback`, `fact_trace_feedback`, `fact_extraction`, eval tables
  (M13); **telemetry** = `fact_session`, `fact_message`, `fact_tool_use`,
  `fact_trace`, `fact_session_facets`, `fact_finding`, cases (M11),
  watermarks; `meta_*` exists in both.
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
  since `addressed` + a configurable quiet window, transition to `verified`;
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
6. **M5/M14 — substrate rule made explicit.** M5's adapter protocol gains
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
