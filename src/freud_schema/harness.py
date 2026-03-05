"""Meta-harness: generate agent system prompts from Freudian archetypes.

The harness composes archetype prompt fragments into complete system prompts
for Claude Agent SDK agents, allowing Freudian psychoanalytic principles to
shape agent behavior at the architectural level.
"""

from __future__ import annotations

from freud_schema.archetypes import (
    ARCHETYPES,
    get_archetype,
    get_by_category,
)
from freud_schema.models import AgenticArchetype, ArchetypeCategory


def compose_system_prompt(
    archetype_names: list[str],
    *,
    task_context: str = "",
    preamble: str = "",
) -> str:
    """Build a system prompt from selected archetypes.

    Args:
        archetype_names: Names of archetypes to include.
        task_context: Description of the specific task (injected after archetypes).
        preamble: Optional text prepended before everything.

    Returns:
        A complete system prompt string.
    """
    archetypes = []
    for name in archetype_names:
        a = get_archetype(name)
        if a is None:
            raise ValueError(f"Unknown archetype: {name!r}")
        archetypes.append(a)

    return _render(archetypes, task_context=task_context, preamble=preamble)


def compose_by_category(
    categories: list[ArchetypeCategory],
    *,
    task_context: str = "",
    preamble: str = "",
) -> str:
    """Build a system prompt from all archetypes in the given categories."""
    archetypes = []
    for cat in categories:
        archetypes.extend(get_by_category(cat))
    if not archetypes:
        raise ValueError(f"No archetypes found for categories: {categories}")
    return _render(archetypes, task_context=task_context, preamble=preamble)


def compose_full(*, task_context: str = "", preamble: str = "") -> str:
    """Build a system prompt using ALL registered archetypes."""
    return _render(ARCHETYPES, task_context=task_context, preamble=preamble)


# ---------------------------------------------------------------------------
# Preset compositions for common agent patterns
# ---------------------------------------------------------------------------

PRESETS: dict[str, list[str]] = {
    "careful-executor": [
        "structural-triad",
        "censor-gate",
        "repetition-compulsion",
        "resistance-detector",
        "death-drive",
    ],
    "creative-explorer": [
        "free-association",
        "condensation",
        "displacement",
        "cathexis",
        "sublimation",
    ],
    "iterative-refiner": [
        "working-through",
        "pleasure-reality",
        "transference",
        "parapraxis-monitor",
    ],
    "minimal-safe": [
        "structural-triad",
        "repetition-compulsion",
        "death-drive",
    ],
}


def compose_preset(
    preset: str,
    *,
    task_context: str = "",
    preamble: str = "",
) -> str:
    """Build a system prompt from a named preset composition.

    Available presets:
        careful-executor  - Safety-first with loop detection and graceful termination
        creative-explorer - Exploratory reasoning with resource awareness
        iterative-refiner - Feedback-driven refinement with bias detection
        minimal-safe      - Lightweight safety baseline
    """
    if preset not in PRESETS:
        available = ", ".join(sorted(PRESETS))
        raise ValueError(f"Unknown preset {preset!r}. Available: {available}")
    return compose_system_prompt(
        PRESETS[preset], task_context=task_context, preamble=preamble
    )


# ---------------------------------------------------------------------------
# Internal rendering
# ---------------------------------------------------------------------------


def _render(
    archetypes: list[AgenticArchetype],
    *,
    task_context: str,
    preamble: str,
) -> str:
    """Render a list of archetypes into a formatted system prompt."""
    sections: list[str] = []

    if preamble:
        sections.append(preamble.strip())

    # Group by category for readability
    by_cat: dict[ArchetypeCategory, list[AgenticArchetype]] = {}
    for a in archetypes:
        by_cat.setdefault(a.category, []).append(a)

    cat_labels = {
        ArchetypeCategory.ARCHITECTURE: "Architecture",
        ArchetypeCategory.REASONING: "Reasoning",
        ArchetypeCategory.CONTROL_FLOW: "Control Flow",
        ArchetypeCategory.OBSERVATION: "Observation",
        ArchetypeCategory.COMMUNICATION: "Communication",
        ArchetypeCategory.RESOURCE_MANAGEMENT: "Resource Management",
    }

    sections.append("# Operating Principles (Freudian Archetypes)\n")

    for cat in ArchetypeCategory:
        cat_archetypes = by_cat.get(cat, [])
        if not cat_archetypes:
            continue
        sections.append(f"## {cat_labels.get(cat, cat.value)}\n")
        for a in cat_archetypes:
            sections.append(f"### {a.name} ({a.freudian_concept})")
            if a.prompt_fragment:
                sections.append(a.prompt_fragment)
            sections.append("")

    if task_context:
        sections.append("# Task Context\n")
        sections.append(task_context.strip())

    return "\n".join(sections).strip() + "\n"
