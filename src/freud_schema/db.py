"""DuckDB schema and connection management for the meta-harness (v0.17).

Dimensional model (Kimball-style):
- 4 SCD Type 2 dimensions: dim_skill, dim_source, dim_rule,
  dim_sampling_config (effective_from/effective_to/is_current/hash_diff).
- 3 registry dimensions (append-only, no SCD-2): dim_project,
  dim_facet_type, dim_finding_type.
- 10 fact tables: fact_session (accumulating snapshot), fact_trace,
  fact_extraction, fact_feedback, fact_trace_feedback, fact_message,
  fact_tool_use, fact_session_facets, fact_finding, fact_proposal.
- 6 analytical views, meta_schema_version, meta_load_log.

Key scheme: MD5 hash surrogate keys (keys.dimension_key), no sequences.
Deterministic keys make transcript re-ingestion idempotent. Every fact
carries a lineage envelope: record_source (CHECK-constrained allowlist)
and etl_run_id (joins meta_load_log). created_at serves as inserted_at.

Naming (decided 2026-07-07): etl_run_id for lineage, session_key for the
harness session a row describes. session_id appears nowhere.

finding_type has NO CHECK constraint by design -- it is open-vocabulary,
registry-validated against dim_finding_type in the store layer, so new
finding vocabularies are data, not DDL changes.

Fact tables carry denormalized dimension attributes at insert time,
eliminating fact-to-fact joins. No FK constraints (DuckDB can't CASCADE
anyway); existence validation lives in the store layer. Tables are
created via CREATE TABLE IF NOT EXISTS; breaking changes go through
reset_schema() -- no migration path, this is an experiment repo.

DDL is stored as lists of individual statements (not multi-statement
strings) so there is no semicolon-splitting anywhere. Semicolons only
appear in get_ddl() output, which serializes for duckdb CLI consumption.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

import duckdb

from freud_schema.tables import (
    AgentRole,
    CorrectionType,
    DetectionMethod,
    FacetMethod,
    FacetOutputType,
    FindingScope,
    MessageRole,
    ProposalStatus,
    RecordSource,
    RuleScope,
    RuleStatus,
    SamplingStrategy,
    SessionStatus,
    SkillOrigin,
    SkillStatus,
    SourceStatus,
    TargetDimension,
    TraceFeedbackType,
    TraceType,
    ValidationStatus,
)

_DEFAULT_DB = Path(__file__).resolve().parent.parent.parent / "data" / "freudagent.duckdb"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_in(column: str, enum_cls: type[Enum]) -> str:
    """Generate a CHECK constraint from a Python enum class."""
    vals = ", ".join(f"'{e.value}'" for e in enum_cls)
    return f"CHECK ({column} IN ({vals}))"


# Shared column blocks. SCD-2 dims and fact lineage envelopes repeat, so
# they are built once -- one place to change, no drift between tables.

def _scd2_cols() -> str:
    return f"""    effective_from TIMESTAMP DEFAULT current_timestamp,
    effective_to TIMESTAMP,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    hash_diff VARCHAR,
    record_source VARCHAR NOT NULL DEFAULT 'native',
    created_at TIMESTAMP DEFAULT current_timestamp,
    {_check_in('record_source', RecordSource)}"""


def _lineage_cols() -> str:
    return f"""    record_source VARCHAR NOT NULL DEFAULT 'native',
    etl_run_id VARCHAR,
    created_at TIMESTAMP DEFAULT current_timestamp,
    {_check_in('record_source', RecordSource)}"""


# ---------------------------------------------------------------------------
# Schema DDL -- each element is one complete statement, no semicolons
# ---------------------------------------------------------------------------


def _build_tables_ddl() -> list[str]:
    """Build CREATE TABLE statements with CHECK constraints.

    Called once at module level to produce _TABLES_DDL.
    Enum classes in tables.py are the authority for valid values.
    """
    return [
        """CREATE TABLE IF NOT EXISTS meta_schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT current_timestamp,
    description VARCHAR
)""",
        f"""CREATE TABLE IF NOT EXISTS meta_load_log (
    etl_run_id VARCHAR NOT NULL,
    operation VARCHAR NOT NULL,
    status VARCHAR NOT NULL DEFAULT 'running',
    started_at TIMESTAMP DEFAULT current_timestamp,
    completed_at TIMESTAMP,
    rows_read INTEGER NOT NULL DEFAULT 0,
    rows_written INTEGER NOT NULL DEFAULT 0,
    rows_skipped INTEGER NOT NULL DEFAULT 0,
    error VARCHAR,
    record_source VARCHAR NOT NULL DEFAULT 'native',
    {_check_in('status', SessionStatus)},
    {_check_in('record_source', RecordSource)}
)""",
        # -- SCD Type 2 dimensions --
        f"""CREATE TABLE IF NOT EXISTS dim_skill (
    skill_key VARCHAR NOT NULL,
    domain VARCHAR NOT NULL,
    task_type VARCHAR NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    content VARCHAR NOT NULL,
    metadata JSON,
    parent_skill_key VARCHAR,
    status VARCHAR NOT NULL DEFAULT 'draft',
    origin VARCHAR NOT NULL DEFAULT 'human_authored',
    activation_conditions JSON,
{_scd2_cols()},
    {_check_in('status', SkillStatus)},
    {_check_in('origin', SkillOrigin)}
)""",
        f"""CREATE TABLE IF NOT EXISTS dim_source (
    source_key VARCHAR NOT NULL,
    content_path VARCHAR NOT NULL,
    media_type VARCHAR NOT NULL,
    metadata JSON,
    source_hash VARCHAR,
    status VARCHAR NOT NULL DEFAULT 'active',
    superseded_by_key VARCHAR,
{_scd2_cols()},
    {_check_in('status', SourceStatus)}
)""",
        f"""CREATE TABLE IF NOT EXISTS dim_rule (
    rule_key VARCHAR NOT NULL,
    name VARCHAR NOT NULL,
    scope VARCHAR NOT NULL DEFAULT 'global',
    domain VARCHAR,
    priority INTEGER NOT NULL DEFAULT 0,
    content VARCHAR NOT NULL,
    status VARCHAR NOT NULL DEFAULT 'active',
{_scd2_cols()},
    {_check_in('scope', RuleScope)},
    {_check_in('status', RuleStatus)}
)""",
        f"""CREATE TABLE IF NOT EXISTS dim_sampling_config (
    config_key VARCHAR NOT NULL,
    domain VARCHAR,
    task_type VARCHAR,
    strategy VARCHAR NOT NULL,
    parameters JSON NOT NULL DEFAULT '{{}}'::JSON,
    max_samples INTEGER NOT NULL DEFAULT 3,
    status VARCHAR NOT NULL DEFAULT 'active',
{_scd2_cols()},
    {_check_in('strategy', SamplingStrategy)},
    {_check_in('status', RuleStatus)}
)""",
        # -- Registry dimensions (append-only, no SCD-2) --
        f"""CREATE TABLE IF NOT EXISTS dim_project (
    project_key VARCHAR NOT NULL,
    project_path VARCHAR NOT NULL,
    project_name VARCHAR,
    first_seen_at TIMESTAMP DEFAULT current_timestamp,
    record_source VARCHAR NOT NULL DEFAULT 'native',
    created_at TIMESTAMP DEFAULT current_timestamp,
    {_check_in('record_source', RecordSource)}
)""",
        f"""CREATE TABLE IF NOT EXISTS dim_facet_type (
    facet_type_key VARCHAR NOT NULL,
    facet_id VARCHAR NOT NULL,
    tier INTEGER NOT NULL DEFAULT 1,
    method VARCHAR NOT NULL DEFAULT 'computed',
    output_type VARCHAR NOT NULL DEFAULT 'text',
    prompt_text VARCHAR,
    prompt_version INTEGER NOT NULL DEFAULT 1,
    description VARCHAR,
    record_source VARCHAR NOT NULL DEFAULT 'native',
    created_at TIMESTAMP DEFAULT current_timestamp,
    {_check_in('method', FacetMethod)},
    {_check_in('output_type', FacetOutputType)},
    {_check_in('record_source', RecordSource)}
)""",
        f"""CREATE TABLE IF NOT EXISTS dim_finding_type (
    finding_type_key VARCHAR NOT NULL,
    finding_type VARCHAR NOT NULL,
    description VARCHAR,
    detection_method VARCHAR NOT NULL DEFAULT 'sql',
    record_source VARCHAR NOT NULL DEFAULT 'native',
    created_at TIMESTAMP DEFAULT current_timestamp,
    {_check_in('detection_method', DetectionMethod)},
    {_check_in('record_source', RecordSource)}
)""",
        # -- Facts --
        f"""CREATE TABLE IF NOT EXISTS fact_session (
    session_key VARCHAR NOT NULL,
    native_session_id VARCHAR NOT NULL,
    project_key VARCHAR,
    task_description VARCHAR,
    task_type VARCHAR,
    parent_session_key VARCHAR,
    agent_role VARCHAR NOT NULL DEFAULT 'subagent',
    status VARCHAR NOT NULL DEFAULT 'running',
    model_used VARCHAR,
    context_loaded JSON,
    token_usage JSON,
    result JSON,
    sampled_session_keys JSON,
    skill_key VARCHAR,
    skill_domain VARCHAR,
    skill_task_type VARCHAR,
    skill_version INTEGER,
    completed_at TIMESTAMP,
{_lineage_cols()},
    {_check_in('agent_role', AgentRole)},
    {_check_in('status', SessionStatus)}
)""",
        f"""CREATE TABLE IF NOT EXISTS fact_trace (
    trace_key VARCHAR NOT NULL,
    session_key VARCHAR NOT NULL,
    parent_trace_key VARCHAR,
    trace_type VARCHAR NOT NULL,
    depth INTEGER NOT NULL DEFAULT 0,
    sequence_order INTEGER NOT NULL DEFAULT 0,
    title VARCHAR NOT NULL,
    content VARCHAR,
    reasoning VARCHAR,
    alternatives JSON,
    outcome JSON,
    child_session_key VARCHAR,
    duration_ms INTEGER,
    skill_key VARCHAR,
    skill_domain VARCHAR,
    skill_task_type VARCHAR,
{_lineage_cols()},
    {_check_in('trace_type', TraceType)}
)""",
        f"""CREATE TABLE IF NOT EXISTS fact_extraction (
    extraction_key VARCHAR NOT NULL,
    session_key VARCHAR NOT NULL,
    output JSON NOT NULL,
    confidence DOUBLE,
    validation_status VARCHAR NOT NULL DEFAULT 'pending',
    validated_by VARCHAR,
    validated_at TIMESTAMP,
    source_key VARCHAR NOT NULL,
    source_path VARCHAR,
    source_media_type VARCHAR,
    skill_key VARCHAR NOT NULL,
    skill_domain VARCHAR,
    skill_task_type VARCHAR,
    skill_version INTEGER,
{_lineage_cols()},
    {_check_in('validation_status', ValidationStatus)}
)""",
        f"""CREATE TABLE IF NOT EXISTS fact_feedback (
    feedback_key VARCHAR NOT NULL,
    extraction_key VARCHAR NOT NULL,
    session_key VARCHAR NOT NULL,
    correction JSON NOT NULL,
    correction_type VARCHAR NOT NULL,
    notes VARCHAR,
    created_by VARCHAR,
    skill_key VARCHAR NOT NULL,
    skill_domain VARCHAR,
    skill_task_type VARCHAR,
    skill_version INTEGER,
    source_key VARCHAR,
    source_path VARCHAR,
{_lineage_cols()},
    {_check_in('correction_type', CorrectionType)}
)""",
        f"""CREATE TABLE IF NOT EXISTS fact_trace_feedback (
    trace_feedback_key VARCHAR NOT NULL,
    trace_key VARCHAR NOT NULL,
    session_key VARCHAR NOT NULL,
    feedback_type VARCHAR NOT NULL,
    content VARCHAR NOT NULL,
    correction JSON,
    created_by VARCHAR,
    trace_type VARCHAR,
    trace_title VARCHAR,
    skill_key VARCHAR,
    skill_domain VARCHAR,
    skill_task_type VARCHAR,
{_lineage_cols()},
    {_check_in('feedback_type', TraceFeedbackType)}
)""",
        f"""CREATE TABLE IF NOT EXISTS fact_message (
    message_key VARCHAR NOT NULL,
    session_key VARCHAR NOT NULL,
    project_key VARCHAR,
    role VARCHAR NOT NULL,
    entry_uuid VARCHAR,
    parent_uuid VARCHAR,
    sequence_num INTEGER NOT NULL DEFAULT 0,
    occurred_at TIMESTAMP,
    content_text VARCHAR,
    has_thinking BOOLEAN NOT NULL DEFAULT FALSE,
    stop_reason VARCHAR,
    input_tokens INTEGER,
    output_tokens INTEGER,
    is_meta BOOLEAN NOT NULL DEFAULT FALSE,
    is_sidechain BOOLEAN NOT NULL DEFAULT FALSE,
{_lineage_cols()},
    {_check_in('role', MessageRole)}
)""",
        f"""CREATE TABLE IF NOT EXISTS fact_tool_use (
    tool_use_key VARCHAR NOT NULL,
    session_key VARCHAR NOT NULL,
    project_key VARCHAR,
    message_key VARCHAR,
    tool_use_id VARCHAR,
    tool_name VARCHAR NOT NULL,
    tool_input JSON,
    is_error BOOLEAN,
    result_text VARCHAR,
    sequence_num INTEGER NOT NULL DEFAULT 0,
    occurred_at TIMESTAMP,
{_lineage_cols()}
)""",
        f"""CREATE TABLE IF NOT EXISTS fact_session_facets (
    facet_row_key VARCHAR NOT NULL,
    session_key VARCHAR NOT NULL,
    facet_type_key VARCHAR,
    facet_id VARCHAR NOT NULL,
    prompt_version INTEGER NOT NULL DEFAULT 1,
    value_text VARCHAR,
    value_numeric DOUBLE,
    value_bool BOOLEAN,
    value_json JSON,
    is_fallback BOOLEAN NOT NULL DEFAULT FALSE,
    extraction_metadata JSON,
{_lineage_cols()}
)""",
        f"""CREATE TABLE IF NOT EXISTS fact_finding (
    finding_key VARCHAR NOT NULL,
    finding_type VARCHAR NOT NULL,
    finding_type_key VARCHAR NOT NULL,
    scope VARCHAR NOT NULL DEFAULT 'project',
    project_key VARCHAR,
    evidence_session_keys JSON,
    occurrence_count INTEGER,
    summary VARCHAR NOT NULL,
    detected_at TIMESTAMP DEFAULT current_timestamp,
{_lineage_cols()},
    {_check_in('scope', FindingScope)}
)""",
        f"""CREATE TABLE IF NOT EXISTS fact_proposal (
    proposal_key VARCHAR NOT NULL,
    target_dimension VARCHAR NOT NULL,
    target_key VARCHAR,
    target_natural_key JSON,
    proposed_content VARCHAR NOT NULL,
    proposed_version INTEGER,
    status VARCHAR NOT NULL DEFAULT 'pending',
    evidence_finding_keys JSON,
    resulting_dimension_key VARCHAR,
    reviewed_by VARCHAR,
    reviewed_at TIMESTAMP,
{_lineage_cols()},
    {_check_in('target_dimension', TargetDimension)},
    {_check_in('status', ProposalStatus)}
)""",
    ]


# Computed once at import -- enums are static, no reason to rebuild per call.
_TABLES_DDL: list[str] = _build_tables_ddl()

_VIEWS: list[str] = [
    """CREATE OR REPLACE VIEW v_feedback_by_skill AS
