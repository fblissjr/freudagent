# Research Review: Data Representation for Agent Consumption

Last updated: 2026-07-08

Before starting execution of [the implementation plan](implementation-plan.md),
we ran a research pass to answer two questions: (1) does the architecture —
files as the agent-facing form of knowledge, a database as
catalog/lineage/governance, a human-gated improvement flywheel, skills with
progressive disclosure — hold up against the 2026 literature and production
practice? (2) What is the best representation for each kind of data an
agent-driven, human-governed knowledge system must consume?

**Verdict: the architecture is confirmed, with six concrete amendments**
(recorded at the end of this document and in the implementation plan). The
strongest single input was Lilian Weng's "Harness Engineering for
Self-Improvement" (Lil'Log, July 2026) and the papers it synthesizes; the
strongest practice signal was the documented convergence of production
harnesses on files-plus-thin-index architectures.

**Sourcing note**: several primary sources (arxiv.org, some vendor blogs)
were unreachable from the research environment (egress policy). Findings
marked *author-claimed* come from verified abstracts, author GitHub READMEs,
or converging secondary sources rather than full paper texts. The Weng post
itself was read in full from its public source.

---

## Part 1: What the literature says about the flywheel design

### The harness post (Weng 2026)

Weng, Lilian. "Harness Engineering for Self-Improvement." Lil'Log, Jul 2026.
https://lilianweng.github.io/posts/2026-07-04-harness/

Directly load-bearing claims for this project:

- **File System as Persistent Memory** (her Pattern 2): "A harness should
  not carry the entire workflow and all logs in context; instead, it should
  keep durable state in files" — because file I/O via bash/grep is a
  foundation skill LLMs are pretrained on, so files-as-memory "naturally
  benefits from improvements in core model capability." This is the
  strongest stated rationale for compiling warehouse knowledge into files
  rather than serving it from rows: **the agent-facing representation should
  be the one the model is best trained to navigate.**
- Sub-agent outputs should live "as files, logs, and status records," not
  transient chat context, so the system "can recover after interruptions and
  reason over its own execution history."
- Her future challenges independently restate this repo's design choices as
  open needs: preserve negative results (challenge 3 — our dead-end traces
  and append-only findings); evaluator and permission control outside the
  self-improvement loop with "held-out tests, trace audits, and human review
  at decision points that matter" (challenge 5); humans "move up the stack,
  not be removed" (challenge 7).
- One warning to internalize: per Weng's summary of STOP (Zelikman et al.,
  COLM 2024), recursive improvement improved with GPT-4 but *degraded* with
  weaker base models (GPT-3.5, Mixtral). Caveat: the original arXiv version
  of STOP reports GPT-4-only experiments and we could not verify the
  weaker-model result against a primary text (the same phenomenon is
  independently reported by "Mind the Gap," arXiv:2412.02674) — the
  directional lesson rests on converging evidence, not one confirmed
  experiment. Flywheel-critical judgment (weakness analysis, proposal
  drafting, eval interpretation) must stay on the strongest model tier;
  only mechanical transforms delegate down.

### ACE — incremental structured entries beat document rewrites

Zhang et al. "Agentic Context Engineering." ICLR 2026 (arXiv:2510.04618).

ACE maintains an evolving "context playbook" of small itemized bullets, each
with an identifier, category, and helpful/harmful counters. The critical
design choice: the curator **never rewrites the whole document** — it emits
delta operations (add/update/remove per bullet) merged by **deterministic,
non-LLM logic**, because iterative full-document rewriting exhibits two
measured failure modes: *brevity bias* (rewrites preferentially drop
domain-specific detail) and *context collapse* (repeated re-summarization
compounds into sudden knowledge loss). Author-claimed results: +10.6% on
agent benchmarks, matching a top production agent with a much smaller model.

**Implication (validates)**: rules/skills as many small versioned rows with
deterministic compilation is ACE's architecture with better guarantees. The
"one big evolving instructions file" pattern is the documented anti-pattern.
**Implication (differentiates)**: ACE's curation is fully automated, and its
documented weakness is exactly that — a noisy reflector silently pollutes
the playbook with no gate. Human approval is the fix for ACE's own
failure mode, not overhead.

### MCE — mechanism and content both evolve, both as data

