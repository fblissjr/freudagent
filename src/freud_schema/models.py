"""Pydantic models for the Freud Schema and its agentic archetype mappings."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ArchetypeCategory(str, Enum):
    """Categories of agentic archetypes derived from Freudian theory."""

    ARCHITECTURE = "architecture"          # Structural model → agent architecture
    REASONING = "reasoning"                # Dream-work → reasoning patterns
    CONTROL_FLOW = "control_flow"          # Drives/compulsions → flow control
    OBSERVATION = "observation"            # Analytic technique → monitoring
    COMMUNICATION = "communication"        # Transference → inter-agent comms
    RESOURCE_MANAGEMENT = "resource_mgmt"  # Libidinal economy → resource allocation


# ---------------------------------------------------------------------------
# Core schema models
# ---------------------------------------------------------------------------


class AgenticArchetype(BaseModel):
    """A mapping from a Freudian concept to a Claude Agent SDK pattern.

    Each archetype is a reusable behavioral pattern for agents, grounded in
    psychoanalytic theory and translated into concrete SDK constructs.
    """

    name: str = Field(description="Short identifier, e.g. 'structural-triad'")
    freudian_concept: str = Field(description="The originating Freudian idea")
    sdk_pattern: str = Field(description="Claude Agent SDK construct or pattern")
    category: ArchetypeCategory = ArchetypeCategory.REASONING
    description: str = Field(default="", description="How the mapping works")
    prompt_fragment: str = Field(
        default="",
        description="A reusable prompt snippet that activates this archetype",
    )
    related_archetypes: list[str] = Field(
        default_factory=list,
        description="Names of archetypes with structural relationships to this one",
    )


class FreudEntry(BaseModel):
    """A row in the Freud extraction schema.

    The original 8 columns from the PDF extraction, plus translation notes
    and agentic overlay fields.

    Core columns (from PDF):
        1.  book_title         - Exact source attribution
        2.  chapter_section    - Structural location in source
        3.  core_topic         - Thematic grouping
        4.  major_finding      - The synthesized theoretical breakthrough
        5.  crucial_quote      - Verbatim encapsulating sentence
        6.  key_terminology    - Psychoanalytic jargon coined or redefined
        7.  source_context     - Historical examples from Freud's writings
        8.  translation_notes  - German→English translation commentary

    Agentic overlay:
        9.  agent_notes        - Freeform mapping to Claude Agent SDK patterns
        10. archetypes         - Structured archetype extractions
    """

    # --- Core 8 columns ---
    book_title: str
    author: str = "Sigmund Freud"
    chapter_section: str = ""
    core_topic: str = ""
    major_finding: str = ""
    crucial_quote: str = ""
    key_terminology: list[str] = Field(default_factory=list)
    source_context: str = ""
    translation_notes: str = ""

    # --- Agentic overlay ---
    agent_notes: str = ""
    archetypes: list[AgenticArchetype] = Field(default_factory=list)
