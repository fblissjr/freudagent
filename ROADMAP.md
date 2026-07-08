# Roadmap: From Single-Operator Experiment to Enterprise Flywheel

Last updated: 2026-07-08

This document is the result of a structural critique of the meta-harness as it
exists today, generalized to a question bigger than this repo: **what would it
take for this architecture to power any enterprise system that cold-starts a
knowledge base and data store, then continuously improves it through a data
flywheel — agents doing the modeling, transformation, and maintenance; humans
governing every change; skills updating dynamically and loading through
progressive disclosure?**

The short answer the critique produced: **the conceptual model scales; the
substrate doesn't.** The parts most systems get wrong — provenance, versioned
knowledge, human approval as a first-class pipeline stage, behavior-as-data —
are already right here. The parts that break are the predictable ones
(single-process storage, no migrations, no identity) plus two less obvious
ones that are the actual hard problems at scale: **retrieval** and **finding
lifecycle**. Nothing in the critique invalidates the model; every gap is an
addition the schema was shaped to receive.

This roadmap records what to preserve, what to rebuild, and in what order —
so that any enterprise-scale descendant of this design inherits the right
invariants and replaces the right substrate.

---

## The Generalized Target

Any enterprise instance of this pattern has the same shape, regardless of
domain:

1. **Cold start**: seed the knowledge base from whatever exists — documents,
   telemetry, historical records, human expertise. Nothing is trustworthy yet;
   everything is versioned from day one.
2. **Sense**: continuously ingest operational data (agent transcripts today;
   any event stream tomorrow) into a warehouse with deterministic keys, so
   re-ingestion is idempotent and lineage is total.
3. **Analyze**: deterministic detectors mine the warehouse for recurring
   patterns and produce typed, evidence-linked findings. Inference is reserved
   for judgment calls only.
4. **Evolve**: findings become proposals; humans approve; approvals create new
   SCD-2 versions of skills and rules. Approval is the one irreducibly human
   atom — nothing auto-applies.
5. **Materialize**: current, active knowledge compiles into the artifacts the
   harness (and eventually human consumers) actually load, each carrying
   provenance back to the proposal and findings that justified it.
6. **Verify**: new knowledge versions are tested against held-out validated
   history before they ship. Regressions block; improvements compound.

Each turn of the loop makes the next turn better. Human corrections are the
training signal. Skills are retrieval, not configuration — loaded by relevance
at L1/L2/L3, never all at once. That is the flywheel, and it is
domain-agnostic: only the seed corpus, the detectors' vocabulary, and the
skill contents change per use case.

---

## Invariants: What Already Scales (Preserve at All Costs)

These survived the critique intact. They are the extractable value of the
experiment and must not be traded away during any rebuild.

### 1. The provenance chain
`finding -> proposal -> human approval -> SCD-2 version -> compiled artifact
with a provenance footer`. This answers the question every long-lived
knowledge base eventually fails: *why does this say what it says, who approved
it, and on what evidence?* Rollback is `rollback_dimension` + recompile.
Knowledge changes are auditable, evidence-linked transactions — not anonymous
edits that rot in place.

### 2. SCD-2 dimensions as the knowledge model
Knowledge decays. Versioned dimensions with `effective_from/to`, `is_current`,
and `hash_diff` change detection make "what did we believe on date X" a plain
query and make staleness distinguishable from currency. This is the correct
data model for a knowledge base intended to outlive its authors.

### 3. Deterministic keys and idempotent ingest
MD5-style hash surrogates from natural keys mean any worker can compute a
row's key without coordination, re-ingestion of unchanged data writes zero
rows *by construction*, and `meta_load_log` makes the guarantee measurable
rather than assumed. This pattern ports directly to distributed enterprise
ETL. (The hash algorithm itself will change — see Phase 1 — but the pattern
is the invariant.)

### 4. Two-layer analysis: deterministic first, inference last
SQL detectors produce typed findings cheaply and repeatably, with no model
calls in the hot path. The LLM layer handles only what pattern-matching
cannot. The open-vocabulary finding-type registry (new finding types are rows,
never enum edits) is exactly right for domains where the taxonomy of problems
is discovered, not designed.

