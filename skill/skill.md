---
name: freud-schema
version: 0.3.0
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
  - hierarchical
  - orchestrator
  - ephemeral
  - context tiering
  - nachtraglichkeit
  - topographic
scope:
  includes:
    - Agent system prompt generation from Freudian archetypes
    - Mapping psychoanalytic concepts to Claude Agent SDK patterns
    - Querying Freud's theoretical corpus (17 core entries)
    - Preset agent configurations (careful-executor, hierarchical-orchestrator, etc.)
  excludes:
    - Actual psychology or any real-world advice (this is satirical)
    - General philosophy unrelated to agent design
---

# Freud Schema Skill

Maps Sigmund Freud's psychoanalytic theory to Claude Agent SDK patterns.

## What This Does

The Freud Schema provides **19 agentic archetypes** derived from psychoanalytic
concepts, organized into 6 categories:

| Category | Archetypes | Agent Pattern |
|----------|-----------|---------------|
| Architecture | structural-triad, censor-gate, psychic-apparatus | Multi-layer + inter-agent topology |
| Reasoning | condensation, displacement, free-association, secondary-revision | Problem-solving and context curation |
| Control Flow | repetition-compulsion, pleasure-reality, death-drive, dream-element | Loop/termination/ephemeral lifecycle |
| Observation | resistance-detector, parapraxis-monitor | Debugging and failure analysis |
| Communication | transference, working-through, nachtraglichkeit | Context transfer, iteration, deferred meaning |
| Resource Mgmt | cathexis, sublimation, topographic-hierarchy | Attention allocation and memory tiering |

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
- **hierarchical-orchestrator**: Tree-shaped orchestrator with ephemeral subagents and memory tiering
- **progressive-refiner**: Feedback-loop driven refinement with retroactive meaning (nachtraglichkeit)

## Reference

- `reference/archetype_patterns.md` — Full archetype catalog with examples
- `reference/translation_matrix.md` — German→English term mappings from Freud's originals
