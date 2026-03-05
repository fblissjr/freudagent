# freudagent

If Freud designed LLMs and agents...

A satirical experiment in agent architecture, born from pure curiosity: what if
we mapped Sigmund Freud's theoretical concepts to Claude Agent SDK patterns?

**This is not a serious psychology project.** It's a playful exploration of
whether century-old psychoanalytic metaphors can produce genuinely useful
patterns for structuring AI agents. (Spoiler: some of them actually do.)

## Prerequisites

- Python >= 3.10
- [uv](https://docs.astral.sh/uv/) (recommended package manager)

## Setup

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and install
git clone https://github.com/fblissjr/freudagent.git
cd freudagent
uv sync --extra dev
```

## Usage

### CLI

```bash
# Query the Freud corpus (14 core entries)
uv run freud-schema list-topics
uv run freud-schema search "wish"
uv run freud-schema term "Id"

# List all 14 agentic archetypes
uv run freud-schema list-archetypes

# Show a specific archetype
uv run freud-schema archetype structural-triad

# Generate a system prompt from a preset
uv run freud-schema prompt --preset careful-executor

# Generate a prompt from specific archetypes with task context
uv run freud-schema prompt structural-triad free-association death-drive \
  --task "Explore this codebase and summarize the architecture"
```

### Python API

```python
from freud_schema.harness import compose_preset, compose_system_prompt
from freud_schema.archetypes import get_archetype, search_archetypes

# Use a preset composition
prompt = compose_preset("careful-executor", task_context="Review this PR for bugs")

# Pick specific archetypes
prompt = compose_system_prompt(
    ["structural-triad", "free-association", "death-drive"],
    task_context="Explore this codebase",
)

# Look up individual archetypes
a = get_archetype("repetition-compulsion")
print(a.prompt_fragment)
```

## Presets

| Preset | Archetypes | Use Case |
|--------|-----------|----------|
| `careful-executor` | structural-triad, censor-gate, repetition-compulsion, resistance-detector, death-drive | Safety-first with loop detection |
| `creative-explorer` | free-association, condensation, displacement, cathexis, sublimation | Exploratory reasoning |
| `iterative-refiner` | working-through, pleasure-reality, transference, parapraxis-monitor | Feedback-driven refinement |
| `minimal-safe` | structural-triad, repetition-compulsion, death-drive | Lightweight safety baseline |

## Project Structure

```
src/freud_schema/
  models.py      - Pydantic models (FreudEntry, AgenticArchetype, ArchetypeCategory)
  archetypes.py  - Registry of 14 agentic archetypes
  harness.py     - Meta-harness for composing system prompts
  dataset.py     - JSONL data loading and querying
  cli.py         - CLI interface
data/
  freud_schema.jsonl - 14 core entries from Freud's works
skill/
  skill.md       - Claude Code skill definition
  reference/     - Archetype patterns, translation matrix
```

## Development

```bash
# Run tests
uv run pytest tests/ -v

# Install in editable mode
uv pip install -e ".[dev]"
```

## License

MIT
