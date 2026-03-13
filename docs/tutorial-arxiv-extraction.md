# Tutorial: Extracting structured data from an arxiv paper

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
do that. The 7-table schema (skills, sources, extractions, sessions, feedback,
rules, meta_schema_version) isn't plumbing -- it's the experiment itself.

**Why `init` is separate from `run`:** You set up the database once, then run
many experiments against it. The schema is idempotent (`CREATE TABLE IF NOT
EXISTS`), so running `init` again is safe.

## 2. Add rules

Rules are constraints that apply across all tasks. They get injected into every
model call as the first layer of context.

```bash
uv run freud-schema rule add \
  --content "Output valid JSON. No markdown fences, no commentary outside the JSON object." \
  --scope global --priority 10

uv run freud-schema rule add \
  --content "Never fabricate data. If a field cannot be determined from the source, use null." \
  --scope global --priority 9

uv run freud-schema rule add \
  --content "Use exact quotes from the paper when populating 'key_quote' fields." \
  --scope domain-specific --domain arxiv --priority 5
```

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
You write a v2 skill that fixes it, mark v1 as deprecated, and re-run. The
database tracks which skill version produced which extraction, so you can
measure whether v2 actually improved things. This is the "flywheel" the
project keeps referencing: extract -> review -> correct -> refine skill ->
re-extract.

**Why `--status active`:** Skills start as `draft` by default. Only `active`
skills are picked up by the orchestrator. This prevents half-written
instructions from accidentally running.

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

**Why the harness doesn't read the file:** This is an intentional gap (see
`internal/BACKLOG.md` under "Source content ingestion"). The orchestrator
currently passes source metadata (path, MIME type) to the model, but doesn't
read the file contents. With Claude Code or Agent SDK as the actual runtime,
the harness assembles context and the runtime handles file reading. For the
echo provider (next step), this doesn't matter -- you're verifying the
pipeline, not the extraction.

Verify:

```bash
uv run freud-schema source list
```

## 5. Run with echo (verify the pipeline)

Before spending API calls or GPU cycles, verify that the pipeline assembles
context correctly.

```bash
uv run freud-schema run --domain arxiv --task-type extraction
```

**Why echo first:** The echo provider returns the exact system prompt and user
message that a real model would receive. If your rules are missing, your skill
is malformed, or your source didn't register, you'll see it in the echo output
-- for free, in milliseconds. This is the same principle as a dry run or a
`--whatif` flag, but it produces a real database record so you can inspect the
full session.

The output will be a JSON object showing the assembled context:

```json
{
  "model": "echo",
  "system_prompt": "# Rules\n\n- Output valid JSON...\n\n# Skill: arxiv / extraction (v1)\n\nYou are extracting...",
  "user_message": "<source id=\"1\" type=\"application/pdf\" path=\"data/papers/attention-is-all-you-need.pdf\" />\nExecute extraction task."
}
```

Look for:
- Are all 3 rules present in the system prompt?
- Is the skill content there, in full?
- Is the source reference in the user message?

## 6. Inspect what happened

```bash
# See the extraction record
uv run freud-schema extraction list

# See the full output
uv run freud-schema extraction show 1

# See the session log (orchestrator + subagent)
uv run freud-schema session list
```

**Why sessions exist:** Every run creates at least two sessions: one
`orchestrator` (the coordination layer) and one or more `subagent` (the
actual work). Sessions track status (running/completed/failed), which skill
was used, what context was loaded, token usage, and the model that actually
responded. This is how you answer "what happened?" after the fact, and how
you compare providers (did the local model use fewer tokens? did it fail
more often?).

## 7. Run with a real model

Pick one:

```bash
# Claude API (requires ANTHROPIC_API_KEY in environment)
uv run freud-schema run --domain arxiv --task-type extraction --model anthropic

# Local OpenAI-compatible server (heylookitsanllm, llama.cpp, vLLM, Ollama)
uv run freud-schema run --domain arxiv --task-type extraction \
  --model local --model-name qwen2.5-coder-1.5b --endpoint http://localhost:8080
```

