"""DuckDB schema and connection management for the experiment harness.

Dimensional model (Kimball-style): 4 dimension tables (dim_skill,
dim_source, dim_rule, dim_sampling_config), 5 fact tables (fact_session,
fact_trace, fact_extraction, fact_feedback, fact_trace_feedback), 6
analytical views, plus meta_schema_version.

Fact tables carry denormalized dimension attributes at insert time,
eliminating fact-to-fact joins. Views replace complex aggregation queries.
No FK constraints (DuckDB can't CASCADE anyway). CHECK constraints
enforce enum values.

Tables are created via CREATE TABLE IF NOT EXISTS. For breaking changes,
use reset_schema() to drop and recreate. No migration path -- this is
an experiment repo.

Enum classes in tables.py are the single source of truth for valid column
values. CHECK constraints are generated from those enums via _check_in().

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
    RuleScope,
    RuleStatus,
    SamplingStrategy,
    SessionStatus,
    SkillOrigin,
    SkillStatus,
    SourceStatus,
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


# ---------------------------------------------------------------------------
# Schema DDL -- each element is one complete statement, no semicolons
# ---------------------------------------------------------------------------

_SEQUENCES: list[str] = [
    "CREATE SEQUENCE IF NOT EXISTS dim_skill_id_seq START 1",
    "CREATE SEQUENCE IF NOT EXISTS dim_source_id_seq START 1",
    "CREATE SEQUENCE IF NOT EXISTS dim_rule_id_seq START 1",
    "CREATE SEQUENCE IF NOT EXISTS dim_sampling_config_id_seq START 1",
    "CREATE SEQUENCE IF NOT EXISTS fact_session_id_seq START 1",
    "CREATE SEQUENCE IF NOT EXISTS fact_trace_id_seq START 1",
    "CREATE SEQUENCE IF NOT EXISTS fact_extraction_id_seq START 1",
    "CREATE SEQUENCE IF NOT EXISTS fact_feedback_id_seq START 1",
    "CREATE SEQUENCE IF NOT EXISTS fact_trace_feedback_id_seq START 1",
]


def _build_tables_ddl() -> list[str]:
    """Build CREATE TABLE statements with CHECK constraints.

    Called once at module level to produce _TABLES_DDL.
    Enum classes in tables.py are the authority for valid values.
    No FK constraints -- DuckDB can't CASCADE anyway. Existence
    validation is handled in the store layer.
    """
    return [
        """CREATE TABLE IF NOT EXISTS meta_schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT current_timestamp,
    description VARCHAR
)""",
        # -- Dimensions --
        f"""CREATE TABLE IF NOT EXISTS dim_skill (
    id INTEGER DEFAULT nextval('dim_skill_id_seq'),
    domain VARCHAR NOT NULL,
    task_type VARCHAR NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    content VARCHAR NOT NULL,
    metadata JSON,
    parent_skill_id INTEGER,
    status VARCHAR NOT NULL DEFAULT 'draft',
    origin VARCHAR NOT NULL DEFAULT 'human_authored',
    activation_conditions JSON,
    created_at TIMESTAMP DEFAULT current_timestamp,
    updated_at TIMESTAMP DEFAULT current_timestamp,
    UNIQUE (domain, task_type, version),
    {_check_in('status', SkillStatus)},
    {_check_in('origin', SkillOrigin)}
)""",
        f"""CREATE TABLE IF NOT EXISTS dim_source (
    id INTEGER DEFAULT nextval('dim_source_id_seq'),
    content_path VARCHAR NOT NULL,
    media_type VARCHAR NOT NULL,
    metadata JSON,
    source_hash VARCHAR,
    status VARCHAR NOT NULL DEFAULT 'active',
    superseded_by INTEGER,
    created_at TIMESTAMP DEFAULT current_timestamp,
    updated_at TIMESTAMP DEFAULT current_timestamp,
    {_check_in('status', SourceStatus)}
)""",
        f"""CREATE TABLE IF NOT EXISTS dim_rule (
    id INTEGER DEFAULT nextval('dim_rule_id_seq'),
    scope VARCHAR NOT NULL DEFAULT 'global',
    domain VARCHAR,
    priority INTEGER NOT NULL DEFAULT 0,
    content VARCHAR NOT NULL,
    status VARCHAR NOT NULL DEFAULT 'active',
    created_at TIMESTAMP DEFAULT current_timestamp,
    updated_at TIMESTAMP DEFAULT current_timestamp,
    {_check_in('scope', RuleScope)},
    {_check_in('status', RuleStatus)}
)""",
        f"""CREATE TABLE IF NOT EXISTS dim_sampling_config (
    id INTEGER DEFAULT nextval('dim_sampling_config_id_seq'),
    domain VARCHAR,
    task_type VARCHAR,
    strategy VARCHAR NOT NULL,
    parameters JSON NOT NULL DEFAULT '{{}}'::JSON,
    max_samples INTEGER NOT NULL DEFAULT 3,
    status VARCHAR NOT NULL DEFAULT 'active',
    created_at TIMESTAMP DEFAULT current_timestamp,
    updated_at TIMESTAMP DEFAULT current_timestamp,
    {_check_in('strategy', SamplingStrategy)},
    {_check_in('status', RuleStatus)}
)""",
        # -- Facts --
        f"""CREATE TABLE IF NOT EXISTS fact_session (
    id INTEGER DEFAULT nextval('fact_session_id_seq'),
    task_description VARCHAR NOT NULL,
    task_type VARCHAR NOT NULL,
    parent_session_id INTEGER,
    agent_role VARCHAR NOT NULL DEFAULT 'subagent',
    status VARCHAR NOT NULL DEFAULT 'running',
    model_used VARCHAR,
    context_loaded JSON,
    token_usage JSON,
    result JSON,
    sampled_session_ids JSON,
    skill_id INTEGER,
    skill_domain VARCHAR,
    skill_task_type VARCHAR,
    skill_version INTEGER,
    created_at TIMESTAMP DEFAULT current_timestamp,
    completed_at TIMESTAMP,
    {_check_in('agent_role', AgentRole)},
    {_check_in('status', SessionStatus)}
)""",
        f"""CREATE TABLE IF NOT EXISTS fact_trace (
    id INTEGER DEFAULT nextval('fact_trace_id_seq'),
    session_id INTEGER NOT NULL,
    parent_trace_id INTEGER,
    trace_type VARCHAR NOT NULL,
    depth INTEGER NOT NULL DEFAULT 0,
    sequence_order INTEGER NOT NULL DEFAULT 0,
    title VARCHAR NOT NULL,
    content VARCHAR,
    reasoning VARCHAR,
    alternatives JSON,
    outcome JSON,
    child_session_id INTEGER,
    duration_ms INTEGER,
    skill_id INTEGER,
    skill_domain VARCHAR,
    skill_task_type VARCHAR,
    created_at TIMESTAMP DEFAULT current_timestamp,
    {_check_in('trace_type', TraceType)}
)""",
        f"""CREATE TABLE IF NOT EXISTS fact_extraction (
    id INTEGER DEFAULT nextval('fact_extraction_id_seq'),
    session_id INTEGER NOT NULL,
    output JSON NOT NULL,
    confidence DOUBLE,
    validation_status VARCHAR NOT NULL DEFAULT 'pending',
    validated_by VARCHAR,
    validated_at TIMESTAMP,
    source_id INTEGER NOT NULL,
    source_path VARCHAR,
    source_media_type VARCHAR,
    skill_id INTEGER NOT NULL,
    skill_domain VARCHAR,
    skill_task_type VARCHAR,
    skill_version INTEGER,
    created_at TIMESTAMP DEFAULT current_timestamp,
    {_check_in('validation_status', ValidationStatus)}
)""",
        f"""CREATE TABLE IF NOT EXISTS fact_feedback (
    id INTEGER DEFAULT nextval('fact_feedback_id_seq'),
    extraction_id INTEGER NOT NULL,
    session_id INTEGER NOT NULL,
    correction JSON NOT NULL,
    correction_type VARCHAR NOT NULL,
    notes VARCHAR,
    created_by VARCHAR,
    skill_id INTEGER NOT NULL,
    skill_domain VARCHAR,
    skill_task_type VARCHAR,
    skill_version INTEGER,
    source_id INTEGER,
    source_path VARCHAR,
    created_at TIMESTAMP DEFAULT current_timestamp,
    {_check_in('correction_type', CorrectionType)}
)""",
        f"""CREATE TABLE IF NOT EXISTS fact_trace_feedback (
    id INTEGER DEFAULT nextval('fact_trace_feedback_id_seq'),
    trace_id INTEGER NOT NULL,
    session_id INTEGER NOT NULL,
    feedback_type VARCHAR NOT NULL,
    content VARCHAR NOT NULL,
    correction JSON,
    created_by VARCHAR,
    trace_type VARCHAR,
    trace_title VARCHAR,
    skill_id INTEGER,
    skill_domain VARCHAR,
    skill_task_type VARCHAR,
    created_at TIMESTAMP DEFAULT current_timestamp,
    {_check_in('feedback_type', TraceFeedbackType)}
)""",
    ]


# Computed once at import -- enums are static, no reason to rebuild per call.
_TABLES_DDL: list[str] = _build_tables_ddl()

_VIEWS: list[str] = [
    """CREATE VIEW IF NOT EXISTS v_feedback_by_skill AS
