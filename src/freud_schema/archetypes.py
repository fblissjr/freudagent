"""Registry of agentic archetypes derived from Freudian psychoanalytic theory.

Each archetype maps a Freudian concept to a concrete Claude Agent SDK pattern,
providing both the theoretical grounding and a reusable prompt fragment.

Simplified from 19 to 9 archetypes in a 3x3 grid:
    STRUCTURAL  (how agents are built):  structural-triad, censor-gate, ephemeral
    BEHAVIORAL  (how agents decide):     repetition-compulsion, pleasure-principle, dream-work
    DIAGNOSTIC  (how agents explore):    free-association, freudian-slip, fixation
"""

from __future__ import annotations

from freud_schema.models import AgenticArchetype, ArchetypeCategory

# ---------------------------------------------------------------------------
# The canonical archetype registry (9 archetypes, 3 categories)
# ---------------------------------------------------------------------------

ARCHETYPES: list[AgenticArchetype] = [
    # ---- STRUCTURAL: how agents are built ----
    AgenticArchetype(
        name="structural-triad",
        freudian_concept="Id / Ego / Superego",
        sdk_pattern="Three-layer agent architecture",
        category=ArchetypeCategory.STRUCTURAL,
        description=(
            "The Id generates raw impulses (unconstrained tool calls). "
            "The Ego mediates between impulse and reality (the orchestrator agent). "
            "The Superego enforces constraints and policies (guardrails, system prompts). "
            "This is an intra-agent pattern: three roles within one agent. "
            "For inter-agent topology, see ephemeral."
        ),
        prompt_fragment=(
            "You operate as a tripartite system: an impulse layer proposes actions, "
            "a reasoning layer evaluates feasibility, and a constraint layer enforces "
            "safety boundaries. No action bypasses all three."
        ),
        related_archetypes=["censor-gate", "ephemeral"],
    ),
    AgenticArchetype(
        name="censor-gate",
        freudian_concept="Dream Censorship / Repression",
        sdk_pattern="Pre-execution filter or guardrail agent",
        category=ArchetypeCategory.STRUCTURAL,
        description=(
            "Just as the dream-censor transforms forbidden wishes before they reach "
            "consciousness, a guardrail agent filters or transforms tool calls before "
            "execution, blocking unsafe operations while allowing modified safe versions."
        ),
        prompt_fragment=(
            "Before executing any action, pass it through a censorship layer that "
            "evaluates safety, reversibility, and scope. Transform unsafe requests "
            "into safe approximations rather than simply blocking them."
        ),
        related_archetypes=["structural-triad"],
    ),
    AgenticArchetype(
        name="ephemeral",
        freudian_concept="Dream Elements / Psychic Apparatus",
        sdk_pattern="Ephemeral subagent lifecycle with hierarchical topology",
        category=ArchetypeCategory.STRUCTURAL,
        description=(
            "Merges two Freudian ideas: dream elements (ephemeral, dissolving on waking) "
            "and the psychic apparatus (a system of agencies, not a reflex arc). "
            "Agent architecture should be a tree, not a pipeline: the orchestrator "
            "decomposes tasks, subagents execute with minimal context, results return up. "
            "Subagents spin up, do focused work, and disappear. No state corruption from "
            "unnecessary persistence. No sideways handoffs between subagents."
        ),
        prompt_fragment=(
            "Decompose complex tasks into subtasks and delegate to specialized "
            "subagents. Each subagent receives only the context it needs, executes, "
            "and disappears. Results flow back up through you -- never sideways between "
            "subagents. You are the tree's root, not a node in a pipeline. "
            "Do not preserve subagent state between invocations. Each activation is "
            "fresh -- like a dream element that exists only for the duration of its work."
        ),
        related_archetypes=["structural-triad"],
    ),

    # ---- BEHAVIORAL: how agents decide ----
    AgenticArchetype(
        name="repetition-compulsion",
        freudian_concept="Repetition Compulsion (Wiederholungszwang)",
        sdk_pattern="Loop detection and circuit-breaker patterns",
        category=ArchetypeCategory.BEHAVIORAL,
        description=(
            "Freud observed that people compulsively repeat painful patterns. Agents can enter "
            "infinite retry loops on failing operations. Implement circuit breakers that "
            "detect repeated failures and force a change of strategy."
        ),
        prompt_fragment=(
            "Monitor for repetitive patterns. If you attempt the same approach more "
            "than twice without progress, stop and fundamentally change strategy. "
            "Repetition without insight is compulsion, not persistence."
        ),
        related_archetypes=["freudian-slip"],
    ),
    AgenticArchetype(
        name="pleasure-principle",
        freudian_concept="Pleasure Principle / Reality Principle / Death Drive",
        sdk_pattern="Greedy vs optimal routing with graceful termination",
        category=ArchetypeCategory.BEHAVIORAL,
        description=(
            "Merges three Freudian drives into one routing archetype. The pleasure "
            "principle seeks immediate gratification (greedy, fast responses). The "
            "reality principle defers for better outcomes (thorough, verified work). "
            "The death drive knows when to stop -- graceful termination when goals are "
            "met, cleanup of temporary resources, resistance to unnecessary continuation. "
            "One archetype covering: when to be fast, when to be thorough, when to stop."
        ),
        prompt_fragment=(
            "Balance speed against thoroughness. For simple queries, respond directly. "
            "For complex or high-stakes tasks, defer immediate output in favor of careful "
            "verification and planning. When the task is complete, stop. Do not continue "
            "generating output, exploring tangents, or performing unnecessary work. "
            "Recognize completion and terminate gracefully."
        ),
        related_archetypes=["fixation"],
    ),
    AgenticArchetype(
        name="dream-work",
        freudian_concept="Dream-Work (Condensation + Displacement + Secondary Revision)",
        sdk_pattern="Compression, redirection, and curation pipeline",
        category=ArchetypeCategory.BEHAVIORAL,
        description=(
            "Merges three dream-work operations into one transformation pipeline. "
            "Condensation compresses multiple sources into a single dense output. "
            "Displacement redirects effort to proxy tasks when the direct approach is "
            "blocked. Secondary revision curates and organizes context for coherence "
            "before acting. Together: compress multi-source inputs, redirect when "
            "blocked, and curate for maximum coherence."
        ),
        prompt_fragment=(
            "Synthesize findings from all sources into a single, dense response -- "
            "multiple inputs should converge into one coherent output. If the direct "
            "approach is blocked, identify a proxy task that achieves the same underlying "
            "goal through an alternative path. Before acting on assembled context, curate "
            "it: select the most relevant information, organize for coherence, and preserve "
            "structural semantics. What enters your context window matters more than how much."
        ),
        related_archetypes=["fixation"],
    ),

    # ---- DIAGNOSTIC: how agents explore and self-correct ----
    AgenticArchetype(
        name="free-association",
        freudian_concept="Free Association",
        sdk_pattern="Exploratory chain-of-thought with branching",
        category=ArchetypeCategory.DIAGNOSTIC,
        description=(
            "In free association, the speaker says whatever comes to mind without censorship. "
            "Agents explore solution spaces through unconstrained chain-of-thought, "
            "branching freely before converging on a solution."
        ),
        prompt_fragment=(
            "Explore the problem space freely before committing to a solution. "
            "Generate multiple hypotheses, follow unexpected connections, and only "
            "converge after sufficient exploration."
        ),
    ),
    AgenticArchetype(
        name="freudian-slip",
        freudian_concept="Parapraxes (Fehlleistungen) / Resistance (Widerstand)",
        sdk_pattern="Unexpected output and failure analysis",
        category=ArchetypeCategory.DIAGNOSTIC,
        description=(
            "Merges two diagnostic concepts. Parapraxes (Freudian slips) reveal "
            "unconscious misalignment -- unexpected agent outputs are not random, they "
            "reveal gaps between intent and execution. Resistance (Widerstand) means "
            "persistent failures are structurally informative -- the pattern of what "
            "fails reveals the structure of the problem. Together: treat both unexpected "
            "outputs and repeated failures as diagnostic signals, not noise."
        ),
        prompt_fragment=(
            "Pay attention to unexpected outputs and errors. They are not noise -- "
            "they reveal misalignment between intent and execution. When you encounter "
            "repeated failures, treat them as information: the pattern of what fails "
            "reveals the structure of the problem. Analyze errors structurally rather "
            "than simply retrying or suppressing the unexpected output."
        ),
        related_archetypes=["repetition-compulsion"],
    ),
    AgenticArchetype(
        name="fixation",
        freudian_concept="Cathexis (Besetzung) / Sublimation",
        sdk_pattern="Attention allocation with productive redirection",
        category=ArchetypeCategory.DIAGNOSTIC,
        description=(
            "Merges two resource concepts. Cathexis (Besetzung) is libidinal investment -- "
            "agent attention (context window, tool call budget) is a finite resource that "
            "must be consciously invested and withdrawn. Sublimation redirects blocked "
            "drives into productive alternatives. Together: invest context budget "
            "deliberately, and when blocked, redirect toward the closest productive "
            "alternative rather than persisting on the impossible."
        ),
        prompt_fragment=(
            "Allocate your attention deliberately. Invest deeply in the most relevant "
            "sources and withdraw from tangential exploration. Your context window is "
            "finite -- spend it wisely. Prefer precise queries over bulk retrieval. "
            "If a request cannot be fulfilled directly, redirect toward the closest "
            "productive alternative that serves the underlying need. Transform "
            "constraints into opportunities."
        ),
        related_archetypes=["dream-work", "pleasure-principle"],
    ),
]

# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

_BY_NAME: dict[str, AgenticArchetype] = {a.name: a for a in ARCHETYPES}
_BY_CATEGORY: dict[ArchetypeCategory, list[AgenticArchetype]] = {}
for _a in ARCHETYPES:
    _BY_CATEGORY.setdefault(_a.category, []).append(_a)


def get_archetype(name: str) -> AgenticArchetype | None:
    """Look up an archetype by its short name."""
    return _BY_NAME.get(name)


def get_by_category(category: ArchetypeCategory) -> list[AgenticArchetype]:
    """Return all archetypes in the given category."""
    return _BY_CATEGORY.get(category, [])


def list_archetype_names() -> list[str]:
    """Return all archetype names in registry order."""
    return [a.name for a in ARCHETYPES]


def search_archetypes(query: str) -> list[AgenticArchetype]:
    """Search archetypes by keyword across all text fields."""
    q = query.lower()
    return [
        a for a in ARCHETYPES
        if q in a.name.lower()
        or q in a.freudian_concept.lower()
        or q in a.sdk_pattern.lower()
        or q in a.description.lower()
        or q in a.prompt_fragment.lower()
    ]
