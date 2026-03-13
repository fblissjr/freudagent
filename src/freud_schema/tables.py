"""Pydantic models for the 6-table experiment harness schema.

These mirror the DuckDB tables in db.py and provide type-safe interfaces
for the store operations. Enum classes are the single source of truth
for valid values -- db.py imports them for CHECK constraints, cli.py
imports them for argparse choices.
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


# ---------------------------------------------------------------------------
# Pydantic models
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
    created_at: datetime | None = None


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
    created_at: datetime | None = None
    completed_at: datetime | None = None


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
    created_at: datetime | None = None


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


class Subtask(BaseModel):
    """A decomposed unit of work within an orchestrator session."""

    type: str
    skill_domain: str
    skill_task_type: str
    source_ids: list[int] = Field(default_factory=list)
    context: dict | None = None
    depends_on: list[int] = Field(default_factory=list)


class TaskPlan(BaseModel):
    """The orchestrator's decomposition of a task into subtasks."""

    subtasks: list[Subtask]
    human_review_required: bool = False