### 5. The compiler model
The warehouse is the source of truth; loaded artifacts are build output with
do-not-edit headers, source lines, and provenance footers. Fail-closed gates
block bad output while preserving the last good compile. This generalizes
beautifully: the same materialize stage can emit agent context today and
human-readable knowledge artifacts tomorrow, with identical provenance.

### 6. Progressive disclosure as the context economics
L1 always loaded, L2 loaded on routing match, L3 loaded on demand. Context
windows are attention, not memory; the constraint is precision and the goal is
recall. This thesis is correct and becomes *more* important at enterprise
scale, not less — but it needs a real retrieval layer under it (Phase 3).

### 7. Data, not code — inside the harness, not outside it
Orchestration frameworks churn; a governed schema of skills, rules, findings,
and provenance survives all of them. Behavior lives in rows, and the thinness
of the orchestration-adjacent modules is the proof. The one amendment: a
knowledge base that humans consult directly needs a serving layer no harness
provides (Phase 6). That is a second consumer of the same data, not a
betrayal of the thesis.

---

## The Phases

Ordered by dependency, not by difficulty. Phases 1–2 are foundations that get
more expensive to retrofit with every row accumulated; 3–5 are the hard
problems; 6 completes the loop for human consumers. Phase 0 is what a fresh
enterprise deployment does on day one.

### Phase 0 — Cold Start Playbook

**Why**: every enterprise instance begins with an empty warehouse and a body
of pre-existing knowledge in the wrong shape. The flywheel needs a first turn.

**What exists as the seed**: `SkillOrigin` already distinguishes
`human_authored` from derived skills; sources carry `media_type`,
`source_hash`, and `superseded_by_key`; the extraction/feedback loop already
handles "agent transforms raw material into structured knowledge, human
corrects it."

**What to build**:
- A documented bootstrap sequence: register domain sources, author seed rules
  and v1 skills by hand, run agent-driven extraction over the seed corpus,
  and route *all* early output through human validation (cold-start output is
  training signal, not truth).
- Confidence tiering from day one: everything derived starts untrusted;
  validation promotes. The `validation_status` machinery already models this —
  the playbook makes it policy.
- Seed-corpus staleness watch: `source_hash` exists but nothing re-checks it.
  Cold-started knowledge decays fastest; detecting changed sources is the
  first maintenance detector worth writing.

### Phase 1 — Substrate Hardening (storage, keys, migrations, tenancy)

**Why**: the single-file, single-process database is the load-bearing wall.
The workaround choreography around the file lock is tolerable for one
operator on one machine and disqualifying for concurrent agents, pipelines,
and reviewers. And "no migration path; breaking changes reset the schema" is
honest for an experiment but definitionally incompatible with a long-term
store: transcript-derived facts are re-ingestable, but **human feedback,
proposals, and approval history are not re-derivable from anything** — they
are the most expensive data in the system.

**What exists as the seed**: all access already goes through the store layer
(never raw connections), which makes the backend swappable. Schema versioning
exists (`meta_schema_version`); nothing consumes it yet.

**What to build**:
- **Backend abstraction made real**: a server database for the transactional
  side (dimensions, proposals, feedback) and/or a lakehouse pattern for the
  analytical side, behind the existing store interface. Flag and port the
  engine-specific SQL in the analytical views.
- **Forward migrations**: invert the reset convention. Once the warehouse
  holds a single human correction, `reset_schema()` is for tests only.
- **Multi-tenant natural keys**: entity identity is currently
  single-namespace (skill = `domain|task_type`, rule = bare `name`). These
  collide the moment two teams exist. Tenancy/team must join the natural key
  — and because keys derive from natural keys, this decision must precede
  data accumulation, not follow it.
- **Key algorithm swap**: truncated SHA-256 in place of MD5. Cryptographically
  irrelevant here, but compliance regimes ban MD5 outright, and keys are
  everywhere — cheap now, brutal later.
- **Split the stores conceptually**: the telemetry warehouse (high-volume,
  sensitive, retention-bound) and the knowledge store (small, precious,
  kept forever) have different access, backup, and lifecycle needs. One file
  conflating both is a liability.

### Phase 2 — Ingest Generalization, Redaction, and Identity

