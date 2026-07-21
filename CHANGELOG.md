# Changelog

## 0.33.3

Visual review of the rendered diagrams, acted on.

### Fixed

- **The animated loop's panel text could not be read.** Six stages over 18
  seconds is 3 seconds each, against 40-55 word panels that need 8-12. The panel
  was decorative in practice. Cycle is now 24 seconds and each panel is two short
  lines; the six-clause caption under the image carries the detail.
- **Two things pulsed at once.** The approve node had an always-on breathing halo
  that ran in every frame, including frames where a different stage was
  highlighted — and highlighting is also a ring. A glancing viewer could not tell
  which stage was current. Approve keeps its amber treatment, now static.
- **Verify turned green and nothing else in the set was green.** Blue meant
  machine stage, amber meant the human step, then a third colour appeared once
  with no meaning attached. Verify is blue.
- **The pulse sat exactly on an arrowhead at every stage.** It orbited at the
  same radius as the direction markers. Now outside them, and large enough to
  read as motion rather than a speck.
- **`progressive-disclosure.svg` had bars of different widths**, so the shrinking
  loaded share — the entire point — could not be seen without reading labels. All
  three bars now share a right edge with different filled fractions. Also
  "shaded" said the opposite of what the picture showed: the loaded parts are the
  highlighted ones.
- **`grounding-layer.svg` labelled two vertically stacked boxes "LEFT-HAND" and
  "RIGHT-HAND".** Nothing was left or right of anything, and the prose says one
  end and the other. Relabelled to match. Its middle box also shared a name with
  the whole card, so neither was distinguishable; it is now "checked knowledge".
- **`human-gate.svg` put the blocking X on the outgoing edge** of the
  self-modification box, reading as "the agent does this, then it is stopped".
  The claim is stronger — no agent-callable tool can do it at all. The X now sits
  before the box and the box is dashed, marking it as something that does not
  happen.
- The hero footer asserted "each turn leaves the knowledge base better" as fact,
  three lines under a README paragraph saying the half that decides that is not
  built. Now "is meant to leave".
- `storage-split.svg` lost a hairline that read as a stray rule and two ticks
  that looked like leftover guides; its BAD AT body copy moved off salmon, which
  was competing with amber-means-human.
- Three images had prose running on the same line after the tag, from an earlier
  reordering pass. Split, and the paragraphs rewrapped.

## 0.33.2

### Changed

- **`skill/reference/flywheel.md` rewritten.** It described the loop as
  "extract -> review -> correct -> aggregate -> refine skill -> verify", which
  omits propose, approve and compile -- the three stages that are the actual
  design. Now the six stages, with what backs each in this repo and what is not
  built, taken from `docs/data-flywheel.md`'s status table rather than invented.
  Adds constraints on both sides, feedback granularity, the breakdown during the
  run, deviation as two-way signal, model-generated feedback and its diversity
  precondition, and skills as a ragged hierarchy -- all previously absent.
- **The twelve "atoms" are now the twelve steps.** "Atom" was a coinage for
  something with an ordinary name, and "Atom IDs" was the worst form of it. They
  are kept as a clearly-labelled finer breakdown rather than deleted, because
  four committed files cite them and they answer a question the six stages do
  not: which steps are deterministic, which need a model, and which only a person
  can do. Every step now maps to a stage in a table, so a reader is not left with
  two unreconciled models.
- The step table is now the definition of record. It previously pointed readers
  at `internal/flywheel_decomposition.json`, which is gitignored -- a committed
  reference sending people to a file they cannot open, for numbers cited from
  committed code.
- `skill/skill.md` routing row for that file said "flywheel atoms"; it now
  describes what the file actually contains.

- **`docs/flywheel-failure-modes.md`** gains two failure modes the design implies
  and the doc had missed: asking people to judge at a level they cannot evaluate,
  and the breakdown being authored instead of observed, which rots the way a data
  catalog does and takes the deviation signal with it. Twenty-two entries now.
  Terminology aligned with the main docs -- "synthetic feedback" is
  model-generated feedback, and held-out, stratified and always-loaded are gone.

- **Visual placement.** In five of seven cases a diagram sat directly under its
  heading, so a reader met the picture before the claim it illustrates. Every
  diagram now follows a one-sentence statement of what it shows. The animated
  loop in the README and the explainer had no gloss, so six stage names arrived
  unexplained; both now carry the same one-line summary the detailed doc has.
  The explainer gains the grounding-layer diagram in the section about it.

### Fixed

- README described `docs/data-flywheel.md` as saying "exactly what runs today",
  which frames the design doc as a status report. It is the vision; one section
  in it reports status. Reworded.

## 0.33.1

Alignment pass on the explainer and README after a review against the stated
design vision.

### Fixed

- **`how-it-works.md` claimed an experience that did not happen.** A section was
  headed "The thing that surprised us" and then described deviation-as-signal,
  which is unbuilt and has never been observed. Renamed to "Deviation cuts both
  ways", which is what it actually is: design reasoning.
- **The explainer resolved a question the design leaves open.** Its central
  paragraph said to keep instructions in a database and build files from rows.
  The design says a skill lives in both — artifact in git, metadata in a table —
  and that what lives where is genuinely open, with versioned-and-immutable as
  the only non-negotiable. Rewritten as "Where the knowledge lives".
- Five named parts of the design were missing from the explainer entirely:
  constraints on both sides, the grounding layer, what a skill is, that the
  breakdown happens during the run and is where interpretability comes from, and
  cold start. All added. The word "skill" appeared zero times in a document about
  maintaining skills.
- "Every set of agent instructions goes stale" restored to "most" in both the
  explainer and README. The detailed doc had the hedge; both derived documents
  had dropped it.
- Build state now disclosed in the opening of the explainer and the README
  rather than only near the bottom. The mechanics were written in the present
  indicative, so a skimmer read them as shipped.
- Author-claimed research is hedged in the explainer, matching the parent's own
  sourcing caveat.
- Cut "Most teams build them, and most of those systems still don't improve" —
  a population claim about the industry with nothing behind it.
- Headings that read as hubris are gone: "The move", "The part everyone gets
  wrong", "The thing that surprised us", "What we can't tell you yet".
- Restored that the harness itself can be the sampling interface, which connects
  to the inside-the-harness thesis and had been cut to a vague "something".

### Changed

- `data-flywheel.md` reconciled an apparent contradiction: "the warehouse is the
  source of truth, the files are a cache" versus "the artifact belongs in git".
  Both are true of different things — compiled rules are rendered from rows,
  skill content is authored as a file with the warehouse holding its history —
  and the doc now says so.
- "altitude" replaced with "level"; the process-mining reference no longer
  asserts scholarly standing it was not given a source for.
- README glosses "harness" on first use and says what the repo physically is.

## 0.33.0

### Changed

- **README cut from 373 lines to 81.** It had become a stale copy of five other
  documents: the CLI reference (which lives in `skill/skill.md`), the full table
  inventory (`skill/reference/schema.md`), the archetype and preset tables
  (`skill/reference/archetypes.md`), the project structure (`CLAUDE.md`) and a
  Python API example (the extraction tutorial). Every one of those was verified
  to exist elsewhere before removal. A front door duplicating five documents is
  the same rot problem this project is about, aimed at ourselves.

  It now does what a README should: says plainly what this is, shows the
  animated loop, and links out. The opening no longer describes the project as
  "a meta-framework for declarative agent orchestration" -- it says agent
  instructions go stale and this is a design for keeping them current.

  The animated flywheel now sits near the top, which is the slot a short
  explainer video would take when one exists.

## 0.32.0

### Added

- **`docs/how-it-works.md`** -- the short explainer derived from
  `data-flywheel.md`. About 1,400 words, five minutes, no jargon at all. Leads
  with the so-what: agent instructions go stale the way every data catalog does,
  and this is a design for making the system keep them current with a person
  approving each change. Carries the animated loop and the approval-gate diagram.

  Written to stand alone for someone arriving from the README who has never seen
  this repo. It does not reference what any doc used to say, because a first-time
  reader has no stake in our history.

  README's "Start here" now leads with it and points at `data-flywheel.md` as the
  detailed source of truth behind it.

## 0.31.0

Documentation only. `docs/data-flywheel.md` restructured and rewritten, not
reordered — the jargon changes touched the argument, so a reorg would have been
pretending.

### Changed

- **Signal now comes before mechanics.** The doc argues that these loops fail
  from lack of signal far more often than from broken mechanics, then spent its
  middle on mechanics and put signal near the end. The structure enacted the
  error the content warns about. Signal is now one continuous section ahead of
  the six stages.
- **Signal was one subject split across two distant sections.** Constraints,
  granularity and the breakdown sat early; feedback grains, model feedback and
  sampling sat late; deviation was buried between them. Merged.
- **The grounding layer moved early.** It is the organising concept and the one
  term we coined, and it previously arrived 400 lines after first being used.
- **The storage principle came out from under skills.** Versioned-and-immutable
  regardless of location is a general claim and now sits with the data model;
  the skills-specific application stays in the skills section.
- **Deviation promoted** out of a third-level subsection.
- The end-to-end diagram moved to the head of the stages it depicts rather than
  sitting below them.

### Removed

Jargon that was never explained, replaced rather than glossed: held-out,
fail-closed, stratified sample, statistical power, and the L1/L2/L3 labels,
which the doc introduced without ever saying what was in each level. Each is now
said plainly — "work already reviewed and marked correct, kept aside", "refuses
rather than degrades", "spread deliberately across", "enough observations to
detect the effect".

### Sharpened

- **The competing explanation.** Previously "base model improvement dominates,
  making the grounding layer neutral at best". Now stated precisely: models
  improve by learning from inputs, outputs and paths rather than from explicit
  rules, which makes the recorded data the valuable asset and generic written
  guidance progressively redundant. What survives is what a model cannot learn
  from pretraining — this organisation's definitions, policies and business
  rules. That yields a testable prediction rather than a worry: the surviving
  corpus should skew toward business-specific rules and away from technique, and
  if it does not, you are writing down things the model would have done anyway.
- **Verification cost.** Previously stated as a universal tension between rigour
  and speed. It is a property of the use case: a daily batch can afford thorough
  verification, an event-triggered path answering in seconds cannot. How
  rigorous the gate is is a deployment decision, not a fixed design point.

### Diagrams

- `progressive-disclosure.svg` asserted three balanced levels as the model while
  sitting beside text calling that a simplification of a ragged hierarchy. Now
  says so, and its panel carries the actual ranking claim rather than a vaguer
  restatement.

## 0.30.1

Documentation only. An alignment pass after six independent reviews of the core
doc, its diagrams, and `.claude/`.

### Fixed

- **Decomposition granularity was inverted.** The doc said work is decomposed
  *until* it reaches a judgeable level. The design is the opposite: decomposition
  and recording go all the way down, and the judgeable level is where a person is
  *asked to look*, which is higher. The doc's version also argued against going
  too fine, which contradicts recording at the lowest granularity. Capture depth
  is not a dial; only the asking is tuned.
- **The decomposition section contradicted its own title.** Headed "Decomposition
  happens during the run", it then redefined decomposition as a cross-run
  dimension. Each run's decomposition is now stated as a fact recorded as it
  happens, with the cross-run pattern presented as something derived on top of
  those facts rather than as what the word means.
