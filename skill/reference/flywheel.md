# Feedback Flywheel

Last updated: 2026-07-21

How recorded work becomes evidence, evidence becomes a governed change, and the
change becomes something the agent loads.

The full design is `docs/data-flywheel.md`; the short explainer is
the repo README; the failure modes are `docs/flywheel-failure-modes.md`.
This reference is the working agent's view: the stages, what backs each one in
this repo, and what is not built.

## The loop

```
ingest -> analyze -> propose -> approve -> compile -> verify -> (ingest)
```

Record what happened. Find what repeats. Turn a pattern into a written proposal
carrying its evidence. A person approves it. It becomes a new version compiled
into what the agent loads. Check it helped, against work already judged correct.

| Stage | What it does | In this repo |
|---|---|---|
| Ingest | Runs, events and documents land at the lowest granularity available. Keys are computed from natural keys, so re-ingesting unchanged material writes nothing | `ingest.py`, `discovery.py`; `ingest transcripts`, `ingest events` -> `fact_*`, every row stamped with an `etl_run_id` into `meta_load_log` |
| Analyze | Deterministic detectors scan for patterns worth acting on. Queries first, a model only for judgements a query cannot make | `couch.py`; `couch run` -> `fact_finding`. Thresholds live in `couch.py`, never in view DDL |
| Propose | A finding with enough evidence becomes a written proposal linked to the records that justify it | `proposal add --evidence <finding-key>,...` -> `fact_proposal` |
| Approve | Nothing reaches the agent's context without a person saying yes | `proposal approve` / `proposal_approve`; creates the SCD-2 version |
| Compile | Current active knowledge renders into the artifacts the agent loads, with provenance | `materialize.py`; `compile --out .claude/rules` |
| Verify | Run the new version against work already reviewed and marked correct, before it ships | not built |

## What sits between the raw material and the agent

The **grounding layer**: governed data with three faces.

- **Left-hand constraints** — what the agent may and must do. Rules, activation
  conditions, policies. This is the side everyone builds, because it feels like
  prompting.
- **Grounding data** — checked knowledge, the evidence behind it, and where it
  came from.
- **Right-hand constraints** — what good means. Success criteria for a task, a
  step, an outcome. Without them an agent can have excellent instructions and
  still no way to be told whether it succeeded, and neither do you. This is the
  side that gets deferred, and deferring it is why these systems so often never
  demonstrably improve.

Both sets of constraints are versioned data and evolve through the same loop as
everything else. The layer has two physical forms: the warehouse holds the
governed truth, compiled files are what the agent reads. Files are built from the
warehouse the way a binary is built from source.

## Where the signal comes from

The six stages are the visible engineering. Signal quality is what decides
whether the loop compounds or merely turns.

### Feedback granularity follows from breaking work down

People can only judge what they can evaluate. Asking whether a whole outcome was
good yields a verdict with nowhere to go — you learn it was bad, not where it
broke.

So work is broken down as far as it goes, judgement is captured wherever a person
can look at one thing and answer confidently, and those judgements aggregate up
to whatever the business cares about.

Two depths, and conflating them causes trouble. **Recording goes to the bottom
regardless**, because you cannot aggregate detail you did not keep and the level
that matters is rarely the one you would have guessed. **Only the asking is
tuned** — set by what a person can meaningfully judge. Too coarse and the
judgement is unactionable; too fine and you are asking about mechanics nobody has
an opinion on.

Once enough human judgements exist at a level, they become the reference that
lets a model make the same judgements at that level.

### The breakdown happens during the run

It is not authored in advance. It is the shape of the work, and it emerges as the
agent goes — leaning on skills, context and data to navigate, the way a person
does. A trivial request has no breakdown; forcing structure onto it would be
invention.

Recording it as it happens is what produces interpretability: not only what the
agent did but why it chose this path, what it considered and discarded, where it
changed approach. You cannot reconstruct that afterwards from an outcome.

Across many runs a pattern appears on top of those per-run facts, and once
established that pattern becomes guidance for future runs — which makes it a
high-level skill rather than a separate catalog anyone has to maintain.

### Deviation is signal in both directions

If the prescribed process and the observed process are both recorded, the gap
between them is information — and most systems look for only one direction.

- The agent departs from the guidance and does **worse**: the guidance was right,
  and either the agent went wrong or the guidance was not explicit enough to
  follow.
