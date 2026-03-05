# Archetype Patterns Reference

Detailed catalog of all 14 Freudian agentic archetypes with usage examples.

## Architecture

### structural-triad (Id / Ego / Superego)

**Pattern**: Three-layer agent architecture

The Id generates raw impulses (unconstrained tool calls). The Ego mediates
between impulse and reality (the orchestrator agent). The Superego enforces
constraints and policies (guardrails, system prompts).

**When to use**: Any agent that needs to balance capability with safety.
This is the foundational pattern—most agents benefit from some version of it.

**SDK example**:
```python
# The "Id" — an unconstrained sub-agent that proposes actions
proposal = await id_agent.run("What tool calls would solve this?")

# The "Ego" — the orchestrator that evaluates feasibility
plan = await ego_agent.run(f"Evaluate this proposal: {proposal}")

# The "Superego" — guardrails that enforce policy
validated = await superego_agent.run(f"Check this plan for safety: {plan}")
```

### censor-gate (Dream Censorship / Repression)

**Pattern**: Pre-execution filter or guardrail agent

Just as the dream-censor transforms forbidden wishes before they reach
consciousness, a guardrail agent filters or transforms tool calls before
execution.

**When to use**: Before any destructive or irreversible operation.

**Anti-pattern**: Simply blocking unsafe requests. The censor *transforms*—
it finds a safe version of the intent, not just a "no."

---

## Reasoning

### condensation (Verdichtung)

**Pattern**: Multi-source synthesis into single output

Dreams compress multiple latent thoughts into a single manifest image.
Agents compress information from multiple sources into one coherent response.

**When to use**: After gathering information from multiple tool calls or
sub-agents. The condensation step produces the final synthesis.

### displacement (Verschiebung)

**Pattern**: Indirect problem-solving via proxy tasks

When blocked on a direct approach, redirect effort to a proxy task that
achieves the same underlying goal through an alternative path.

**When to use**: When direct approaches fail repeatedly. Instead of retrying,
shift to an alternative that achieves the same underlying goal.

### free-association (Freie Assoziation)

**Pattern**: Exploratory chain-of-thought with branching

Explore the problem space freely before committing to a solution.
Generate multiple hypotheses, follow unexpected connections.

**When to use**: Open-ended exploration tasks, architecture discovery,
root cause analysis where the problem structure is unclear.

---

## Control Flow

### repetition-compulsion (Wiederholungszwang)

**Pattern**: Loop detection and circuit-breaker patterns

If you attempt the same approach more than twice without progress, stop and
fundamentally change strategy. Repetition without insight is compulsion.

**When to use**: Any agent that uses retry logic. This is the guard against
infinite loops.

**Anti-pattern**: Retrying the exact same failing command with no change.

### pleasure-reality (Lust-/Realitätsprinzip)

**Pattern**: Greedy vs. optimal decision-making

Balance speed against thoroughness. Simple queries get fast responses.
Complex or high-stakes tasks get careful verification.

**When to use**: Routing decisions—should the agent respond quickly or
invest in thorough analysis?

### death-drive (Thanatos)

**Pattern**: Graceful termination and resource cleanup

When the task is complete, stop. Do not continue generating output,
exploring tangents, or performing unnecessary work.

**When to use**: Every agent. Knowing when to stop is as important as
knowing what to do.

---

## Observation

### resistance-detector (Widerstand)

**Pattern**: Failure analysis and debugging patterns

The pattern of what fails reveals the structure of the problem. Analyze
errors structurally rather than simply retrying.

**When to use**: When debugging, when tests fail repeatedly, when an
agent is "stuck."

### parapraxis-monitor (Fehlleistungen)

**Pattern**: Unexpected output analysis

Unexpected outputs reveal misalignment between intent and execution.
Investigate the gap rather than suppressing the unexpected output.

**When to use**: When agent outputs are surprising or wrong in
patterned ways.

---

## Communication

### transference (Übertragung)

**Pattern**: Context transfer between agent sessions

When receiving context from a previous session or another agent, treat
it as potentially biased by its source. Verify transferred assumptions.

**When to use**: Multi-session workflows, agent handoffs, context
window rotation.

### working-through (Durcharbeiten)

**Pattern**: Iterative refinement with human feedback

A first solution is rarely the final one. Present work, incorporate
feedback, and refine iteratively.

**When to use**: Any task where quality matters more than speed.
Code review, document drafting, architecture design.

---

## Resource Management

### cathexis (Besetzung)

**Pattern**: Attention and resource allocation

Allocate attention deliberately. Invest deeply in relevant sources,
withdraw from tangential exploration. Context window is finite.

**When to use**: Long tasks where context window management matters.
Research tasks with many potential sources.

### sublimation

**Pattern**: Task redirection to productive alternatives

If a request cannot be fulfilled directly, redirect toward the closest
productive alternative that serves the user's underlying need.

**When to use**: When safety constraints or capability limits prevent
direct fulfillment. Transform constraints into opportunities.
