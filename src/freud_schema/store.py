"""CRUD operations and retrieval queries for the experiment harness.

All queries are parameterized. JSON fields are serialized with orjson
on write and deserialized on read via automatic type detection from
DuckDB's cursor.description (type_code == "JSON").
"""

from __future__ import annotations

import duckdb
import orjson

from freud_schema.db import init_schema
from freud_schema.tables import (
    Extraction,
    Feedback,
    Rule,
    RuleScope,
    RuleStatus,
    Session,
    SessionStatus,
    Skill,
    SkillStatus,
    Source,
    SourceStatus,
    ValidationStatus,
)


def _json(val: dict | None) -> str | None:
    """Serialize a dict to JSON string for DuckDB, or None."""
    if val is None:
        return None
    return orjson.dumps(val).decode()


def _from_json(val: str | None) -> dict | None:
    """Deserialize a JSON string from DuckDB, or None."""
    if val is None:
        return None
    return orjson.loads(val)


class ExperimentStore:
    """Data access layer for the experiment harness."""

    def __init__(self, con: duckdb.DuckDBPyConnection):
        self.con = con
        init_schema(con)

    # -------------------------------------------------------------------
    # Generic row conversion
    # -------------------------------------------------------------------

    @staticmethod
    def _row_to_dict(description: list, row: tuple) -> dict:
        """Convert a DuckDB row to a dict, deserializing JSON columns.

        Uses cursor.description to map by column name (not position).
        JSON columns detected via DuckDBPyType == "JSON" and deserialized
        with orjson. All other types pass through as-is.
        """
        d = {}
        for col_desc, value in zip(description, row):
            if value is not None and col_desc[1] == "JSON":
                value = _from_json(value)
            d[col_desc[0]] = value
        return d

    def _fetchone(self, sql: str, params: list | None = None) -> dict | None:
        result = self.con.execute(sql, params or [])
        row = result.fetchone()
        if row is None:
            return None
        return self._row_to_dict(result.description, row)

    def _fetchall(self, sql: str, params: list | None = None) -> list[dict]:
        result = self.con.execute(sql, params or [])
        desc = result.description
        return [self._row_to_dict(desc, r) for r in result.fetchall()]

    # -------------------------------------------------------------------
    # Skills
    # -------------------------------------------------------------------

    def insert_skill(self, skill: Skill) -> int:
        result = self.con.execute(
            """INSERT INTO skills (domain, task_type, version, content, metadata,
               parent_skill_id, status)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               RETURNING id""",
            [skill.domain, skill.task_type, skill.version, skill.content,
             _json(skill.metadata), skill.parent_skill_id, skill.status],
        ).fetchone()
        return result[0]

    def get_skill(self, skill_id: int) -> Skill | None:
        d = self._fetchone("SELECT * FROM skills WHERE id = ?", [skill_id])
        return Skill(**d) if d else None

    def get_active_skill(self, domain: str, task_type: str) -> Skill | None:
        """Find the latest active skill for a domain + task_type."""
        d = self._fetchone(
            """SELECT * FROM skills
               WHERE domain = ? AND task_type = ? AND status = ?
               ORDER BY version DESC LIMIT 1""",
            [domain, task_type, SkillStatus.ACTIVE],
        )
        return Skill(**d) if d else None

    def list_skills(
        self, domain: str | None = None, status: SkillStatus | None = None
    ) -> list[Skill]:
        query = "SELECT * FROM skills WHERE 1=1"
        params: list = []
        if domain:
            query += " AND domain = ?"
            params.append(domain)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY domain, task_type, version DESC"
        return [Skill(**d) for d in self._fetchall(query, params)]

    def activate_skill(self, skill_id: int) -> None:
        self.con.execute(
            "UPDATE skills SET status = ?, updated_at = current_timestamp WHERE id = ?",
            [SkillStatus.ACTIVE, skill_id],
        )

    def deprecate_skill(self, skill_id: int) -> None:
        self.con.execute(
            "UPDATE skills SET status = ?, updated_at = current_timestamp WHERE id = ?",
            [SkillStatus.DEPRECATED, skill_id],
        )

    # -------------------------------------------------------------------
    # Sources
    # -------------------------------------------------------------------

    def insert_source(self, source: Source) -> int:
        result = self.con.execute(
            """INSERT INTO sources (content_path, media_type, metadata, source_hash, status)
               VALUES (?, ?, ?, ?, ?)
               RETURNING id""",
            [source.content_path, source.media_type, _json(source.metadata),
             source.source_hash, source.status],
        ).fetchone()
        return result[0]

    def get_source(self, source_id: int) -> Source | None:
        d = self._fetchone("SELECT * FROM sources WHERE id = ?", [source_id])
        return Source(**d) if d else None

    def get_sources_by_ids(self, source_ids: list[int]) -> dict[int, Source]:
        """Bulk fetch sources by ID. Returns {id: Source} map."""
        if not source_ids:
            return {}
        placeholders = ", ".join("?" for _ in source_ids)
        return {
            d["id"]: Source(**d)
            for d in self._fetchall(
                f"SELECT * FROM sources WHERE id IN ({placeholders})",
                source_ids,
            )
        }

    def list_sources(self, status: SourceStatus | None = None) -> list[Source]:
        query = "SELECT * FROM sources WHERE 1=1"
        params: list = []
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC"
        return [Source(**d) for d in self._fetchall(query, params)]

    # -------------------------------------------------------------------
    # Sessions
    # -------------------------------------------------------------------

    def insert_session(self, session: Session) -> int:
        result = self.con.execute(
            """INSERT INTO sessions (task_description, task_type, parent_session_id,
               agent_role, skill_id, context_loaded, model_used, token_usage, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               RETURNING id""",
            [session.task_description, session.task_type, session.parent_session_id,
             session.agent_role, session.skill_id, _json(session.context_loaded),
             session.model_used, _json(session.token_usage), session.status],
        ).fetchone()
        return result[0]

    def complete_session(
        self,
        session_id: int,
        *,
        status: SessionStatus = SessionStatus.COMPLETED,
        result: dict | None = None,
    ) -> None:
        self.con.execute(
            """UPDATE sessions SET status = ?, result = ?,
               completed_at = current_timestamp WHERE id = ?""",
            [status, _json(result), session_id],
        )

    def get_session(self, session_id: int) -> Session | None:
        d = self._fetchone("SELECT * FROM sessions WHERE id = ?", [session_id])
        return Session(**d) if d else None

    def list_sessions(
        self,
        status: SessionStatus | None = None,
        parent_id: int | None = None,
        limit: int | None = None,
    ) -> list[Session]:
        query = "SELECT * FROM sessions WHERE 1=1"
        params: list = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if parent_id is not None:
            query += " AND parent_session_id = ?"
            params.append(parent_id)
        query += " ORDER BY created_at DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        return [Session(**d) for d in self._fetchall(query, params)]

    # -------------------------------------------------------------------
    # Extractions
    # -------------------------------------------------------------------

    def insert_extraction(self, extraction: Extraction) -> int:
        result = self.con.execute(
            """INSERT INTO extractions (source_id, skill_id, session_id, output,
               confidence, validation_status)
               VALUES (?, ?, ?, ?, ?, ?)
               RETURNING id""",
            [extraction.source_id, extraction.skill_id, extraction.session_id,
             _json(extraction.output), extraction.confidence,
             extraction.validation_status],
        ).fetchone()
        return result[0]

    def get_extraction(self, extraction_id: int) -> Extraction | None:
        d = self._fetchone("SELECT * FROM extractions WHERE id = ?", [extraction_id])
        return Extraction(**d) if d else None

    def update_validation(
        self,
        extraction_id: int,
        *,
        status: ValidationStatus,
        validated_by: str | None = None,
    ) -> None:
        self.con.execute(
            """UPDATE extractions SET validation_status = ?, validated_by = ?,
               validated_at = current_timestamp WHERE id = ?""",
            [status, validated_by, extraction_id],
        )

    def list_extractions(
        self,
        skill_id: int | None = None,
        validation_status: ValidationStatus | None = None,
        limit: int = 50,
    ) -> list[Extraction]:
        query = "SELECT * FROM extractions WHERE 1=1"
        params: list = []
        if skill_id is not None:
            query += " AND skill_id = ?"
            params.append(skill_id)
        if validation_status:
            query += " AND validation_status = ?"
            params.append(validation_status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return [Extraction(**d) for d in self._fetchall(query, params)]

    def get_validated_extractions(self, skill_id: int, limit: int = 10) -> list[Extraction]:
        """Retrieval query: find prior validated extractions for a skill."""
        return self.list_extractions(
            skill_id=skill_id, validation_status=ValidationStatus.VALIDATED, limit=limit
        )

    # -------------------------------------------------------------------
    # Feedback
    # -------------------------------------------------------------------

    def insert_feedback(self, fb: Feedback) -> int:
        result = self.con.execute(
            """INSERT INTO feedback (extraction_id, session_id, skill_id,
               correction, correction_type, notes, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               RETURNING id""",
            [fb.extraction_id, fb.session_id, fb.skill_id,
             _json(fb.correction), fb.correction_type, fb.notes, fb.created_by],
        ).fetchone()
        return result[0]

    def list_feedback(self, skill_id: int | None = None) -> list[Feedback]:
        query = "SELECT * FROM feedback WHERE 1=1"
        params: list = []
        if skill_id is not None:
            query += " AND skill_id = ?"
            params.append(skill_id)
        query += " ORDER BY created_at DESC"
        return [Feedback(**d) for d in self._fetchall(query, params)]

    def aggregate_feedback(self, skill_id: int) -> list[tuple[str, int]]:
        """Count corrections by type for a skill -- the flywheel signal."""
        rows = self.con.execute(
            """SELECT correction_type, COUNT(*) as cnt
               FROM feedback WHERE skill_id = ?
               GROUP BY correction_type ORDER BY cnt DESC""",
            [skill_id],
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    # -------------------------------------------------------------------
    # Rules
    # -------------------------------------------------------------------

    def insert_rule(self, rule: Rule) -> int:
        result = self.con.execute(
            """INSERT INTO rules (scope, domain, priority, content, status)
               VALUES (?, ?, ?, ?, ?)
               RETURNING id""",
            [rule.scope, rule.domain, rule.priority, rule.content, rule.status],
        ).fetchone()
        return result[0]

    def get_rules(self, domain: str | None = None) -> list[Rule]:
        """Load active rules: global + domain-specific, ordered by priority."""
        query = "SELECT * FROM rules WHERE status = ?"
        params: list = [RuleStatus.ACTIVE]
        if domain:
            query += " AND (scope = ? OR domain = ?)"
            params.extend([RuleScope.GLOBAL, domain])
        else:
            query += " AND scope = ?"
            params.append(RuleScope.GLOBAL)
        query += " ORDER BY priority DESC"
        return [Rule(**d) for d in self._fetchall(query, params)]

    def list_rules(self) -> list[Rule]:
        return [Rule(**d) for d in self._fetchall(
            "SELECT * FROM rules ORDER BY scope, domain, priority DESC"
        )]
