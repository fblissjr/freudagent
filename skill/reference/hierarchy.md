# Tree Architecture and Harness Mapping

How FreudAgent's data layer maps to tree-shaped agent architectures.

## The Core Idea

Agents are trees, not workflows. An orchestrator decomposes tasks, subagents get precisely
scoped context, do focused work, and return results up. The harness IS the orchestrator.
FreudAgent is the data layer that feeds the harness, not a mini-framework that reimplements
orchestration in Python.

```
            Harness (orchestrator)
           /         |          \
     subagent-1  subagent-2  subagent-3
     (skill A)   (skill B)   (skill C)
         |           |           |
     extraction  extraction  extraction
         \           |           /
          results flow back to schema
```

Every handoff is where it breaks. Pipelines (A -> B -> C) degrade context at each hop.
Trees return through the parent, preserving context integrity.

## Progressive Disclosure Per Subagent

Each subagent gets only what it needs, assembled by `assemble_runner_context()`:

| Layer | Content | Size |
|-------|---------|------|
| 0 (optional) | Archetype identity (preset) | Small -- behavioral constraints |
| 1 | Rules (global + domain) | Small -- constraints and policies |
| 2 | Skill (domain/task_type) | Medium -- the actual instructions |
| 3 | Sources (content references) | Variable -- what to process |
| Task | Parameters (what to do) | Small -- the specific ask |

The orchestrator (harness) sees the full task. Each subagent sees only its slice.
This is progressive disclosure at the execution level.

## How Claude Code Consumes FreudAgent

Claude Code IS the harness. FreudAgent lives inside it:

- **L1 (always loaded)**: CLAUDE.md positions FreudAgent as a data layer
- **L2 (loaded on match)**: `skill/skill.md` body -- CLI reference, workflow
- **L3 (loaded on demand)**: `skill/reference/*.md` -- schema, archetypes, hierarchy

Claude Code's own orchestration capabilities (Agent tool, multi-step reasoning,
file operations) handle decomposition and routing. FreudAgent provides:
- DuckDB schema via MCP tools for data access
- CLI for data management (`freud-schema skill add`, `source add`, etc.)
- Context assembly (`assemble_runner_context()`) for harness integration
- Archetype-composed system prompts for behavioral shaping

## How Agent SDK Would Consume FreudAgent

The 12 flywheel atoms (see `reference/flywheel.md`) map to Agent SDK primitives:

| SDK Primitive | Flywheel Atom | Example |
|---------------|---------------|---------|
| Agent | Pattern Detector, Skill Updater, Holdout Tester | Autonomous reasoning tasks |
| Tool | Context Assembly, Feedback Collection, Version Activation | Deterministic operations |
| Handoff | Phase transitions (Review -> Aggregation -> Evolution) | Controlled delegation |
| Human-in-the-loop | Quality Assessment, Correction Submission, Approval | Irreducibly human steps |

The Agent SDK becomes the harness. FreudAgent's schema, context assembly, and archetypes
feed it the same way they feed Claude Code -- as data, not as a wrapper.

## Why Not Workflows

Workflows encode routing in code: "after extraction, do validation, then aggregation."
This conflates context assembly (FreudAgent's job) with orchestration (the harness's job).

The tree architecture instead:
1. The harness decides what to decompose and how to route
2. FreudAgent provides the data each subagent needs
3. Results return through the parent, not sideways
4. The harness adapts routing based on results (not a fixed pipeline)

The meta-framework is inside the harness, not outside it.