SELECT
    skill_key, skill_domain, skill_task_type, skill_version,
    correction_type,
    COUNT(*) as correction_count,
    MAX(created_at) as last_seen
FROM fact_feedback
GROUP BY skill_key, skill_domain, skill_task_type, skill_version, correction_type""",
    """CREATE OR REPLACE VIEW v_feedback_fields AS
SELECT skill_key, correction_type, field_name, COUNT(*) as mention_count
FROM (
    SELECT skill_key, correction_type, unnest(json_keys(correction)) as field_name
    FROM fact_feedback
)
GROUP BY skill_key, correction_type, field_name""",
    """CREATE OR REPLACE VIEW v_recurring_traces AS
SELECT
    skill_key, skill_domain, skill_task_type,
    trace_type, title,
    COUNT(*) as occurrence_count,
    COUNT(DISTINCT session_key) as session_count,
    LIST(DISTINCT session_key ORDER BY session_key) as session_keys,
    MIN(trace_key) as example_trace_key
FROM fact_trace
WHERE skill_key IS NOT NULL
GROUP BY skill_key, skill_domain, skill_task_type, trace_type, title""",
    """CREATE OR REPLACE VIEW v_recurring_trace_feedback AS
SELECT
    skill_key, skill_domain, skill_task_type,
    feedback_type, trace_title,
    COUNT(*) as occurrence_count,
    LIST(DISTINCT session_key ORDER BY session_key) as session_keys
