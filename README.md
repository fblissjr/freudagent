# freudagent

Mostly a joke repo.

Satirical experiment and meta-harness for data-driven agent orchestration, grounded in an inside joke of
Freudian archetypes. Not a framework, but a satirical test bed for answering: "Does declarative
data-driven orchestration produce measurably better results than code-driven workflow approaches?"

But still mostly a joke repo. Becoming less so over time though. Weird.

## Prerequisites

- Python >= 3.10
- [uv](https://docs.astral.sh/uv/) (package manager)

## Setup

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh

git clone https://github.com/fblissjr/freudagent.git
cd freudagent
uv sync --extra dev
```

## Usage

### CLI -- Freud Corpus

```bash
# Query the Freud corpus (17 core entries)
uv run freud-schema list-topics
uv run freud-schema search "wish"
uv run freud-schema term "Id"
```

### CLI -- Archetypes and Prompts

```bash
# List all 9 archetypes
uv run freud-schema list-archetypes

# Show a specific archetype
uv run freud-schema archetype structural-triad
uv run freud-schema archetype dream-work

# Generate a system prompt from a preset
uv run freud-schema prompt --preset careful-executor
uv run freud-schema prompt --preset hierarchical-orchestrator

# Generate a prompt from specific archetypes with task context
uv run freud-schema prompt structural-triad free-association fixation \
  --task "Explore this codebase and summarize the architecture"
```

### CLI -- Experiment Harness

```bash
# Initialize the DuckDB schema
uv run freud-schema db init

# Check table counts
uv run freud-schema db status

# Register a skill
uv run freud-schema skill add \
  --domain legal --task-type extraction \
  --content "Extract party names and dates from contracts" \
  --status active

# Register a source
uv run freud-schema source add --path ./contracts/sample.pdf --media-type application/pdf

# Add a rule
uv run freud-schema rule add --content "Always preserve original formatting" --scope global

# List what you have
uv run freud-schema skill list
uv run freud-schema source list
uv run freud-schema rule list

# View feedback (the flywheel signal)
uv run freud-schema feedback --skill-id 1 --aggregate

# Nuclear option
uv run freud-schema db reset
```

### Python API

```python
from freud_schema.harness import compose_preset, compose_system_prompt
from freud_schema.archetypes import get_archetype, search_archetypes

# Use a preset composition
prompt = compose_preset("careful-executor", task_context="Review this PR for bugs")

# Tree-shaped orchestrator with ephemeral subagents
prompt = compose_preset(
    "hierarchical-orchestrator",
    task_context="Decompose and execute a multi-step refactor",
)

# Pick specific archetypes
prompt = compose_system_prompt(
    ["structural-triad", "free-association", "fixation"],
    task_context="Explore this codebase",
)

# Look up individual archetypes
a = get_archetype("repetition-compulsion")
print(a.prompt_fragment)
```

## Archetypes (9, in a 3x3 grid)

| Category | Archetypes | Pattern |
|----------|-----------|---------|
| Structural | structural-triad, censor-gate, ephemeral | How agents are built |
| Behavioral | repetition-compulsion, pleasure-principle, dream-work | How agents decide |
| Diagnostic | free-association, freudian-slip, fixation | How agents explore and self-correct |

**Intra-agent** archetypes (e.g. `structural-triad`) define roles within a
single agent. **Inter-agent** archetypes (e.g. `ephemeral`) define topology
and lifecycle between agents.

## Presets (5)

| Preset | Archetypes | Use Case |
|--------|-----------|----------|
| `careful-executor` | structural-triad, censor-gate, repetition-compulsion, freudian-slip, pleasure-principle | Safety-first with loop detection |
| `creative-explorer` | free-association, dream-work, fixation | Exploratory reasoning |
| `iterative-refiner` | dream-work, pleasure-principle, freudian-slip | Feedback-driven refinement |
| `minimal-safe` | structural-triad, repetition-compulsion, pleasure-principle | Lightweight safety baseline |
| `hierarchical-orchestrator` | ephemeral, dream-work, fixation, pleasure-principle | Tree-shaped orchestrator with ephemeral subagents |

## Experiment Harness

The big addition. A 6-table DuckDB schema implementing declarative agent
orchestration: behavior comes from data (skills, rules, sources), not code.
The orchestrator is a thin loop. Model calls are pluggable -- pass any callable.

Subagents get context via the progressive disclosure hierarchy:
**rules -> skill -> source -> task**.

| Table | Purpose |
|-------|---------|
| `skills` | Declarative instructions loaded at runtime (domain + task_type + version) |
| `sources` | Raw artifacts to process (file paths, MIME types, metadata) |
| `extractions` | Structured output from agent runs (with validation status) |
| `sessions` | Logged agent executions (orchestrator + subagent, token tracking) |
| `feedback` | Human corrections on extractions (the flywheel signal) |
| `rules` | Constraints applied globally or per-domain (priority-ordered) |

## Project Structure

```
src/freud_schema/
  models.py          - Pydantic models (FreudEntry, AgenticArchetype)
  archetypes.py      - Registry of 9 agentic archetypes (3x3 grid)
  harness.py         - Meta-harness for composing system prompts
  dataset.py         - JSONL data loading and querying
  cli.py             - CLI interface
  db.py              - DuckDB schema (6 tables) and connection management
  tables.py          - Pydantic models for experiment harness tables
  store.py           - CRUD operations and retrieval queries
  orchestrator.py    - Thin orchestrator loop + subagent runner
data/
  freud_schema.jsonl - 17 core entries from Freud's works
  freudagent.duckdb  - Experiment database (gitignored)
skill/
  skill.md           - Claude Code skill definition
  reference/         - Archetype patterns, translation matrix
```

## Development

```bash
uv sync --extra dev
uv run pytest tests/ -v
```

Dependencies: pydantic >= 2.0, duckdb >= 0.9, orjson >= 3.9.

## License

MIT
