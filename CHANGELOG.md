# Changelog

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
