---
name: freud-schema
version: 0.24.0
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

Last updated: 2026-07-09

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
(before the subcommand) and defaults to `data/freudagent.duckdb`. `--tenant` is also
global and defaults to `default`; it scopes the four tenant-keyed dims (skills, rules,
sources, sampling configs) and `compile` -- omitting it preserves single-tenant behavior.

> **If DuckDB MCP is available (Claude Code sessions):** Prefer `mcp__duckdb__execute_query`
> over CLI commands for all database operations. DuckDB is single-process -- the MCP server
> holds the connection, so CLI commands that touch the DB will fail with a lock error.
> CLI commands that don't open a connection (corpus queries, archetype/preset commands,
> `db ddl`) still work.

Keys are sha256/32 hashes (`keys.dimension_key()`), not integers -- every command that
takes an entity reference (skill, source, rule, extraction, feedback, session,
trace) accepts a full key or a unique prefix, git-short-hash style, resolved via
`store.resolve_key()`. An ambiguous or non-matching prefix exits with an error.

### Data Management

```bash
freud-schema db init                          # Create tables
freud-schema db status                        # Show row counts
freud-schema db reset                         # Drop and recreate all tables (destructive)
freud-schema rule add --name always-json --content "..." --priority 10
freud-schema skill add --domain D --task-type T --content "..." --status active [--version N]
freud-schema source add --path /data/doc.pdf --media-type application/pdf [--hash]
```

`rule add` requires `--name` -- it doubles as the rule's stable identity and the
future compile target filename (`.claude/rules/<name>.md`).

### Review and Feedback

```bash
freud-schema extraction list [--status pending]
freud-schema extraction show <key-or-prefix>
freud-schema extraction validate <key-or-prefix>
freud-schema feedback add --extraction-key <key-or-prefix> --type wrong_value --correction '{...}'
freud-schema feedback list --skill-key <key-or-prefix> --aggregate
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
freud-schema skill deprecate <key-or-prefix>
freud-schema skill activate <key-or-prefix>
```

### Session History

```bash
freud-schema session list [--status completed]
freud-schema session show <key-or-prefix>
```

### Transcript Ingestion (sense)

```bash
freud-schema ingest transcripts                        # everything under the Claude Code projects dir
freud-schema ingest transcripts --project freudagent   # one project (substring match)
freud-schema ingest transcripts --since 2026-07-01     # incremental by file mtime
```

Idempotent by key construction: re-running against unchanged files writes zero
rows (verify via `meta_load_log`). Root sessions ingest as orchestrator, nested
subagents link to their parents with agentType/description from `.meta.json`
sidecars. This is a CLI-time operation -- it needs the database lock, so run it
when the DuckDB MCP server is not connected, or ingest to a separate file and
`ATTACH` it from the MCP session.

### The Couch (analyze)

```bash
freud-schema couch run                  # deterministic detectors -> fact_finding (no model calls)
freud-schema couch run --warehouse-only  # skip filesystem detectors (stale_source)
freud-schema couch list [--type retry_loop]
```

Detects retry loops, tool error clusters, interruption hotspots, and
permission friction, with evidence session keys attached; plus stale
sources (registered via `source add --hash`) whose file content changed
since their baseline -- a hybrid detector that reads the filesystem, so
`--warehouse-only` skips it where the corpus is absent. The LLM layer
(user-correction patterns) runs inside Claude Code -- see the `/couch`
project skill.

### Evolve and Materialize

```bash
freud-schema proposal add --target dim_rule \
    --natural-key '{"name": "no-retry-loops"}' \
    --content "..." --evidence <finding-key>,<finding-key>
freud-schema proposal list [--status pending]
freud-schema proposal show <key-or-prefix>
freud-schema proposal approve <key-or-prefix> [--by NAME]   # creates the SCD-2 version
freud-schema proposal reject <key-or-prefix> [--by NAME]
freud-schema compile --out .claude/rules [--scope global]
```

Approval is the one human atom -- nothing auto-applies. `compile` renders
current active rules to `<name>.md` with a do-not-edit header, a source
line, and a provenance footer naming the approving proposal and its
findings. The privacy gate is fail-closed: files containing home paths or
the OS username are blocked, and the last good compile survives.
Rollback: `store.rollback_dimension()` then recompile.

## Corpus

17 entries from Freud's major works, searchable by topic, book, terminology, and full text:

```bash
freud-schema list-topics
freud-schema search "dream"
freud-schema term "condensation"
```
