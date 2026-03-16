# Retrieval Thesis

FreudAgent is a reference implementation of progressive disclosure applied to agent
orchestration. The L1/L2/L3 hierarchy isn't an organizational convenience -- it's the
core architectural claim: skills are retrieval, not configuration.

## Skills as Retrieval

Context windows are attention, not memory. Loading everything into context is cheap in
tokens but expensive in precision -- the model attends to irrelevant material, diluting
focus. Loading too little is cheap in attention but expensive in recall -- the model lacks
what it needs.

The constraint is precision (only relevant context). The goal is recall (everything needed).
FreudAgent's progressive disclosure hierarchy resolves this tension: L1 gives the minimum
always-needed context, L2 loads on routing match, L3 loads on explicit demand.

See `reference/context-assembly.md` for how `assemble_runner_context()` implements this
as a concrete function.

## FreudAgent Demonstrates Its Own Thesis

FreudAgent's own skill directory is a working example of the L1/L2/L3 hierarchy:

- **L1**: `CLAUDE.md` -- always loaded by Claude Code. Positions FreudAgent, lists key
  conventions, and names the core files. Small enough to always be present.
- **L2**: `skill/skill.md` -- loaded when activation keywords match. Contains the CLI
  reference and a routing table that points to L3 references. Medium-sized, loaded by
  routing decision.
- **L3**: `skill/reference/*.md` -- loaded on demand when deeper context is needed.
  Schema details, archetype specifications, flywheel decomposition. Large in aggregate,
  but only one or two are loaded per task.

The skill directory IS the thesis. The fact that you're reading this file (L3) because
something routed you here (L2) because a keyword matched (L1) is the proof.

See `reference/hierarchy.md` for how this maps to tree-shaped agent architectures.

## The Schema as Controlled Retrieval

The DuckDB schema maps directly to progressive disclosure levels:

| Level | Schema Element | When Loaded |
|-------|---------------|-------------|
| L1 | `rules` | Always -- global and domain constraints |
| L2 | `skills` | On routing -- matched by domain + task_type |
| L3 | `sources`, `extractions`, `feedback` | On demand -- per execution |

Rules are L1 because they're constraints that apply regardless of task. Skills are L2
because they're selected by a routing decision (which domain, which task type). Sources,
extractions, and feedback are L3 because they're specific to a particular execution --
you only load them when you're actually doing the work.

See `reference/schema.md` for the full table schema and enum definitions.

## Inside the Harness, Not Outside

FreudAgent provides data; the harness orchestrates. This is more durable than wrapping
the harness because the data layer survives harness changes. The same schema, skills,
rules, and context assembly feed Claude Code today, could feed the Agent SDK tomorrow,
and could feed a local inference stack after that.

Building inside means FreudAgent's retrieval hierarchy composes with the harness's own
retrieval (Claude Code's skill system, Agent SDK's tool routing). Building outside means
competing with it.

See `reference/hierarchy.md` for the concrete harness mapping table.
