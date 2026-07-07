# Tutorial: The feedback flywheel end-to-end

Last updated: 2026-07-07

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