Ye et al. "Meta Context Engineering via Agentic Skill Evolution."
arXiv:2601.21557 (author-claimed details from abstract + project README).

MCE formalizes a skill as a context function `c_s = (ρ_s, F_s)`: static
components ρ (knowledge bases, decision rules, examples) and **dynamic
operators F (retrieval, filtering, composition logic)**, evolved at separate
levels of a bi-level optimization. Skills are stored as **file collections**
(skill definition + context/data rollouts in a working directory), operated
on with plain file tools (Read/Write/Edit/Glob/Grep/Bash). Author-claimed:
large improvements over ACE precisely because the *mechanism* is evolvable,
not just the content.

**Implication (validates)**: skills-as-file-collections with progressive
disclosure is the published pattern. **Implication (amends)**: selection and
retrieval *operators* should be versioned data alongside content — not
hardcoded harness logic. Activation conditions are the start of this;
they should grow into a full ρ/F split.

### Meta-Harness — filesystem for history; structured metadata for selection

Lee et al. "Meta-Harness: End-to-End Optimization of Model Harnesses."
arXiv:2603.28052 (author-claimed details from abstract + project README).

The optimized object is "the code that determines what information to store,
retrieve, and present to the model." The proposer agent accesses "the source
code, scores, and execution traces of all prior candidates **through a
filesystem**" — grep/cat over durable state instead of context stuffing.
Selection of prior candidates uses **structured metadata (scores, task
specs, execution history), not embeddings**. Notably, the reference
implementation uses a Claude Code skill directory — the same pattern as this
repo.

**Honest gap**: neither MCE nor Meta-Harness benchmarks filesystem *against*
a database or vector store; both assume a filesystem and argue
against context-stuffing. The filesystem-vs-DB question is settled by
production practice (below), not by these papers.

### Self-Harness — our loop, with lessons to copy

Zhang et al. "Self-Harness: Harnesses That Improve Themselves."
arXiv:2606.09498 (author-claimed details from abstract + secondary sources).

Their loop maps stage-for-stage onto the flywheel: weakness mining from
execution traces → bounded proposals over declared editable surfaces →
validation → merge. Three details are directly copyable:

1. **Failure records are root-cause-typed, not symptom-typed**: each carries
   the terminal verifier-level cause, the causal status of the implicated
   agent behavior, and the abstract mechanism the trace exposes — because
   two failures with identical surface outcomes (timeout, missing artifact)
   can have different causal mechanisms.
2. **The acceptance gate is two-sided**: a candidate must improve on
   held-in data (the mined weakness is fixed) *and* not regress on held-out
   data (nothing else broke). Accept only on both.
3. **Proposals are bounded**: grounded in an identified failure mechanism,
   targeting one declared editable surface, deliberately minimal — with
   passing behaviors and previously-attempted edits in the proposer's
   context.

Their gate is fully automated where ours is human-approved — and their own
reported findings argue for our choice: reward hacking, catastrophic
forgetting, and under-exploration reappear in **amplified** form in
LM-driven harness self-editing, because a language-model proposer can
construct structured exploits and because edits to shared components
propagate non-locally. Author-claimed gains on Terminal-Bench-2.0 are large
(e.g. 40.5%→61.9%) and model-specific.

### ScientistOne — type the evidence links

Meng et al. "ScientistOne." arXiv:2605.26340 (author-claimed).

Chain-of-Evidence requires every claim to trace to a grounding source, with
**four claim types carrying distinct resolution rules**: citation claims
(source exists and says what's claimed), numerical claims (value traces to a
recorded output), methodological claims (prose resolves to actual
implementation), conclusion claims (derived from supporting claims by
verifiable steps). Author-claimed: zero hallucinated references, and a
75-paper audit where *every* non-CoE baseline produced surface-plausible
outputs hiding evidence-chain failures.

