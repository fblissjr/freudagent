# Feedback Flywheel

How extractions become corrections become skill improvements.

## The Loop

```
extract -> review -> correct -> aggregate -> refine skill -> verify -> extract (improved)
```

The flywheel converts extraction errors into skill improvements. Each turn through
the loop makes the next extraction better. The signal is human corrections -- every
correction is a training signal.

## Current Implementation

What exists today in the schema:

1. **Extract**: `freud-schema run` produces extractions stored in the `extractions` table
2. **Review**: `freud-schema extraction show N` displays output for human review
3. **Correct**: `freud-schema feedback add` records typed corrections in the `feedback` table
4. **Aggregate**: `freud-schema feedback list --aggregate` shows correction patterns per skill

What does NOT exist yet:

5. **Refine**: No automated path from feedback patterns to skill updates
6. **Verify**: No holdout testing to measure whether refinement improved quality

## The 12 Atoms

The flywheel decomposes into 12 atoms across 4 phases (see `internal/flywheel_decomposition.json`):

### Phase 1: Human Review & Correction
- **1.1.1 Context Assembly** (tool): Load extraction, source, skill, prior corrections
- **1.1.2 Quality Assessment** (human): Field-by-field comparison against source
- **1.1.3 Correction Submission** (human): Typed correction with before/after per field

### Phase 2: Signal Aggregation
- **1.2.1 Feedback Collection** (tool): Query feedback grouped by correction_type
- **1.2.2 Pattern Detection** (agent): Identify recurring corrections, flag conflicts
- **1.2.3 Threshold Evaluation** (tool): Compare patterns against domain thresholds

### Phase 3: Skill Evolution
- **1.3.1 Update Synthesis** (agent): Draft skill changes from qualifying patterns
- **1.3.2 Human Approval** (human): Review proposed diff, approve/modify/reject
- **1.3.3 Version Activation** (tool): Create new skill version, deprecate old

### Phase 4: Impact Verification
- **1.4.1 Holdout Testing** (agent): Run new skill against validated extractions
- **1.4.2 Regression Detection** (agent): Compare accuracy vs previous version
- **1.4.3 Metric Recording** (tool): Write flywheel health metrics

## Correction Types

| Type | Meaning | Signal |
|------|---------|--------|
| field_mapping | Extracted to wrong field | Skill schema confusion |
| wrong_value | Value extracted incorrectly | Instruction gap |
| missing_field | Field not extracted | Skill needs expansion |
| false_positive | Non-existent data fabricated | Instruction needs constraint |

## Agent SDK Mapping

The 12 atoms map directly to Agent SDK primitives:

- **tool** atoms -> SDK tools (deterministic, no reasoning needed)
- **agent** atoms -> SDK agents (autonomous reasoning tasks)
- **human** atoms -> SDK human-in-the-loop (irreducibly human decisions)

Cross-phase dependencies become SDK handoffs. Early exit conditions (no corrections
needed, threshold not met) are branching logic in the orchestrator agent.

The flywheel IS the Agent SDK harness adapter.