**Why**: today's ingest is transcript-shaped and the privacy gate is
fail-closed at the *wrong end of the pipe* — it blocks leaks at compile time
while accepting a dirty warehouse. At enterprise scale, once sensitive
content is *in* the warehouse, the warehouse itself is the exposure:
retention policy, deletion requests, and audit all land on it. And every
actor column (`created_by`, `reviewed_by`, `validated_by`) is free-text,
which means the governance loop cannot ask "who may approve?"

**What exists as the seed**: the lineage envelope (`record_source` allowlist,
`etl_run_id` joining the load log) already anticipates multiple ingestion
sources; the load-run context manager gives every operation typed stats.

**What to build**:
- **Generic event grain**: generalize the message/tool-use fact tables so
  agent transcripts are one `record_source` among many enterprise event
  streams, rather than the privileged shape.
- **Ingest-time redaction**: secret scanning and sensitive-content
  classification *before* rows land, making the warehouse clean by
  construction. The compile-time gate remains as the backstop it was always
  meant to be.
- **Real identity and authorization**: actors become principals; proposal
  approval becomes a permissioned action; scoping (who sees which projects,
  domains, findings) becomes enforceable. Conflicting knowledge across teams
  is handled by *scoping*, not forced resolution — two teams can hold
  different active rules for the same name in different scopes.

### Phase 3 — Retrieval as a First-Class Layer

**Why**: this is the actual hard problem. Skill routing today is exact-match
on `(domain, task_type)`, and `activation_conditions` is a stub nothing
reads. That works when the harness is the router choosing among dozens of
skills. At enterprise scale the consumers describe their needs in fuzzy
language and the system must rank *thousands* of knowledge units — and the
progressive-disclosure thesis assumes the routing decision is cheap and
known, when at scale the routing decision **is** the product. Relatedly:
rules currently compile flat into an always-loaded directory; hundreds of
rules would blow the context budget and contradict the thesis itself.

**What exists as the seed**: the L1/L2/L3 hierarchy and the schema's mapping
of levels to tables (rules always; skills on match; sources/history on
demand) is the right frame. `activation_conditions` is the right column
waiting for semantics. Rule `scope`/`domain` columns exist for scoped
loading.

**What to build**:
- **Hybrid retrieval over knowledge units**: full-text plus vector search
  plus structured filters over skills, rules, findings, and validated
  extractions, with ranking. This is what makes L2 "loaded on match" real
  when matches are semantic rather than exact.
- **Activation conditions with teeth**: skills declare when they apply;
  the assembly layer evaluates conditions against the task, retrieves
  candidates, and loads winners — L2 selection becomes ranked retrieval.
- **Scoped materialization**: rules compile into scope- and domain-organized
  artifacts so L1 stays small at any rule count. Always-loaded content must
  stay bounded no matter how large the knowledge base grows; everything else
  earns its context window through retrieval.
- **Drift detection between truth and build output**: compiled artifacts are
  a cache of the warehouse; at scale, a check that compiled state matches
  current dimensions belongs in CI, not in trust.

### Phase 4 — Finding Lifecycle and the Review Workflow

**Why**: findings are append-only trend data with no state. Each analysis run
re-emits everything it sees. With one careful operator running it
occasionally, "did the pattern shrink" being a plain query is fine; run it
continuously at enterprise volume and the review queue is mostly
re-detections with no way to distinguish *new* from *known* from *resolved*.
Meanwhile the single human-approval atom — correct for governance — becomes a
throughput bottleneck without a workflow around it.

**What exists as the seed**: deterministic keys make recurrence recognition
nearly free (same finding, same natural key). Proposal status and reviewer
fields exist. The flywheel decomposition already names "flag conflicts" and
"threshold evaluation" as atoms — unimplemented but correctly identified.

**What to build**:
- **Findings become cases**: open → triaged → addressed-by-version-X →
  verified-shrunk → closed, with dedup against prior runs and a "what is NEW
  since the last run" view as the default human entry point.
- **Incremental detection**: detectors run from watermarks, analyzing only
  new data since the last run — required both for correctness of "new vs
  known" and for the scale math (full-table scans with unbounded evidence
  aggregation die at enterprise event volume; windowed detection with
  retention policies does not).