- Feedback origin labelling was hardened past the design: human versus
  model-derived is the floor, more granular origin is the direction, and the doc
  had rejected the binary as insufficient.
- "Agent skills will rot" restored to "most, not all".
- "the job that created it" restored to "the ETL run that created it" -- plainer
  here was less precise, and ETL run is the standard term.
- Evals reconnected to version trending. They appeared only as a pre-ship gate;
  they are also the outcome measure a skill's version history is trended against.
  A skill table without eval scores says what changed and when, not whether it
  helped.
- Cold start had lost its home and was left as a dangling forward reference. It
  now has a section under the data model.
- Open/closed vocabularies no longer claim to be "most of this design" -- it was
  one of four competing claims about which part decides everything.

### Diagrams

- `grounding-layer.svg` rewritten. It drew one constraint face plus two other
  things, contradicting the doc's headline claim of constraints on both sides.
  Now left-hand constraints, grounding data, right-hand constraints, with the two
  constraint faces sharing a treatment the middle does not, and deviation added
  to the right-hand list.
- `storage-split.svg` rewritten. It listed skills as living in git only, directly
  contradicting the section it illustrates. Now shows a skill's artifact and its
  metadata across both stores, leading with the versioned-and-immutable invariant.
- `human-gate.svg` and the hero's stage 4 panel both stated the gate as an
  absolute guarantee. Scoped to tools that route through it, since the doc now
  says anything with write access is in the threat model.
- Hero: verify node no longer dashed, which was a leftover status signal.

### Elsewhere

- `.claude/skills/db-query.md`: `ingest_events` was missing from the write-tools
  prose list though present in the table below it.
- `CLAUDE.md` and `README.md` still described `ingest.py` with the retired "Sense"
  stage name.

## 0.30.0

Documentation only. `docs/data-flywheel.md` becomes the detailed source of truth
for the design; a plain-English explainer will be derived from it separately.

### Added

- **Constraints on both sides.** An agent needs left-hand constraints (what it
  may and must do) and right-hand constraints (what good means). Most systems
  build only the first, and deferring the second is why they never demonstrably
  improve. Evals are the right-hand constraint set, not a gate bolted on the end.
- **Feedback granularity follows from decomposition.** People can only judge what
  they can evaluate; judging a whole outcome yields a verdict with nowhere to go.
  Work decomposes until a person can answer confidently, judgement is captured
  there, and results aggregate up to business altitude. Interpretability comes
  from the decomposition, not the evaluation.
- **Decomposition happens during the run.** It is the shape of the work, emerging
  as the agent goes, not an artifact authored in advance -- and depth is
  genuinely variable, sometimes zero. The execution tree of one run is a fact;
  the decomposition is the dimension learned from many, which then becomes
  orchestrator-level guidance. An authored decomposition would rot exactly like
  a data catalog.
- **Deviation as bidirectional signal.** Comparing prescribed process against
  observed process is conformance checking. A departure with a worse result means
  the guidance was right; a departure with an equal or better result means the
  guidance was wrong and the agent found out. Every detector described before
  this found only problems. Safe only when outcomes are measurable at the level
  the deviation occurred, and when guidance declares enough structure to depart
  from.
- **Skills as a ragged hierarchy** spanning orchestrator-level decomposition down
  to field-level semantics -- what a column means to this business, which of
  three date columns anyone means. That bottom rung is the best-evidenced part of
  the whole design and was previously unmentioned. L1/L2/L3 is named as the
  teaching simplification of arbitrary depth; progressive disclosure is lazy
  traversal of it.
- **Skills live in git and in a table.** Artifact in git, metadata in rows:
  version, identifier, the job that created it, what changed and why. The second
  half is what lets you ask whether a skill's evolution moved outcomes. The
  invariant underneath holds regardless of storage -- versioned and immutable,
  new rows never edits.
- **Catalog rot as the motivation.** Every organisation's data catalog is
  accurate at onboarding and describes a company that no longer exists within a
  year. Agent skills rot the same way for the same reason. The question is not
  how to write good instructions but who keeps them current.
- Two failure modes in the companion doc: safeguards optimised away (steps
  guarding rare events look like waste in every sample without the rare event),
  and deviation acted on without outcome measurement.

### Changed

- Terminology. Ingestion is called ingestion; pipelines are pipelines. Invented
  vocabulary removed where a standard term exists -- the "sense" stage is now
  ingest, "publish" is compile, and "objects" (never an established term here)
  is replaced by ordinary facts and dimensions. Coinage kept only for the
  grounding layer, which has no other name.
- The hero diagram follows the rename, drops its per-stage status chips now that
  status lives in one section, and stops dashing the verify node.
- `storage-split.svg` leads with the invariant rather than the split.

## 0.29.0

Documentation only. No code or schema changes. `docs/data-flywheel.md` was
rewritten after a six-lens review; the version bump reflects that it is a
different document rather than an edit of the old one.

### Changed

- **`docs/data-flywheel.md` reframed against the vision, not the code.** The
  previous version was structured around what this repo does today, with a
  status marker on every stage. Owner correction: the ground truth is the design
  recorded in ROADMAP, the research review and the implementation plan -- the
  code is one reference implementation of it. The doc now describes how these
  systems should work, and confines current state to one section near the end.
- Examples generalized from agent telemetry to enterprise material (documents,
  policies, records), with agent transcripts presented as one signal source
  among many rather than the privileged case.
- **New section: what the loop runs on.** The doc previously had no unit of
  work. It listed correction types without ever introducing the thing being
  corrected, and referred to sources twice without saying they were registered
  rows. Sources, outputs, validations, corrections, findings and proposals are
  now named with their grain, and cold start is described.
- **New section: where the signal comes from.** Feedback is a labelled overlay
  on immutable records, carrying who or what produced it. Model-generated
  feedback is positioned as amplification requiring a diverse human seed, with
  the two failure mechanisms when diversity is missing (the model falls back on
  its own priors, or stretches feedback from an unrelated slice). Sampling is
  framed as a product surface the harness itself can provide.
- **New section: provenance is a chain, not a footer.** The old text described
  the compiled footer, which is the rendering rather than the architecture. Now
  states it as relationships between rows and shows one worked lineage question.
- **New section: what would show this is wrong.** Names three falsifying
  conditions, including the competing explanation neither document had
  entertained -- that base model improvement outpaces the value of an
  accumulated rule corpus, making the grounding layer neutral at best.
- Restored specificity that had been generalized away: ACE's measured
  rewrite-failure mechanism (brevity bias and context collapse) in place of
  "instructions files grow until nobody trusts them"; the argument that the
  human gate fixes a documented failure of automated curation rather than being
  general caution; the reason root-cause typing matters; selection operators as
  versioned data; open vocabularies as registry rows, and the deliberate
  contrast with the vocabularies that stay closed.
- Added a sources section carrying the research review's own caveats. Several
  cited results were reachable only as abstracts and are author-claimed; the doc
  previously restated them as settled fact while arguing that claims must be
  checkable.
- The July 2026 run is now reported against the doc's own metric: three
  proposals and three approvals is a zero rejection rate, which is
  indistinguishable from a rubber stamp at n=3. Listed as evidence the machinery
  connects, not that the governance works.
- Failure-mode summary gains "one reviewer becomes the policy" and "the
  knowledge base only ever grows", both previously omitted from the main doc.
- `docs/flywheel-failure-modes.md`: the model-generated-feedback entry gains the
  two concrete failure mechanisms and the labelling/sampling controls.
- `docs/assets/storage-split.svg`: adds the bridge. The diagram encoded the
  two-panel version of the storage split, dropping the third row of the research
  review's table -- the warehouse as catalog and governance over the files --
  which is the row most easily lost in summary and the one that makes the split
  a hierarchy rather than two peers.
- `ROADMAP.md` Phase 3 listed vector search as a co-equal retrieval component,
  contradicting adopted research amendment 5 (lexical plus structured-metadata
  ranking required; embeddings optional and last). Corrected.

### Removed

- Claims that were not true of the design or the code: that the privacy gate
  scans for secrets (it matches home paths and usernames; ingest-time redaction
  is unbuilt), that skills compile to files with provenance footers (only rules
  do), that the footer names the approver (it names the proposal and evidence),
  and that the approval prompt cannot be made silent (it depends on permission
  hygiene and on no other write surface being reachable).
- An unkept promise in the third paragraph to put repo vocabulary in brackets
  throughout. It never did this once.

## 0.28.3

### Fixed

- **Proposal evidence keys are resolved instead of stored verbatim.**
  `ops.proposal_add` now passes every `--evidence` entry through
  `store.resolve_key("fact_finding", ...)` before building the `Proposal`, so a
  full key or any unique prefix works and the resolved full key is what lands in
  the row. A key matching nothing, or matching more than one finding, raises
  before `insert_proposal` is called, so no partial proposal is left behind.
  The MCP `proposal_add` tool inherits this, since it routes through the same
  dispatch layer.

  Why it mattered more than a usability papercut: `couch list` prints
  `finding_key[:8]` and `materialize._render` prints `k[:8]` in the compiled
  provenance footer, so pasting a listed key recorded a reference matching no
  row -- and the footer truncated it back to 8 characters, making a broken
  evidence link render identically to a valid one. Evidence links are what make
  a proposal checkable rather than merely plausible, so a silent break there
  defeats the mechanism.

  `store.insert_proposal` is deliberately unchanged; it is the low-level write
  path and still accepts whatever it is given. Prefix resolution belongs at the
  ops layer, where every other key argument already resolves.
- `cli.py`'s `proposal add` branch gained the
  `except ValueError -> stderr -> sys.exit(1)` wrapper that `approve`/`reject`
  already had. Without it the fix above would have replaced a silent wrong
  answer with a raw traceback.

### Tests

- 433 (up from 426). Seven new: full-key round trip, prefix resolving to the
  full key, non-existent key raising with nothing written, ambiguous prefix
  raising with nothing written, `evidence=None` and `[]` unchanged, and a CLI
  end-to-end asserting a clean exit(1) with no traceback. The ambiguity case is
  deterministic by construction rather than by luck -- `finding_key` is a
  sha256/32 hex digest, so its leading character has 16 possible values and
  distinct salted findings are guaranteed to collide on a 1-character prefix.

### Docs

- `docs/tutorial-flywheel.md` section 11 rewritten. It previously documented the
  SQL workaround for getting full keys and flagged the behaviour as a rough
  edge; it now explains that prefixes resolve, and keeps the direct query as the
  way to see more detail than `couch list` shows.

## 0.28.2

Documentation only. No code, schema, or data changes.

### Added