FROM fact_trace_feedback
WHERE skill_key IS NOT NULL
GROUP BY skill_key, skill_domain, skill_task_type, feedback_type, trace_title""",
    """CREATE OR REPLACE VIEW v_skill_feedback_patterns AS
SELECT
    skill_key, skill_domain, skill_task_type, skill_version,
    correction_type,
    COUNT(*) as pattern_count,
    SUM(COUNT(*)) OVER (PARTITION BY skill_key) as total_feedback
FROM fact_feedback
GROUP BY skill_key, skill_domain, skill_task_type, skill_version, correction_type""",
    """CREATE OR REPLACE VIEW v_session_feedback_count AS
SELECT
    session_key, skill_key,
    COUNT(*) as feedback_count
FROM fact_feedback
GROUP BY session_key, skill_key""",
    # --- Couch views: SQL-only finding detectors over the ingested grain ---
    # No thresholds in the DDL: couch.py's detectors own them, passed as
    # parameters into the store's query_* methods. Views use CREATE OR
    # REPLACE so definition changes reach existing databases (IF NOT
    # EXISTS would silently pin the old definition forever).
    """CREATE OR REPLACE VIEW v_retry_loops AS
SELECT
    project_key, session_key, tool_name,
    tool_input::VARCHAR as tool_input_text,
    COUNT(*) as attempts,
    SUM(CASE WHEN is_error THEN 1 ELSE 0 END) as errors
