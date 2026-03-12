---
name: freud-schema
version: 0.4.0
description: Freudian psychoanalytic archetypes for Claude agent architecture
activation:
  - freud
  - psychoanalytic
  - archetype
  - agent architecture
  - structural model
  - id ego superego
  - dream-work
  - repetition compulsion
  - hierarchical
  - orchestrator
  - ephemeral
  - freudian slip
  - fixation
  - pleasure principle
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

The Freud Schema provides **9 agentic archetypes** derived from psychoanalytic
concepts, organized into a 3x3 grid across 3 categories:

| Category | Archetypes | Agent Pattern |
|----------|-----------|---------------|
| Structural | structural-triad, censor-gate, ephemeral | Multi-layer architecture + hierarchical topology |
| Behavioral | repetition-compulsion, pleasure-principle, dream-work | Loop control, routing, transformation |
| Diagnostic | free-association, freudian-slip, fixation | Exploration, failure analysis, attention allocation |

## Quick Start

```python
from freud_schema.harness import compose_preset, compose_system_prompt

# Use a preset composition
prompt = compose_preset("careful-executor", task_context="Review this PR for bugs")

# Or pick specific archetypes
prompt = compose_system_prompt(
    ["structural-triad", "free-association", "pleasure-principle"],
    task_context="Explore this codebase and summarize the architecture",
)
```

## Presets

- **careful-executor**: Safety-first agent with loop detection and graceful termination
- **creative-explorer**: Exploratory reasoning with resource awareness
- **iterative-refiner**: Feedback-driven refinement with diagnostic analysis
- **minimal-safe**: Lightweight safety baseline (3 archetypes)
- **hierarchical-orchestrator**: Tree-shaped orchestrator with ephemeral subagents
- **progressive-refiner**: Feedback-loop driven refinement with failure analysis

## Reference

- `reference/archetype_patterns.md` -- Full archetype catalog with examples
- `reference/translation_matrix.md` -- German->English term mappings from Freud's originals