- **`docs/flywheel-failure-modes.md`** -- eighteen ways a data flywheel fails,
  in six groups (signal starvation, biased signal, self-reference, decay, gate
  failures, measurement failures). Each entry gives what it looks like, why it
  happens, how to catch it, and what to do. Generalized past this repo: it
  applies to any system that improves itself from its own usage data, whether
  the knowledge is prompts, rules, indexes or weights.

  The through-line: these loops die from lack of signal far more often than from
  broken mechanics, and the mechanical half is the visible engineering problem.
  Three entries worth calling out because they are counterintuitive rather than
  merely bad --
  - *success starves the loop*: the fuel is errors, so removing errors removes
    fuel, and falling correction volume is genuinely ambiguous between "got
    good" and "stopped looking"
  - *rubber-stamped validation becomes ground truth*: output waved through as
    correct enters the verification set, so a later version that fixes the error
    fails the gate -- verification actively blocking a real improvement
  - *the evidence is pruned and the rule survives*: retention deletes the
    telemetry a rule cited, the citation still renders, and the trail looks
    intact until someone follows it (already observed here after a schema reset)

  Ends with an honest table of what this repo defends against today. Most rows
  say none.
- `docs/data-flywheel.md` gains a "How this goes wrong" section: the five most
  common failures as a table, the two counterintuitive ones in prose, and a link
  through to the full document.

## 0.28.1

Documentation only. No code, schema, or data changes.

### Added

- **`docs/data-flywheel.md`** -- the architecture and data flow end to end, in
  plain English, generalized past this repo: what a data flywheel actually is,
  the six stages (sense, analyse, propose, approve, publish, verify), where
  human feedback enters at two grains, and the three design choices underneath
  (progressive disclosure, the files/warehouse split, behavior as data). Every
  stage carries an explicit built/partial/planned marker against the milestone
  map, so the doc cannot quietly overstate current state. Written as the entry
  point for a first-time reader; links out to the tutorials, ROADMAP,
  implementation plan, and research review for depth.
- **`docs/assets/*.svg`** -- five diagrams. `flywheel-tldr.svg` is an 18-second
  SMIL-animated walkthrough that narrates each stage in turn with its status;
  the other four are static (grounding layer, the files-vs-warehouse storage
  split, the human approval gate, progressive disclosure). Constraint worth
  remembering: GitHub strips inline `<svg>` from markdown, so these are
  standalone files referenced with `<img>`, and they use SMIL rather than
  `<style>` blocks so they animate when loaded as images. Each carries a dark
  self-contained background so it reads in both light and dark themes.
- README gains a "Start here" pointer; CLAUDE.md's repo map gains the doc and
  the assets directory with the SVG constraint noted.
- **`docs/tutorial-flywheel.md` sections 9-16** -- the governed path, which no
  tutorial covered before: `ingest transcripts` -> `couch run` -> `couch list`
  -> `proposal add --evidence` -> `proposal show` -> `proposal approve` ->
  `compile`. Includes the detector/threshold table, the anatomy of a compiled
  file with its provenance footer, rejection as a first-class outcome, and why
  the agent-invoked MCP tools cannot activate a rule. Steps 1-8 (hand-authoring
  a v2 skill from feedback) now hand off to it explicitly. Every command and
  expected-output block was executed against a scratch database before being
  written down.

### Changed

- **Retired "substrate" as a term.** It was covering three unrelated ideas,
  which is why it read as vague: the storage foundations (ROADMAP Phase 1,
  implementation-plan Track A), the question of which store a given kind of
  data belongs in (the research review's Part 2), and plain "raw material"
  (synthetic-corpus README). One word for three concepts hid a distinction
  that matters, so each sense got its own plain wording rather than a single
  replacement:
  - storage foundations -> "storage" ("Phase 1 — Storage Hardening",
    "Track A — Storage", "the storage track")
  - which store data belongs in -> "the storage split", or the two named
    directly; the research review's table column header is now "Where it
    lives", and research amendment 6 is "storage split made explicit"
    (kept in sync with the `mask_signature` docstring in `ingest.py`, which
    cites it by name)
  - raw material -> "source data"
  "Store" was rejected for the second sense: it collides with
  `ExperimentStore` and the "all access goes through the store layer" rule,
  which is the established meaning here. Released CHANGELOG entries keep the
  old wording — that history is not rewritten.
- `docs/assets/substrate.svg` renamed to `storage-split.svg`, matching its own
  title ("Two stores, two jobs").
- **README brought back in line with the code.** It had drifted badly: keys were
  still described as MD5 (sha256/32 since 0.23), the dimensional model was
  listed as 7 dims / 10 facts / 6 views (actually 9 / 11 / 10, counted from
  `ALL_TABLES` and `ALL_VIEWS`), the table inventory omitted `dim_tenant`,
  `dim_event_type`, `fact_event`, `meta_key_algorithm` and the four couch
  detector views, and the Project Structure block predated `db.py`, `store.py`,
  `ops.py`, `ingest.py`, `couch.py`, `materialize.py` and `mcp_server.py`
  existing. Also added the missing `uv sync --extra mcp` to optional
  dependencies -- it is required for `mcp-serve`, which `.mcp.json` depends on.
- ROADMAP Phase 1 drops the "load-bearing wall" metaphor for direct language.

### Dependencies

- `uv lock --upgrade` -- 14 packages moved, floors in `pyproject.toml`
  deliberately unchanged (this is a library; raising floors without a reason
  narrows what consumers can install). Notable: anthropic 0.94.1 -> 0.117.0,
  duckdb 1.5.2 -> 1.5.4, pydantic 2.13.0 -> 2.13.4, pytest 9.0.3 -> 9.1.1.
  Full suite green afterward.

### Fixed

- Tightened the self-modification claim in the new doc and its diagrams. It read
  "the write tools only ever create drafts", which is true of the agent-invoked
  MCP tools and false of the CLI, where `rule add` defaults to active. Now
  scoped to agent-callable tools, with the reason stated: a human runs the CLI.

### Known rough edge

`proposal add --evidence` stores finding keys verbatim -- nothing resolves
prefixes -- while `couch list` only prints 8-char prefixes. Pasting from one
into the other records a reference that matches no row, and the compiled
provenance footer truncates to 8 chars too, so a broken reference renders
identically to a good one. Workaround (query `fact_finding` for the full key) is
documented in the tutorial; fix options are in the internal backlog.

## 0.28.0

Realism and conflict layer for the synthetic corpus: messy real-world
formats, temporal/staleness data, and a machine-readable authority/conflict
evaluation set. No schema change (data + scripts + tests only).

### Added

- **Messy / real-world formats** (`data/synthetic/messy/`, `drive_chaos/`):
  human-exported spreadsheets (header-not-row-1, embedded subtotals, EU
  locale), an OCR-vs-clean invoice pair, JUnit and EDI-style XML, an ICS
  calendar export (cross-format join to the meeting notes), a SQL INSERT
  dump, a paginated JSON:API response set, a mixed syslog/CEF/key=value log,
  HTML intranet and newsletter pages, a raw-vs-clean ASR transcript pair, an
  mbox thread with top-posting/quote-trails, a slide-deck outline with
  speaker notes, and a shared-drive folder of near-duplicate versioned
  drafts plus a temp artifact. Several ship with clean ground truth so
  structuring is a scored task.
- **Temporal / staleness data** (`data/synthetic/time/`): KB page revision
  histories (`page_history.jsonl`, including the revision where the batch
  limit was correctly 500 before the 500->1000 change), org-chart and
  roadmap snapshot series at three dates, and a draft/approved/superseded
  policy chain (`policy_versions.jsonl`). Generated by a new deterministic
  `write_temporal()` phase (existing generated files stay byte-identical).
- **Authority / conflict eval set** (`data/synthetic/{governance,external,eval}/`):
  a system-of-record registry, a source-authority scoring model
  (`base_authority` + `half_life_days` per source type), a DACI decision log
  with one reversed decision, an IC strategy proposal, an external analyst
  note with planted factual errors, and `eval/conflicts.jsonl` -- the answer
  key mapping each of seven conflicts (stale-vs-current, draft-vs-approved,
  aspirational-vs-actual, cross-system metric, junior-vs-exec, the
  seniority-is-not-truth guardrail, identity metadata) to its correct value
  and resolution rule.
- `scripts/build_citation_graph.py`: derives `eval/citation_edges.csv` (every
  corpus ID mention as a `(from_path, to_id)` edge) from the whole corpus --
  the substrate for source-centrality/PageRank-style scoring. Standalone (not
  in `generate()`) so the determinism test's temp-dir regen stays reproducible.
- Tests: `test_synthetic_temporal.py`, `test_synthetic_conflicts.py`,
  `test_citation_graph.py` (determinism, staleness anchors, conflict schema +
  resolution-rule vocabulary, every conflict source path resolves, no phantom
  employee/account citations). 424 tests total.

### Fixed

- `.gitignore`: the `*.log` rule silently excluded the synthetic incident log
  (`unstructured/logs/api-gateway-2026-03-11.log`) from commits while the
  committed manifest referenced it -- a fresh checkout had a broken corpus
  (two failing tests). Added a scoped negation so corpus fixture logs are
  tracked; the runbook's illustrative `EMP-####` ticket example no longer
  uses a phantom employee id.

## 0.27.0

The public synthetic corpus: a committed, all-fictional dataset under
`data/synthetic/` for developing and evaluating the flywheel (and the
eventual human surfaces over post-agent-processed data) without touching
the private warehouse. No schema change.

### Added

- `data/synthetic/` -- 77 files, ~1.2 MiB, one coherent scenario (a
  fictional B2B usage-analytics SaaS, 2026-01-05 to 2026-06-30) spanning:
  issue-tracker and helpdesk SaaS exports (JSON/JSONL with comment and
  message threads), CRM CSVs, wiki-style knowledge-base pages (markdown +
  frontmatter), a relational OLTP extract (DDL + 4 CSVs incl. a 2,250-row
  usage fact), human feedback (CSAT CSV, NPS JSONL, and
  `annotation_corrections.jsonl` typed to the `CorrectionType` taxonomy),
  unstructured streams (team chat JSONL, a gateway log, `.eml` emails,
  call transcripts), and two generic JSONL event streams shaped for
  `freud-schema ingest events`. A cross-source incident narrative
  (INC-2026-0311) threads through logs, chat, issues, tickets, invoices,
  usage, events, a postmortem, and NPS -- ground truth for multi-source
  reasoning evals. Planted extraction traps (deprecated limits table,
  split retention tiers) pair with the corrections file. `MANIFEST.json`
  is the machine-readable inventory. The hand-authored layer also covers
  ten knowledge-base pages, H1-2026 release notes keyed to real tracker
  issues, an engineering design doc, an order-form/MSA template (whose
  section 6.3 the invoice-dispute thread invokes), a customer-contraction
  arc matching the closed subscription rows, a sales-pipeline arc, an
  OpenAPI 3.1 spec, and a status-page incident-history export.
- `data/synthetic/internal/` -- the fictional company's own enterprise
  systems: HRIS (124 employees + PTO + monthly headcount), ITSM
  (tickets/assets/change records, incl. the failed change behind the
  incident), finance (vendors/POs/expenses/monthly GL/AR aging), IAM
  (app catalog + Q2 access review), security (phishing sims), executive
  KPI scorecard, and corporate docs (SOC 2 memo, policies, runbook,
  all-hands, onboarding). GL reconciles to invoices and expenses; a
  compliance arc threads termination -> offboarding gap -> access-review
  revocation -> runbook fix -> SOC 2 finding. Badge-access and
  security-alert JSONL streams join the ingest-ready `events/` set.
- Cross-granularity "join challenge" datasets with exact ground truth
  (weekly ticket metrics, monthly headcount, quarterly KPIs, domain-keyed
  web analytics requiring key derivation, and a messy-name AR aging
  snapshot requiring entity resolution), documented in the corpus README
  and guarded by `tests/test_synthetic_granularity.py` and
  `tests/test_synthetic_internal.py` (402 tests total).
- `.gitignore`: anchored the `internal/` ignore to the repo root --
  the unanchored pattern was silently ignoring
  `data/synthetic/internal/`.
- `scripts/generate_synthetic_data.py` -- deterministic generator for the
  structured/volume files (fixed seed, fixed dates, no wall-clock reads;
  byte-identical re-runs). Hand-authored documents are left untouched and
  re-inventoried into the manifest.
- `tests/test_synthetic_data.py` -- corpus guards: generator determinism,
  manifest/disk parity, cross-source reference integrity, incident
  anchors, and end-to-end idempotent ingest of the event streams through
  `ingest_events`.
- `.gitignore` note marking `data/synthetic/` as the public exception to
  the private-data defaults.

## 0.26.0

M5 of the enterprise-scale implementation plan: the generic event grain and
ingest-adapter protocol, so agent transcripts become one source among many --
plus the fresh-ingest speed optimization from the risk register, landed
alongside since M5's schema reset is the natural trigger point (BACKLOG
"fresh-ingest insert speed"). **Schema v7 -- reset required.**

