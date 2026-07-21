# Tutorial: Extracting structured data from an arxiv paper

Last updated: 2026-07-21

This walks through the full FreudAgent pipeline using a real arxiv paper as
the data source. Every step explains not just the command but why the system
is designed that way.

The paper: [Attention Is All You Need](https://arxiv.org/abs/1706.03762)
(Vaswani et al., 2017). Chosen because it's universally known, has clear
extractable structure, and is complex enough to be interesting.

## What you'll learn

- Why the schema IS the architecture (not code)
- Why skills, rules, and sources are separate concerns
- Why echo-first development catches problems before API calls
- Why feedback is the point, not a nice-to-have

---

## 0. Prerequisites

```bash
# Core install
uv sync --extra dev

# If you want to run against Claude (optional -- echo works without API keys)
uv sync --extra anthropic

# If you want to run against a local model like heylookitsanllm (optional)
uv sync --extra local
```

Download the paper to use as a source artifact:

```bash
mkdir -p data/papers
curl -L -o data/papers/attention-is-all-you-need.pdf \
  https://arxiv.org/pdf/1706.03762
```

## 1. Initialize the database

```bash
uv run freud-schema db init
```

**Why a database, not files?** The thesis FreudAgent tests is: "Does
declarative data-driven orchestration produce measurably better results than
code-driven workflow approaches?" To test that, you need structured records of
what was attempted, what was produced, and what humans corrected. Files can't
do that. The dimensional schema (9 dimension tables, 11 fact tables, 10 analytical
views) isn't plumbing -- it's the experiment itself.

**Why `init` is separate from `run`:** You set up the database once, then run
many experiments against it. The schema is idempotent (`CREATE TABLE IF NOT
EXISTS`), so running `init` again is safe.

## 2. Add rules

Rules are constraints that apply across all tasks. They get injected into every
model call as the first layer of context.

```bash
uv run freud-schema rule add \
  --name valid-json-output \
  --content "Output valid JSON. No markdown fences, no commentary outside the JSON object." \
  --scope global --priority 10

uv run freud-schema rule add \
  --name no-fabrication \
  --content "Never fabricate data. If a field cannot be determined from the source, use null." \
  --scope global --priority 9

uv run freud-schema rule add \
  --name exact-quotes \
  --content "Use exact quotes from the paper when populating 'key_quote' fields." \
  --scope domain-specific --domain arxiv --priority 5
```

**Why `--name` is required:** `name` is the rule's stable identity -- it's also
the future compile target filename (`.claude/rules/<name>.md`). A row id isn't
stable enough for that; a name is.

**Why rules are separate from skills:** Rules are invariants. "Don't fabricate
data" applies whether you're extracting from arxiv papers, legal contracts, or
medical records. Skills change per task; rules persist. Separating them means
you can swap skills without re-stating your safety constraints, and you can
tighten rules without touching task-specific instructions.

**Why priority matters:** When multiple rules apply, they're ordered by priority
(highest first). The model sees "output valid JSON" before "use exact quotes."
This mirrors how human instructions work: the most important constraint should
frame everything that follows.

Verify:

```bash
uv run freud-schema rule list
```

## 3. Add a skill

A skill is a set of domain-specific instructions for a particular task type.
This is where you tell the model what to extract and how to structure it.

```bash
uv run freud-schema skill add \
  --domain arxiv --task-type extraction \
  --status active \
  --content 'You are extracting structured metadata from an academic paper.

Given the paper source, extract the following fields into a JSON object:

{
  "title": "Full paper title",
  "authors": ["List of author names"],
  "year": 2017,
  "arxiv_id": "e.g. 1706.03762",
  "abstract_summary": "1-2 sentence summary of the abstract",
  "key_contribution": "The single most important contribution, one sentence",
  "architecture_components": ["List of named components or modules introduced"],
  "key_findings": [
    {"finding": "Description", "evidence": "How they demonstrated it", "key_quote": "Exact quote"}
  ],
  "datasets_used": ["List of datasets mentioned in experiments"],
  "limitations_stated": ["Limitations the authors explicitly acknowledge"]
}

Extract only what is stated in the paper. For fields you cannot determine, use null.'
```

**Why skills are versioned and have status:** Skills evolve. Your first
extraction prompt will be imperfect. Feedback (step 8) tells you what's wrong.
You write a v2 skill that fixes it and re-run -- `dim_skill` is SCD-2, so
inserting a higher version automatically supersedes v1 (no separate deprecate
step). The database tracks which skill version produced which extraction, so
you can measure whether v2 actually improved things. This is the "flywheel"
the project keeps referencing: extract -> review -> correct -> refine skill ->
re-extract.

**Why `--status active`:** Skills start as `draft` by default. Only `active`
skills are picked up by `get_active_skill()` when the harness assembles context.
This prevents half-written instructions from accidentally being used.

Verify:

```bash
uv run freud-schema skill list
```

## 4. Register the source

A source is a pointer to an artifact. The harness tracks what's been processed,
by which skill, with what results.

```bash
uv run freud-schema source add \
  --path data/papers/attention-is-all-you-need.pdf \
  --media-type application/pdf
```

**Why sources are registered, not just passed as arguments:** Because the
database needs to track provenance. When you look at an extraction later, you
need to know: which source produced it, which skill processed it, which model
ran it, how many tokens it used. If sources were just CLI arguments, that
chain breaks.

**Why the harness reads the file, not the data layer:** The data layer tracks
source metadata (path, MIME type) but doesn't read file contents. The harness
(Claude Code, Agent SDK) reads files directly. Claude Code uses the Read tool;
Agent SDK uses whatever file access the runtime provides. The RLM provider is
an exception -- it loads source content into the REPL namespace (see the
[RLM tutorial](tutorial-rlm-provider.md)).

Verify:

```bash
uv run freud-schema source list
```

## 5. Verify context assembly

Before spending API calls or GPU cycles, verify that the data layer assembles
context correctly. The `EchoProvider` returns the exact system prompt and user
message that a real model would receive.

```python
from freud_schema.db import connect
from freud_schema.store import ExperimentStore
from freud_schema.orchestrator import EchoProvider, assemble_runner_context

store = ExperimentStore(connect("data/freudagent.duckdb"))
skill = store.get_active_skill("arxiv", "extraction")
sources = store.list_sources()

system_prompt, user_message = assemble_runner_context(
    store, skill_key=skill.skill_key,
    source_keys=[s.source_key for s in sources], domain="arxiv",
)

# See exactly what a model would receive
echo = EchoProvider()
result = echo.complete(system_prompt, user_message)
print(result.content)
store.close()
```

Or in Claude Code, use the store-ops MCP server's `query` tool to inspect skills,
rules, and sources directly. The harness (Claude Code, Agent SDK) handles extraction
-- step 6b below is the primary path.

Look for:
- Are all 3 rules present in the system prompt?
- Is the skill content there, in full?
- Is the source reference in the user message?

## 6. Inspect results after extraction

After the harness produces extractions (step 6b below), inspect them:

```bash
# See extraction records
uv run freud-schema extraction list

# See the full output (key or unique prefix from the list above,
# git-short-hash style, e.g. 4f2b9c31)
uv run freud-schema extraction show 4f2b9c31

# See the session log
uv run freud-schema session list
```

**Why sessions exist:** Every extraction creates a `fact_session` record.
Sessions track status (running/completed/failed), which skill was used, what
context was loaded, token usage, and the model that actually responded. This
is how you answer "what happened?" after the fact, and how you compare
providers (did the local model use fewer tokens? did it fail more often?).

## 6b. How the harness does extraction

Extraction is the harness's job -- Claude Code, Agent SDK, or whatever orchestrates.
The CLI manages data (skills, rules, sources, feedback). The harness reads data,
calls models, and stores results.

**Activation.** When you mention "extraction", "arxiv", or "experiment harness" in
conversation, Claude Code matches the skill frontmatter keywords and loads
`skill/skill.md` (L2). The routing table there points to the specific reference
files (L3) Claude Code needs. This is the same progressive disclosure hierarchy
the CLI implements, but the harness handles routing natively.

**File access.** Claude Code reads the PDF directly via the Read tool. It reads the
file, understands the content, and extracts from it directly.

**Data access.** Claude Code uses the store-ops MCP server (`freud-schema mcp-serve`,
configured in `.mcp.json`) for all database operations: the read-only `query` tool
(single SELECT, enforced by `classify_readonly`) for inspection, and typed write tools
(`rule_add`, `skill_add`, `source_add`, `feedback_add`, `extraction_validate`, and so
on) for writes. The CLI cannot access the database while that server holds the
connection -- DuckDB allows only one process to connect to a file at a time. Use the
CLI for standalone scripting or when the MCP server is not running.

**Orchestration.** If the task requires decomposition (e.g., "extract from these 5
papers and compare"), Claude Code uses its Agent tool to spawn subagents. Each subagent
gets precisely scoped context via `assemble_runner_context()`. The harness handles the
tree; FreudAgent provides the data.

Same schema. Same data. The harness orchestrates; FreudAgent provides data. That's the thesis.

## 7. Run extraction via the harness

Extraction happens through the harness (Claude Code, Agent SDK), not the CLI.
The provider infrastructure (`get_provider()`, `EchoProvider`, `ClaudeProvider`,
`OpenAICompatProvider`, `RLMProvider`) and context assembly (`assemble_runner_context()`)
are available as Python APIs for the harness to call.

In Claude Code, extraction is native: read the source, call the model, store results
via MCP tools. The same skill, rules, and source produce the same context regardless
of which harness orchestrates. The `fact_session` table records token counts and model
names, so provider comparisons accumulate automatically.

## 8. Review and validate

```bash
# List all extractions
uv run freud-schema extraction list

# Look at the real extraction (the second one, after echo) -- use its
# key or a unique prefix, e.g. 8d3a7e02
uv run freud-schema extraction show 8d3a7e02

# If it looks good
uv run freud-schema extraction validate 8d3a7e02 --by "your-name"

# If it's wrong
uv run freud-schema extraction reject 8d3a7e02 --by "your-name"
```

**Why validation is explicit:** The harness doesn't assume model output is
correct. Every extraction starts as `pending`. A human (or a second model, in
a more advanced setup) marks it `validated` or `rejected`. This creates a
labeled dataset: inputs (source + skill) paired with quality judgments. That's
the foundation for measuring whether declarative orchestration actually works.

## 9. Add feedback (close the flywheel)

Suppose the extraction missed the paper's stated limitations, or hallucinated
an author name. Feedback records what went wrong:

```bash
# The model missed a limitation
uv run freud-schema feedback add \
  --extraction-key 8d3a7e02 --type missing_field \
  --correction '{"field": "limitations_stated", "missing": "The paper notes that attention on very long sequences is computationally expensive."}' \
  --notes "Section 7 discusses this explicitly" \
  --by "your-name"

# The model got an author wrong
uv run freud-schema feedback add \
  --extraction-key 8d3a7e02 --type wrong_value \
  --correction '{"field": "authors", "was": "Ashish Vaswan", "should_be": "Ashish Vaswani"}' \
  --by "your-name"
```

**Why feedback is structured, not freeform:** Feedback has a `correction_type`
enum (`field_mapping`, `wrong_value`, `missing_field`, `false_positive`).
This isn't bureaucracy -- it's signal. When you aggregate feedback across many
extractions, patterns emerge:

```bash
uv run freud-schema feedback list --skill-key 9c1e4a7b --aggregate
```

If `missing_field` dominates, your skill instructions aren't explicit enough
about what to extract. If `wrong_value` dominates, the model is hallucinating
and you need stricter rules. If `false_positive` dominates, the skill is
over-extracting. The correction type tells you where to intervene.

**This is the flywheel:** feedback aggregation -> skill refinement -> re-run ->
better extractions -> less feedback. The database makes the loop measurable.

## 10. Try with a preset (archetype composition)

Presets compose Freudian archetypes into the system prompt, changing agent
behavior without changing the skill or rules. The harness passes the preset
name to `assemble_runner_context()` or calls `compose_preset()` directly.

```python
from freud_schema.harness import compose_preset

# Safety-first: censor-gate filters output, repetition-compulsion detects loops
prompt = compose_preset("careful-executor")

# Exploratory: free-association encourages lateral connections
prompt = compose_preset("creative-explorer")
```

Or via CLI for inspection:

```bash
uv run freud-schema prompt --preset careful-executor
uv run freud-schema prompt --preset creative-explorer
```

**Why archetypes matter for an experiment harness:** The thesis question is
whether declarative orchestration produces better results. Archetypes are one
axis of that experiment: does adding a "censor-gate" (which tells the model
to filter uncertain outputs) actually reduce hallucination? Does
"free-association" (which encourages exploring tangential connections) find
things a strict extractor misses? You can only answer these questions if the
behavior change is declarative (data in the prompt) rather than procedural
(different code paths). Compare the output of the two presets above --
the system prompt changes, but nothing else does.

## 11. Check the database state

```bash
uv run freud-schema db status
```

This shows row counts across all tables. After this tutorial, you should see:

- 3 rules
- 1 skill
- 1 source
- 2+ extractions (echo + real model)
- 1 session per extraction
- 1-2 feedback entries

Every row is a data point in the experiment. The schema isn't infrastructure.
It's the result.

---

## What to try next

- **Add more papers.** Register several arxiv sources and extract from all of
  them via the harness.

- **Write a v2 skill.** Based on feedback, write a better extraction prompt.
  Add it with `--version 2 --status active` -- v1 is superseded automatically
  (SCD-2), no separate deprecate step needed -- and re-run. Compare extractions.
  See the [flywheel tutorial](tutorial-flywheel.md) for a full walkthrough.

- **Compare providers.** Run the same skill against Claude and a local model.
  Use `session list` to compare token counts and check extractions for quality
  differences.

- **Add domain rules.** If arxiv papers need special handling (e.g., "Treat
  section numbers as hierarchical: 3.1 is a subsection of 3"), add a
  domain-specific rule instead of modifying the skill.

- **Query the database directly.** Use the store-ops MCP server's `query` tool or the CLI:
  ```bash
  uv run freud-schema db ddl | duckdb :memory:
  ```
