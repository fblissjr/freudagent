---
name: freud-schema
version: 0.2.0
description: Freudian psychoanalytic archetypes for Claude agent architecture
activation:
  - freud
  - psychoanalytic
  - archetype
  - agent architecture
  - structural model
  - id ego superego
  - dream-work
  - transference
  - repetition compulsion
scope:
  includes:
    - Agent system prompt generation from Freudian archetypes
    - Mapping psychoanalytic concepts to Claude Agent SDK patterns
    - Querying Freud's theoretical corpus (14 core entries)
    - Preset agent configurations (careful-executor, creative-explorer, etc.)
  excludes:
    - Actual psychology or any real-world advice (this is satirical)
    - General philosophy unrelated to agent design
---

# Freud Schema Skill

Maps Sigmund Freud's psychoanalytic theory to Claude Agent SDK patterns.

## What This Does

The Freud Schema provides **14 agentic archetypes** derived from psychoanalytic
concepts, organized into 6 categories:

| Category | Archetypes | Agent Pattern |
|----------|-----------|---------------|
| Architecture | structural-triad, censor-gate | Multi-layer agent design |
| Reasoning | condensation, displacement, free-association | Problem-solving strategies |
| Control Flow | repetition-compulsion, pleasure-reality, death-drive | Loop/termination control |
| Observation | resistance-detector, parapraxis-monitor | Debugging and failure analysis |
| Communication | transference, working-through | Context transfer and iteration |
| Resource Mgmt | cathexis, sublimation | Attention and task allocation |

## Quick Start

```python
from freud_schema.harness import compose_preset, compose_system_prompt

# Use a preset composition
prompt = compose_preset("careful-executor", task_context="Review this PR for bugs")

# Or pick specific archetypes
prompt = compose_system_prompt(
    ["structural-triad", "free-association", "death-drive"],
    task_context="Explore this codebase and summarize the architecture",
)
```

## Presets

- **careful-executor**: Safety-first agent with loop detection and graceful termination
- **creative-explorer**: Exploratory reasoning with resource awareness
- **iterative-refiner**: Feedback-driven refinement with bias detection
- **minimal-safe**: Lightweight safety baseline (3 archetypes)

## Reference

- `reference/archetype_patterns.md` — Full archetype catalog with examples
- `reference/translation_matrix.md` — German→English term mappings from Freud's originals
