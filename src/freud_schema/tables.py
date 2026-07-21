"""Pydantic models for the meta-harness dimensional schema (v0.17).

Models mirror the DuckDB tables in db.py. Key scheme: sha256/32 hash
surrogate keys (keys.dimension_key) everywhere -- no sequences, no
integer ids.
Dimensions are SCD Type 2 (effective_from/effective_to/is_current/
hash_diff); registry dimensions (dim_project, dim_facet_type,
dim_finding_type) are append-only without SCD-2. Facts are append-only
with a lineage envelope (record_source, etl_run_id), except fact_session
which is an accumulating snapshot (status/result/completed_at update as
the session progresses -- legitimate Kimball, not a violation).

Naming decided 2026-07-07: etl_run_id is the lineage identifier (joins
meta_load_log); session_key exclusively means the harness session a row
describes. session_id appears nowhere.

Enum classes are the single source of truth for valid values -- db.py
imports them for CHECK constraints, cli.py for argparse choices.
finding_type is deliberately NOT an enum: it is open-vocabulary,
registry-validated against dim_finding_type in the store layer.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums: single source of truth for valid column values (closed sets only)
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


class RecordSource(str, Enum):
    """Where a row came from. Allowlist per the lineage pattern --
    every writer must declare itself."""

    NATIVE = "native"
    TRANSCRIPT_INGEST = "transcript_ingest"
    HISTORY_JSONL = "history_jsonl"
    EVENT_INGEST = "event_ingest"
    DERIVED = "derived"


class ProposalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class TargetDimension(str, Enum):
    """Dimensions a proposal may target. Genuinely closed: a new member
    means the evolve loop learned to modify a new kind of rule-bearing
    dimension, which is a code change by definition."""

    DIM_SKILL = "dim_skill"
    DIM_RULE = "dim_rule"
    DIM_SAMPLING_CONFIG = "dim_sampling_config"


class FindingScope(str, Enum):
    PROJECT = "project"
    GLOBAL = "global"


class FacetMethod(str, Enum):
    COMPUTED = "computed"
    REGEX = "regex"
    LLM = "llm"
    CLUSTER = "cluster"


class FacetOutputType(str, Enum):
    TEXT = "text"
    NUMERIC = "numeric"
    BOOL = "bool"
    JSON = "json"


class DetectionMethod(str, Enum):
    SQL = "sql"
    LLM = "llm"
    HYBRID = "hybrid"


class FeedbackOriginKind(str, Enum):
    """What produced a piece of feedback.

    Deliberately CLOSED, unlike origin_id. This is the column filters are
    written against -- "exclude model-derived rows from this measurement",
    "hold a human-only slice". An open vocabulary here fails silently: one
    writer records `llm`, another `model`, and the exclusion filter misses
    rows while looking like it worked. Adding a kind means measurement code
    has to handle it, which is an engineering decision, not a row.

    UNSPECIFIED is the default on purpose. A row that defaulted to HUMAN
    would contaminate the slice everything else is measured against, and it
    would look like a clean measurement while doing it.
    """

    HUMAN = "human"
    MODEL = "model"
    USAGE_SIGNAL = "usage_signal"
    DOWNSTREAM_SYSTEM = "downstream_system"
    UNSPECIFIED = "unspecified"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


# ---------------------------------------------------------------------------
# SCD-2 dimension models (versioned reference data)
# ---------------------------------------------------------------------------


class Skill(BaseModel):
    """A declarative skill: domain-specific instructions loaded at runtime.

    Entity key: dimension_key(domain, task_type). All SCD-2 rows for the
    same skill share skill_key; version + is_current distinguish them.
    """

    skill_key: str | None = None
    tenant_id: str = "default"
    domain: str
    task_type: str
    version: int = 1
    content: str = Field(description="The actual instructions, markdown")
    metadata: dict | None = None
    parent_skill_key: str | None = None
    status: SkillStatus = SkillStatus.DRAFT
    origin: SkillOrigin = SkillOrigin.HUMAN_AUTHORED
    activation_conditions: dict | None = Field(
        default=None,
        description="JSON conditions for dynamic loading",
    )
    # SCD-2 + lineage
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    is_current: bool = True
    hash_diff: str | None = None
    record_source: RecordSource = RecordSource.NATIVE
    created_at: datetime | None = None


class Source(BaseModel):
    """A raw artifact to be processed (PDF, image, document).

    Entity key: dimension_key(content_path).
    """

    source_key: str | None = None
    tenant_id: str = "default"
    content_path: str = Field(description="File path or object store reference")
    media_type: str = Field(description="MIME type, e.g. application/pdf")
    metadata: dict | None = None
    source_hash: str | None = None
    status: SourceStatus = SourceStatus.ACTIVE
    superseded_by_key: str | None = None
    # SCD-2 + lineage
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    is_current: bool = True
    hash_diff: str | None = None
    record_source: RecordSource = RecordSource.NATIVE
    created_at: datetime | None = None


class Rule(BaseModel):
    """A constraint applied to all agents (global) or a specific domain.

    Entity key: dimension_key(name). The name doubles as the compile
    target filename (.claude/rules/<name>.md), which is why rules gained
    a required name in v0.17.
    """

    rule_key: str | None = None
    tenant_id: str = "default"
    name: str = Field(description="Stable identity; compile target filename")
    scope: RuleScope = RuleScope.GLOBAL
    domain: str | None = None
    priority: int = 0
    content: str = Field(description="The rule text, markdown")
    status: RuleStatus = RuleStatus.ACTIVE
    # SCD-2 + lineage
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    is_current: bool = True
    hash_diff: str | None = None
    record_source: RecordSource = RecordSource.NATIVE
    created_at: datetime | None = None


class SamplingConfig(BaseModel):
    """Configuration for prior run sampling in context assembly.

    Entity key: dimension_key(domain, task_type) -- NULL-safe.
    """

    config_key: str | None = None
    tenant_id: str = "default"
    domain: str | None = None
    task_type: str | None = None
    strategy: SamplingStrategy
    parameters: dict = Field(default_factory=dict)
    max_samples: int = 3
    status: RuleStatus = RuleStatus.ACTIVE
    # SCD-2 + lineage
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    is_current: bool = True
    hash_diff: str | None = None
    record_source: RecordSource = RecordSource.NATIVE
    created_at: datetime | None = None


# ---------------------------------------------------------------------------
# Registry dimensions (append-only, no SCD-2)
# ---------------------------------------------------------------------------


class Tenant(BaseModel):
    """A conformed tenant dimension -- entity identity stops being
    single-namespace once the four SCD-2 dims key off (tenant_id, ...).

    Key: dimension_key(tenant_id). Append-only, like Project: tenant
    identity doesn't evolve shape over time the way skills/rules do.
    """

    tenant_key: str | None = None
    tenant_id: str
    display_name: str | None = None
    record_source: RecordSource = RecordSource.NATIVE
    created_at: datetime | None = None


class Project(BaseModel):
    """A conformed project dimension -- what makes cross-project queries
    a GROUP BY instead of a cross-database merge.

    Key: dimension_key(project_path). Project identity doesn't change
    shape over time the way skills/rules do, so no SCD-2.
    """

    project_key: str | None = None
    project_path: str
    project_name: str | None = None
    first_seen_at: datetime | None = None
    record_source: RecordSource = RecordSource.NATIVE
    created_at: datetime | None = None


class FacetType(BaseModel):
    """Registry row for a behavioral facet. Adding a facet is a row plus
    a populator, not a schema migration.

    Key: dimension_key(facet_id, prompt_version) -- bumping a prompt
    version adds a row, never overwrites.
    """

    facet_type_key: str | None = None
    facet_id: str
    tier: int = 1
    method: FacetMethod = FacetMethod.COMPUTED
    output_type: FacetOutputType = FacetOutputType.TEXT
    prompt_text: str | None = None
    prompt_version: int = 1
    description: str | None = None
    record_source: RecordSource = RecordSource.NATIVE
    created_at: datetime | None = None


class FeedbackOrigin(BaseModel):
    """Registry row for one thing that produces feedback: a named person, a
    specific model version, a usage signal, a downstream system.

    origin_id is open vocabulary -- which person or which model version is
    discovered by running the loop and must never require a schema change.
    The kind it maps to is closed (see FeedbackOriginKind).

    Key: dimension_key(origin_id).
    """

    feedback_origin_key: str | None = None
    origin_id: str
    origin_kind: FeedbackOriginKind = FeedbackOriginKind.UNSPECIFIED
    description: str | None = None
    record_source: RecordSource = RecordSource.NATIVE


class FindingType(BaseModel):
    """Registry row for a finding vocabulary entry. finding_type is
    open-vocabulary by design (decided 2026-07-07): new domains seed
    their finding types as data, the same way they seed skills.

    Key: dimension_key(finding_type).
    """

    finding_type_key: str | None = None
    finding_type: str
    description: str | None = None
    detection_method: DetectionMethod = DetectionMethod.SQL
    record_source: RecordSource = RecordSource.NATIVE
    created_at: datetime | None = None


class EventType(BaseModel):
    """Registry row for an event vocabulary entry (M5) -- the
    generalization of FindingType for the generic event grain. Open
    vocabulary, same reasoning as finding_type: any ingest adapter's event
    shapes are rows here, never enum edits.

    Key: dimension_key(event_type).
    """

    event_type_key: str | None = None
    event_type: str
    description: str | None = None
    schema_hint: dict | None = Field(
        default=None,
        description="Optional JSON shape hint for this event type's payload",
    )
    record_source: RecordSource = RecordSource.NATIVE
    created_at: datetime | None = None


# ---------------------------------------------------------------------------
# Fact models (event data with denormalized dimension attributes)
# ---------------------------------------------------------------------------


class Session(BaseModel):
    """A harness session -- native experiment run or ingested transcript.

    Accumulating snapshot fact: status/result/completed_at update as the
    session progresses. record_source distinguishes origins so views work
    across both without a UNION.

    Key: dimension_key(record_source, native_session_id).
    """

    session_key: str | None = None
    native_session_id: str | None = Field(
        default=None,
        description="Claude Code session uuid for ingested transcripts; "
                    "store-generated uuid for native runs",
    )
    project_key: str | None = None
    task_description: str | None = None
    task_type: str | None = None
    parent_session_key: str | None = None
    agent_role: AgentRole = AgentRole.SUBAGENT
    skill_key: str | None = None
    context_loaded: dict | None = None
    model_used: str | None = None
    token_usage: dict | None = None
    status: SessionStatus = SessionStatus.RUNNING
    result: dict | None = None
    sampled_session_keys: list[str] | None = Field(
        default=None,
        description="Prior session keys injected as context for this run",
    )
    # Denormalized from dim_skill
    skill_domain: str | None = None
    skill_task_type: str | None = None
    skill_version: int | None = None
    # Lineage
    tenant_key: str | None = None
    record_source: RecordSource = RecordSource.NATIVE
    etl_run_id: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None


class Message(BaseModel):
    """One user/assistant entry in a transcript. Full grain from day one
    (decided 2026-07-07): user-correction detection is structurally
    impossible at session-level aggregation.

    Key: dimension_key(session_key, entry_uuid) -- deterministic, so
    re-ingestion is idempotent.
    """

    message_key: str | None = None
    session_key: str
    project_key: str | None = None
    role: MessageRole
    entry_uuid: str | None = None
    parent_uuid: str | None = None
    sequence_num: int = 0
    occurred_at: datetime | None = None
    content_text: str | None = None
    has_thinking: bool = False
    thinking_text: str | None = Field(
        default=None,
        description="The turn's reasoning, kept verbatim. Captured at ingest "
                    "rather than self-reported: a trail the agent has to "
                    "volunteer is switched on after someone suspects a "
                    "problem, and by then the run you wanted is gone",
    )
    stop_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    is_meta: bool = False
    is_sidechain: bool = False
    # Lineage
    tenant_key: str | None = None
    record_source: RecordSource = RecordSource.TRANSCRIPT_INGEST
    etl_run_id: str | None = None
    created_at: datetime | None = None


class ToolUse(BaseModel):
    """One tool_use content block, joined to its tool_result where present.
    Deliberately no per-tool typed columns -- tool-specific detail stays
    in tool_input.

    Key: dimension_key(session_key, tool_use_id) -- deterministic.
    """

    tool_use_key: str | None = None
    session_key: str
    project_key: str | None = None
    message_key: str | None = None
    tool_use_id: str | None = None
    tool_name: str
    tool_input: dict | None = None
    is_error: bool | None = Field(
        default=None,
        description="Tri-state: True/False from tool_result, None if no result",
    )
    result_text: str | None = None
    sequence_num: int = 0
    occurred_at: datetime | None = None
    # Lineage
    tenant_key: str | None = None
    record_source: RecordSource = RecordSource.TRANSCRIPT_INGEST
    etl_run_id: str | None = None
    created_at: datetime | None = None


class Event(BaseModel):
    """One generic ingested event -- the generalization of Message/ToolUse
    for non-transcript sources (M5). Any enterprise event stream ingests
    through this grain via an IngestAdapter (ingest.py); transcripts keep
    their richer typed projection (Message/ToolUse) instead of also
    landing here -- typed tables are for sources rich enough to deserve
    them.

    Key: dimension_key(stream_key, native_event_id) -- deterministic, so
    re-ingestion is idempotent, matching Message/ToolUse.
    """

    event_key: str | None = None
    stream_key: str
    native_event_id: str | None = Field(
        default=None,
        description="Source stream's own event id, if any -- falls back "
                    "to a random uuid (non-idempotent for that row) like "
                    "entry_uuid/tool_use_id do",
    )
    event_type: str = Field(
        description="Open vocabulary, registry-validated against "
                    "dim_event_type in the store layer -- no CHECK constraint",
    )
    occurred_at: datetime | None = None
    actor: str | None = None
    payload: dict | None = None
    content_text: str | None = Field(
        default=None, description="Extracted searchable text, if any",
    )
    signature: str | None = Field(
        default=None,
        description="Optional normalized template signature (amendment 6 "
                    "normalization hook, e.g. mask_signature())",
    )
    sequence_num: int = 0
    # Lineage
    tenant_key: str | None = None
    record_source: RecordSource = RecordSource.EVENT_INGEST
    etl_run_id: str | None = None
    created_at: datetime | None = None


class SessionFacet(BaseModel):
    """EAV fact: one value of one facet for one session.

    Key: dimension_key(session_key, facet_id, prompt_version).
    """

    facet_row_key: str | None = None
    session_key: str
    facet_type_key: str | None = None
    facet_id: str
    prompt_version: int = 1
    value_text: str | None = None
    value_numeric: float | None = None
    value_bool: bool | None = None
    value_json: dict | list | None = None
    is_fallback: bool = False
    extraction_metadata: dict | None = None
    # Lineage
    tenant_key: str | None = None
    record_source: RecordSource = RecordSource.DERIVED
    etl_run_id: str | None = None
    created_at: datetime | None = None


class Finding(BaseModel):
    """A couch output: one detected pattern with its evidence. Append-only
    -- re-running Analyze produces new rows, so trends work for free.

    finding_type is registry-validated against dim_finding_type in the
    store layer, never a CHECK constraint.
    """

    finding_key: str | None = None
    finding_type: str
    finding_type_key: str | None = None
    scope: FindingScope = FindingScope.PROJECT
    project_key: str | None = None
    evidence_session_keys: list[str] | None = None
    occurrence_count: int | None = None
    summary: str = Field(description="Human-readable; must be pre-scrubbed "
                                     "of paths/usernames (compile is fail-closed)")
    detected_at: datetime | None = None
    # Lineage
    tenant_key: str | None = None
    record_source: RecordSource = RecordSource.DERIVED
    etl_run_id: str | None = None
    created_at: datetime | None = None


class Proposal(BaseModel):
    """An evolve output: one proposed dimension change, pending until a
    human approves or rejects. Approval creates the new SCD-2 row and
    records it in resulting_dimension_key."""

    proposal_key: str | None = None
    target_dimension: TargetDimension
    target_key: str | None = Field(
        default=None,
        description="Entity key of the dim row to evolve; None for new entities",
    )
    target_natural_key: dict | None = None
    proposed_content: str
    proposed_version: int | None = None
    status: ProposalStatus = ProposalStatus.PENDING
    evidence_finding_keys: list[str] | None = None
    resulting_dimension_key: str | None = None
    review_notes: str | None = Field(
        default=None,
        description="Why the reviewer decided as they did. Rejection rate is a "
                    "health measure; without the reason it cannot distinguish a "
                    "gate catching real problems from one objecting to wording",
    )
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    # Lineage
    tenant_key: str | None = None
    record_source: RecordSource = RecordSource.DERIVED
    etl_run_id: str | None = None
    created_at: datetime | None = None


class Extraction(BaseModel):
    """Structured output from processing a source with a skill."""

    extraction_key: str | None = None
    source_key: str
    skill_key: str
    session_key: str
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
    # Lineage
    tenant_key: str | None = None
    record_source: RecordSource = RecordSource.NATIVE
    etl_run_id: str | None = None
    created_at: datetime | None = None


class Feedback(BaseModel):
    """A human correction on an extraction, closing the flywheel loop."""

    feedback_key: str | None = None
    extraction_key: str
    session_key: str
    skill_key: str
    correction: dict = Field(description="What changed: before/after")
    correction_type: CorrectionType
    notes: str | None = None
    created_by: str | None = None
    # What produced this judgment. feedback_origin_key points at the registry;
    # origin_kind is denormalized so excluding model-derived rows from a
    # measurement never needs a join -- the filter has to be cheap enough that
    # it always gets written.
    feedback_origin_key: str | None = None
    origin_kind: FeedbackOriginKind = FeedbackOriginKind.UNSPECIFIED
    # Denormalized from dim_skill
    skill_domain: str | None = None
    skill_task_type: str | None = None
    skill_version: int | None = None
    # Denormalized from dim_source (via extraction)
    source_key: str | None = None
    source_path: str | None = None
    # Lineage
    tenant_key: str | None = None
    record_source: RecordSource = RecordSource.NATIVE
    etl_run_id: str | None = None
    created_at: datetime | None = None


class Trace(BaseModel):
    """A single node in a session's reasoning trace tree."""

    trace_key: str | None = None
    session_key: str
    parent_trace_key: str | None = None
    trace_type: TraceType
    depth: int = 0
    sequence_order: int = 0
    title: str = Field(description="One-line summary, queryable and groupable")
    content: str | None = Field(default=None, description="Full detail of what happened")
    reasoning: str | None = Field(default=None, description="Why this decision/path/outcome")
    alternatives: dict | None = Field(default=None, description="What else was considered")
    outcome: dict | None = Field(default=None, description="Structured result of this node")
    child_session_key: str | None = Field(
        default=None, description="For subagent_spawn: spawned session",
    )
    duration_ms: int | None = None
    # Denormalized from fact_session / dim_skill
    skill_key: str | None = None
    skill_domain: str | None = None
    skill_task_type: str | None = None
    # Lineage
    tenant_key: str | None = None
    record_source: RecordSource = RecordSource.NATIVE
    etl_run_id: str | None = None
    created_at: datetime | None = None


class TraceFeedback(BaseModel):
    """Human feedback on a specific trace node -- the trace-level flywheel signal."""

    trace_feedback_key: str | None = None
    trace_key: str
    session_key: str
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
    skill_key: str | None = None
    skill_domain: str | None = None
    skill_task_type: str | None = None
    # Lineage
    tenant_key: str | None = None
    record_source: RecordSource = RecordSource.NATIVE
    etl_run_id: str | None = None
    created_at: datetime | None = None


# ---------------------------------------------------------------------------
# Meta models
# ---------------------------------------------------------------------------


class LoadRun(BaseModel):
    """One row per ingestion/compile run -- operational visibility for
    Sense and Materialize. Status values shared with SessionStatus
    (running/completed/failed)."""

    etl_run_id: str | None = None
    operation: str = Field(description="e.g. ingest_transcripts, compile")
    status: SessionStatus = SessionStatus.RUNNING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    rows_read: int = 0
    rows_written: int = 0
    rows_skipped: int = 0
    error: str | None = None
    record_source: RecordSource = RecordSource.NATIVE