- The agent departs and does the **same or better, faster**: the guidance was
  wrong, and the agent found out. The proposal to generate is to update the
  guidance to match what actually works.

Two conditions make this safe. It needs measurable outcomes at the level the
deviation happened, or you cannot tell a genuine shortcut from a corner cut and
you will promote the corner cut. And it needs enough declared structure in the
guidance to depart from measurably. Note the trap: some steps exist to prevent
something rare, and skipping them looks strictly better every time until the rare
thing happens — which is why rules should carry why they exist, not only what to
do.

### Model-generated feedback amplifies; it does not substitute

Human review does not scale to the volume these systems produce, so seeding a
model from human judgements is the obvious move. It works, but the precondition
is **diversity** of the seed, not size. A seed concentrated in one slice fails two
ways on everything else: the model falls back on its own prior knowledge, which is
not this organisation's judgement and was reviewed by nobody, or it stretches the
feedback it has onto material that feedback was never about. Both produce labels
that are consistent, plausible and wrong, and the errors are systematic rather
than random, so they compound instead of averaging out.

The controls are structural: keep the origin label on every record so
model-derived feedback can be excluded from any measurement that matters, keep a
floor on the proportion of human judgements, and when the two disagree believe the
people and find out why.

### Feedback is a labelled overlay on immutable records

An output stays as produced. Feedback about it is a separate record pointing at
it, carrying what produced it. The original stays recoverable, several people can
disagree about the same output without overwriting each other, and what we
thought about this and when stays answerable.

## Correction types

Field-level corrections. Each kind points at a different defect in the guidance.
The vocabulary is closed — `CorrectionType` in `tables.py`.

| Type | What it means | What it tells you |
|---|---|---|
| `wrong_value` | the value is incorrect | the instructions are ambiguous |
| `missing_field` | something was not extracted | the guidance needs to ask for more |
| `field_mapping` | right value, wrong place | the output shape is confusing |
| `false_positive` | the agent invented something | the guidance needs a constraint |

Recorded via `feedback add --extraction-key <key-or-prefix> --type T
--correction '{...}'`; aggregated with `feedback list --skill-key <key> --aggregate`.

Feedback about a unit of knowledge itself — outdated, unclear, or in fact the
thing that solved the problem — is a second level that lets people who read the
knowledge base, not only people reviewing agent output, turn the same loop. Not
built.

## Skills are a ragged hierarchy

A skill is not an atomic instruction. It is a composition — rules, code,
references, other skills — of variable depth. Ragged rather than balanced: one
branch goes four levels, its sibling goes one.

They span the full range. At the top, orchestration guidance: how work of this
kind breaks down, in what order, with what checkpoints — where learned breakdowns
live. At the bottom, semantic definitions: what this field means in this
business, which of three date columns anybody means by "closed", what this team
counts as an active customer. That bottom rung is the least glamorous part and
the one with the strongest evidence behind it, because these systems fail in real
organisations on not knowing which column was meant, not on reasoning.

See `reference/retrieval-thesis.md` for how only the applicable part gets loaded,
and `reference/hierarchy.md` for the tree architecture.

## The twelve steps: a finer cut of the same loop

The six stages above are the model. The twelve steps below are a **finer breakdown
of the same loop**, kept for one specific purpose the stages do not serve:
assigning each step to an Agent SDK primitive — deterministic tool, model-driven
agent, or irreducibly human. When the question is "who or what executes this
step", use the steps. For everything else, use the stages.

Two things to hold onto so this does not read as a competing model.

**Scope.** The decomposition covers one pass over a single reviewed output — from
an output arriving for review through to a verified new version. It is a zoom-in,
not a rival account. It has no step for ingesting *runs* because it treats the run that produced
the output as upstream of itself.

**Alignment.** Every step sits inside a stage:

