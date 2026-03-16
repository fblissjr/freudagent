# Archetypes and Presets

The 9 Freudian agentic archetypes in a 3x3 grid, plus 6 presets for composing them.

## The 3x3 Grid

| Category | Archetypes | Pattern |
|----------|-----------|---------|
| **Structural** | structural-triad, censor-gate, ephemeral | How agents are built |
| **Behavioral** | repetition-compulsion, pleasure-principle, dream-work | How agents decide |
| **Diagnostic** | free-association, freudian-slip, fixation | How agents explore and self-correct |

### Structural (How Agents Are Built)

- **structural-triad** (Id/Ego/Superego): Three-layer architecture. Id generates raw impulses,
  Ego mediates, Superego enforces constraints.
- **censor-gate** (Dream Censorship): Pre-execution filter. Transforms unsafe requests into
  safe alternatives -- doesn't just block.
- **ephemeral** (Dream Elements + Psychic Apparatus): Tree topology with ephemeral subagents.
  Spin up, do focused work, disappear. No sideways handoffs.

### Behavioral (How Agents Decide)

- **repetition-compulsion** (Wiederholungszwang): Loop detection. If the same approach fails
  twice, change strategy fundamentally.
- **pleasure-principle** (Pleasure/Reality/Death Drive): Greedy vs optimal routing with
  graceful termination. Simple queries get fast responses. Done means stop.
- **dream-work** (Condensation + Displacement + Revision): Compress, redirect, curate.
  Three transformation stages as one pipeline.

### Diagnostic (How Agents Explore and Self-Correct)

- **free-association** (Freie Assoziation): Exploratory chain-of-thought. Generate hypotheses
  before committing to a solution.
- **freudian-slip** (Parapraxes + Resistance): Unexpected outputs and persistent failures
  are diagnostic signals, not noise.
- **fixation** (Cathexis + Sublimation): Invest context window deliberately. When blocked,
  redirect to the closest productive alternative.

## Presets (6 Compositions)

| Preset | Archetypes | Use When |
|--------|-----------|----------|
| careful-executor | structural-triad, censor-gate, repetition-compulsion, freudian-slip, pleasure-principle | Extraction tasks needing precision |
| creative-explorer | free-association, dream-work, fixation | Open-ended analysis |
| iterative-refiner | dream-work, pleasure-principle, freudian-slip | Tasks with feedback to incorporate |
| minimal-safe | structural-triad, repetition-compulsion, pleasure-principle | Simple tasks, low overhead |
| hierarchical-orchestrator | ephemeral, dream-work, fixation, pleasure-principle | Multi-step decomposition |
| recursive-decomposer | dream-work, free-association, fixation, pleasure-principle | RLM: condensation, exploration, attention, completion |

## How Presets Flow Into Execution

```python
# Context assembly with preset
system_prompt, user_message = assemble_runner_context(
    store, skill_id=1, source_ids=[1, 2], preset="careful-executor"
)
# system_prompt now contains:
#   - Archetype fragments (from preset)
#   - Rules (from DB)
#   - Skill instructions (from DB)
```

The preset shapes behavioral constraints. The skill provides task-specific instructions.
Rules add universal constraints. All three compose into a single system prompt.

## Prompt Composition

`compose_system_prompt()` in `harness.py` renders archetypes grouped by category:

```
# Operating Principles (Freudian Archetypes)

## Structural
### structural-triad (Id / Ego / Superego)
[prompt fragment]

## Behavioral
### repetition-compulsion (Wiederholungszwang)
[prompt fragment]
```

For detailed archetype patterns and examples, see `archetype_patterns.md`.
For German-English translation context, see `translation_matrix.md`.
