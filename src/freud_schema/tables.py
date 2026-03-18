"""Pydantic models for the dimensional experiment harness schema.

Models mirror the DuckDB tables in db.py: dimension tables (dim_skill,
dim_source, dim_rule, dim_sampling_config) and fact tables (fact_session,
fact_trace, fact_extraction, fact_feedback, fact_trace_feedback).

Fact models include denormalized dimension attributes populated at
insert time by the store layer. Enum classes are the single source
of truth for valid values -- db.py imports them for CHECK constraints,
cli.py imports them for argparse choices.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums: single source of truth for valid column values
# ---------------------------------------------------------------------------


class SkillStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class SourceStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class SessionStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentRole(str, Enum):
    ORCHESTRATOR = "orchestrator"
    SUBAGENT = "subagent"


class ValidationStatus(str, Enum):
    PENDING = "pending"
    VALIDATED = "validated"
    REJECTED = "rejected"


class CorrectionType(str, Enum):
    FIELD_MAPPING = "field_mapping"
    WRONG_VALUE = "wrong_value"
    MISSING_FIELD = "missing_field"
    FALSE_POSITIVE = "false_positive"


class RuleScope(str, Enum):
    GLOBAL = "global"
    DOMAIN_SPECIFIC = "domain-specific"


class RuleStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class TraceType(str, Enum):
    DECISION_POINT = "decision_point"
    PATH_TAKEN = "path_taken"
    PATH_DISCARDED = "path_discarded"
    INSIGHT = "insight"
    DEAD_END = "dead_end"
    SUBAGENT_SPAWN = "subagent_spawn"
    TOOL_CALL = "tool_call"
    CONCLUSION = "conclusion"


class TraceFeedbackType(str, Enum):
    PATH_CORRECTION = "path_correction"
    POSITIVE_SIGNAL = "positive_signal"
    DEAD_END_CONFIRMATION = "dead_end_confirmation"
    REASONING_ERROR = "reasoning_error"


class SamplingStrategy(str, Enum):
    RECENT = "recent"
    RANDOM = "random"
    STRATIFIED_OUTCOME = "stratified_outcome"
    STRATIFIED_FEEDBACK = "stratified_feedback"
    HIGH_FEEDBACK = "high_feedback"


class SkillOrigin(str, Enum):
    HUMAN_AUTHORED = "human_authored"
    DATA_DERIVED = "data_derived"


# ---------------------------------------------------------------------------
# Dimension models (reference data)
# ---------------------------------------------------------------------------


class Skill(BaseModel):
    """A declarative skill: domain-specific instructions loaded at runtime."""

    id: int | None = None
    domain: str
    task_type: str
    version: int = 1
    content: str = Field(description="The actual instructions, markdown")
    metadata: dict | None = None
    parent_skill_id: int | None = None
    status: SkillStatus = SkillStatus.DRAFT
    origin: SkillOrigin = SkillOrigin.HUMAN_AUTHORED
    activation_conditions: dict | None = Field(
        default=None,
        description="JSON conditions for dynamic loading",
    )
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Source(BaseModel):
    """A raw artifact to be processed (PDF, image, document)."""

    id: int | None = None
    content_path: str = Field(description="File path or object store reference")
    media_type: str = Field(description="MIME type, e.g. application/pdf")
    metadata: dict | None = None
    source_hash: str | None = None
    status: SourceStatus = SourceStatus.ACTIVE
    superseded_by: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Rule(BaseModel):
    """A constraint applied to all agents (global) or a specific domain."""

    id: int | None = None
    scope: RuleScope = RuleScope.GLOBAL
    domain: str | None = None
    priority: int = 0
    content: str = Field(description="The rule text, markdown")
    status: RuleStatus = RuleStatus.ACTIVE
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SamplingConfig(BaseModel):
    """Configuration for prior run sampling in context assembly."""

    id: int | None = None
    domain: str | None = None
    task_type: str | None = None
    strategy: SamplingStrategy
    parameters: dict = Field(default_factory=dict)
    max_samples: int = 3
    status: RuleStatus = RuleStatus.ACTIVE
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ---------------------------------------------------------------------------
# Fact models (event data with denormalized dimension attributes)
# ---------------------------------------------------------------------------


class Session(BaseModel):
    """A logged agent execution (orchestrator or subagent)."""

    id: int | None = None
    task_description: str
    task_type: str
    parent_session_id: int | None = None
    agent_role: AgentRole = AgentRole.SUBAGENT
    skill_id: int | None = None
    context_loaded: dict | None = None
    model_used: str | None = None
    token_usage: dict | None = None
    status: SessionStatus = SessionStatus.RUNNING
    result: dict | None = None
    sampled_session_ids: list[int] | None = Field(
        default=None,
        description="Prior session IDs injected as context for this run",
    )
    # Denormalized from dim_skill
    skill_domain: str | None = None
    skill_task_type: str | None = None
    skill_version: int | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None


class Extraction(BaseModel):
    """Structured output from processing a source with a skill."""

    id: int | None = None
    source_id: int
    skill_id: int
    session_id: int
    output: dict = Field(description="The structured data produced")
    confidence: float | None = None
    validation_status: ValidationStatus = ValidationStatus.PENDING
    validated_by: str | None = None
    validated_at: datetime | None = None
    # Denormalized from dim_source
    source_path: str | None = None
    source_media_type: str | None = None
    # Denormalized from dim_skill
    skill_domain: str | None = None
    skill_task_type: str | None = None
    skill_version: int | None = None
    created_at: datetime | None = None


class Feedback(BaseModel):
    """A human correction on an extraction, closing the flywheel loop."""

    id: int | None = None
    extraction_id: int
    session_id: int
    skill_id: int
    correction: dict = Field(description="What changed: before/after")
    correction_type: CorrectionType
    notes: str | None = None
    created_by: str | None = None
    # Denormalized from dim_skill
    skill_domain: str | None = None
    skill_task_type: str | None = None
    skill_version: int | None = None
    # Denormalized from dim_source (via extraction)
    source_id: int | None = None
    source_path: str | None = None
    created_at: datetime | None = None


class Trace(BaseModel):
    """A single node in a session's reasoning trace tree."""

    id: int | None = None
    session_id: int
    parent_trace_id: int | None = None
    trace_type: TraceType
    depth: int = 0
    sequence_order: int = 0
    title: str = Field(description="One-line summary, queryable and groupable")
    content: str | None = Field(default=None, description="Full detail of what happened")
    reasoning: str | None = Field(default=None, description="Why this decision/path/outcome")
    alternatives: dict | None = Field(default=None, description="What else was considered")
    outcome: dict | None = Field(default=None, description="Structured result of this node")
    child_session_id: int | None = Field(
        default=None, description="For subagent_spawn: spawned session",
    )
    duration_ms: int | None = None
    # Denormalized from fact_session / dim_skill
    skill_id: int | None = None
    skill_domain: str | None = None
    skill_task_type: str | None = None
    created_at: datetime | None = None


class TraceFeedback(BaseModel):
    """Human feedback on a specific trace node -- the trace-level flywheel signal."""

    id: int | None = None
    trace_id: int
    session_id: int
    feedback_type: TraceFeedbackType
    content: str = Field(description="Human's feedback text")
    correction: dict | None = Field(
        default=None,
        description="Structured correction, nullable for positive_signal",
    )
    created_by: str | None = None
    # Denormalized from fact_trace
    trace_type: str | None = None
    trace_title: str | None = None
    # Denormalized from fact_session / dim_skill
    skill_id: int | None = None
    skill_domain: str | None = None
    skill_task_type: str | None = None
    created_at: datetime | None = None