| Step | Who does it | Stage |
|---|---|---|
| 1.1.1 Context assembly — load the output, its source, its skill, prior corrections | tool | (pre-judgement) |
| 1.1.2 Quality assessment — compare against the source at a judgeable level | human | ingest (signal) |
| 1.1.3 Correction submission — typed correction, before/after per field | human | ingest (signal) |
| 1.2.1 Feedback collection — query feedback grouped by `correction_type` | tool | analyze |
| 1.2.2 Pattern detection — recurring corrections, conflicts flagged | agent | analyze |
| 1.2.3 Threshold evaluation — compare against per-domain thresholds | tool | analyze -> propose |
| 1.3.1 Update synthesis — draft the change from qualifying patterns | agent | propose |
| 1.3.2 Human approval — review the proposed diff, approve or reject | human | approve |
| 1.3.3 Version activation — write the new version | tool | approve -> compile |
| 1.4.1 Reference-set testing — run the candidate against work already judged correct | agent | verify |
| 1.4.2 Regression detection — compare against the previous version | agent | verify |
| 1.4.3 Metric recording — write flywheel health metrics | tool | verify |

These numbers are stable and cited elsewhere in the repo. Three steps are marked
human and all three are meant to be: 1.1.2 and 1.1.3 are judgement capture, which
is the other thing that cannot be handed to a model. What 1.3.2 uniquely marks is
that nothing reaches the agent's context without it, which is why the codebase
names it at `store.approve_proposal()`, `ops.py` and `mcp_server.py`. The table above is the definition of record: it is
committed, and the numbers are cited from committed code, so they cannot depend on
anything that is not.

Two corrections to the original decomposition, from changes since it was written:

- 1.3.3 does not deprecate the old version as a separate step. SCD-2 evolution
  closes the prior row automatically when the new one is inserted; there is no
  manual deprecate.
- The breakdown assumes a skill is the only thing that evolves. Proposals now target a
  closed set of dimensions — `TargetDimension`: `dim_skill`, `dim_rule`,
  `dim_sampling_config`. Closed on purpose: a new member means the loop learned to
  change a new kind of thing, which is an engineering decision rather than a row
  somebody inserted.

### Mapping to Agent SDK primitives

- **tool** steps -> SDK tools (deterministic, no reasoning needed)
- **agent** steps -> SDK agents (autonomous reasoning tasks)
- **human** steps -> SDK human-in-the-loop (irreducibly human decisions)

Cross-phase dependencies become SDK handoffs; early exits (no corrections needed,
threshold not met) are branching logic in the orchestrating agent.

The gate is built in the tools, not in a policy document: `rule_add` and
`skill_add` always create the non-compiling status regardless of what a caller
asks for, drafts never compile, and `proposal_approve` must never be allowlisted —
the harness's permission prompt *is* the approval. The honest limit: a gate in one
tool surface is only as strong as the surfaces beside it. Anything with write
access is in its threat model.

## What is built

Matches the implementation-status table in `docs/data-flywheel.md`. This is a
research repo at single-operator scale, not a product.

| Stage | State |
|---|---|
| Ingest | working, for agent transcripts and generic event streams |
| Analyze | detection works; findings have no lifecycle, so recurrence is not tracked |
| Propose | proposals work and carry evidence; claim types are not built |
| Approve | working, including the draft-only tool gate |
| Compile | compiling and provenance footers work; scoped output and the drift check are not built |
| Verify | not built |

Also unbuilt: nearly everything in the signal section above — right-hand
constraints, the breakdown as governed data, conformance checking, deviation as
signal, model-generated feedback with its controls, and the sampler that would
spread review deliberately. Plus ranked retrieval, redaction on the way in,
identity and permissions, unit-level feedback, and consolidation passes.

The mechanical half of the loop exists; the signal-quality half mostly does not.
That is the normal order these get built in, and it is also why so many plateau.

## Dev / eval data

`data/synthetic/` is a committed, all-fictional corpus for developing and
evaluating this loop end to end (see its `README.md`). Directly relevant here:

- `feedback/annotation_corrections.jsonl` — typed corrections in the
  `CorrectionType` taxonomy above; ready-made signal input.
- `eval/conflicts.jsonl` — the answer key for conflicting "facts": each record
  gives the competing sources, the correct value, and the **resolution rule**
  (`recency_supersession`, `process_status`, `document_type_authority`,
  `system_of_record`, `org_authority`). Ground truth for the
  conflicting-feedback problem the loop must eventually handle.
- `governance/` — system-of-record and source-authority registries (the scoring
  model in structured form). `eval/citation_edges.csv` — the source-centrality
  graph. `time/` — staleness ground truth (page histories, snapshots, policy
  supersession).

The corpus regenerates deterministically; see its README for the
`generate_synthetic_data.py` + `build_citation_graph.py` sequence.
