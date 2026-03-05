# FreudAgent

Psychoanalytic archetypes for Claude agent architecture.

## Project Structure

```
src/freud_schema/
  models.py      - Pydantic models (FreudEntry, AgenticArchetype)
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

- Python >= 3.10, Pydantic >= 2.0
- Package manager: **uv** (always use `uv run`, `uv sync`, `uv pip`)
- Tests: `uv run pytest tests/`
- Install: `uv sync --extra dev`

## Conventions

- Models use Pydantic v2 (`model_validate`, `model_dump`)
- Data stored as JSONL (one JSON object per line)
- Archetype names use kebab-case: `structural-triad`, `death-drive`
- Categories use the `ArchetypeCategory` enum

## Key Concepts

The **meta-harness** (`harness.py`) composes archetype prompt fragments into
complete system prompts. Use presets for common patterns:

- `careful-executor` — safety-first with loop detection
- `creative-explorer` — exploratory reasoning
- `iterative-refiner` — feedback-driven refinement
- `minimal-safe` — lightweight safety baseline