**Implication (amends)**: a proposal's justification is really several claim
kinds — a numerical claim (the detector's counts), a methodological claim
(what the rule text changes), a conclusion claim (the pattern will shrink).
Evidence links should carry a claim type so each is independently checkable,
rather than one generic evidence key. And the general lesson: don't trust
prose summaries of evidence — verify claims against the rows they cite
before compiling.

---

## Part 2: What production practice says about where data belongs

### The files-vs-database question is resolved by role, not by winner

The clearest practice signal of 2025–2026: Anthropic **built RAG with a
local vector DB into early Claude Code and removed it** — "we found pretty
quickly that agentic search generally works better. It is also simpler and
doesn't have the same issues around security, privacy, staleness, and
reliability" (Boris Cherny). Several other harnesses reportedly followed;
Cursor is the notable counterexample, keeping embeddings for whole-codebase
semantic recall on large unfamiliar repos. Meanwhile AGENTS.md (Linux
Foundation-stewarded, 30+ tools) and Anthropic's Agent Skills (SKILL.md with
frontmatter, three-tier progressive disclosure, adopted cross-vendor within
weeks) standardized **markdown files as the agent-facing knowledge
interface**.

On the other side, agent *memory* research (Zep's temporal knowledge graph,
Mem0's vector+graph+KV hybrid, A-MEM's linked atomic notes) uses structured
stores without exception — because episodic/relational facts need temporal
and relationship structure flat files don't encode. And DuckLake (v1.0,
2026) states the hybrid principle outright: files hold content, a SQL
catalog holds "schemas, snapshots, file lists, statistics" — **the
database's job is catalog and governance, not primary storage.**

The division of labor that everything converges on (this repo's name for
the resulting layer is the **grounding layer**: constraints on one end,
grounding data in the middle, verifiers and feedback on the other — the
warehouse its governed truth, compiled files its agent-facing form):

| Data character | Where it lives | Agent access path |
|---|---|---|
| Versioned knowledge artifacts (code, docs, skills, rules) | Markdown/code files in git | Agentic navigation: glob/grep/read, frontmatter routing, progressive disclosure |
| Episodic, relational, high-volume events (telemetry, feedback, provenance, metrics) | Structured store (columnar/relational) | Aggregation views, detectors, purpose-built query methods — never raw scans |
| The bridge | DB as catalog/lineage/governance **over** the files | Compilation with provenance; drift checks; audit |

A pure-markdown knowledge corpus fails not on retrieval (grep + naming +
frontmatter scale surprisingly far) but on **aggregation, concurrent writes,
lineage, temporal queries, and governance**. A pure database fails not on those but
on **agent navigation** — models are pretrained on files and shell idioms,
and `LIKE` scans over free-text columns are the worst of both worlds. The
`LIKE`-on-every-column problem is a symptom of putting artifact-shaped data
in rows; the grep-can't-count problem is a symptom of putting event-shaped
data in files. Neither one should hold the other's data.

Key sources: Anthropic "Effective Context Engineering for AI Agents";
Anthropic "Equipping Agents with Agent Skills"; agents.md; vadim.blog on
Claude Code's no-indexing decision; Cursor's codebase-indexing writeups;
Zep (arXiv:2501.13956); Mem0 (arXiv:2504.19413); A-MEM (arXiv:2502.12110);
DuckLake v1.0 announcement; "Everything is Context" (arXiv:2512.05470).

### Per-data-type recommendations

**Code.** Git is settled; the question is metadata layers. In production:
convention files (AGENTS.md / CLAUDE.md, hierarchical, nearest-wins) are the
standard; ADRs are shifting from retrospective records to *active
governance* docs agents check before architectural changes; generated repo
maps (tree-sitter symbol extraction with PageRank-style ranking under a
token budget, per Aider) and LSP-backed symbol tools (Serena) reduce
navigation cost. Grep-only vs. indexed is genuinely contested — Anthropic
ships grep-only; indexed tools claim large tool-call reductions in
vendor-run benchmarks. Data created *from* human/agent/code interaction
splits by the same rule: durable distilled guidance → markdown in the
repo (compiled, provenance-stamped); episodic traces/feedback/findings → the
warehouse. Insight should never live only in transcripts.

**Diagrams and images.** Diagrams-as-code (Mermaid, D2) as the source of
truth wherever the diagram is agent-authored or agent-maintained: git-
diffable, agent-editable, natively rendered by GitHub/GitLab, and the
default output format in Claude Code's own docs. For raster images that must
exist (screenshots, photos, external figures): colocated sidecar markdown
descriptions (caption + OCR hybrid — caption-only hallucinates on text-heavy
diagrams), discoverable by glob/grep; database rows carry catalog metadata
(hash, source, lineage), not the description. Multimodal embeddings remain
niche for this use. Vision models are treated as *converters to text*, not a
reason to keep knowledge in pixels.