**Why multiple providers:** The experiment harness is provider-agnostic by
design. The same skill, rules, and source produce the same context regardless
of whether Claude, a local model, or echo processes it. This lets you compare:
does Claude's extraction outperform a 1.5B local model? By how much? At what
cost? The `sessions` table records token counts and model names from the actual
response, so the data for that comparison accumulates automatically.

**Why `--model-name` is separate from `--model`:** `--model` selects the
provider (the transport layer: Anthropic SDK, httpx, or echo). `--model-name`
selects the specific model within that provider. For Anthropic, it defaults to
`claude-sonnet-4-6`. For local, it's whatever your server is running.

## 8. Review and validate

```bash
# List all extractions
uv run freud-schema extraction list

# Look at the real extraction (the second one, after echo)
uv run freud-schema extraction show 2

# If it looks good
uv run freud-schema extraction validate 2 --by "your-name"

# If it's wrong
uv run freud-schema extraction reject 2 --by "your-name"
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
  --extraction-id 2 --type missing_field \
  --correction '{"field": "limitations_stated", "missing": "The paper notes that attention on very long sequences is computationally expensive."}' \
  --notes "Section 7 discusses this explicitly" \
  --by "your-name"

# The model got an author wrong
uv run freud-schema feedback add \
  --extraction-id 2 --type wrong_value \
  --correction '{"field": "authors", "was": "Ashish Vaswan", "should_be": "Ashish Vaswani"}' \
  --by "your-name"
```

**Why feedback is structured, not freeform:** Feedback has a `correction_type`
enum (`field_mapping`, `wrong_value`, `missing_field`, `false_positive`).
This isn't bureaucracy -- it's signal. When you aggregate feedback across many
extractions, patterns emerge:

```bash
uv run freud-schema feedback list --skill-id 1 --aggregate
```

If `missing_field` dominates, your skill instructions aren't explicit enough
about what to extract. If `wrong_value` dominates, the model is hallucinating
and you need stricter rules. If `false_positive` dominates, the skill is
over-extracting. The correction type tells you where to intervene.

**This is the flywheel:** feedback aggregation -> skill refinement -> re-run ->
better extractions -> less feedback. The database makes the loop measurable.

## 10. Try with a preset (archetype composition)

Presets compose Freudian archetypes into the system prompt, changing agent
behavior without changing the skill or rules.

```bash
# Safety-first: censor-gate filters output, repetition-compulsion detects loops
uv run freud-schema run --domain arxiv --task-type extraction \
  --model echo --preset careful-executor

# Exploratory: free-association encourages lateral connections
uv run freud-schema run --domain arxiv --task-type extraction \
  --model echo --preset creative-explorer
```

**Why archetypes matter for an experiment harness:** The thesis question is
whether declarative orchestration produces better results. Archetypes are one
axis of that experiment: does adding a "censor-gate" (which tells the model
to filter uncertain outputs) actually reduce hallucination? Does
"free-association" (which encourages exploring tangential connections) find
things a strict extractor misses? You can only answer these questions if the
behavior change is declarative (data in the prompt) rather than procedural
(different code paths). Compare the echo output of the two presets above --
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
- 2+ sessions per extraction (orchestrator + subagent each)
- 1-2 feedback entries

Every row is a data point in the experiment. The schema isn't infrastructure.
It's the result.

---

## What to try next

- **Add more papers.** Register several arxiv sources and run against all of
  them at once (omit `--source-id` to process all active sources).

- **Write a v2 skill.** Based on feedback, write a better extraction prompt.
  Add it as a new skill (same domain/task-type, version 2, status active),
  deprecate v1, and re-run. Compare extractions.

- **Compare providers.** Run the same skill against Claude and a local model.
  Use `session list` to compare token counts and check extractions for quality
  differences.

- **Add domain rules.** If arxiv papers need special handling (e.g., "Treat
  section numbers as hierarchical: 3.1 is a subsection of 3"), add a
  domain-specific rule instead of modifying the skill.

- **Query the database directly.** Use the DuckDB MCP tools or the CLI:
  ```bash
  uv run freud-schema db ddl | duckdb :memory:
  ```