### Added

- `tables.py`: `RecordSource.EVENT_INGEST`; new registry model `EventType`
  (mirrors `FindingType` -- open vocabulary, `schema_hint JSON`); new fact
  model `Event` (the generalization of `Message`/`ToolUse` for non-transcript
  sources -- `stream_key`, `native_event_id`, `event_type`, `occurred_at`,
  `actor`, `payload`, `content_text`, `signature`, `sequence_num`, lineage
  envelope).
- `db.py`: `dim_event_type` (registry, append-only, mirrors
  `dim_finding_type`) and `fact_event` (indexed on `(stream_key,
  occurred_at)` and `(event_type)`); both registered in `ALL_TABLES`
  (dependents-first drop order). `_SCHEMA_VERSIONS` bumped to 7.
- `store.py`: `register_event_type`/`get_event_type`/`list_event_types`
  (mirror the finding-type registry methods); `stream_key_for(record_source,
  native_stream_id)` (named recipe, generalizes `session_key_for`);
  `event_key_for(stream_key, native_event_id)`; `insert_events(events) ->
  int` (batched existence check, single-stream guard, registry-validates
  `event_type` before writing -- fails closed on an unregistered type, same
  pattern as `insert_finding`) and a thin `insert_event` delegating to it;
  `get_event`/`list_events` read helpers.
