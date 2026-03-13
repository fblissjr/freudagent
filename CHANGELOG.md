# Changelog

## 0.7.0

### Added

- **Archetype preset wiring**: archetypes are no longer decorative -- they flow into execution
  - `--preset` flag on `freud-schema run` composes archetype system prompt into context
  - `assemble_runner_context()` accepts optional `preset` param
  - `run_simple()` and `run_task()` propagate preset through the full pipeline
  - `freud-schema run --domain D --task-type T --preset careful-executor --model echo` shows archetypes in output
- **Skill rewrite**: `skill/skill.md` rewritten as a Claude Code data layer skill
  - Documents full CLI workflow: setup, data management, extraction, review, feedback
  - Reflects harness-agnostic architecture (FreudAgent feeds the harness, doesn't wrap it)
- 4 new tests: preset context assembly, preset in run_simple, no-preset baseline, invalid preset error

### Changed

- Backlog rewritten to reflect multi-harness north star and the inside/outside architectural pivot
  - Identifies orchestrator.py's API wrapper as the wrong pattern
  - Documents Provider protocol design (not implemented)
  - Documents harness adapter designs: Claude Code skill, Agent SDK workflow, MLX local
  - References flywheel decomposition JSON for Agent SDK mapping

## 0.6.1

### Added

- **Schema versioning**: `meta_schema_version` table tracks applied schema versions
  - Idempotent migration infrastructure (`_MIGRATIONS` list in `db.py`)
  - `get_schema_version()` query function
  - `db status` now displays current schema version
  - Pattern adopted from agent-state: replaces destructive-only schema evolution with safe, incremental migrations

## 0.6.0

### Added

- **`run` command**: Execute the orchestrator against database contents
  - `freud-schema run --domain D --task-type T` processes all active sources
  - `--source-id N` (repeatable) to target specific sources
  - `--model echo` (default) shows assembled context for pipeline verification
  - `--model anthropic` calls Claude API (requires `anthropic` SDK)
  - `--task` for additional task context
- **`extraction` commands**: `list`, `show`, `validate`, `reject`
- **`session list`**: View execution history (orchestrator + subagent sessions)
- **`feedback add`**: Close the flywheel loop with corrections on extractions
  - `--extraction-id`, `--type`, `--correction` (JSON), `--notes`, `--by`
- `EchoModel` -- built-in model for pipeline verification without API keys
- `get_model()` factory for model callables (echo, anthropic)
- `run_simple()` -- convenience function: skill + sources -> extractions
- 7 new tests for EchoModel, get_model, run_simple, end-to-end echo pipeline

### Changed

- `--db` moved from per-subparser to global root argument (all commands now use same DB)
- `feedback` CLI restructured to use subparsers: `feedback list` (was top-level), `feedback add` (new)
  - Old: `freud-schema feedback --skill-id 1 --aggregate`
  - New: `freud-schema feedback list --skill-id 1 --aggregate`
- `EchoModel` returns compact JSON; display layer handles formatting (eliminates double serialize)
- N+1 source lookups in `_handle_run` and `extraction list` replaced with bulk fetch + map
- Extracted `_print_json()` helper for duplicated JSON display logic
- `feedback add` uses `args.extraction_id` directly instead of `ext.id` (type-safe)

## 0.5.0

### Added

- **Experiment harness**: 6-table DuckDB schema for declarative agent orchestration
  - `skills` -- domain-specific instructions loaded at runtime
  - `sources` -- raw artifacts (file paths, MIME types)
  - `extractions` -- structured output with validation status
  - `sessions` -- logged agent executions with token tracking
  - `feedback` -- human corrections (the flywheel signal)
  - `rules` -- global and domain-specific constraints
- `db.py` -- DuckDB connection management and schema DDL
- `tables.py` -- Pydantic models for all 6 tables + TaskPlan/Subtask
- `store.py` -- ExperimentStore with typed CRUD operations, retrieval queries, feedback aggregation
- `orchestrator.py` -- Thin orchestrator loop + subagent runner with pluggable model calls
  - `assemble_runner_context()` -- progressive disclosure hierarchy (rules -> skill -> source -> task)
  - `run_subtask()` -- execute a single subtask with context assembly and session logging
  - `run_task()` -- process a TaskPlan respecting dependency order
- CLI commands: `db init|reset|status`, `skill add|list`, `source add|list`, `rule add|list`, `feedback`
- 18 new tests for schema, store CRUD, context assembly, orchestrator, and error handling
- DuckDB files added to .gitignore

### Changed

- Merged `progressive-refiner` preset into `iterative-refiner` (identical after archetype simplification)
- Presets reduced from 6 to 5
- CLI `export` command now uses orjson instead of json
- pyproject.toml: added duckdb, orjson dependencies; bumped to 0.5.0; updated description

## 0.4.0

### Changed

- **Aggressive archetype simplification: 19 -> 9** in a clean 3x3 grid
- ArchetypeCategory enum reduced from 6 categories to 3: STRUCTURAL, BEHAVIORAL, DIAGNOSTIC
- All 6 presets updated to reference new archetype names

### Added

- `ephemeral` archetype (merges `dream-element` + `psychic-apparatus`)
- `pleasure-principle` archetype (merges `pleasure-reality` + `death-drive`)
- `dream-work` archetype (merges `condensation` + `displacement` + `secondary-revision`)
- `freudian-slip` archetype (merges `parapraxis-monitor` + `resistance-detector`)
- `fixation` archetype (merges `cathexis` + `sublimation`)
- Tests for merged archetypes (verify each merge captures source concepts)
- 3x3 grid test (3 categories, 3 archetypes each)

### Removed

- 10 archetypes absorbed into merges or cut entirely
- Cut entirely (concepts absorbed into system-level design, not individual archetypes):
  `nachtraglichkeit`, `working-through`, `transference`, `topographic-hierarchy`
- Merged away: `condensation`, `displacement`, `secondary-revision`, `dream-element`,
  `psychic-apparatus`, `pleasure-reality`, `death-drive`, `parapraxis-monitor`,
  `resistance-detector`, `cathexis`, `sublimation`
- 3 obsolete ArchetypeCategory values: OBSERVATION, COMMUNICATION, RESOURCE_MANAGEMENT

## 0.3.1

### Changed

- Updated README.md to reflect current state: 19 archetypes, 17 entries, 6 presets
- Added architectural scopes section (intra-agent vs inter-agent)
- Added `hierarchical-orchestrator` and `progressive-refiner` to preset table
- Added `related_archetypes` usage and new preset examples to Python API section

## 0.3.0

### Added

- 5 new archetypes (14 -> 19): `psychic-apparatus`, `topographic-hierarchy`, `dream-element`, `nachtraglichkeit`, `secondary-revision`
- `related_archetypes` field on `AgenticArchetype` model (backward-compatible, default empty list)
- 3 new JSONL entries (14 -> 17): Interpretation of Dreams Ch. VII, Project for a Scientific Psychology, Letter 52/Mystic Writing Pad
- 2 new presets: `hierarchical-orchestrator`, `progressive-refiner`
- 5 new translation matrix entries: Nachtraglichkeit, Sekundare Bearbeitung, Bahnung, Wunderblock, Psychischer Apparat
- Archetype pattern reference entries for all 5 new archetypes
- Tests for new archetypes, presets, related_archetypes validation, and new JSONL entries

### Changed

- Updated `cathexis` description to reference RAM hierarchy and precise investment over diffuse attention
- Updated `structural-triad` description to clarify intra-agent scope vs `psychic-apparatus` inter-agent scope
- Skill activation keywords expanded (hierarchical, orchestrator, ephemeral, context tiering, nachtraglichkeit, topographic)
- `related_archetypes` enforced as bidirectional: `condensation`, `death-drive`, `working-through` now reference back to their counterparts
- `search_archetypes` now searches `prompt_fragment` in addition to other text fields
- CLAUDE.md updated to reflect current counts and presets

### Fixed

- Stray character in `pyproject.toml` dev dependencies
- Unused `json` import in `dataset.py`
- Removed phantom `duckdb` dependency (declared but never imported)
- Inconsistent mutable defaults on `FreudEntry` (`[]` -> `Field(default_factory=list)`)
- Redundant test functions (`test_new_archetypes_exist`, `test_new_presets`) merged into existing tests
- Repeated `load_entries()` disk reads in tests replaced with module-scoped fixture

## 0.2.0

- Initial agentic overlay: 14 archetypes, 4 presets, meta-harness, CLI

## 0.1.0

- Core schema: 14 JSONL entries, Pydantic models, dataset queries
