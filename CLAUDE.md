# FreudAgent

Mostly a joke repo.

Satirical experiment and meta-harness for data-driven agent orchestration, grounded in an inside joke of
Freudian archetypes. Not a framework, but a satirical test bed for answering: "Does declarative
data-driven orchestration produce measurably better results than code-driven workflow approaches?"

But still mostly a joke repo. Becoming less so over time though. Weird.

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
internal/            - Analysis docs (gitignored)
```

## Development

- Python >= 3.10, Pydantic >= 2.0, DuckDB >= 0.9, orjson >= 3.9
- Package manager: **uv** (always use `uv run`, `uv sync`, `uv pip`)
- Tests: `uv run pytest tests/`
- Install: `uv sync --extra dev`

## Conventions

- Models use Pydantic v2 (`model_validate`, `model_dump`)
- List fields use `Field(default_factory=list)`, never bare `[]` defaults
- Data stored as JSONL (one JSON object per line) for Freud corpus
- Experiment data stored in DuckDB (6-table schema)
- JSON serialization: **orjson** (not json)
- Archetype names use kebab-case: `structural-triad`, `dream-work`
- Categories use the `ArchetypeCategory` enum (3 categories: STRUCTURAL, BEHAVIORAL, DIAGNOSTIC)
- `related_archetypes` must be bidirectional: if A lists B, B must list A
- Tests use a module-scoped `entries` fixture for JSONL data (no repeated `load_entries()` calls)
- Experiment tests use in-memory DuckDB (`:memory:`)
- No phantom dependencies -- only add to `pyproject.toml` what the code actually imports

## Archetypes (9, in a 3x3 grid)

| Category | Archetypes | Pattern |
|----------|-----------|---------|
| Structural | structural-triad, censor-gate, ephemeral | How agents are built |
| Behavioral | repetition-compulsion, pleasure-principle, dream-work | How agents decide |
| Diagnostic | free-association, freudian-slip, fixation | How agents explore and self-correct |

## Presets (5)

- `careful-executor` -- safety-first with loop detection and termination
- `creative-explorer` -- exploratory reasoning with resource awareness
- `iterative-refiner` -- feedback-driven refinement with diagnostic analysis
- `minimal-safe` -- lightweight safety baseline
- `hierarchical-orchestrator` -- tree-shaped orchestrator with ephemeral subagents

## Experiment Harness (6-table schema)

The harness implements declarative agent orchestration: behavior comes from data
(skills, rules, sources), not code. The schema is the architecture.

| Table | Purpose |
|-------|---------|
| skills | Declarative instructions loaded at runtime (domain + task_type + version) |
| sources | Raw artifacts to process (file paths, MIME types, metadata) |
| extractions | Structured output from agent runs (with validation status) |
| sessions | Logged agent executions (orchestrator + subagent, token tracking) |
| feedback | Human corrections on extractions (the flywheel signal) |
| rules | Constraints applied globally or per-domain (priority-ordered) |

CLI: `freud-schema db init`, `freud-schema skill add/list`, `freud-schema source add/list`,
`freud-schema rule add/list`, `freud-schema feedback --skill-id N --aggregate`

## Architecture Notes

Archetypes span two scopes:
- **Intra-agent** (`structural-triad`): roles within a single agent
- **Inter-agent** (`ephemeral`): hierarchical topology and ephemeral subagent lifecycle

The orchestrator uses archetype-composed system prompts for its own behavior.
Subagents use the progressive disclosure hierarchy: rules -> skill -> source -> task.
Model calls are pluggable (pass any callable). The code is a thin loop; behavior is data.
