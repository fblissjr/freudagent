# Tutorial: The feedback flywheel end-to-end

Last updated: 2026-07-21

This walks through the full flywheel loop: extract, review, correct, refine skill,
re-extract, compare. Every step uses real CLI commands against the database.

**Prerequisite:** Complete the [arxiv extraction tutorial](tutorial-arxiv-extraction.md)
through step 9 (feedback exists in the database). You should have:

- At least 1 skill (arxiv/extraction, v1, active)
- At least 1 source (the attention paper)
- At least 1 extraction
- At least 1 feedback entry

If you skipped the real model step, that's fine -- echo output works for demonstrating
the flywheel mechanics.

---

## 1. See the signal

Aggregate feedback by correction type to identify patterns:

```bash
uv run freud-schema feedback list --skill-key 9c1e4a7b --aggregate
```

Output looks like:

```
Feedback for skill 9c1e4a7b:
  missing_field             1x
  wrong_value               1x
```

Each correction type tells you something different about the skill:
- `missing_field` -- the skill doesn't ask for something it should
- `wrong_value` -- the skill's instructions are ambiguous, leading to errors
- `false_positive` -- the skill over-extracts, fabricating data
- `field_mapping` -- the skill's schema is confusing, causing misplacement

## 2. Read the corrections

Look at the individual feedback entries to understand the specific failures:

```bash
uv run freud-schema feedback list --skill-key 9c1e4a7b
```

Then review the extraction that was corrected (use the extraction key or a
unique prefix from the feedback output -- your keys will differ from this
example):

```bash
uv run freud-schema extraction show <extraction-key>
```

The goal: identify patterns. If multiple corrections say "missing limitation" or
"wrong author name," that's a signal the skill needs targeted improvement.

## 3. Draft a v2 skill

Based on the feedback, write a v2 skill that addresses the identified gaps.
Here's an example that adds explicit instructions for the fields that got feedback:

```bash
uv run freud-schema skill add \
  --domain arxiv --task-type extraction \
  --version 2 --status active \
  --content 'You are extracting structured metadata from an academic paper.

Given the paper source, extract the following fields into a JSON object:

{
  "title": "Full paper title, exactly as written",
  "authors": ["List of ALL author names, spelled exactly as in the paper header"],
  "year": 2017,
  "arxiv_id": "e.g. 1706.03762",
  "abstract_summary": "1-2 sentence summary of the abstract",
  "key_contribution": "The single most important contribution, one sentence",
  "architecture_components": ["List of named components or modules introduced"],
  "key_findings": [
    {"finding": "Description", "evidence": "How they demonstrated it", "key_quote": "Exact quote from paper"}
  ],
  "datasets_used": ["List of datasets mentioned in experiments section"],
  "limitations_stated": ["Every limitation the authors explicitly acknowledge, including computational cost concerns"]
}

IMPORTANT:
- Author names must match the paper exactly. Do not abbreviate or modify spelling.
- For limitations_stated: check the conclusion and discussion sections thoroughly. Papers often state limitations implicitly (e.g., "attention on very long sequences is computationally expensive").
- Extract only what is stated in the paper. For fields you cannot determine, use null.'
```

**What changed from v1:**
- Author instruction strengthened: "spelled exactly as in the paper header"
- Limitations instruction expanded: explicit guidance to check conclusion/discussion,
  example of an implicit limitation
- Key quote instruction clarified: "Exact quote from paper" vs just "Exact quote"

These changes map directly to the feedback: `wrong_value` on authors -> spelling instruction;
`missing_field` on limitations -> expanded extraction guidance.

## 4. v1 is superseded automatically

`dim_skill` is SCD-2, keyed by `(domain, task_type)` -- v1 and v2 share the
same `skill_key`. Inserting v2 in step 3 already closed v1's row
(`is_current = false`), so there's no separate deprecate step: `get_active_skill()`
only ever looks at the current row, and v2 is now it. Running
`skill deprecate <key>` at this point would flip the *current* row (v2, the
one you just activated) to `deprecated` instead -- not what you want here.
`skill deprecate`/`skill activate` are for retiring or reinstating whichever
version is current, independent of adding a new one.