FROM fact_tool_use
GROUP BY project_key, session_key, tool_name, tool_input::VARCHAR""",
    """CREATE OR REPLACE VIEW v_tool_error_clusters AS
SELECT
    project_key, tool_name,
    COUNT(*) as uses,
    SUM(CASE WHEN is_error THEN 1 ELSE 0 END) as errors,
    ROUND(100.0 * SUM(CASE WHEN is_error THEN 1 ELSE 0 END) / COUNT(*), 1) as error_pct,
    LIST(DISTINCT session_key) FILTER (is_error) as error_session_keys
FROM fact_tool_use
GROUP BY project_key, tool_name""",
    """CREATE OR REPLACE VIEW v_interruption_hotspots AS
SELECT
    project_key,
    COUNT(*) as interruptions,
    COUNT(DISTINCT session_key) as session_count,
    LIST(DISTINCT session_key) as session_keys
FROM fact_message
WHERE role = 'user' AND content_text LIKE '[Request interrupted by user%'
GROUP BY project_key""",
    """CREATE OR REPLACE VIEW v_permission_friction AS
SELECT
    project_key, tool_name,
    COUNT(*) as denials,
    COUNT(DISTINCT session_key) as session_count,
    LIST(DISTINCT session_key) as session_keys
FROM fact_tool_use
WHERE is_error
  AND (result_text ILIKE '%permission%'
       OR result_text ILIKE '%denied%'
       OR result_text ILIKE '%doesn''t want to proceed%'
       OR result_text ILIKE '%user rejected%')
