---
name: freud-schema
version: 0.16.1
description: Data layer for declarative agent orchestration -- schema, archetypes, and context assembly loaded into any harness
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
  - extraction
  - experiment harness
  - skill management
  - feedback flywheel
scope:
  includes:
    - Managing skills, rules, sources, and feedback in the experiment harness
    - Providing context assembly and provider abstractions for harness integration
    - Querying Freud's theoretical corpus (17 core entries)
    - Generating agent system prompts from Freudian archetypes
    - Reviewing and validating extraction output
    - Closing the feedback loop with corrections
  excludes:
    - Actual psychology or any real-world advice (this is satirical)
    - General philosophy unrelated to agent design
    - Orchestration (task decomposition, routing, looping -- the harness's job)
---

# FreudAgent Data Layer

FreudAgent is a pure data layer for declarative agent orchestration. It provides schema,
context assembly, archetypes, and prompt composition that get loaded INTO whichever harness
is running. The harness (Claude Code, Agent SDK, local inference) handles orchestration.
FreudAgent handles data.

## When to Load Which Reference

| Working with... | Load |
|-----------------|------|
| DuckDB schema, tables, queries | `reference/schema.md` |
| Archetypes, presets, prompt composition | `reference/archetypes.md` |
| Understanding the tree architecture | `reference/hierarchy.md` |
| Context assembly, progressive disclosure | `reference/context-assembly.md` |
| Feedback loop, flywheel atoms | `reference/flywheel.md` |
| Archetype usage patterns and examples | `reference/archetype_patterns.md` |
| German-English translation nuances | `reference/translation_matrix.md` |
| Retrieval thesis, progressive disclosure rationale | `reference/retrieval-thesis.md` |

## CLI Reference

All commands use `freud-schema` (or `uv run freud-schema`). The `--db` flag is global
(before the subcommand) and defaults to `data/freudagent.duckdb`.

> **If DuckDB MCP is available (Claude Code sessions):** Prefer `mcp__duckdb__execute_query`
> over CLI commands for all database operations. DuckDB is single-process -- the MCP server
> holds the connection, so CLI commands that touch the DB will fail with a lock error.
> CLI commands that don't open a connection (corpus queries, archetype/preset commands,
> `db ddl`) still work.

### Data Management

```bash
freud-schema db init                          # Create tables
freud-schema db status                        # Show row counts
freud-schema rule add --content "..." --priority 10
freud-schema skill add --domain D --task-type T --content "..." --status active [--version N]
freud-schema source add --path /data/doc.pdf --media-type application/pdf
```

### Review and Feedback

```bash
freud-schema extraction list [--status pending]
freud-schema extraction show N
freud-schema extraction validate N
freud-schema feedback add --extraction-id N --type wrong_value --correction '{...}'
freud-schema feedback list --skill-id N --aggregate
```

### Archetypes and Prompts

```bash
freud-schema list-archetypes
freud-schema archetype structural-triad
freud-schema list-presets
freud-schema prompt --preset careful-executor
```

### Skill Lifecycle

```bash
freud-schema skill deprecate <id>
freud-schema skill activate <id>
```

### Session History

```bash
freud-schema session list [--status completed]
freud-schema session show <id>
```

## Corpus

17 entries from Freud's major works, searchable by topic, book, terminology, and full text:

```bash
freud-schema list-topics
freud-schema search "dream"
freud-schema term "condensation"
```
