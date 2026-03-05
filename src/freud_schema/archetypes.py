"""Registry of agentic archetypes derived from Freudian psychoanalytic theory.

Each archetype maps a Freudian concept to a concrete Claude Agent SDK pattern,
providing both the theoretical grounding and a reusable prompt fragment.
"""

from __future__ import annotations

from freud_schema.models import AgenticArchetype, ArchetypeCategory

# ---------------------------------------------------------------------------
# The canonical archetype registry
# ---------------------------------------------------------------------------

ARCHETYPES: list[AgenticArchetype] = [
    # ---- Architecture (Structural Model) ----
    AgenticArchetype(
        name="structural-triad",
        freudian_concept="Id / Ego / Superego",
        sdk_pattern="Three-layer agent architecture",
        category=ArchetypeCategory.ARCHITECTURE,
        description=(
            "The Id generates raw impulses (unconstrained tool calls). "
            "The Ego mediates between impulse and reality (the orchestrator agent). "
            "The Superego enforces constraints and policies (guardrails, system prompts)."
        ),
        prompt_fragment=(
            "You operate as a tripartite system: an impulse layer proposes actions, "
            "a reasoning layer evaluates feasibility, and a constraint layer enforces "
            "safety boundaries. No action bypasses all three."
        ),
    ),
    AgenticArchetype(
        name="censor-gate",
        freudian_concept="Dream Censorship / Repression",
        sdk_pattern="Pre-execution filter or guardrail agent",
        category=ArchetypeCategory.ARCHITECTURE,
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
    ),

    # ---- Reasoning (Dream-Work) ----
    AgenticArchetype(
        name="condensation",
        freudian_concept="Condensation (Verdichtung)",
        sdk_pattern="Multi-source synthesis into single output",
        category=ArchetypeCategory.REASONING,
        description=(
            "Dreams compress multiple latent thoughts into a single manifest image. "
            "Agents compress information from multiple tool calls, documents, or "
            "sub-agent results into a single coherent response."
        ),
        prompt_fragment=(
            "Synthesize findings from all sources into a single, dense response. "
            "Multiple inputs should converge into one coherent output, like a dream "
            "condensing many thoughts into one image."
        ),
    ),
    AgenticArchetype(
        name="displacement",
        freudian_concept="Displacement (Verschiebung)",
        sdk_pattern="Indirect problem-solving via proxy tasks",
        category=ArchetypeCategory.REASONING,
        description=(
            "Dreams shift emotional charge from the real target to a substitute. "
            "When blocked on a direct approach, agents redirect effort to a proxy "
            "task that achieves the same underlying goal."
        ),
        prompt_fragment=(
            "If the direct approach is blocked, identify a proxy task that achieves "
            "the same underlying goal through an alternative path. Shift focus to "
            "what is achievable rather than persisting on what is blocked."
        ),
    ),
    AgenticArchetype(
        name="free-association",
        freudian_concept="Free Association",
        sdk_pattern="Exploratory chain-of-thought with branching",
        category=ArchetypeCategory.REASONING,
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

    # ---- Control Flow (Drives & Compulsions) ----
    AgenticArchetype(
        name="repetition-compulsion",
        freudian_concept="Repetition Compulsion (Wiederholungszwang)",
        sdk_pattern="Loop detection and circuit-breaker patterns",
        category=ArchetypeCategory.CONTROL_FLOW,
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
    ),
    AgenticArchetype(
        name="pleasure-reality",
        freudian_concept="Pleasure Principle vs. Reality Principle",
        sdk_pattern="Greedy vs. optimal decision-making",
        category=ArchetypeCategory.CONTROL_FLOW,
        description=(
            "The pleasure principle seeks immediate gratification; the reality "
            "principle defers for better outcomes. Agents must balance quick "
            "approximate answers (greedy) against thorough, verified responses."
        ),
        prompt_fragment=(
            "Balance speed against thoroughness. For simple queries, respond "
            "directly. For complex or high-stakes tasks, defer immediate output "
            "in favor of careful verification and planning."
        ),
    ),
    AgenticArchetype(
        name="death-drive",
        freudian_concept="Thanatos / Death Drive",
        sdk_pattern="Graceful termination and resource cleanup",
        category=ArchetypeCategory.CONTROL_FLOW,
        description=(
            "The death drive seeks return to an inorganic state. Agents must know "
            "when to stop: graceful termination when goals are met, cleanup of "
            "temporary resources, and resistance to unnecessary continuation."
        ),
        prompt_fragment=(
            "When the task is complete, stop. Do not continue generating output, "
            "exploring tangents, or performing unnecessary cleanup. Recognize "
            "completion and terminate gracefully."
        ),
    ),

    # ---- Observation (Analytic Technique) ----
    AgenticArchetype(
        name="resistance-detector",
        freudian_concept="Resistance (Widerstand)",
        sdk_pattern="Failure analysis and debugging patterns",
        category=ArchetypeCategory.OBSERVATION,
        description=(
            "In Freud's framework, resistance blocks uncomfortable insights. When agents "
            "hit persistent failures, the failure itself is informative—it reveals "
            "something about the problem structure that direct approaches miss."
        ),
        prompt_fragment=(
            "When you encounter repeated failures, treat them as information. "
            "The pattern of what fails reveals the structure of the problem. "
            "Analyze errors structurally rather than simply retrying."
        ),
    ),
    AgenticArchetype(
        name="parapraxis-monitor",
        freudian_concept="Parapraxes (Fehlleistungen)",
        sdk_pattern="Unexpected output analysis",
        category=ArchetypeCategory.OBSERVATION,
        description=(
            "Freudian slips reveal unconscious intentions. Unexpected agent outputs "
            "(wrong tool calls, malformed responses) are not random—they reveal "
            "misalignment between the prompt and the agent's interpretation."
        ),
        prompt_fragment=(
            "Pay attention to unexpected outputs and errors. They are not noise—"
            "they reveal misalignment between intent and execution. Investigate the "
            "gap rather than suppressing the unexpected output."
        ),
    ),

    # ---- Communication (Transference) ----
    AgenticArchetype(
        name="transference",
        freudian_concept="Transference (Übertragung)",
        sdk_pattern="Context transfer between agent sessions",
        category=ArchetypeCategory.COMMUNICATION,
        description=(
            "In Freud's theory, people project past relationships onto new ones. When "
            "context transfers between agent sessions or sub-agents, prior assumptions "
            "and biases transfer too. Make context transfer explicit and auditable."
        ),
        prompt_fragment=(
            "When receiving context from a previous session or another agent, "
            "treat it as potentially biased by its source. Verify transferred "
            "assumptions rather than inheriting them uncritically."
        ),
    ),
    AgenticArchetype(
        name="working-through",
        freudian_concept="Working Through (Durcharbeiten)",
        sdk_pattern="Iterative refinement with human feedback",
        category=ArchetypeCategory.COMMUNICATION,
        description=(
            "Insight alone is not enough; one must work through resistance "
            "repeatedly. Agents must iterate on solutions with human feedback, "
            "not just produce a single output and declare success."
        ),
        prompt_fragment=(
            "A first solution is rarely the final one. Present your work, "
            "incorporate feedback, and refine iteratively. Understanding the problem "
            "deepens with each pass."
        ),
    ),

    # ---- Resource Management (Libidinal Economy) ----
    AgenticArchetype(
        name="cathexis",
        freudian_concept="Cathexis (Besetzung) / Libidinal Economy",
        sdk_pattern="Attention and resource allocation",
        category=ArchetypeCategory.RESOURCE_MANAGEMENT,
        description=(
            "Libido is invested in objects; withdrawal causes anxiety. Agent "
            "attention (context window, tool call budget) is a finite resource "
            "that must be consciously invested and withdrawn."
        ),
        prompt_fragment=(
            "Allocate your attention deliberately. Invest deeply in the most "
            "relevant sources and withdraw from tangential exploration. Your "
            "context window is finite—spend it wisely."
        ),
    ),
    AgenticArchetype(
        name="sublimation",
        freudian_concept="Sublimation",
        sdk_pattern="Task redirection to productive alternatives",
        category=ArchetypeCategory.RESOURCE_MANAGEMENT,
        description=(
            "Sublimation redirects unacceptable drives into socially valued "
            "activities. When an agent cannot fulfill a request directly "
            "(safety, capability), it redirects toward the closest productive "
            "alternative."
        ),
        prompt_fragment=(
            "If a request cannot be fulfilled directly, redirect toward the "
            "closest productive alternative that serves the user's underlying "
            "need. Transform constraints into opportunities."
        ),
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
    ]