Verify v2 is the only current row:

```bash
uv run freud-schema skill list
```

You should see one row: v2, `active`. `skill list` only shows current rows --
v1's closed row still exists in `dim_skill` with `is_current = false`; inspect
it with the DuckDB MCP tools if you want the version history:

```sql
SELECT version, status, is_current, effective_from, effective_to
FROM dim_skill WHERE skill_key = '9c1e4a7b...' ORDER BY effective_from;
```

## 5. Re-extract

Run the same source through the new skill via the harness. In Claude Code, the
harness handles extraction natively. Programmatically:

```python
from freud_schema.orchestrator import get_provider, assemble_runner_context
from freud_schema.db import connect
from freud_schema.store import ExperimentStore

store = ExperimentStore(connect("data/freudagent.duckdb"))
skill = store.get_active_skill("arxiv", "extraction")  # picks up v2 automatically
sources = store.list_sources()

system_prompt, user_message = assemble_runner_context(
    store, skill_key=skill.skill_key,
    source_keys=[s.source_key for s in sources], domain="arxiv",
)

provider = get_provider("echo")  # or "anthropic", "local", "rlm", etc.
result = provider.complete(system_prompt, user_message)
print(result.content)
store.close()
```

`get_active_skill()` automatically picks up the latest active skill (v2), so no
additional routing is needed.

## 6. Compare extractions

List all extractions to find the v1 and v2 extraction keys, then compare:

```bash
uv run freud-schema extraction list

# Compare the two (use your actual keys or unique prefixes)
uv run freud-schema extraction show <v1-extraction-key>
uv run freud-schema extraction show <v2-extraction-key>
```

With the echo provider, the difference is in the system prompt: v2's system prompt
contains the strengthened instructions. With a real model, the difference is in the
output -- v2 should produce more accurate author names and catch more limitations.

## 7. Inspect the session

List sessions to find the keys, then inspect the v2 run:

```bash
uv run freud-schema session list

# Show the session from the v2 run (use its actual key or unique prefix)
uv run freud-schema session show <session-key>
```

This shows the model used, token usage (if using a real provider), context loaded,
and the result. Compare the v1 and v2 sessions to see how the context assembly changed.

## 8. What's manual vs automated

The flywheel has 12 atoms across 4 phases (see `skill/reference/flywheel.md`):

**Phase 1 (Human Review & Correction):** Partially automated. Context assembly is a
tool operation. Quality assessment and correction submission are irreducibly human --
you need domain knowledge to judge whether an extraction is correct.

**Phase 2 (Signal Aggregation):** Partially automated. `feedback list --aggregate`
collects and counts. Pattern detection (identifying that "missing_field" corrections
all target the same field) is currently human reasoning.

**Phase 3 (Skill Evolution):** Manual. You drafted the v2 skill based on feedback
patterns. `skill add --version 2` is a tool -- and, since `dim_skill` is SCD-2,
it automatically supersedes v1 with no separate deprecate step -- but the
synthesis step (deciding what to change) is human.

**Phase 4 (Impact Verification):** Manual. You compared extractions by eye. Holdout
testing (running the new skill against already-validated extractions to measure
regression) is documented in the backlog but not implemented.

The database makes the full loop traceable: every extraction knows which skill version
produced it, every feedback entry knows which extraction it corrects, and every session
knows which skill and model were used. Closing the loop automatically (having an agent
draft v2 from feedback patterns) is deferred -- see `internal/BACKLOG.md`.

Steps 1-8 above changed a skill by hand: you read the feedback, you wrote v2, you
ran `skill add`. That works, but nothing recorded *why* v2 says what it says.

The rest of this tutorial walks the governed path instead -- the one where a change
is evidence-linked, human-approved, and compiled with its provenance attached. It
uses rules rather than skills, and its signal comes from the warehouse rather than
from your corrections, but it ends at the same gate.

---

## 9. The second source of signal

