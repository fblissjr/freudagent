"""Pydantic models for the Freud Schema and its agentic archetype mappings."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ArchetypeCategory(str, Enum):
    """Categories of agentic archetypes derived from Freudian theory.

    Three-category taxonomy:
        STRUCTURAL  -- how agents are built
        BEHAVIORAL  -- how agents decide
        DIAGNOSTIC  -- how agents explore and self-correct
    """

    STRUCTURAL = "structural"    # How agents are built
    BEHAVIORAL = "behavioral"    # How agents decide
    DIAGNOSTIC = "diagnostic"    # How agents explore and self-correct


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
    category: ArchetypeCategory = ArchetypeCategory.BEHAVIORAL
    description: str = Field(default="", description="How the mapping works")
    prompt_fragment: str = Field(
        default="",
        description="A reusable prompt snippet that activates this archetype",
    )
    related_archetypes: list[str] = Field(
        default_factory=list,
        description="Names of archetypes with structural relationships to this one",
    )
