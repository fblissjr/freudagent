"""DuckDB schema and connection management for the experiment harness.

The schema implements the 6-table architecture for declarative agent
orchestration: skills, sources, extractions, sessions, feedback, rules.

Schema versioning follows the agent-state pattern: a meta_schema_version
table tracks applied versions, and migrations use idempotent DDL
(CREATE IF NOT EXISTS, ALTER TABLE ... ADD COLUMN IF NOT EXISTS).
"""

from __future__ import annotations

from pathlib import Path

import duckdb

_DEFAULT_DB = Path(__file__).resolve().parent.parent.parent / "data" / "freudagent.duckdb"

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_SEQUENCES = """
CREATE SEQUENCE IF NOT EXISTS skills_id_seq START 1;
CREATE SEQUENCE IF NOT EXISTS sources_id_seq START 1;
CREATE SEQUENCE IF NOT EXISTS extractions_id_seq START 1;
CREATE SEQUENCE IF NOT EXISTS sessions_id_seq START 1;
CREATE SEQUENCE IF NOT EXISTS feedback_id_seq START 1;
CREATE SEQUENCE IF NOT EXISTS rules_id_seq START 1;
"""

_TABLES = """
CREATE TABLE IF NOT EXISTS meta_schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT current_timestamp,
    description VARCHAR
);

CREATE TABLE IF NOT EXISTS skills (
    id INTEGER PRIMARY KEY DEFAULT nextval('skills_id_seq'),
    domain VARCHAR NOT NULL,
    task_type VARCHAR NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    content VARCHAR NOT NULL,
    metadata JSON,
    parent_skill_id INTEGER,
    status VARCHAR NOT NULL DEFAULT 'draft',
    created_at TIMESTAMP DEFAULT current_timestamp,
    updated_at TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY DEFAULT nextval('sources_id_seq'),
    content_path VARCHAR NOT NULL,
    media_type VARCHAR NOT NULL,
    metadata JSON,
    source_hash VARCHAR,
    status VARCHAR NOT NULL DEFAULT 'active',
    superseded_by INTEGER,
    created_at TIMESTAMP DEFAULT current_timestamp,
    updated_at TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY DEFAULT nextval('sessions_id_seq'),
    task_description VARCHAR NOT NULL,
    task_type VARCHAR NOT NULL,
    parent_session_id INTEGER,
    agent_role VARCHAR NOT NULL DEFAULT 'subagent',
    skill_id INTEGER,
    context_loaded JSON,
    model_used VARCHAR,
    token_usage JSON,
    status VARCHAR NOT NULL DEFAULT 'running',
    result JSON,
    created_at TIMESTAMP DEFAULT current_timestamp,
    completed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS extractions (
    id INTEGER PRIMARY KEY DEFAULT nextval('extractions_id_seq'),
    source_id INTEGER NOT NULL,
    skill_id INTEGER NOT NULL,
    session_id INTEGER NOT NULL,
    output JSON NOT NULL,
    confidence DOUBLE,
    validation_status VARCHAR NOT NULL DEFAULT 'pending',
    validated_by VARCHAR,
    validated_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY DEFAULT nextval('feedback_id_seq'),
    extraction_id INTEGER NOT NULL,
    session_id INTEGER NOT NULL,
    skill_id INTEGER NOT NULL,
    correction JSON NOT NULL,
    correction_type VARCHAR NOT NULL,
    notes VARCHAR,
    created_by VARCHAR,
    created_at TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY DEFAULT nextval('rules_id_seq'),
    scope VARCHAR NOT NULL DEFAULT 'global',
    domain VARCHAR,
    priority INTEGER NOT NULL DEFAULT 0,
    content VARCHAR NOT NULL,
    status VARCHAR NOT NULL DEFAULT 'active',
    created_at TIMESTAMP DEFAULT current_timestamp,
    updated_at TIMESTAMP DEFAULT current_timestamp
);
"""

_INITIAL_VERSION = """
INSERT INTO meta_schema_version (version, description)
SELECT 1, 'Initial 6-table schema'
WHERE NOT EXISTS (SELECT 1 FROM meta_schema_version WHERE version = 1);
"""

# Future migrations: (version, description, sql) tuples.
_MIGRATIONS: list[tuple[int, str, str]] = []


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------


def connect(db_path: str | Path | None = None) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection. Use :memory: for tests."""
    path = str(db_path) if db_path else str(_DEFAULT_DB)
    return duckdb.connect(path)


def init_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Create all tables, seed version 1, and run pending migrations."""
    for stmt in _SEQUENCES.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            con.execute(stmt)
    for stmt in _TABLES.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            con.execute(stmt)

    # Seed initial version
    con.execute(_INITIAL_VERSION)

    # Run any pending migrations
    _run_migrations(con)


def _run_migrations(con: duckdb.DuckDBPyConnection) -> None:
    """Apply migrations that haven't been recorded yet."""
    if not _MIGRATIONS:
        return
    applied = {
        row[0]
        for row in con.execute("SELECT version FROM meta_schema_version").fetchall()
    }
    for version, description, sql in _MIGRATIONS:
        if version in applied:
            continue
        con.execute(sql)
        con.execute(
            "INSERT INTO meta_schema_version (version, description) VALUES (?, ?)",
            [version, description],
        )
        applied.add(version)


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
