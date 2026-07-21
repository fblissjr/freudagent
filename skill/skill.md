---
name: freud-schema
version: 0.37.0
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

Last updated: 2026-07-21

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
| Feedback loop, the six stages, signal quality | `reference/flywheel.md` |
| Archetype usage patterns and examples | `reference/archetype_patterns.md` |
| German-English translation nuances | `reference/translation_matrix.md` |
| Retrieval thesis, progressive disclosure rationale | `reference/retrieval-thesis.md` |
| What a reasoning trace should contain (capture path unbuilt) | `reference/trace-capture.md` |

## CLI Reference

All commands use `freud-schema` (or `uv run freud-schema`). The `--db` flag is global
(before the subcommand) and defaults to `data/freudagent.duckdb`. `--tenant` is also
global and defaults to `default`; it scopes the four tenant-keyed dims (skills, rules,
sources, sampling configs) and `compile` -- omitting it preserves single-tenant behavior.

> **If an MCP server is connected (Claude Code sessions):** DuckDB is single-process --
> whichever server holds the connection, `freud-schema` CLI commands that touch the DB
> will fail with a lock error. CLI commands that don't open a connection (corpus queries,
> archetype/preset commands, `db ddl`) still work regardless.
>
> Prefer the **store-ops server** (`freud-schema mcp-serve`, configured in `.mcp.json`,
> implementation plan M16): its `query` tool covers reads, and every write goes through
> a gated tool (`rule_add`, `skill_add`, `source_add`, `feedback_add`,
> `feedback_origin_add`, `finding_add`,
> `extraction_validate`/`reject`, `proposal_add`/`reject`, `couch_run`, `compile`,
> `ingest_transcripts`, `ingest_events`) instead of a CLI write-window toggle.
> `proposal_approve` is never allowlisted -- every approval surfaces the permission
> prompt by design. If the session is instead connected to a generic `duckdb` MCP
> server, use `mcp__duckdb__execute_query` for reads and fall back to a CLI write
> window for writes.

Keys are sha256/32 hashes (`keys.dimension_key()`), not integers -- every command that
takes an entity reference (skill, extraction, proposal, session, trace) accepts a
full key or a unique prefix, git-short-hash style, resolved via
`store.resolve_key()`. An ambiguous or non-matching prefix exits with an error.
No command takes a source, rule, or feedback key today.

### Data Management

```bash
freud-schema db init                          # Create tables
freud-schema db status                        # Show row counts
freud-schema db reset                         # Drop and recreate all tables (destructive)
freud-schema rule add --name always-json --content "..." --priority 10
freud-schema skill add --domain D --task-type T --content "..." --status active [--version N]
freud-schema source add --path /data/doc.pdf --media-type application/pdf [--no-hash]
freud-schema origin add --id owner --kind human      # what produces feedback
freud-schema origin list
```

Source hashing is on by default; `--no-hash` opts out. The `stale_source`
detector SKIPS sources with no baseline, so an unhashed source is invisible to
it rather than merely unmonitored.

`origin` registers what produces a judgment. `origin_id` is open vocabulary (a
person, a model version, an upstream system); `--kind` is a closed set --
human, model, usage_signal, downstream_system, unspecified -- because filters
are written against it. Feedback recorded without an origin is labeled
`unspecified`, never `human`, so an unattributed row cannot land in the
human-only slice.

`rule add` requires `--name` -- it doubles as the rule's stable identity and the
future compile target filename (`.claude/rules/<name>.md`).

### Review and Feedback

```bash
freud-schema extraction list [--status pending]
freud-schema extraction show <key-or-prefix>
freud-schema extraction validate <key-or-prefix>
freud-schema feedback add --extraction-key <key-or-prefix> --type wrong_value --correction '{...}' [--origin owner]
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

### Transcript Ingestion

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

### Generic Event Ingestion (M5)

```bash
freud-schema ingest events --root ./events                # everything under a JSONL events root
freud-schema ingest events --root ./events --since 2026-07-01
```

Any non-transcript source ingests through the same idempotent, lineage-stamped
path: `IngestAdapter` (`discover()` + `parse()`, `ingest.py`) is the protocol,
`JsonlEventAdapter` is the reference implementation -- one stream per `*.jsonl`
file under `--root`, one JSON object per line (`{id, type, timestamp, actor,
payload}` plus an optional `text`). Rows land in `fact_event`; distinct event
types auto-register in `dim_event_type` (open vocabulary, same pattern as
`finding_type`). `--stream-type` is reserved for future multi-adapter
selection. In-session, use the store-ops `ingest_events` tool instead of the
CLI (same lock rule as `ingest_transcripts`).

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

### Propose, approve and compile

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

Approval is the one step only a person can do -- nothing auto-applies. `compile` renders
current active rules to `<name>.md` with a do-not-edit header, a source
line, and a provenance footer naming the approving proposal and its
findings. The privacy gate is fail-closed: files containing home paths or
the OS username are blocked, and the last good compile survives.
Rollback: `store.rollback_dimension()` then recompile.

### Store-Ops MCP Server

```bash
freud-schema mcp-serve                # stdio; needs uv sync --extra mcp
```

The in-session write surface (implementation plan M16). `cli.py` and
`mcp_server.py` both call the same `ops.py` dispatch functions, so CLI and
MCP behavior cannot drift. The server holds the single DuckDB connection
for the session -- configure it once in `.mcp.json` (already committed)
instead of the generic `duckdb` MCP server. Gate design: `rule_add`/
`skill_add` always create the non-compiling status (rules: `inactive`,
skills: `draft`) no matter what status is requested; the only path to
activation is `proposal_add` -> `proposal_approve`, and `proposal_approve`
must never be allowlisted -- every approval surfaces the permission
prompt. No tool exposes `db reset`, `db ddl`, or raw writes.

## Corpus

17 entries from Freud's major works, searchable by topic, book, terminology, and full text:

```bash
freud-schema list-topics
freud-schema search "dream"
freud-schema term "condensation"
```