Steps 1-8 started from a correction you wrote. The other source is the warehouse
itself: what actually happened across sessions. Detectors read it and emit findings.

This half needs ingested history, so run this first if you have not already:

```bash
uv run freud-schema ingest transcripts
```

Ingest is idempotent -- keys are derived from content, so running it twice writes
zero rows the second time.

## 10. Run the detectors

```bash
uv run freud-schema couch run
```

```
Couch run 14cb4c00: 2 finding(s) recorded.
```

The identifier is the load-run id, truncated to 8 characters. Every couch run gets
one, and it joins to `meta_load_log`.

These are SQL detectors. No model is called, so the run is cheap and repeatable.
Five ship today:

| Finding type | What it looks for | Threshold |
|---|---|---|
| `retry_loop` | same tool, identical input, repeatedly in one session | 3 attempts |
| `tool_error_cluster` | a tool failing at an elevated rate in a project | 20 uses and 15% errors |
| `interruption_hotspot` | repeated mid-turn user interruptions | 3 interruptions |
| `permission_friction` | repeated permission denials for the same tool | 3 denials |
| `stale_source` | a registered source file whose content changed | any hash mismatch |

`stale_source` reads the filesystem as well as the warehouse, so it needs a baseline
recorded by `source add --hash`. Skip it with `couch run --warehouse-only`.

Now list what was found:

```bash
uv run freud-schema couch list --type retry_loop
```

```
  [ef2433c7] retry_loop n=4: Read: 2 identical-input call loop(s) across 1 session(s), worst 3 attempts
```

Each finding carries the session keys that evidence it, so the claim is checkable
rather than merely assertable.

## 11. Pick the evidence

The finding keys you just listed are what the next step cites. Copy the one you
want straight from `couch list` -- the truncated 8-character form is fine.
Evidence keys resolve like every other key argument in the CLI: a full key or any
unique prefix works, and what gets stored is always the resolved full key.

A prefix matching nothing, or matching more than one finding, is an error and no
proposal is written. That matters more here than elsewhere: a proposal's evidence
is what makes it checkable rather than merely plausible, and both `couch list`
and the compiled provenance footer print keys truncated to 8 characters, so an
unresolved reference would look exactly like a valid one.

To see full keys and more detail than `couch list` shows, query the table
directly through the store-ops MCP server's `query` tool or any read-only SQL
surface:

```sql
SELECT finding_key, finding_type, occurrence_count, summary
FROM fact_finding
WHERE finding_type = 'retry_loop'
ORDER BY created_at DESC
LIMIT 5;
```

```
ef2433c73b175c86c921dfe17da35274 | retry_loop | 4 | Read: 2 identical-input call loop(s)...
```

## 12. Draft a proposal

A finding says something is happening. A proposal says what to do about it.

```bash
uv run freud-schema proposal add \
  --target dim_rule \
  --natural-key '{"name": "no-identical-retries"}' \
  --content 'After a tool call fails, never repeat the exact same call with the exact same input more than once. Two identical failures mean the approach is wrong.' \
  --evidence ef2433c7
```

```
Proposal created (pending): key=c7c0caf768571ffd1ecb07675f384fde
```

The key prints in full here precisely so you can paste it into the next command.

Notes on the arguments:

- `--target` is one of `dim_rule`, `dim_skill`, `dim_sampling_config`
- `--natural-key` is JSON identifying the entity to evolve. Rules need `name`, and
  accept `scope`, `domain` and `priority`. Skills need `domain` and `task_type`
- `--evidence` takes a comma-separated list of finding keys or unique prefixes,
  resolved to full keys before anything is written
- the proposal is created `pending`. Nothing has changed yet

## 13. Review it

This is the step the whole design exists to protect. Read the proposal and check
its evidence against the rows it cites, rather than trusting its summary.

```bash
uv run freud-schema proposal show c7c0caf7
```

```
  Proposal: c7c0caf768571ffd1ecb07675f384fde
  Status: pending
  Target: dim_rule
  Natural key: {"name":"no-identical-retries"}
  Evidence findings: ef2433c7
  Proposed content:
    After a tool call fails, never repeat the exact same call with the exact same input more than once. Two identical failures mean the approach is wrong.
```