SELECT
    skill_id, skill_domain, skill_task_type, skill_version,
    correction_type,
    COUNT(*) as correction_count,
    MAX(created_at) as last_seen
FROM fact_feedback
GROUP BY skill_id, skill_domain, skill_task_type, skill_version, correction_type""",
    """CREATE VIEW IF NOT EXISTS v_feedback_fields AS
SELECT skill_id, correction_type, field_name, COUNT(*) as mention_count
FROM (
    SELECT skill_id, correction_type, unnest(json_keys(correction)) as field_name
    FROM fact_feedback
)
GROUP BY skill_id, correction_type, field_name""",
    """CREATE VIEW IF NOT EXISTS v_recurring_traces AS
SELECT
    skill_id, skill_domain, skill_task_type,
    trace_type, title,
    COUNT(*) as occurrence_count,
    COUNT(DISTINCT session_id) as session_count,
    LIST(DISTINCT session_id ORDER BY session_id) as session_ids,
    MIN(id) as example_trace_id
FROM fact_trace
WHERE skill_id IS NOT NULL
GROUP BY skill_id, skill_domain, skill_task_type, trace_type, title""",
    """CREATE VIEW IF NOT EXISTS v_recurring_trace_feedback AS
SELECT
    skill_id, skill_domain, skill_task_type,
    feedback_type, trace_title,
    COUNT(*) as occurrence_count,
    LIST(DISTINCT session_id ORDER BY session_id) as session_ids