- **Review workflow at volume**: triage tiers (risk-scored auto-routing,
  batch review, escalation), reviewer assignment, and queue SLAs — built
  *around* the proposal table, which already supports it, not into a new
  system. Approval remains the human atom; the workflow makes it survivable.
- **Per-domain detector thresholds as data**: thresholds move from module
  constants to registry rows, tunable per domain without code changes —
  already flagged in the code as the planned extension.

### Phase 5 — The Verification Gate (closing the flywheel)

**Why**: the loop's final phase — holdout testing, regression detection,
metric recording — is honestly documented as not existing. This is the
difference between a knowledge base that is *evolving* and one that is
*drifting*. With one careful human, eyeballs suffice; with many approvers and
compounding versions, every approved change is a hope unless it is tested
against history before it ships.

**What exists as the seed**: validated extractions are already queryable as a
holdout set; sessions carry skill version stamps, so "accuracy by version" is
a join away; the flywheel decomposition specifies all three verification
atoms and their handoffs.

**What to build**:
- **Eval gates before compile**: candidate skill/rule versions run against
  held-out validated history; regression blocks materialization, improvement
  ships. The gate is fail-closed, like the privacy gate — the last good
  version keeps serving.
- **Flywheel health metrics as rows**: correction rates per version,
  time-to-validation, finding recurrence after a rule lands — the measures
  that tell you whether the loop is actually compounding or just spinning.
- **A/B by version**: SCD-2 already keeps every version live in history;
  serving a prior version to a control slice is a query parameter, not an
  architecture change.

### Phase 6 — The Serving Layer (humans as first-class consumers)

**Why**: the consumers today are agents assembling context. An enterprise
knowledge system's other consumer is a human at the moment of need — and no
harness provides search, browse, or feedback capture for them. The feedback
grain also reflects agent-output QA (field-level correction types) rather
than knowledge-unit feedback ("this is outdated," "this resolved my
problem") or passive usage signals (was it retrieved? did it help?).

**What exists as the seed**: the compiler model generalizes to any output
target with identical provenance; the query surface already exposes
everything a read API needs; a UI experiment (`a2ui/`) already sketches
visual surfaces over the store.

**What to build**:
- **A second materialize target**: human-readable knowledge artifacts
  compiled from the same dimensions, with the same do-not-edit headers and
  provenance footers — the knowledge base humans read *is* build output.
- **A query/serving API** in front of the store: retrieval (Phase 3) exposed
  to human search, scoped by identity (Phase 2).
- **Widened feedback grain**: knowledge-unit-level feedback types alongside
  field-level correction types, plus usage telemetry as a passive signal
  feeding the same aggregation the flywheel already runs. Human clicks and
  corrections land in the same warehouse, drive the same findings, and turn
  the same flywheel.
- **Staleness as a standing detector**: watched sources (Phase 0's hash
  re-check) produce findings when upstream material changes, proposing
  re-extraction — maintenance becomes a loop the system runs on itself.

---

## Sequencing Rationale

- **Phase 1 before data accumulates**: natural-key tenancy and the hash
  algorithm are baked into every key in the system. Changing them later means
  rekeying the world; changing them now costs a refactor.
- **Phase 2 before scale**: a warehouse that was ever dirty stays a
  liability. Redaction retrofits require reprocessing everything ingested
  before it.
- **Phase 3 and 4 in parallel after 1–2**: retrieval serves consumers;
  lifecycle serves maintainers. They share no schema surface and can proceed
  independently.
- **Phase 5 before scaling approvals**: the verification gate is what makes
  a larger reviewer pool safe. Adding reviewers before adding regression
  detection scales drift, not quality.
- **Phase 6 last but designed-for throughout**: every earlier phase's choices
  (provenance, scoping, retrieval, feedback grain) are what make the serving
  layer thin when it arrives.

## Non-Goals

- **Reimplementing orchestration.** The harness decomposes, routes, and
  loops. This project remains a data layer; every phase above adds data,
  gates, and query surface — never a competing execution engine.
- **Autonomous knowledge mutation.** No phase removes the human approval
  atom. The flywheel's speed comes from making review cheap (dedup, triage,
  eval gates), never from skipping it.
- **A universal ontology.** Finding types, facet types, and skill domains
  stay open-vocabulary registries. The taxonomy of any domain is discovered
  through the loop, not designed up front.