Commands that take a key accept a unique prefix, git-short-hash style.

If it does not hold up:

```bash
uv run freud-schema proposal reject c7c0caf7 --by "reviewer"
```

Rejection touches no dimension table. It records the status, the reviewer and the
time, and stops there. A rejection rate near zero is a sign the gate is not being
used rather than a sign that everything proposed was good.

## 14. Approve

```bash
uv run freud-schema proposal approve c7c0caf7 --by "reviewer"
```

```
Proposal c7c0caf7 approved. Dimension key: 41e373fd2c53f65f3369289a60dab0e8
Run `freud-schema compile --out <dir>` to materialize.
```

Approving does the write. For a rule it calls the same SCD-2 insert path as
`rule add`: if a rule with that natural key already exists and the content differs,
the current row is closed and a new version opens, active. Nothing is overwritten,
so the previous version stays queryable.

The proposal row is updated too, with `resulting_dimension_key` pointing at the
version it created. That is the link that makes the next step's footer possible.

## 15. Compile

Approval changed a row. It did not change anything the agent loads. Compiling does:

```bash
uv run freud-schema compile --out .claude/rules
```

```
  wrote   no-identical-retries.md
Compile: 1 written, 0 removed, 0 blocked.
```

The file:

```markdown
<!-- compiled by freud-schema: do not edit; change the dimension row and recompile -->
<!-- source: dim_rule 41e373fd2c53f65f3369289a60dab0e8 effective_from 2026-07-21T10:27:36 -->

After a tool call fails, never repeat the exact same call with the exact same input more than once. Two identical failures mean the approach is wrong.

<!-- provenance: proposal c7c0caf7; findings ef2433c7 -->
```

Read the footer backwards and you have the whole chain: this file came from that
proposal, which cited that finding, which aggregated those sessions. That is what
the governed path buys you over editing a file by hand.

Three behaviours worth knowing:

- only current, active rules for the tenant compile. Deprecated and historical
  versions are skipped
- files in the output directory that start with the compiled marker but no longer
  match a rule are deleted. Hand-written files are never touched
- a privacy gate runs before each write. If rendered output contains a home
  directory path or the current username, that file is blocked and the previous
  good version is left in place. Blocked files make the command exit non-zero

A rule added directly with `rule add` compiles fine, but has no provenance footer.
There is no proposal behind it to cite.

## 16. What an agent can and cannot do here

Everything above is the human path, run from a terminal. An agent working in a
session reaches the same operations through the store-ops MCP server, with one
deliberate difference: it cannot switch anything on for itself.

- `rule_add` and `skill_add` as MCP tools force the non-compiling status
  (`inactive` for rules, `draft` for skills) whatever status the caller asks for.
  A draft never compiles, so it never loads
- the only route to active is `proposal_add` then `proposal_approve`
- `proposal_approve` must never be allowlisted in permissions config. The harness
  permission prompt it raises is the approval

The CLI has no such restriction, because a human is typing it. The gate is aimed
at agent-invoked tools specifically.

---

## What to try next

- **Add more feedback on v2.** Extract via the harness with a real model, review
  the output, add corrections. Does v2 actually produce fewer errors? The database
  answers this.

- **Aggregate across versions.** Use the DuckDB MCP tools to compare feedback
  counts between skill versions -- `skill_version` is denormalized onto
  `fact_feedback`, so no join is needed:
  ```sql
  SELECT skill_key, skill_version, COUNT(*) as corrections
  FROM fact_feedback
  GROUP BY skill_key, skill_version
  ```

- **Try different presets.** Use `assemble_runner_context(..., preset="careful-executor")`
  vs no preset. Does the censor-gate archetype reduce false positives?

- **Compare providers.** Extract with the same v2 skill using `get_provider("anthropic")`
  vs `get_provider("local")`. Which produces more corrections? The `fact_session`
  table tracks this automatically.