FROM fact_trace_feedback
WHERE skill_id IS NOT NULL
GROUP BY skill_id, skill_domain, skill_task_type, feedback_type, trace_title""",
    """CREATE VIEW IF NOT EXISTS v_skill_feedback_patterns AS
SELECT
    skill_id, skill_domain, skill_task_type, skill_version,
    correction_type,
    COUNT(*) as pattern_count,
    SUM(COUNT(*)) OVER (PARTITION BY skill_id) as total_feedback
FROM fact_feedback
GROUP BY skill_id, skill_domain, skill_task_type, skill_version, correction_type""",
    """CREATE VIEW IF NOT EXISTS v_session_feedback_count AS
SELECT
    session_id, skill_id,
    COUNT(*) as feedback_count
FROM fact_feedback
GROUP BY session_id, skill_id""",
]

_INDEXES: list[str] = [
    # dim_skill
    "CREATE INDEX IF NOT EXISTS idx_dim_skill_domain_type_status ON dim_skill(domain, task_type, status)",
    # dim_source
    "CREATE INDEX IF NOT EXISTS idx_dim_source_hash ON dim_source(source_hash)",
    # fact_session
    "CREATE INDEX IF NOT EXISTS idx_fact_session_parent ON fact_session(parent_session_id)",
    "CREATE INDEX IF NOT EXISTS idx_fact_session_skill ON fact_session(skill_id)",
    "CREATE INDEX IF NOT EXISTS idx_fact_session_status_created ON fact_session(status, created_at DESC)",
    # fact_trace
    "CREATE INDEX IF NOT EXISTS idx_fact_trace_session ON fact_trace(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_fact_trace_parent ON fact_trace(parent_trace_id)",
    "CREATE INDEX IF NOT EXISTS idx_fact_trace_session_depth ON fact_trace(session_id, depth, sequence_order)",
    "CREATE INDEX IF NOT EXISTS idx_fact_trace_type ON fact_trace(trace_type)",
    "CREATE INDEX IF NOT EXISTS idx_fact_trace_skill ON fact_trace(skill_id)",
    # fact_extraction
    "CREATE INDEX IF NOT EXISTS idx_fact_extraction_skill_validation ON fact_extraction(skill_id, validation_status)",
    "CREATE INDEX IF NOT EXISTS idx_fact_extraction_session ON fact_extraction(session_id)",
    # fact_trace_feedback
    "CREATE INDEX IF NOT EXISTS idx_fact_trace_feedback_trace ON fact_trace_feedback(trace_id)",
    "CREATE INDEX IF NOT EXISTS idx_fact_trace_feedback_session ON fact_trace_feedback(session_id)",
    # fact_feedback
    "CREATE INDEX IF NOT EXISTS idx_fact_feedback_skill ON fact_feedback(skill_id)",
    "CREATE INDEX IF NOT EXISTS idx_fact_feedback_extraction ON fact_feedback(extraction_id)",
    # dim_sampling_config
    "CREATE INDEX IF NOT EXISTS idx_dim_sampling_config_domain ON dim_sampling_config(domain, task_type, status)",
]

_INITIAL_VERSION = """INSERT INTO meta_schema_version (version, description)
SELECT 1, 'Initial 6-table schema'
WHERE NOT EXISTS (SELECT 1 FROM meta_schema_version WHERE version = 1)"""

_SCHEMA_V2 = """INSERT INTO meta_schema_version (version, description)
SELECT 2, '10-table schema: traces, trace_feedback, sampling_configs + indexes + cascades'
WHERE NOT EXISTS (SELECT 1 FROM meta_schema_version WHERE version = 2)"""

_SCHEMA_V3 = """INSERT INTO meta_schema_version (version, description)
SELECT 3, 'Dimensional model: dim_/fact_ tables, denormalized facts, 6 views, no FKs'
WHERE NOT EXISTS (SELECT 1 FROM meta_schema_version WHERE version = 3)"""

_ALL_DDL: list[str] = _SEQUENCES + _TABLES_DDL + _VIEWS + _INDEXES


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_ddl() -> str:
    """Return the full DDL (sequences + tables + views + indexes) as a SQL string.

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
    con.execute(_INITIAL_VERSION)
    con.execute(_SCHEMA_V2)
    con.execute(_SCHEMA_V3)


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
    # Drop views first
    for view in ("v_feedback_by_skill", "v_feedback_fields",
                 "v_recurring_traces", "v_recurring_trace_feedback",
                 "v_skill_feedback_patterns", "v_session_feedback_count"):
        con.execute(f"DROP VIEW IF EXISTS {view}")
    # Drop tables (dependents first)
    for table in ("fact_trace_feedback", "fact_feedback", "fact_trace",
                  "fact_extraction", "fact_session",
                  "dim_source", "dim_skill", "dim_rule",
                  "dim_sampling_config", "meta_schema_version"):
        con.execute(f"DROP TABLE IF EXISTS {table}")
    # Drop sequences
    for seq in ("fact_trace_feedback_id_seq", "fact_trace_id_seq",
                "dim_sampling_config_id_seq", "fact_feedback_id_seq",
                "fact_extraction_id_seq", "fact_session_id_seq",
                "dim_source_id_seq", "dim_skill_id_seq", "dim_rule_id_seq"):
        con.execute(f"DROP SEQUENCE IF EXISTS {seq}")
    init_schema(con)
