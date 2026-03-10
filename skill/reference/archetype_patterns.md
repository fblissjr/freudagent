# Archetype Patterns Reference

Detailed catalog of all 19 Freudian agentic archetypes with usage examples.

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

### topographic-hierarchy (Topographic Model)

**Pattern**: Context window tiering across memory hierarchy

Organize information by accessibility: active context (conscious),
on-demand references (preconscious), and database/file retrieval
(unconscious). Never promote bulk data to active context.

**When to use**: Any agent managing multiple information sources at
different levels of abstraction. Orchestrators coordinating tool calls.

**SDK example**:
```python
# Conscious: minimal coordination context in system prompt
# Preconscious: tool descriptions loaded by the SDK on demand
# Unconscious: database queries only when needed
result = await agent.run(
    "Find the relevant records",  # agent decides WHEN to query
    tools=[database_search, file_read],  # tools available, not pre-loaded
)
```

**Anti-pattern**: Loading entire database tables into the context window.
The unconscious should be queried precisely, not dumped into consciousness.

---

## Inter-Agent Architecture

### psychic-apparatus (Psychischer Apparat)

**Pattern**: Hierarchical orchestrator with ephemeral subagents

The psychic apparatus is a system of agencies, not a reflex arc. Agent
architecture should be a tree: orchestrator decomposes, subagents execute,
results return up. No agent-to-agent handoffs.

**When to use**: Multi-agent systems. Any architecture where tasks need
decomposition and delegation.

**SDK example**:
```python
# Tree topology: orchestrator delegates, results flow up
async def orchestrator(task: str):
    subtasks = decompose(task)
    results = []
    for subtask in subtasks:
        # Subagent gets only what it needs
        result = await subagent.run(subtask, context=minimal_context(subtask))
        results.append(result)
    return synthesize(results)
```

**Anti-pattern**: Pipeline architectures where Agent A hands off to Agent B
which hands off to Agent C. Context degrades at each hop. Always return
through the parent.

### dream-element (Traumelemente)

**Pattern**: Ephemeral subagent lifecycle

Subagents spin up with precise context, execute their task, and disappear.
No state preservation between invocations. Each activation is fresh.

**When to use**: Any subagent invocation. Default to ephemeral unless
there is a specific reason to persist state.

**SDK example**:
```python
# Each subagent is ephemeral -- no shared state
async def run_ephemeral(task: str, context: str) -> str:
    agent = Agent(
        model="claude-sonnet-4-6",
        system=compose_preset("minimal-safe", task_context=context),
    )
    result = await agent.run(task)
    # Agent is not stored. Output consumed. Agent disappears.
    return result.output
```

**Anti-pattern**: Persisting subagent state between invocations, leading
to context pollution and stale assumptions carrying forward.

---

## Retroactive Meaning

### nachtraglichkeit (Deferred Action)

**Pattern**: Progressive data refinement through feedback loops

Don't wait for perfect data. Use what you have, store structured outputs,
close the feedback loop. Each iteration retroactively gives meaning to
previous outputs.

**When to use**: Iterative workflows, data pipeline development, any
process where data quality improves through use rather than upfront
preparation.

**SDK example**:
```python
# Cycle 1: rough extraction
raw = await agent.run("Extract key entities from this document")
store(raw, version=1)

# Cycle 2: with human feedback, retroactively improves understanding
refined = await agent.run(
    f"Refine this extraction based on feedback: {feedback}",
    context=load(version=1),
)
store(refined, version=2)  # v1 now has meaning it didn't have before
```

**Anti-pattern**: Spending excessive time preparing "perfect" training data
before any use. The using IS the preparation.

### secondary-revision (Sekundare Bearbeitung)

**Pattern**: Context curation and narrative coherence

Before filling the context window, select, organize, and format for
maximum coherence. What enters matters more than how much. Preserve
structural semantics (visual layout carries weight).

**When to use**: Before any complex reasoning step. When assembling
context from multiple sources for a critical decision.

**Anti-pattern**: Indiscriminately concatenating all available context.
Condensation compresses; secondary-revision curates. Different operations.
