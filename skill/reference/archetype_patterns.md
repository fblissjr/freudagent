# Archetype Patterns Reference

Detailed catalog of all 9 Freudian agentic archetypes with usage examples.

## Structural (How Agents Are Built)

### structural-triad (Id / Ego / Superego)

**Pattern**: Three-layer agent architecture

The Id generates raw impulses (unconstrained tool calls). The Ego mediates
between impulse and reality (the orchestrator agent). The Superego enforces
constraints and policies (guardrails, system prompts).

**When to use**: Any agent that needs to balance capability with safety.
This is the foundational pattern -- most agents benefit from some version of it.

**SDK example**:
```python
# The "Id" -- an unconstrained sub-agent that proposes actions
proposal = await id_agent.run("What tool calls would solve this?")

# The "Ego" -- the orchestrator that evaluates feasibility
plan = await ego_agent.run(f"Evaluate this proposal: {proposal}")

# The "Superego" -- guardrails that enforce policy
validated = await superego_agent.run(f"Check this plan for safety: {plan}")
```

### censor-gate (Dream Censorship / Repression)

**Pattern**: Pre-execution filter or guardrail agent

Just as the dream-censor transforms forbidden wishes before they reach
consciousness, a guardrail agent filters or transforms tool calls before
execution.

**When to use**: Before any destructive or irreversible operation.

**Anti-pattern**: Simply blocking unsafe requests. The censor *transforms* --
it finds a safe version of the intent, not just a "no."

### ephemeral (Dream Elements / Psychic Apparatus)

**Pattern**: Ephemeral subagent lifecycle with hierarchical topology

**Merges**: dream-element (ephemeral lifecycle) + psychic-apparatus (tree topology)

Agent architecture should be a tree, not a pipeline: the orchestrator
decomposes tasks, subagents execute with minimal context, results return up.
Subagents spin up, do focused work, and disappear. No state corruption from
unnecessary persistence. No sideways handoffs.

**When to use**: Multi-agent systems. Any architecture where tasks need
decomposition and delegation with process isolation.

**SDK example**:
```python
# Tree topology: orchestrator delegates, results flow up
async def orchestrator(task: str):
    subtasks = decompose(task)
    results = []
    for subtask in subtasks:
        # Subagent is ephemeral -- gets only what it needs
        agent = Agent(
            model="claude-sonnet-4-6",
            system=compose_preset("minimal-safe", task_context=subtask),
        )
        result = await agent.run(subtask)
        results.append(result.output)
        # Agent is not stored. Output consumed. Agent disappears.
    return synthesize(results)
```

**Anti-pattern**: Pipeline architectures where Agent A hands off to Agent B
which hands off to Agent C. Context degrades at each hop. Always return
through the parent.

---

## Behavioral (How Agents Decide)

### repetition-compulsion (Wiederholungszwang)

**Pattern**: Loop detection and circuit-breaker patterns

If you attempt the same approach more than twice without progress, stop and
fundamentally change strategy. Repetition without insight is compulsion.

**When to use**: Any agent that uses retry logic. This is the guard against
infinite loops.

**Anti-pattern**: Retrying the exact same failing command with no change.

### pleasure-principle (Pleasure / Reality / Death Drive)

**Pattern**: Greedy vs optimal routing with graceful termination

**Merges**: pleasure-reality (speed vs thoroughness) + death-drive (graceful termination)

Balance speed against thoroughness. Simple queries get fast responses.
Complex or high-stakes tasks get careful verification. And when the task
is complete, stop -- do not continue generating output, exploring tangents,
or performing unnecessary work.

**When to use**: Every routing decision (fast vs thorough) and every task
completion check (done vs keep going).

### dream-work (Condensation + Displacement + Secondary Revision)

**Pattern**: Compression, redirection, and curation pipeline

**Merges**: condensation (compress) + displacement (redirect) + secondary-revision (curate)

Three dream-work operations as one transformation pipeline:
1. **Compress**: Synthesize multi-source inputs into single dense output
2. **Redirect**: If direct approach is blocked, shift to a proxy task
3. **Curate**: Select, organize, and format context for maximum coherence

**When to use**: After gathering information from multiple sources. When
direct approaches fail. Before any complex reasoning step.

**Anti-pattern**: Indiscriminately concatenating all available context.
Curate first, then compress.

---

## Diagnostic (How Agents Explore and Self-Correct)

### free-association (Freie Assoziation)

**Pattern**: Exploratory chain-of-thought with branching

Explore the problem space freely before committing to a solution.
Generate multiple hypotheses, follow unexpected connections.

**When to use**: Open-ended exploration tasks, architecture discovery,
root cause analysis where the problem structure is unclear.

### freudian-slip (Parapraxes / Resistance)

**Pattern**: Unexpected output and failure analysis

**Merges**: parapraxis-monitor (unexpected outputs) + resistance-detector (structural failures)

Unexpected outputs reveal misalignment between intent and execution.
Persistent failures reveal the structure of the problem. Both are diagnostic
signals, not noise.

**When to use**: When agent outputs are surprising or wrong in patterned ways.
When debugging. When tests fail repeatedly. When an agent is "stuck."

**Anti-pattern**: Suppressing unexpected outputs or simply retrying failures
without analysis.

### fixation (Cathexis / Sublimation)

**Pattern**: Attention allocation with productive redirection

**Merges**: cathexis (attention investment) + sublimation (productive redirection)

Context window is finite -- invest it deliberately. When blocked, redirect
toward the closest productive alternative rather than persisting.

**When to use**: Long tasks where context window management matters. When
safety constraints or capability limits prevent direct fulfillment.

**Anti-pattern**: Loading entire database tables into the context window.
The unconscious should be queried precisely, not dumped into consciousness.

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