GROUP BY project_key, tool_name""",
]

_INDEXES: list[str] = [
    # dim_skill
    "CREATE INDEX IF NOT EXISTS idx_dim_skill_domain_type_status ON dim_skill(domain, task_type, status)",
    "CREATE INDEX IF NOT EXISTS idx_dim_skill_key_current ON dim_skill(skill_key, is_current)",
    # dim_source
    "CREATE INDEX IF NOT EXISTS idx_dim_source_hash ON dim_source(source_hash)",
    "CREATE INDEX IF NOT EXISTS idx_dim_source_key_current ON dim_source(source_key, is_current)",
    # dim_rule
    "CREATE INDEX IF NOT EXISTS idx_dim_rule_key_current ON dim_rule(rule_key, is_current)",
    # dim_project
    "CREATE INDEX IF NOT EXISTS idx_dim_project_path ON dim_project(project_path)",
    # fact_session
    "CREATE INDEX IF NOT EXISTS idx_fact_session_parent ON fact_session(parent_session_key)",
    "CREATE INDEX IF NOT EXISTS idx_fact_session_skill ON fact_session(skill_key)",
    "CREATE INDEX IF NOT EXISTS idx_fact_session_status_created ON fact_session(status, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_fact_session_project ON fact_session(project_key)",
    "CREATE INDEX IF NOT EXISTS idx_fact_session_source ON fact_session(record_source)",
    # fact_trace
    "CREATE INDEX IF NOT EXISTS idx_fact_trace_session ON fact_trace(session_key)",
    "CREATE INDEX IF NOT EXISTS idx_fact_trace_parent ON fact_trace(parent_trace_key)",
    "CREATE INDEX IF NOT EXISTS idx_fact_trace_session_depth ON fact_trace(session_key, depth, sequence_order)",
    "CREATE INDEX IF NOT EXISTS idx_fact_trace_type ON fact_trace(trace_type)",
    "CREATE INDEX IF NOT EXISTS idx_fact_trace_skill ON fact_trace(skill_key)",
    # fact_extraction
    "CREATE INDEX IF NOT EXISTS idx_fact_extraction_skill_validation ON fact_extraction(skill_key, validation_status)",
    "CREATE INDEX IF NOT EXISTS idx_fact_extraction_session ON fact_extraction(session_key)",
    # fact_trace_feedback
    "CREATE INDEX IF NOT EXISTS idx_fact_trace_feedback_trace ON fact_trace_feedback(trace_key)",
    "CREATE INDEX IF NOT EXISTS idx_fact_trace_feedback_session ON fact_trace_feedback(session_key)",
    # fact_feedback
    "CREATE INDEX IF NOT EXISTS idx_fact_feedback_skill ON fact_feedback(skill_key)",
    "CREATE INDEX IF NOT EXISTS idx_fact_feedback_extraction ON fact_feedback(extraction_key)",
    # dim_sampling_config
    "CREATE INDEX IF NOT EXISTS idx_dim_sampling_config_domain ON dim_sampling_config(domain, task_type, status)",
    # fact_message / fact_tool_use (ingestion-scale tables)
    "CREATE INDEX IF NOT EXISTS idx_fact_message_session ON fact_message(session_key, sequence_num)",
    "CREATE INDEX IF NOT EXISTS idx_fact_message_key ON fact_message(message_key)",
    "CREATE INDEX IF NOT EXISTS idx_fact_tool_use_session ON fact_tool_use(session_key, sequence_num)",
    "CREATE INDEX IF NOT EXISTS idx_fact_tool_use_name ON fact_tool_use(tool_name)",
    "CREATE INDEX IF NOT EXISTS idx_fact_tool_use_project ON fact_tool_use(project_key)",
    "CREATE INDEX IF NOT EXISTS idx_fact_message_project ON fact_message(project_key)",
    "CREATE INDEX IF NOT EXISTS idx_fact_tool_use_key ON fact_tool_use(tool_use_key)",
    # fact_session_facets
    "CREATE INDEX IF NOT EXISTS idx_fact_session_facets_session ON fact_session_facets(session_key)",
    "CREATE INDEX IF NOT EXISTS idx_fact_session_facets_facet ON fact_session_facets(facet_id, prompt_version)",
    # fact_finding / fact_proposal
    "CREATE INDEX IF NOT EXISTS idx_fact_finding_type ON fact_finding(finding_type)",
    "CREATE INDEX IF NOT EXISTS idx_fact_finding_project ON fact_finding(project_key)",
    "CREATE INDEX IF NOT EXISTS idx_fact_proposal_status ON fact_proposal(status)",
    # meta_load_log
    "CREATE INDEX IF NOT EXISTS idx_meta_load_log_run ON meta_load_log(etl_run_id)",
]

_SCHEMA_VERSIONS: list[tuple[int, str]] = [
    (1, "Initial 6-table schema"),
    (2, "10-table schema: traces, trace_feedback, sampling_configs + indexes + cascades"),
    (3, "Dimensional model: dim_/fact_ tables, denormalized facts, 6 views, no FKs"),
    (4, "v0.17 meta-harness: MD5 hash keys, SCD-2 dims, registries, "
        "fact_message/tool_use/facets/finding/proposal, meta_load_log"),
    (5, "v0.19 couch: project_key conformed onto fact_message/fact_tool_use, "
        "4 SQL finding views"),
]

# Canonical table inventory, in dependency order (dependents first) so it
# doubles as reset_schema's drop order. Single source of truth: the CLI's
# `db status` and any other inventory consumer iterate this, never their
# own hand-maintained copy.
ALL_TABLES: tuple[str, ...] = (
    "fact_proposal", "fact_finding", "fact_session_facets",
    "fact_tool_use", "fact_message",
    "fact_trace_feedback", "fact_feedback", "fact_trace",
    "fact_extraction", "fact_session",
    "dim_finding_type", "dim_facet_type", "dim_project",
    "dim_source", "dim_skill", "dim_rule", "dim_sampling_config",
    "meta_load_log", "meta_schema_version",
)

ALL_VIEWS: tuple[str, ...] = (
    "v_feedback_by_skill", "v_feedback_fields",
    "v_recurring_traces", "v_recurring_trace_feedback",
    "v_skill_feedback_patterns", "v_session_feedback_count",
    "v_retry_loops", "v_tool_error_clusters",
    "v_interruption_hotspots", "v_permission_friction",
)

_ALL_DDL: list[str] = _TABLES_DDL + _VIEWS + _INDEXES


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_ddl() -> str:
    """Return the full DDL (tables + views + indexes) as a SQL string.

    Joins statements with semicolons for duckdb CLI consumption:
        freud-schema db ddl | duckdb :memory:
    """
    return ";\n".join(_ALL_DDL) + ";\n"


def connect(db_path: str | Path | None = None) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection. Use :memory: for tests."""
    path = str(db_path) if db_path else str(_DEFAULT_DB)
    try:
        return duckdb.connect(path)
    except duckdb.IOException as e:
        if "lock" in str(e).lower():
            raise duckdb.IOException(
                "Database is locked by another process (likely the DuckDB MCP server).\n"
                "Use MCP tools (execute_query) for database access during this session,\n"
                "or stop the MCP server to use the CLI."
            ) from None
        raise


def init_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Create all tables, views, indexes and seed schema versions."""
    for stmt in _ALL_DDL:
        con.execute(stmt)
    for version, description in _SCHEMA_VERSIONS:
        con.execute(
            """INSERT INTO meta_schema_version (version, description)
               SELECT ?, ?
               WHERE NOT EXISTS (SELECT 1 FROM meta_schema_version WHERE version = ?)""",
            [version, description, version],
        )


def get_schema_version(con: duckdb.DuckDBPyConnection) -> int:
    """Return the highest applied schema version, or 0 if unversioned."""
    try:
        row = con.execute(
            "SELECT MAX(version) FROM meta_schema_version"
        ).fetchone()
        return row[0] if row and row[0] is not None else 0
    except duckdb.CatalogException:
        return 0


def reset_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Drop and recreate all tables. Destructive -- for tests and resets."""
    for view in ALL_VIEWS:
        con.execute(f"DROP VIEW IF EXISTS {view}")
    for table in ALL_TABLES:  # dependency order: dependents first
        con.execute(f"DROP TABLE IF EXISTS {table}")
    init_schema(con)
