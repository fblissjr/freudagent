# Tutorial: Cold start -- from empty database to a turning flywheel

Last updated: 2026-07-21

This is the day-one playbook: what to do when the warehouse is empty and the
knowledge you want the agent to use exists only as documents and expertise in
the wrong shape. It walks the bootstrap sequence end to end and ends with the
system's first self-maintenance signal -- a staleness finding on a seed
document that changed after registration.

The principle behind every step: **cold-start output is training signal, not
truth.** Everything derived from the seed corpus starts untrusted; human
validation promotes it. The `validation_status` machinery models this --
the playbook makes it policy.

**Prerequisite:** none. This starts from nothing.

---

## 1. Create the warehouse

```bash
uv run freud-schema db init
uv run freud-schema db status
```

`db status` shows every table at zero except the seeds: `dim_tenant` has the
`default` tenant, `meta_key_algorithm` records `sha256/32`, and
`meta_schema_version` says what DDL you're on.

## 2. Register the seed corpus -- with staleness baselines

Register every seed document you'll extract from. Use `--hash` so each
source records a sha256 baseline of its current bytes:

```bash
uv run freud-schema source add --path ./corpus/domain-guide.md \
    --media-type text/markdown --hash
uv run freud-schema source add --path ./corpus/reference-tables.pdf \
    --media-type application/pdf --hash
```

Why `--hash` matters: cold-started knowledge decays fastest, because seed
corpora are exactly the documents someone else maintains. The baseline is
what lets the couch's `stale_source` detector tell you, later, that a source
changed out from under the knowledge you derived from it (step 8).

## 3. Author the seed constraints and skills by hand

Rules first -- the constraints that apply regardless of task:

```bash
uv run freud-schema rule add --name always-cite-source \
    --content "Every extracted fact must reference the source it came from." \
    --priority 10
```

Then the v1 skills, human-authored (`origin` defaults to `human_authored` --
the provenance distinction matters later, when data-derived versions start
competing with your seeds):

```bash
uv run freud-schema skill add --domain acme --task-type extraction \
    --content "Extract the field definitions from domain documents: name, type, constraints." \
    --status active
```

Don't over-author. The flywheel's whole point is that corrections will
improve these; a thin skill plus ten corrections beats a thick skill plus
zero, because the corrections are evidence and the thickness is guesswork.

## 4. Extract -- inside the harness

The harness (Claude Code, Agent SDK) runs the extraction: it assembles
context from the rules + skill + source (see
`skill/reference/context-assembly.md`) and writes `fact_extraction` rows.
This library never calls models -- extraction happens wherever your agent
runs.

For a dry run without a harness, the echo provider exercises the plumbing:
see the [arxiv extraction tutorial](tutorial-arxiv-extraction.md) for the
full extraction walkthrough.

## 5. Validate everything -- the cold-start gate

List what came back, and judge every single one:

```bash
uv run freud-schema extraction list --status pending
uv run freud-schema extraction show <key-prefix>
uv run freud-schema extraction validate <key-prefix>   # or: reject
```

During cold start, do not sample -- review all of it. Validated extractions
become the holdout history that later verification runs against (the eval
gate milestone); every un-reviewed extraction you let through pollutes that
foundation. Volume comes later; trust comes first.

## 6. Correct what's wrong -- typed, not freeform

Where an extraction is wrong, reject it and record *why* with a typed
correction:

```bash
uv run freud-schema feedback add --extraction-key <key-prefix> \
    --type missing_field \
    --correction '{"constraints": "the skill never asks for field constraints"}'
```

The correction types are the signal taxonomy: `missing_field` (skill needs
expansion), `wrong_value` (instructions ambiguous), `field_mapping` (schema
confusion), `false_positive` (needs constraint). See the
[flywheel tutorial](tutorial-flywheel.md) for how these aggregate.

## 7. First turn of the flywheel

Once corrections accumulate, the loop closes exactly as it does at steady
state -- aggregate, propose, approve, compile:

```bash
uv run freud-schema feedback list --skill-key <key-prefix> --aggregate
uv run freud-schema proposal add --target dim_skill \
    --natural-key '{"domain": "acme", "task_type": "extraction"}' \
    --content "..."
uv run freud-schema proposal approve <key-prefix> --by you
uv run freud-schema compile --out .claude/rules
```

No `--evidence` yet: it resolves each key against `fact_finding`, and a
cold-start database hasn't run a detector yet -- `couch run` is step 8.
Skip it for this first revolution; once findings exist, later proposals can
cite them.

That's one full revolution: seed -> extract -> validate -> correct ->
aggregate -> approve -> compile. Every turn after this one gets cheaper,
because the corrections are doing the authoring.

## 8. The first maintenance signal: staleness

Weeks later, someone edits a seed document. Simulate it:

```bash
echo "a new section the derived skills know nothing about" >> ./corpus/domain-guide.md
uv run freud-schema couch run
uv run freud-schema couch list --type stale_source
```

```
  [3fa2c19d] stale_source n=1: domain-guide.md: content changed since its
  baseline hash was recorded (source 8b1e42aa)
```

The `stale_source` detector recomputes each registered source's hash and
compares it to the baseline from step 2. It is registered with
`detection_method = hybrid` -- it reads the warehouse *and* the filesystem,
so the finding is not reproducible from the warehouse alone, and
`couch run --warehouse-only` skips it on machines where the corpus is not
present.

What to do with the finding is the flywheel again: re-extract from the
changed source, validate, and let the diff drive corrections. Staleness is
not an error -- it's the system telling you which knowledge to re-derive.

## Recap: the cold-start rules

1. **Baseline everything you register** (`source add --hash`) -- future
   staleness detection is free at registration time and impossible to
   retrofit precisely.
2. **Author thin, correct loudly** -- seed skills are scaffolding for
   corrections, not finished work.
3. **Validate all cold-start output** -- it becomes the holdout history
   everything later is measured against.
4. **Typed corrections over freeform notes** -- the aggregation views only
   see what the taxonomy captures.
5. **Close the loop once, manually, end to end** -- before any volume. If
   one revolution doesn't work by hand, automation will only make it fail
   faster.