**Structured systems and APIs.** The strongest evidence of any category:
semantic layers beat raw text-to-SQL decisively (dbt's own benchmark
reports large per-model gains for covered queries via its semantic layer —
pairs like 84%→100% — over raw text-to-SQL; Spider 2.0 under agentic
evaluation drops to ~21%, enterprise variants lower). The working pattern: governed metric/entity definitions exposed via
MCP; schema cards with column descriptions and sample values *as data*;
access rules compiled before query execution. For agents: purpose-built
query tools over raw SQL access; token-shaped results (CSV over JSON,
cursor pagination); let the agent write aggregations rather than retrieve
raw rows. Reference data snapshots as Parquet files for zero-infra agent
access; live MCP queries where freshness/governance dominate.

**Documents.** Full convergence on **markdown-normalized documents as the
shared format** (MarkItDown, Docling, Unstructured — all converting
everything to markdown at ingest), with YAML frontmatter conventions
emerging as a vendor-neutral spec (Google's Open Knowledge Format;
Anthropic's SKILL.md frontmatter). Retrieval strategy splits by corpus size:
agentic navigation over ToC/hierarchical indexes for single/few-document
work; chunk-and-embed with contextual augmentation only at large multi-doc
corpus scale. Convert once at ingest, keep structure, index with small
always-loaded surfaces.

**Logs.** The clearest *database* case: "treat logs like data, not text."
Production pattern: structured pipeline (OTel-style, with redaction at the
pipeline) → columnar store or Parquet; **template mining (Drain-style) to
collapse variable text into stable signatures** before any model sees them;
pre-aggregation; agents query via SQL/purpose-built tools (Loki's MCP,
DuckDB-over-Parquet), never grep raw volume. Tiered retention: recent detail
hot, older data summarized/redacted. The grep-vs-SQL threshold argument in
practice: files are fine for tens-to-hundreds of entries as working memory;
ranked/structured access wins beyond that; the resolution is again tiered —
filesystem for working state, database as source of truth for volume.

---

## Part 3: Amendments adopted

These are folded into [the implementation plan](implementation-plan.md) as
the Research-Review Amendments section; recorded here with their rationale.

1. **Root-cause-typed findings** (M11): findings/cases gain
   terminal-cause / causal-status / mechanism fields, filled by the
   LLM analysis layer — detectors find symptoms; findings should record
   mechanisms. (Self-Harness failure-record structure.)
2. **Two-sided eval gate** (M13): acceptance requires improvement on the
   held-in split (targeted weakness fixed) *and* non-regression on the
   held-out split; held-in membership derives from the proposal's evidence
   chain, and an empty held-in set fails closed. (Self-Harness acceptance
   rule.)
3. **Typed evidence links** (M12/M13): evidence references carry a claim
   kind (reference — cited row exists and supports the statement,
   ScientistOne's citation claim adapted to internal evidence — plus
   numerical / methodological / conclusion; registry, not enum) so each is
   independently checkable before approval and compile.
   (ScientistOne Chain-of-Evidence.)
4. **Selection operators as data** (M9): activation conditions grow toward
   MCE's ρ/F split — retrieval/selection/composition logic versioned and
   evolvable through the same proposal flywheel as content.
5. **Retrieval priority reordered** (M8): lexical search plus
   structured-metadata ranking are the required core (status boosts at
   ship time; eval-score and usage-signal boosts wire in when the eval and
   serving milestones land); embeddings remain optional and last — matching
   both the papers (structured-metadata selection) and production practice
   (agentic search first, embeddings for large fuzzy corpora only).
6. **Storage split made explicit** (M5/M14): event-shaped ingest gains
   template-mining normalization (Drain-style signatures) as an adapter
   capability; compiled knowledge artifacts adopt YAML frontmatter for
   routing metadata; agent-authored diagrams compile as diagrams-as-code.

One deliberate non-change: human approval stays, now with
empirical backing — the fully-automated alternative's own literature
reports amplified reward hacking and non-local edit propagation, and the
strongest automated system (Self-Harness) flags that higher-stakes changes
need "stronger acceptance gates than pass-rate non-regression alone."
