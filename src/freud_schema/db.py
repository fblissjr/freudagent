"""DuckDB schema and connection management for the experiment harness.

The schema implements the 7-table architecture for declarative agent
orchestration: skills, sources, extractions, sessions, feedback, rules,
plus meta_schema_version for tracking.

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
    SessionStatus,
    SkillStatus,
    SourceStatus,
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
    "CREATE SEQUENCE IF NOT EXISTS skills_id_seq START 1",
    "CREATE SEQUENCE IF NOT EXISTS sources_id_seq START 1",
    "CREATE SEQUENCE IF NOT EXISTS extractions_id_seq START 1",
    "CREATE SEQUENCE IF NOT EXISTS sessions_id_seq START 1",
    "CREATE SEQUENCE IF NOT EXISTS feedback_id_seq START 1",
    "CREATE SEQUENCE IF NOT EXISTS rules_id_seq START 1",
]


def _build_tables_ddl() -> list[str]:
    """Build CREATE TABLE statements with CHECK and FK constraints.

    Called once at module level to produce _TABLES_DDL.
    Enum classes in tables.py are the authority for valid values.
    """
    return [
        """CREATE TABLE IF NOT EXISTS meta_schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT current_timestamp,
    description VARCHAR
)""",
        f"""CREATE TABLE IF NOT EXISTS skills (
    id INTEGER PRIMARY KEY DEFAULT nextval('skills_id_seq'),
    domain VARCHAR NOT NULL,
    task_type VARCHAR NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    content VARCHAR NOT NULL,
    metadata JSON,
    parent_skill_id INTEGER REFERENCES skills(id),
    status VARCHAR NOT NULL DEFAULT 'draft',
    created_at TIMESTAMP DEFAULT current_timestamp,
    updated_at TIMESTAMP DEFAULT current_timestamp,
    {_check_in('status', SkillStatus)}
)""",
        f"""CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY DEFAULT nextval('sources_id_seq'),
    content_path VARCHAR NOT NULL,
    media_type VARCHAR NOT NULL,
    metadata JSON,
    source_hash VARCHAR,
    status VARCHAR NOT NULL DEFAULT 'active',
    superseded_by INTEGER REFERENCES sources(id),
    created_at TIMESTAMP DEFAULT current_timestamp,
    updated_at TIMESTAMP DEFAULT current_timestamp,
    {_check_in('status', SourceStatus)}
)""",
        f"""CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY DEFAULT nextval('rules_id_seq'),
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
        f"""CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY DEFAULT nextval('sessions_id_seq'),
    task_description VARCHAR NOT NULL,
    task_type VARCHAR NOT NULL,
    parent_session_id INTEGER REFERENCES sessions(id),
    agent_role VARCHAR NOT NULL DEFAULT 'subagent',
    skill_id INTEGER REFERENCES skills(id),
    context_loaded JSON,
    model_used VARCHAR,
    token_usage JSON,
    status VARCHAR NOT NULL DEFAULT 'running',
    result JSON,
    created_at TIMESTAMP DEFAULT current_timestamp,
    completed_at TIMESTAMP,
    {_check_in('agent_role', AgentRole)},
    {_check_in('status', SessionStatus)}
)""",
        f"""CREATE TABLE IF NOT EXISTS extractions (
    id INTEGER PRIMARY KEY DEFAULT nextval('extractions_id_seq'),
    source_id INTEGER NOT NULL REFERENCES sources(id),
    skill_id INTEGER NOT NULL REFERENCES skills(id),
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    output JSON NOT NULL,
    confidence DOUBLE,
    validation_status VARCHAR NOT NULL DEFAULT 'pending',
    validated_by VARCHAR,
    validated_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT current_timestamp,
    {_check_in('validation_status', ValidationStatus)}
)""",
        f"""CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY DEFAULT nextval('feedback_id_seq'),
    extraction_id INTEGER NOT NULL REFERENCES extractions(id),
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    skill_id INTEGER NOT NULL REFERENCES skills(id),
    correction JSON NOT NULL,
    correction_type VARCHAR NOT NULL,
    notes VARCHAR,
    created_by VARCHAR,
    created_at TIMESTAMP DEFAULT current_timestamp,
    {_check_in('correction_type', CorrectionType)}
)""",
    ]


# Computed once at import -- enums are static, no reason to rebuild per call.
_TABLES_DDL: list[str] = _build_tables_ddl()

_INITIAL_VERSION = """INSERT INTO meta_schema_version (version, description)
SELECT 1, 'Initial 6-table schema'
WHERE NOT EXISTS (SELECT 1 FROM meta_schema_version WHERE version = 1)"""

_ALL_DDL: list[str] = _SEQUENCES + _TABLES_DDL


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_ddl() -> str:
    """Return the full DDL (sequences + tables) as a SQL string.

    Joins statements with semicolons for duckdb CLI consumption:
        freud-schema db ddl | duckdb :memory:
    """
    return ";\n".join(_ALL_DDL) + ";\n"


def connect(db_path: str | Path | None = None) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection. Use :memory: for tests."""
    path = str(db_path) if db_path else str(_DEFAULT_DB)
    return duckdb.connect(path)


def init_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Create all tables and seed version 1."""
    for stmt in _ALL_DDL:
        con.execute(stmt)
    con.execute(_INITIAL_VERSION)


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
    for table in ("feedback", "extractions", "sessions", "sources", "skills",
                  "rules", "meta_schema_version"):
        con.execute(f"DROP TABLE IF EXISTS {table}")
    for seq in ("feedback_id_seq", "extractions_id_seq", "sessions_id_seq",
                "sources_id_seq", "skills_id_seq", "rules_id_seq"):
        con.execute(f"DROP SEQUENCE IF EXISTS {seq}")
    init_schema(con)