- `ingest.py`: `IngestAdapter` protocol (`@runtime_checkable`) --
  `discover(root, since) -> list[SourceUnit]`, `parse(unit) ->
  Iterator[RawEvent]`, plus an optional `normalize(text) -> str` hook
  (amendment 6). `TranscriptAdapter` conforms to the protocol's shape
  (reuses `discover_sessions`/`iter_typed_entries`) but is not wired into
  `ingest_transcripts()`, which is unchanged. `JsonlEventAdapter` is the
  second reference adapter: one stream per `*.jsonl` file under a root
  (`native_stream_id` = the file's path relative to root), one JSON object
  per line (`{id, type, timestamp, actor, payload}` + optional `text`);
  `normalize()` delegates to the new `mask_signature()`. `mask_signature(text)`
  -- Drain-style-lite template signature: regex-masks UUIDs, quoted strings,
  hex strings >= 8 chars, and bare numbers to stable placeholders (documented
  as a cheap normalization step, not real template mining). New
  `ingest_events(store, *, root, stream_type=None, since=None) -> dict`,
  wrapped in `load_run("ingest_events")`: auto-registers each distinct event
  type in `dim_event_type`, writes rows idempotently (unchanged file = zero
  rows, grown file = delta only).
- `ops.py`: `ingest_events` (same dispatch-layer pattern as
  `ingest_transcripts`).
- `mcp_server.py`: `ingest_events` tool, mirroring `ingest_transcripts`.
- `cli.py`: `ingest events --root DIR [--stream-type T] [--since ISO]`.
- tests: `tests/test_events.py` (store-layer -- registry validation,
  single-stream guard, `stream_key_for`/`event_key_for` recipes, and
  row-content equivalence for the JSON-spill bulk insert covering None/NULL,
  timestamps, JSON columns, unicode, and embedded newlines/quotes in text,
  for `fact_event`/`fact_message`/`fact_tool_use`); `tests/test_ingest_events.py`
  (ingest-layer -- adapter protocol conformance, `mask_signature` masking and
  stability, `JsonlEventAdapter`/`TranscriptAdapter` discover/parse round
  trips, `ingest_events()` idempotency and grown-file delta, couch-detector
  non-interference); MCP/ops round-trip tests for `ingest_events` in
  `tests/test_mcp_server.py`; CLI smoke test in `tests/test_experiment.py`.

### Changed (fresh-ingest speed, BACKLOG "fresh-ingest insert speed" -- DONE)

- `store.py`: `insert_messages`, `insert_tool_uses`, and the new
  `insert_events` now load their post-dedupe miss rows through a new private
  `_bulk_insert_json()` instead of `con.executemany()` -- rows spill to a
  temp newline-delimited JSON file (orjson, `tempfile.TemporaryDirectory`,
  always cleaned up) and load with one `INSERT INTO <table> (cols...) SELECT
  cols... FROM read_json(?, format='newline_delimited', columns={...})` per
  batch, with an explicit per-column type spec. orjson serializes nested
  dict/list payloads as native JSON (not double-encoded strings) and
  datetimes as ISO 8601, both of which `read_json`'s `columns=` type-casts
  correctly. The batched existence-check dedupe, single-session/stream
  guards, and `meta_load_log` counting semantics are unchanged -- only the
  final write mechanism changed. Measured on a synthetic 50k-row
  `fact_message`-shaped fixture: ~54.5s for `executemany` vs. ~0.09s for the
  spill+`read_json` path -- **~600x**, exceeding the BACKLOG's ~300x
  estimate.

### Deviations from spec

- `fact_event` does not carry a denormalized `event_type_key` column the way
  `fact_finding` carries `finding_type_key` -- the task spec's own column
  list for `fact_event` omitted it, and open-vocabulary registry validation
  (the actual point) works identically without the denormalized reference.
- Row-content equivalence between the new spill+`read_json` path and the old
  `executemany` path is asserted against literal expected values
  (`tests/test_events.py`) rather than by keeping both code paths live in
  production -- the task spec offered this as an explicit alternative
  ("keep the old path available... or by asserting against expected
  literals -- your choice").

## 0.25.0

M16 of the enterprise-scale implementation plan: the store-ops MCP server --
the harness's write surface during sessions, and the durable fix for the
CLI write-window dance and the `/couch` skill's raw-INSERT exception.

**Gate hardening (post-implementation review)**: DuckDB types read-only
PRAGMAs, SHOW, and DESCRIBE as `StatementType.SELECT` by rewriting them to
pragma table functions, so parser-type classification alone let
`PRAGMA database_list` through `query()`'s read-only gate. A first-token
allowlist (SELECT/WITH/FROM/SHOW/DESCRIBE/SUMMARIZE) closes the hole;
regression tests cover PRAGMA (bare and comment-prefixed), CALL, SET, and
the allowed introspection forms.

### Added

- `ops.py`: the shared write-op dispatch layer -- pure functions taking
  `(store, typed params)` and returning plain dicts, one per write
  operation (`rule_add`, `skill_add`, `source_add`, `feedback_add`,
  `finding_add`, `proposal_add`, `proposal_approve`, `proposal_reject`,
  `extraction_validate`, `extraction_reject`, `compile_rules`, `couch_run`,
  `ingest_transcripts`). `cli.py` and `mcp_server.py` both call these
  instead of `ExperimentStore` directly, so the two surfaces cannot drift.
  `finding_add` wraps `store.insert_finding` in its own `couch_llm`
  load_run, retiring the `/couch` skill's raw-INSERT exception -- LLM
  judgment now writes through the one write path like every SQL detector.
- `mcp_server.py`: the store-ops MCP server, behind the new `mcp` extra.
  `classify_readonly(sql)` enforces `query()`'s read-only contract at the
  parser level via `duckdb.extract_statements()` -- exactly one statement,
  SELECT-typed only, rejecting INSERT/UPDATE/DELETE/DDL/ATTACH/COPY/
  PRAGMA/EXPORT and multi-statement smuggling before anything reaches the
  connection. `build_server(store, db_path)` registers `query` plus one
  tool per `ops.py` write function; `serve(db_path)` opens the single
  DuckDB connection for the session and runs the server over stdio.
  Self-modification gate (non-negotiable, from the M16 risk analysis):
  `rule_add`/`skill_add` always create the non-compiling status (rules:
  `inactive`; skills: `draft`) regardless of what a caller requests, so a
  session cannot make a rule or skill load into its own future context by
  calling these tools directly -- the only path to activation is
  `proposal_add` -> `proposal_approve`. `proposal_approve`'s tool
  description opens with an explicit "never allowlist this tool" sentence
  and requires `reviewed_by` with no default. No tool exposes `db reset`,
  `db ddl`, or any raw-write escape hatch.
- `cli.py`: new `mcp-serve` subcommand (uses the global `--db` flag),
  guarded import with an `uv sync --extra mcp` install hint when the extra
  is missing.
- `.mcp.json`: project MCP config pointing at `freud-schema mcp-serve`, so
  the repo self-describes its connection holder.
- `pyproject.toml`: new `mcp` extra (`mcp>=1.2`); also added to `dev` so
  the gate tests run without an extra install step.
- tests/test_mcp_server.py: `ops.py` round trips against `:memory:` for
  every write op; `classify_readonly` acceptance (SELECT, WITH...SELECT)
  and one rejection test per bypass class (INSERT, UPDATE, DELETE, CREATE
  TABLE, DROP, ATTACH, COPY, PRAGMA, EXPORT DATABASE, multi-statement);
  gate tests proving `rule_add`/`skill_add` force the non-compiling status
  even when `active` is requested, a gated rule does not compile, and a
  full flywheel turn (rule stays inactive -> proposal -> approve ->
  compile) passes through tool wrappers alone; server-construction tests
  behind `pytest.importorskip("mcp")` covering the registered tool
  inventory, `proposal_approve`'s gate-sentence description, and the
  absence of any reset/ddl-named tool.

### Changed

- `cli.py`: the write handlers (`rule add`, `skill add`, `source add`,
  `feedback add`, `proposal add/approve/reject`, `extraction
  validate/reject`, `compile`, `couch run`, `ingest`) are now thin --
  parse args, call the matching `ops.py` function, print. No behavior
  change; the CLI is the second consumer of the same dispatch layer the
  MCP server uses, not a separate implementation.
- CLAUDE.md's "DuckDB MCP" section rewritten for the new reality: the
  store-ops server is the preferred connection holder, with the gate
  design and the generic-server migration note; the old CLI-write-window
  rules are kept as the fallback path for sessions still on a generic
  `duckdb` MCP server.
- `.claude/skills/couch.md`: step 4 now records findings via the
  `finding_add` MCP tool; the old raw-INSERT SQL recipe moved to a
  fallback appendix for sessions without the store-ops server.
- `skill/skill.md`: CLI reference gains `mcp-serve`; the "if an MCP server
  is available" callout now recommends the store-ops server first.

### Deviations from spec

- `query()`'s read-only gate does not special-case `EXPLAIN`. The plan
  allowed it "if duckdb types it separately and it wraps a SELECT"; in
  practice `duckdb.extract_statements()` types `EXPLAIN <anything>` as
  `StatementType.EXPLAIN` with no exposed handle on the wrapped
  statement, and `EXPLAIN ANALYZE <write>` actually executes the wrapped
  statement. `classify_readonly()` takes the plan's own fallback instead:
  SELECT only, unconditionally -- `EXPLAIN` is rejected like every other
  non-SELECT type. See docs/implementation-plan.md's M16 as-shipped note.

## 0.24.0

M0 of the enterprise-scale implementation plan: the cold-start playbook and
the first maintenance detector. The flywheel now has a documented first turn
and a standing signal for when seed knowledge decays.

### Added

- couch.py: `stale_source` detector -- recomputes each active source's
  content hash and compares it to the baseline recorded at registration;
  emits one GLOBAL-scope finding per changed source, basename only in the
  summary (privacy rules apply). Registered with `detection_method = hybrid`:
  it reads the warehouse AND the filesystem, so the finding is not
  reproducible from the warehouse alone. Sources without a baseline hash and
  missing files are skipped.
- couch.py: `source_content_hash()` -- sha256 hexdigest of a source file's
  bytes (full digest; a content fingerprint, not a key), shared by the CLI
  baseline and the detector's recomputation.
- couch.py: `run_couch(include_filesystem=True)` -- False skips filesystem
  detectors for warehouse-only runs (CI, machines without the corpus).
- cli.py: `source add --hash` records the staleness baseline;
  `couch run --warehouse-only` skips filesystem detectors.
- docs/tutorial-cold-start.md: the day-one playbook -- seed corpus with
  staleness baselines, thin human-authored skills, validate-everything
  cold-start gating, typed corrections, first flywheel turn, and the first
  staleness finding. Linked from README.
- tests: TestStaleSource in test_couch.py (mutated/unchanged/no-baseline/
  missing-file/warehouse-only paths, hybrid registration, and a
  basename-only privacy assertion).

### Changed

- `_insert` in couch.py takes a scope parameter (default PROJECT) so
  non-project findings (stale_source is GLOBAL) share the one write path.


## 0.23.0

M2+M3 of the enterprise-scale implementation plan: key algorithm versioning
and tenancy in natural keys, landed as a single reset (per the M1 no-migrations
policy -- SHA-256 keys with the tenant component already in the natural key,
so the warehouse resets once, not twice).

### Added

- keys.py: `KEY_ALGORITHM = "sha256/32"` constant; `dimension_key()` and
  `hash_diff()` now hash with SHA-256, truncated to the first 32 hex chars
  (same length as the MD5 hex scheme they replace -- no column width or
  prefix-resolution changes).
- db.py: `meta_key_algorithm` (single-row, seeded with `KEY_ALGORITHM` at
  `init_schema()`) so a database self-describes its key scheme.
- db.py/tables.py/store.py: `dim_tenant` registry (append-only, mirrors
  `dim_project`), seeded with a `default` tenant at `init_schema()`.
  `ExperimentStore.ensure_tenant()`/`get_tenant()`/`list_tenants()` and the
  `tenant_key_for()` recipe.
- tables.py: `tenant_id: str = "default"` on `Skill`, `Rule`, `Source`,
  `SamplingConfig`; `tenant_key: str | None = None` denormalized onto every
  fact model.
- cli.py: global `--tenant` flag (default `"default"`), threaded into
  `skill add`, `rule add`, `source add`, `sampling-config add`, the
  `dim_skill` prefix-resolving handlers, and `compile`.
- `_SCHEMA_VERSIONS`: version 6, "sha256/32 keys, dim_tenant registry,
  tenant-scoped natural keys, meta_key_algorithm".
- Tests: `tests/test_tenancy.py` (two-tenant collision, default-tenant
  back-compat, `resolve_key` tenant scoping, `init_schema` seeds); golden
  sha256/32 key values and the `KEY_ALGORITHM` constant added to
  `tests/test_keys.py`.

### Changed

- The four SCD-2 dims' natural keys now lead with `tenant_id`: skill =
  `(tenant_id, domain, task_type)`, rule = `(tenant_id, name)`, source =
  `(tenant_id, content_path)`, sampling config = `(tenant_id, domain,
  task_type)`. Two tenants can hold the "same" entity without collision.
- store.py: `get_active_skill()`, `get_rules()`, `get_sampling_config()`,
  and `resolve_key()` (for the four tenant-keyed dims only) gained a
  `tenant_id` parameter, defaulting to `"default"` -- omitting it preserves
  pre-0.23 behavior exactly. `_resolve_skill_attrs()` additionally resolves
  the skill's `tenant_key`; the five skill-denormalizing fact inserts
  (session, trace, extraction, feedback, trace_feedback) set the fact's
  `tenant_key` from it when a skill is linked, else from the model's own
  `tenant_key` or the default tenant. `insert_derived_skill()` inherits the
  parent skill's `tenant_id`. `approve_proposal()` reads an optional
  `tenant_id` out of `target_natural_key`, defaulting to `"default"`.
- materialize.py: `compile_rules()` gained a `tenant_id` parameter
  (default `"default"`); compiles one tenant's rules per run.
- Docs (CLAUDE.md, skill/skill.md, skill/reference/schema.md,
  skill/reference/context-assembly.md, a2ui/prompt_addendum.md): MD5 ->
  sha256/32 throughout; schema.md/a2ui docs gained `dim_tenant` (and
  schema.md gained `meta_key_algorithm`) plus `tenant_id`/`tenant_key`
  column documentation.

### Notes

- No data migration, per the M1 policy: existing databases reset
  (`reset_schema()`) and re-ingest; deterministic keys make re-ingest
  idempotent, native test rows (skills, rules, feedback, proposals) are
  disposable and recreated as needed.
- `hash_diff()`/natural-key content fingerprints do not include `tenant_id`
  -- it is identity, not content, consistent with `domain`/`task_type`/
  `name`/`content_path` already being excluded from `hash_diff()`.

## 0.22.0

M1 of the enterprise-scale implementation plan: reset-based schema
lifecycle, codified. Plus the planning-doc arc that produced it.

### Added

- `ROADMAP.md`: enterprise-scale roadmap generalized from a structural
  critique -- seven invariants worth preserving, seven phases of substrate
  work, explicitly scoped to a production descendant, not this repo.
- `docs/implementation-plan.md`: 15-milestone build plan (M0-M14) across
  six tracks, with dated research-review amendments and a risk register.
- `docs/research-agent-data-representation.md`: research pass over the 2026
  harness-engineering literature (ACE, MCE, Meta-Harness, Self-Harness,
  ScientistOne, Weng's harness post) and production practice, validating
  the files-as-truth + warehouse-as-catalog architecture; per-data-type
  representation guidance (code, diagrams, structured data, documents,
  logs); six adopted amendments.
- CLAUDE.md: **grounding layer** definition (constraints on one end,
  grounding data in the middle, verifiers and feedback on the other;
  warehouse = governed truth, compiled files = agent-facing form).
- CLAUDE.md: the no-migrations convention is now an explicit standing
  policy (owner decision, 2026-07-08) -- all warehouse data is disposable
  test/research data; never build migration machinery -- plus the standard
  schema-change recipe (edit DDL -> reset -> re-ingest -> recreate native
  test rows).
- `skill/reference/schema.md`: schema-change recipe note in Notes.

### Changed

- db.py: `_SCHEMA_VERSIONS` documented as a plain DDL changelog, NOT a
  migration ledger; module docstring cites the policy. No behavior change.

Quality pass over the Phase 0-3 code: a 4-angle cleanup review plus an 8-angle
correctness review, findings applied.

### Changed

- **Views use CREATE OR REPLACE** (was CREATE VIEW IF NOT EXISTS): view
  definition changes now reach existing databases instead of being silently
  pinned to the old definition forever.
- **One write path per fact table**: `insert_message`/`insert_tool_use` are
  thin delegators to the batch methods, so the column lists cannot drift
  (same principle as `_write_skill_row`, which both skill write paths now
  share). Batch inserts do one existing-key fetch per session and insert only
  the misses -- unchanged re-ingest drops from ~2min to ~5s. Batches raise on
  mixed-session input (the dedupe is per-session by design).
- `v_retry_loops` carries no threshold in the DDL; couch detectors own
  thresholds, parameterized through new store view-query methods
  (`query_retry_loops` etc. -- couch/materialize no longer touch private
  store helpers).
- `resolve_key(table, prefix)` drops the derivable `key_col` argument and
  escapes LIKE wildcards in prefixes; CLI resolution calls simplified
  accordingly.
- `load_run()` context manager owns the meta_load_log lifecycle for all
  operations and yields typed `LoadRunStats` (counter typos raise instead of
  silently logging zeros); failure rows now record counters accumulated
  before the error (per-file transactions make earlier writes durable).
- Canonical `ALL_TABLES`/`ALL_VIEWS` inventories in db.py drive
  `reset_schema()` and `db status`; an inventory test keeps both honest.
- SCD-2 insert guard shared across source/rule/sampling-config inserts;
  named key recipes (`session_key_for`, `message_key_for`) replace formula
  re-derivation in ingest.
- Test fixtures deduplicated to conftest; stale duplicate schema tests
  removed.

## 0.20.0

Phase 3 of the meta-harness plan: evolve + materialize. The loop is closed --
the first rule mined from real session history is compiled into this repo's
`.claude/rules/` with its full evidence chain.

### Added

- **Proposal lifecycle**: `approve_proposal` applies a pending proposal to its
  target dimension (rule evolve/create, skill version bump with data_derived
  origin, sampling config) as an SCD-2 evolution, recording
  resulting_dimension_key, reviewer, and timestamp. `reject_proposal` records
  the decision and changes nothing downstream. Pending-only guards on both.
  Approval is the one human atom -- nothing calls it automatically.
- **`rollback_dimension`**: close the current SCD-2 row, reopen the prior one.
  Symmetric with evolution, no destructive undo; recompile to propagate.
- **The compiler** (`materialize.py`): `compile --out DIR [--scope]` renders
  current active rules to `<name>.md` with a do-not-edit header, a source line
  (dimension key + effective_from), and a provenance footer naming the
  approving proposal and its evidence findings. Managed-file hygiene: files for
  deactivated rules are removed, but only files carrying the compiled marker --
  hand-written neighbors are never touched. Deterministic output.
- **Fail-closed privacy gate**: rendered files containing home-directory paths
  or the OS username are not written; the last good compile of a blocked rule
  survives; CLI exits nonzero on any block.
- CLI: `proposal add|list|show|approve|reject`, `compile`.
- `.claude/rules/no-identical-retries.md`: the first compiled rule, evidence:
  16 retry-loop findings mined from real transcripts across the project corpus.
- Tests: `test_evolve.py`, `test_materialize.py` (including planted-leak gate
  tests and rollback-then-recompile round-trip).

## 0.19.0

Phase 2 of the meta-harness plan: the couch. Analysis passes over the
warehouse produce typed, evidence-linked findings.

### Added

- **SQL finding detectors** (`couch.py` + 4 views: `v_retry_loops`,
  `v_tool_error_clusters`, `v_interruption_hotspots`, `v_permission_friction`).
  `freud-schema couch run` seeds the finding-type registry (4 SQL-detected +
  2 LLM-detected vocabularies) and records `fact_finding` rows with
  evidence session keys and occurrence counts. No model calls. Findings are
  append-only trend data keyed per run. Summaries are built from tool names,
  counts, and rates only -- never tool inputs, message text, paths, or URLs
  (scrubbed by construction, since findings feed the future compile step).
- `freud-schema couch list [--type]` to review findings.
- `/couch` skill (`.claude/skills/couch.md`): the LLM layer -- the harness
  judges user-correction patterns in scoped subagents and records findings
  via MCP, with non-negotiable privacy rules (describe the pattern, never
  quote the transcript).
- `project_key` conformed onto `fact_message` and `fact_tool_use` at ingest
  (dimensional fix: per-project finding views would otherwise need a
  fact-to-fact join through fact_session). Schema version 5.
- Tests: `test_couch.py` -- one fixture per finding pattern, each with a
  below-threshold neighbor asserting no false positives, plus a
  no-content-in-summaries privacy test.

## 0.18.0

Phase 1 of the meta-harness plan: sense. Claude Code's own session transcripts
become warehouse facts.

### Added

- **Transcript ingestion**: `freud-schema ingest transcripts [--root] [--project]
  [--since]`. One fact_session per transcript (root sessions as orchestrator,
  nested subagents linked via parent_session_key with agentType/description from
  their .meta.json sidecars), one fact_message per user/assistant entry, one
  fact_tool_use per tool_use block joined to its tool_result, dim_project from
  the session's cwd. Idempotent by key construction: re-running against
  unchanged files writes zero rows; a resumed session's grown file inserts only
  its new entries. All runs logged in meta_load_log.
- `discovery.py`: transcript discovery for the current nested layout
  (`<project>/<parent-uuid>/subagents/agent-<id>.jsonl` + sidecars), built fresh
  and verified against on-disk data.
- **Vendored ccutils parsers** (`vendor/ccutils_parsers/`): the typed transcript
  parser (12 discriminated entry types, Unknown* fallbacks, extra="allow") and
  the history.jsonl parser, with upstream commit provenance headers.
- Store: `transaction()` context manager (one transcript file per transaction),
  `count_rows()`, `update_session_progress()` (accumulating-snapshot updates
  with transcript-derived timestamps, not wall clock).
- Tests: `test_ingest.py` -- includes Phase 1's falsifiable milestone (idempotent
  re-ingest measured via meta_load_log counts) and incremental growth coverage.

## 0.17.0

Phase 0 of the meta-harness plan (see internal plan doc): the schema realigned
to the star-schema reference pattern so transcript ingestion (Phase 1) can be
idempotent by construction.

### Changed

- **MD5 hash surrogate keys everywhere** (`keys.dimension_key`), replacing all
  9 sequences and integer ids. Entity keys are deterministic from natural keys:
  skills = (domain, task_type), sources = content_path, rules = name, sampling
  configs = (domain, task_type). Every model field renamed `id` -> `<table>_key`;
  all cross-references renamed (`skill_id` -> `skill_key`, `session_id` ->
  `session_key`, etc.). `session_id` no longer exists anywhere in the DDL:
  `etl_run_id` is the lineage identifier, `session_key` the harness session.
- **SCD Type 2 on all four core dimensions** (`effective_from`/`effective_to`/
  `is_current`/`hash_diff`): attribute changes close the current row and insert
  a new one; rows never mutate; `updated_at` dropped. `insert_source`/`insert_rule`
  are idempotent on identical re-adds and evolve on change. Skill status changes
  (activate/deprecate) are SCD-2 evolutions. Skill versions are monotonic per
  entity.
- **Rules are keyed by a new required `name`** (also the future compile target
  filename `.claude/rules/<name>.md`).
- **fact_session unified across origins**: one row per harness session, native
  experiment run or ingested transcript, distinguished by `record_source`
  (CHECK-constrained allowlist). `task_description`/`task_type` now nullable;
  new `native_session_id`, `project_key` columns. Documented as an accumulating
  snapshot fact (status/result update in place; all other facts append-only).
- CLI id arguments become keys with git-style unique-prefix resolution
  (`store.resolve_key`); `rule add` requires `--name`.
- Schema version 3 -> 4. Breaking change via `reset_schema()`, no migration.

### Added

- `keys.py`: `dimension_key()` / `hash_diff()` -- deterministic, NULL-safe key
  generation; the primitive Phase 1's idempotent re-ingest guarantee builds on.
- **8 new tables**: `dim_project` (conformed project dimension), `dim_facet_type`
  + `fact_session_facets` (facet registry, EAV), `dim_finding_type` (open
  finding vocabulary -- registry-validated in the store, deliberately no CHECK
  enum), `fact_message` + `fact_tool_use` (transcript grain, deterministic keys,
  skip-if-exists inserts), `fact_finding` (couch outputs, evidence-linked),
  `fact_proposal` (evolve outputs, pending/approved/rejected lifecycle), plus
  `meta_load_log` (one row per ingest/compile run).
- Lineage envelope on every fact: `record_source` + `etl_run_id`; load-run
  lifecycle methods (`start_load_run`/`complete_load_run`).
- New enums: `RecordSource`, `ProposalStatus`, `TargetDimension`, `FindingScope`,
  `FacetMethod`, `FacetOutputType`, `DetectionMethod`, `MessageRole`.
- New store methods: project/facet-type/finding-type registries, message/tool-use
  inserts, findings, proposals, `resolve_key` prefix resolution.
- Tests: `test_keys.py`, `test_schema_v017.py`, `test_store_v017.py`.
- `[tool.pytest.ini_options]` anchoring rootdir (test collection previously
  escaped the repo and broke against an unrelated parent directory).

## 0.16.1

### Fixed

- **README.md**: Experiment Harness section updated from stale 7-table description to
  dimensional model (4 dim + 5 fact tables, 6 views). Project Structure updated with
  current file descriptions, added missing directories (scripts/, a2ui/, internal/).
- **skill/reference/schema.md**: Column-level fixes -- dim_sampling_config domain/task_type
  now nullable with parameters/status columns, dim_skill adds parent_skill_id/activation_conditions,
  dim_source adds superseded_by, fact_trace adds parent_trace_id/content (reordered for
  tree-structure clarity), fact_extraction adds validated_at, fact_trace_feedback renames
  notes->content and adds correction/skill_task_type, fact_feedback adds skill_version/source_path.
  Enum Values table now includes dim_sampling_config.status.
- **a2ui/prompt_addendum.md**: Removed stale FK language, added denormalized fields to
  Extraction and Session entities, added Trace and TraceFeedback data shapes.

## 0.16.0

### Changed

- **Dimensional model redesign** (Kimball-style): all tables renamed to `dim_*` (reference
  data) and `fact_*` (event data). Fact tables carry denormalized dimension attributes
  at insert time, eliminating all fact-to-fact joins.
- **6 analytical views** replace complex Python aggregation: `v_feedback_by_skill`,
  `v_feedback_fields`, `v_recurring_traces`, `v_recurring_trace_feedback`,
  `v_skill_feedback_patterns`, `v_session_feedback_count`. N+1 query patterns eliminated.
- `aggregate_feedback`, `get_recurring_traces`, `get_recurring_trace_feedback`,
  `get_skills_with_feedback_patterns` rewritten as view-backed single queries
- `sample_prior_sessions` HIGH_FEEDBACK strategy uses `v_session_feedback_count` view
  instead of correlated subquery
- Schema version 2 -> 3 (dimensional model)

### Added

- Insert-time denormalization: `insert_session` populates `skill_domain/skill_task_type/skill_version`,
  `insert_trace` populates skill attrs from session, `insert_extraction` populates source
  and skill attrs, `insert_feedback` populates skill and source attrs,
  `insert_trace_feedback` populates trace and skill attrs
- Session skill attribute caching in store for bulk trace inserts
- **Store-level existence validation** (`_require` helper): all fact insert methods validate
  required references exist before insert (replaces FK enforcement). Raises `ValueError`
  with clear message for orphaned references.
- **Prior run trace filtering**: `_format_prior_runs` now only includes signal-bearing traces
  (decision_point, dead_end, insight, conclusion, subagent_spawn). Skips tool_call,
  path_taken, path_discarded to avoid blowing up context with mechanical detail.
  Shows summary count ("3 of 50" format).

### Removed

- **FreudAgent MCP server** (`mcp_server.py`, `freud-mcp` entry point, `fastmcp` dependency):
  70% of tools were 1:1 SQL mappings the duckdb MCP already handles; views solve the rest.
  Access data via duckdb MCP + views (Claude Code) or CLI (terminal).
- All 15 FK REFERENCES clauses (DuckDB can't enforce CASCADE anyway; existence
  validation done in store layer)
- PRIMARY KEY on dimension and fact tables (sequences still guarantee unique IDs)

## 0.15.0

### Added

- **Run traces** (`traces` table): hierarchical reasoning trace nodes attached to
  sessions. 8 trace types: decision_point, path_taken, path_discarded, insight,
  dead_end, subagent_spawn, tool_call, conclusion. Tree structure via parent_trace_id.
- **Trace feedback** (`trace_feedback` table): human feedback on specific trace nodes.
  4 feedback types: path_correction, positive_signal, dead_end_confirmation, reasoning_error.
- **Sampling configs** (`sampling_configs` table): per-domain/task-type prior run
  sampling configuration. 5 strategies: recent, random, stratified_outcome,
  stratified_feedback, high_feedback.
- **Prior run injection**: `assemble_runner_context()` accepts `prior_runs` and
  `include_feedback_summary` parameters. Prior runs formatted as interpretable
  system prompt blocks with traces, feedback, and outcomes.
- **Skill evolution**: `origin` field (human_authored/data_derived) and
  `activation_conditions` JSON on skills. `insert_derived_skill()` tracks provenance.
  Pattern detection: `get_skills_with_feedback_patterns()`, `get_recurring_traces()`,
  `get_recurring_trace_feedback()`.
- **FreudAgent MCP server** (`freud-mcp`): typed MCP tools wrapping ExperimentStore.
  30+ tools for sessions, traces, extractions, feedback, sampling, pattern detection,
  and raw SQL escape hatch. Replaces generic DuckDB MCP server.
- **PostToolUse hook** (`scripts/trace-hook.sh`): automatic tool_call trace capture
  to JSONL buffer. `bulk_import_traces` MCP tool loads buffer into DB at session end.
- **Trace capture reference** (`skill/reference/trace-capture.md`): instructions for
  Claude on self-reporting reasoning traces during extraction runs.
- **Schema hardening**: UNIQUE constraint on skills `(domain, task_type, version)`,
  16 indexes across all tables, enhanced `aggregate_feedback` with field-level detail
  and optional examples.
- **Temporal queries**: `list_sessions` and `list_extractions` accept `created_after`
  and `created_before` date range filters. `list_sessions` adds `skill_id` filter.
- **Rich retrieval**: `get_extraction_with_feedback()`, `get_session_with_context()`,
  `get_sessions_with_context()` for joined data access.
- **Store methods**: `sample_prior_sessions()` (5 strategies), `get_active_sub_skills()`,
  `insert_derived_skill()`, `delete_session_traces()`, 10 trace/trace-feedback CRUD methods.
- **CLI commands**: `trace list|show|patterns`, `trace-feedback add|list`,
  `sampling-config add|list`, `skill patterns`. `skill list` shows origin column.
  `db status` shows all 10 tables.
- 45 new tests covering all new tables, constraints, store methods, context assembly,
  and CLI commands.

### Changed

- Schema version 1 -> 2 (10 tables, up from 7)
- `aggregate_feedback` returns `list[dict]` with correction_type, count, fields, examples
  (was `list[tuple[str, int]]`)
- `Session` model adds `sampled_session_ids: list[int] | None`
- `Skill` model adds `origin: SkillOrigin` and `activation_conditions: dict | None`
- `list_skills` accepts `origin` and `parent_skill_id` filters
- `_json()` helper widened to accept `dict | list | None`
- pyproject.toml: version 0.15.0, `freud-mcp` script entry point, `mcp` optional extra

## 0.14.0

### Removed

- **`freud-schema run` CLI command** -- orchestration belongs to the harness, not
  the data layer. Use Claude Code (MCP tools + Agent tool) or Agent SDK for extraction.
- `run_single()` from orchestrator module
- `_handle_run` CLI handler and `run` subparser
- 8 tests for removed orchestration code; 1 test rewritten to insert session directly

## 0.13.2

### Fixed

- **DuckDB lock detection**: `connect()` catches `IOException` on locked database files
  and raises a clear message directing users to MCP tools instead of raw traceback
- **Connection lifecycle**: `ExperimentStore` now supports context manager protocol
  (`with ExperimentStore(...) as store:`). All 8 CLI handlers use `with` blocks --
  previously leaked connections.

### Changed

- **DuckDB MCP routing docs**: CLAUDE.md, db-query skill, skill.md, and arxiv tutorial
  now explicitly state that CLI cannot access the DB while MCP server is active.
  MCP tools are the primary interface during Claude Code sessions.

## 0.13.1

### Added

- **CLI: `skill deprecate <id>` and `skill activate <id>`** -- expose existing store
  methods for skill lifecycle management
- **CLI: `session show <id>`** -- display full session details including context loaded,
  token usage, and result JSON
- **CLI: `--version` flag on `skill add`** -- specify skill version (default: 1) for
  flywheel v1/v2 comparisons
- **Retrieval thesis** (`skill/reference/retrieval-thesis.md`): architecture note
  connecting FreudAgent's L1/L2/L3 hierarchy to the progressive disclosure thesis
- **Flywheel tutorial** (`docs/tutorial-flywheel.md`): end-to-end walkthrough of the
  feedback loop -- extract, review, correct, refine skill, re-extract, compare
- **Claude Code native path** (step 6b in arxiv tutorial): documents how Claude Code
  consumes the data layer natively vs the CLI test utility
- 6 new tests: skill deprecate/activate CLI, session show, skill version roundtrip,
  nonexistent ID error handling for deprecate/activate/session show

## 0.13.0

### Changed

- **Pure data layer**: Removed orchestration from library. FreudAgent is now strictly
  a data layer (schema, context assembly, providers). Orchestration is the harness's job.
- CLI `run` command simplified to single-shot execution (`run_single()`) -- test utility,
  not orchestrator
- CLAUDE.md rewritten to position FreudAgent as a meta-framework inside the harness
- `skill/` restructured to demonstrate L1/L2/L3 progressive disclosure hierarchy
  - `skill.md` rewritten as L2 routing document
  - 5 new L3 reference files: schema, archetypes, context-assembly, hierarchy, flywheel

### Removed

- `run_task()`, `run_subtask()`, `run_simple()` from orchestrator module
- `TaskPlan`, `Subtask` Pydantic models from tables module
- 13 orchestration tests replaced by direct context assembly + provider tests

## 0.12.0

### Added

- **RLM (Recursive Language Model) provider**: inference-time scaffold that treats
  the user's prompt as a Python REPL variable, enabling iterative code-based
  exploration of large inputs
  - `rlm.py` -- `RLMProvider`, REPL engine, system prompt, source content loading
  - `RLMProvider` wraps any inner provider with a multi-turn REPL loop: the model
    writes code to probe, slice, and transform input via a persistent namespace
  - `llm_query()` function injected into REPL namespace for recursive sub-calls
  - `FINAL()`/`FINAL_VAR()` termination functions for explicit answer delivery
  - Sandboxed execution: restricted builtins (no `open`, `import`, `exec`),
    per-iteration timeout via `signal.alarm`, output truncation
  - Source content loading: `load_source_content()` reads text/JSON files directly,
    attempts `pdftotext` for PDFs, degrades gracefully for unsupported types
  - Source tag parsing: `<source>` XML tags in user messages trigger automatic
    content loading into the `context` variable
  - RLM metadata in session results: iteration count, sub-query count, per-iteration
    trace (code length, stdout/stderr length, termination action)
- **`complete_chat()` method** on `OpenAICompatProvider` and `ClaudeProvider`:
  multi-turn message history support for RLM and other iterative patterns.
  Backward-compatible -- `complete()` remains the required protocol method.
- **`recursive-decomposer` preset**: dream-work + free-association + fixation +
  pleasure-principle, mapping RLM behaviors to Freudian archetypes
- `metadata` field on `CompletionResult` for provider-specific structured data
- CLI flags: `--max-iterations` (REPL iteration limit), `--sub-model` (provider
  for `llm_query()` sub-calls)
- `rlm` and `rlm-anthropic` provider names in `get_provider()` factory
- 33 new tests: parsing, sandboxed execution, source loading, REPL loop,
  termination, token aggregation, multi-turn, preset integration, orchestrator pipeline

### Changed

- `OpenAICompatProvider.complete()` now delegates to `complete_chat()` internally
- `run_subtask()` merges `CompletionResult.metadata` into session result JSON

## 0.11.0

### Added

- **LLM-generated A2UI surfaces**: replaced static Python surface templates with
  runtime LLM generation (Claude, Gemini, or echo fallback)
  - `adapter.py` -- v0.9-to-v0.8 message translator for `@a2ui/lit` renderer
    (component restructuring, property mapping, typed data model conversion)
  - `providers.py` -- `A2UIProvider` protocol with 3 implementations:
    `EchoA2UIProvider`, `ClaudeA2UIProvider`, `GeminiA2UIProvider`
  - `prompt.py` -- system prompt assembly from skill files + component catalog +
    FreudAgent data shapes + few-shot examples
  - `prompt_addendum.md` -- FreudAgent entity descriptions for LLM context
- **Lit client** (`a2ui/client/`): Vite + Lit app using `@a2ui/lit` renderer
  - `src/app.ts` -- main app component with nav, provider selector, surface rendering
  - `src/api.ts` -- HTTP client for compose + action endpoints
  - `src/theme.ts` -- dark theme for `@a2ui/lit`
  - Builds to `a2ui/static/` (replaces old vanilla JS client)
- **Provider parameter** on `compose_surface` tool -- select LLM at request time
- **Free-form surface requests** -- no more hardcoded surface enum; LLM generates any layout
- 38 new tests: adapter (28), providers (10)

### Changed

- `compose_surface` now uses LLM pipeline: provider -> bridge validate -> adapter convert
- `queries.py` simplified: `model_dump(mode='json')` replaces 5 manual `*_to_dict` functions
- `server.py` serves built Lit app as static files via Starlette `StaticFiles`
- `pyproject.toml` updated: `anthropic` and `google-genai` optional deps, updated py-modules

### Removed

- `surfaces.py` -- 370 lines of hand-built component trees replaced by LLM generation
- `tests/test_surfaces.py` -- tests for deleted surfaces
- `static/index.html` -- vanilla JS renderer replaced by Lit client build output

## 0.10.0

### Added

- **A2UI integration** (`a2ui/`): visual surfaces for the experiment harness via A2UI v0.9 protocol
  - `server.py` -- MCP server with stdio (Claude Desktop) and HTTP (standalone web) modes
  - `bridge.py` -- structural A2UI validator (version, message types, component topology,
    JSON Pointer syntax, circular ref detection); optional `a2ui-agent` upgrade path
  - `queries.py` -- data access layer wrapping `ExperimentStore` for A2UI data models
  - `surfaces.py` -- 5 A2UI surface templates: extraction card, extraction list,
    session timeline, feedback summary, dashboard
  - `static/index.html` -- standalone web client with vanilla JS A2UI renderer
    (Text, Column, Row, Card, Button, Icon, Divider, Image, TextField, Tabs),
    SSE consumer, action sender, dark theme
- **5 MCP tools**: `render_a2ui`, `compose_surface`, `list_extractions`,
  `show_extraction`, `dashboard`
- **Interactivity**: validate/reject extractions from the web UI via POST actions,
  feedback submission
- **A2UI List component** in extraction list surface -- constant component count
  regardless of item count (data-driven via `itemTemplate`)
- **Session timeline grouping** -- children appear under their parent session,
  visually indented by depth level
- 34 tests: bridge validation (17), surface template validity (17)

### Changed

- Store uses a cached singleton connection (one DuckDB connection per server
  lifetime, not per tool call)
- Removed dead SSE infrastructure from web client (REST-only transport for now)
- Dropped `sse-starlette` dependency
- Shared `conftest.py` for test fixtures

## 0.9.0

### Added

- **Provider protocol**: `Provider` (protocol class) and `CompletionResult` (dataclass) replace
  the old `ModelCall` callable. Providers return structured responses with token counts and model info.
- **3 built-in providers**:
  - `EchoProvider` -- pipeline verification (replaces `EchoModel`)
  - `ClaudeProvider` -- Anthropic SDK, extracts `input_tokens`, `output_tokens`, `model` from response
  - `OpenAICompatProvider` -- any OpenAI-compatible endpoint via httpx (heylookitsanllm, llama.cpp, vLLM, Ollama)
- `get_provider()` factory: `"echo"`, `"anthropic"`, `"local"` with `model_name` and `base_url` params
- CLI `--endpoint` flag for local provider base URL
- CLI `--model local` option
- `token_usage` parameter on `store.complete_session()` -- set at completion time from provider response
- 4 new tests: token usage population, model_used from response, OpenAI-compat request format, get_provider local

### Changed

- `Session.token_usage` is now populated from provider responses (was always None)
- `Session.model_used` is set from the actual model in the response, not just the caller's string
- All `model_fn` parameters renamed to `provider` across orchestrator, CLI, and tests
- `run_subtask`, `run_task`, `run_simple` accept `provider: Provider` instead of `model_fn: ModelCall`

### Removed

- `ModelCall` protocol, `EchoModel` class, `get_model()` factory, `_call_anthropic` closure

## 0.8.0

### Added

- **8 enum classes** in `tables.py` as single source of truth for valid column values:
  `SkillStatus`, `SourceStatus`, `SessionStatus`, `AgentRole`, `ValidationStatus`,
  `CorrectionType`, `RuleScope`, `RuleStatus`
- **CHECK constraints** on all enum-like columns in DuckDB DDL (generated from Python enums)
- **10 FK constraints** enforcing referential integrity across all 6 tables
- `get_sources_by_ids()` bulk fetch method on `ExperimentStore` (eliminates N+1 in orchestrator)
- `get_ddl()` public function and `freud-schema db ddl` CLI command -- prints full DDL
  with CHECK + FK constraints for piping to `duckdb` CLI
- Generic `_fetchone`/`_fetchall` helpers on `ExperimentStore` -- uses `cursor.description`
  to build dicts by column name with automatic JSON deserialization via type detection
- 11 new tests: enum validation (5), CHECK constraint, FK constraint, prior results flow-through,
  all-subtasks-fail session state, exception session state, subtask named fields

### Changed

- `Subtask.skill_query: dict` replaced with `skill_domain: str` + `skill_task_type: str`
  (eliminates `.get("domain", "")` calls, gives IDE completion + type checking)
- All Pydantic model fields updated from bare `str` to enum types
- `store.py` method signatures typed: `complete_session(status: SessionStatus)`,
  `update_validation(status: ValidationStatus)`, `list_skills(status: SkillStatus)`, etc.
- CLI `choices=` derived from enum classes instead of hardcoded lists (also adds missing `deprecated` to skill status)
- `run_simple()` and all orchestrator code uses enum values for Session/Extraction construction
- All SQL string literals (`'active'`, `'deprecated'`, `'global'`) replaced with parameterized
  enum values -- zero hardcoded strings bypass the enum authority

### Removed

- Migration v2 infrastructure (`_MIGRATIONS`, `_run_migrations`, `_restore_migration_data`) --
  experiment repo, no legacy data, breaking changes are fine
- 6 `_row_to_*` positional-index methods in `store.py` -- replaced by generic dict conversion
  that is column-order-agnostic and auto-detects JSON columns from DuckDB type metadata

### Fixed

- **Prior results silently dropped**: `subtask.context and prior_results` gate removed --
  `subtask.context` was never set, so dependent subtasks never received upstream results
- **Session state lies**: orchestrator session now marked `"failed"` when all subtasks fail;
  `try/except/finally` ensures sessions never stay `"running"` after exceptions
- **Pydantic model mutation**: `extraction.id = ext_id` replaced with `store.get_extraction(ext_id)`
- **Source N+1 in context assembly**: `assemble_runner_context` uses `get_sources_by_ids()` bulk fetch

## 0.7.0

### Added

- **Archetype preset wiring**: archetypes are no longer decorative -- they flow into execution
  - `--preset` flag on `freud-schema run` composes archetype system prompt into context
  - `assemble_runner_context()` accepts optional `preset` param
  - `run_simple()` and `run_task()` propagate preset through the full pipeline
  - `freud-schema run --domain D --task-type T --preset careful-executor --model echo` shows archetypes in output
- **Skill rewrite**: `skill/skill.md` rewritten as a Claude Code data layer skill
  - Documents full CLI workflow: setup, data management, extraction, review, feedback
  - Reflects harness-agnostic architecture (FreudAgent feeds the harness, doesn't wrap it)
- 4 new tests: preset context assembly, preset in run_simple, no-preset baseline, invalid preset error

### Changed

- Promoted deferred `compose_preset` import to top-level in `orchestrator.py`
- Removed dead `orchestrator_preset` parameter from `run_task()` (was only logged, never used)
- Bumped `pyproject.toml` version to 0.7.0
- Backlog rewritten to reflect multi-harness north star and the inside/outside architectural pivot
  - Identifies orchestrator.py's API wrapper as the wrong pattern
  - Documents Provider protocol design (not implemented)
  - Documents harness adapter designs: Claude Code skill, Agent SDK workflow, MLX local
  - References flywheel decomposition JSON for Agent SDK mapping

## 0.6.1

### Added

- **Schema versioning**: `meta_schema_version` table tracks applied schema versions
  - Idempotent migration infrastructure (`_MIGRATIONS` list in `db.py`)
  - `get_schema_version()` query function
  - `db status` now displays current schema version
  - Pattern adopted from agent-state: replaces destructive-only schema evolution with safe, incremental migrations

## 0.6.0

### Added

- **`run` command**: Execute the orchestrator against database contents
  - `freud-schema run --domain D --task-type T` processes all active sources
  - `--source-id N` (repeatable) to target specific sources
  - `--model echo` (default) shows assembled context for pipeline verification
  - `--model anthropic` calls Claude API (requires `anthropic` SDK)
  - `--task` for additional task context
- **`extraction` commands**: `list`, `show`, `validate`, `reject`
- **`session list`**: View execution history (orchestrator + subagent sessions)
- **`feedback add`**: Close the flywheel loop with corrections on extractions
  - `--extraction-id`, `--type`, `--correction` (JSON), `--notes`, `--by`
- `EchoModel` -- built-in model for pipeline verification without API keys
- `get_model()` factory for model callables (echo, anthropic)
- `run_simple()` -- convenience function: skill + sources -> extractions
- 7 new tests for EchoModel, get_model, run_simple, end-to-end echo pipeline

### Changed

- `--db` moved from per-subparser to global root argument (all commands now use same DB)
- `feedback` CLI restructured to use subparsers: `feedback list` (was top-level), `feedback add` (new)
  - Old: `freud-schema feedback --skill-id 1 --aggregate`
  - New: `freud-schema feedback list --skill-id 1 --aggregate`
- `EchoModel` returns compact JSON; display layer handles formatting (eliminates double serialize)
- N+1 source lookups in `_handle_run` and `extraction list` replaced with bulk fetch + map
- Extracted `_print_json()` helper for duplicated JSON display logic
- `feedback add` uses `args.extraction_id` directly instead of `ext.id` (type-safe)

## 0.5.0

### Added

- **Experiment harness**: 6-table DuckDB schema for declarative agent orchestration
  - `skills` -- domain-specific instructions loaded at runtime
  - `sources` -- raw artifacts (file paths, MIME types)
  - `extractions` -- structured output with validation status
  - `sessions` -- logged agent executions with token tracking
  - `feedback` -- human corrections (the flywheel signal)
  - `rules` -- global and domain-specific constraints
- `db.py` -- DuckDB connection management and schema DDL
- `tables.py` -- Pydantic models for all 6 tables + TaskPlan/Subtask
- `store.py` -- ExperimentStore with typed CRUD operations, retrieval queries, feedback aggregation
- `orchestrator.py` -- Thin orchestrator loop + subagent runner with pluggable model calls
  - `assemble_runner_context()` -- progressive disclosure hierarchy (rules -> skill -> source -> task)
  - `run_subtask()` -- execute a single subtask with context assembly and session logging
  - `run_task()` -- process a TaskPlan respecting dependency order
- CLI commands: `db init|reset|status`, `skill add|list`, `source add|list`, `rule add|list`, `feedback`
- 18 new tests for schema, store CRUD, context assembly, orchestrator, and error handling
- DuckDB files added to .gitignore

### Changed

- Merged `progressive-refiner` preset into `iterative-refiner` (identical after archetype simplification)
- Presets reduced from 6 to 5
- CLI `export` command now uses orjson instead of json
- pyproject.toml: added duckdb, orjson dependencies; bumped to 0.5.0; updated description

## 0.4.0

### Changed

- **Aggressive archetype simplification: 19 -> 9** in a clean 3x3 grid
- ArchetypeCategory enum reduced from 6 categories to 3: STRUCTURAL, BEHAVIORAL, DIAGNOSTIC
- All 6 presets updated to reference new archetype names

### Added

- `ephemeral` archetype (merges `dream-element` + `psychic-apparatus`)
- `pleasure-principle` archetype (merges `pleasure-reality` + `death-drive`)
- `dream-work` archetype (merges `condensation` + `displacement` + `secondary-revision`)
- `freudian-slip` archetype (merges `parapraxis-monitor` + `resistance-detector`)
- `fixation` archetype (merges `cathexis` + `sublimation`)
- Tests for merged archetypes (verify each merge captures source concepts)
- 3x3 grid test (3 categories, 3 archetypes each)

### Removed

- 10 archetypes absorbed into merges or cut entirely
- Cut entirely (concepts absorbed into system-level design, not individual archetypes):
  `nachtraglichkeit`, `working-through`, `transference`, `topographic-hierarchy`
- Merged away: `condensation`, `displacement`, `secondary-revision`, `dream-element`,
  `psychic-apparatus`, `pleasure-reality`, `death-drive`, `parapraxis-monitor`,
  `resistance-detector`, `cathexis`, `sublimation`
- 3 obsolete ArchetypeCategory values: OBSERVATION, COMMUNICATION, RESOURCE_MANAGEMENT

## 0.3.1

### Changed

- Updated README.md to reflect current state: 19 archetypes, 17 entries, 6 presets
- Added architectural scopes section (intra-agent vs inter-agent)
- Added `hierarchical-orchestrator` and `progressive-refiner` to preset table
- Added `related_archetypes` usage and new preset examples to Python API section

## 0.3.0

### Added

- 5 new archetypes (14 -> 19): `psychic-apparatus`, `topographic-hierarchy`, `dream-element`, `nachtraglichkeit`, `secondary-revision`
- `related_archetypes` field on `AgenticArchetype` model (backward-compatible, default empty list)
- 3 new JSONL entries (14 -> 17): Interpretation of Dreams Ch. VII, Project for a Scientific Psychology, Letter 52/Mystic Writing Pad
- 2 new presets: `hierarchical-orchestrator`, `progressive-refiner`
- 5 new translation matrix entries: Nachtraglichkeit, Sekundare Bearbeitung, Bahnung, Wunderblock, Psychischer Apparat
- Archetype pattern reference entries for all 5 new archetypes
- Tests for new archetypes, presets, related_archetypes validation, and new JSONL entries

### Changed

- Updated `cathexis` description to reference RAM hierarchy and precise investment over diffuse attention
- Updated `structural-triad` description to clarify intra-agent scope vs `psychic-apparatus` inter-agent scope
- Skill activation keywords expanded (hierarchical, orchestrator, ephemeral, context tiering, nachtraglichkeit, topographic)
- `related_archetypes` enforced as bidirectional: `condensation`, `death-drive`, `working-through` now reference back to their counterparts
- `search_archetypes` now searches `prompt_fragment` in addition to other text fields
- CLAUDE.md updated to reflect current counts and presets

### Fixed

- Stray character in `pyproject.toml` dev dependencies
- Unused `json` import in `dataset.py`
- Removed phantom `duckdb` dependency (declared but never imported)
- Inconsistent mutable defaults on `FreudEntry` (`[]` -> `Field(default_factory=list)`)
- Redundant test functions (`test_new_archetypes_exist`, `test_new_presets`) merged into existing tests
- Repeated `load_entries()` disk reads in tests replaced with module-scoped fixture

## 0.2.0

- Initial agentic overlay: 14 archetypes, 4 presets, meta-harness, CLI

## 0.1.0

- Core schema: 14 JSONL entries, Pydantic models, dataset queries
