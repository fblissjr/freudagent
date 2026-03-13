---
name: freud-schema
version: 0.7.0
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
    - Running extractions against sources with archetype-composed prompts
    - Querying Freud's theoretical corpus (17 core entries)
    - Generating agent system prompts from Freudian archetypes
    - Reviewing and validating extraction output
    - Closing the feedback loop with corrections
  excludes:
    - Actual psychology or any real-world advice (this is satirical)
    - General philosophy unrelated to agent design
    - Direct model API calls (the harness handles execution natively)
---

# FreudAgent Data Layer

FreudAgent is a harness-agnostic data layer for declarative agent orchestration. It provides
schema, archetypes, and context assembly that get loaded INTO whichever runtime is appropriate.
When used as a Claude Code skill, Claude Code IS the harness -- FreudAgent feeds it data,
Claude Code handles execution natively.

## How This Works Inside Claude Code

Claude Code is one of several harnesses FreudAgent supports. The key principle: FreudAgent
never wraps Claude Code. Instead, Claude Code reads from the schema and uses its own native
capabilities (Agent tool, file operations, reasoning) for execution.

The workflow:
1. **Read** skills, rules, and sources from DuckDB via CLI
2. **Compose** archetype-informed context using presets
3. **Execute** using Claude Code's native capabilities (not a model API call)
4. **Store** results back as extractions via CLI
5. **Review** and provide feedback to close the flywheel loop

## CLI Reference

All commands use `freud-schema` (or `uv run freud-schema`). The `--db` flag is global
(before the subcommand) and defaults to `data/freudagent.duckdb`.

### Setup

```bash
# Initialize the database
freud-schema db init

# Check status
freud-schema db status
```

### Data Management

```bash
# Add rules (loaded into every run's system prompt)
freud-schema rule add --content "Output valid JSON" --priority 10
freud-schema rule add --content "Use ISO dates" --scope domain-specific --domain insurance

# Add skills (domain-specific instructions)
freud-schema skill add --domain insurance --task-type extraction \
  --content "Extract policy number, effective date, and named insureds." \
  --status active

# Or load skill content from a file
freud-schema skill add --domain legal --task-type extraction \
  --file ./skills/legal_extraction.txt --status active

# Register sources
freud-schema source add --path /data/policy_001.pdf --media-type application/pdf

# List what's in the database
freud-schema rule list
freud-schema skill list
freud-schema source list
```

### Running Extractions

```bash
# Run with echo model (shows assembled context, no API call)
freud-schema run --domain insurance --task-type extraction --model echo

# Run with archetype preset (composes Freudian system prompt)
freud-schema run --domain insurance --task-type extraction --preset careful-executor --model echo

# Target specific sources
freud-schema run --domain insurance --task-type extraction --source-id 1 --source-id 3
```

### Review and Feedback

```bash
# List extractions
freud-schema extraction list
freud-schema extraction list --status pending

# Show extraction details
freud-schema extraction show 1

# Validate or reject
freud-schema extraction validate 1
freud-schema extraction reject 2

# Add feedback (closes the flywheel loop)
freud-schema feedback add --extraction-id 1 --type wrong_value \
  --correction '{"field": "effective_date", "before": "2026-01-01", "after": "2026-03-01"}'

# View feedback patterns
freud-schema feedback list --skill-id 1 --aggregate
```

### Archetypes and Presets

```bash
# List archetypes
freud-schema list-archetypes

# Show archetype details
freud-schema archetype structural-triad

# List presets
freud-schema list-presets

# Generate a system prompt from a preset
freud-schema prompt --preset careful-executor

# Generate from specific archetypes
freud-schema prompt structural-triad free-association --task "Review this extraction"
```

### Session History

```bash
freud-schema session list
freud-schema session list --status completed
```

## Presets (Archetype Compositions)

Each preset selects a combination of Freudian archetypes that shape the agent's system prompt:

| Preset | Behavior | Use When |
|--------|----------|----------|
| careful-executor | Safety-first with loop detection | Extraction tasks needing precision |
| creative-explorer | Exploratory reasoning | Open-ended analysis, codebase exploration |
| iterative-refiner | Feedback-driven refinement | Tasks with existing feedback to incorporate |
| minimal-safe | Lightweight safety baseline | Simple tasks, low overhead |
| hierarchical-orchestrator | Tree-shaped coordination | Multi-step tasks with subtask decomposition |

## Archetypes (9, 3x3 Grid)

| Category | Archetypes | Pattern |
|----------|-----------|---------|
| Structural | structural-triad, censor-gate, ephemeral | How agents are built |
| Behavioral | repetition-compulsion, pleasure-principle, dream-work | How agents decide |
| Diagnostic | free-association, freudian-slip, fixation | How agents explore and self-correct |

## Corpus

17 entries from Freud's major works, searchable by topic, book, terminology, and full text:

```bash
freud-schema list-topics
freud-schema search "dream"
freud-schema term "condensation"
```
