"""CRUD operations and retrieval queries for the experiment harness.

All queries are parameterized. JSON fields are serialized with orjson
on write and deserialized on read.
"""

from __future__ import annotations

import duckdb
import orjson

from freud_schema.db import init_schema
from freud_schema.tables import Extraction, Feedback, Rule, Session, Skill, Source


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
        row = self.con.execute(
            "SELECT * FROM skills WHERE id = ?", [skill_id]
        ).fetchone()
        if row is None:
            return None
        return self._row_to_skill(row)

    def get_active_skill(self, domain: str, task_type: str) -> Skill | None:
        """Find the latest active skill for a domain + task_type."""
        row = self.con.execute(
            """SELECT * FROM skills
               WHERE domain = ? AND task_type = ? AND status = 'active'
               ORDER BY version DESC LIMIT 1""",
            [domain, task_type],
        ).fetchone()
        if row is None:
            return None
        return self._row_to_skill(row)

    def list_skills(self, domain: str | None = None, status: str | None = None) -> list[Skill]:
        query = "SELECT * FROM skills WHERE 1=1"
        params: list = []
        if domain:
            query += " AND domain = ?"
            params.append(domain)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY domain, task_type, version DESC"
        rows = self.con.execute(query, params).fetchall()
        return [self._row_to_skill(r) for r in rows]

    def activate_skill(self, skill_id: int) -> None:
        self.con.execute(
            "UPDATE skills SET status = 'active', updated_at = current_timestamp WHERE id = ?",
            [skill_id],
        )

    def deprecate_skill(self, skill_id: int) -> None:
        self.con.execute(
            "UPDATE skills SET status = 'deprecated', updated_at = current_timestamp WHERE id = ?",
            [skill_id],
        )

    def _row_to_skill(self, row: tuple) -> Skill:
        return Skill(
            id=row[0], domain=row[1], task_type=row[2], version=row[3],
            content=row[4], metadata=_from_json(row[5]),
            parent_skill_id=row[6], status=row[7],
            created_at=row[8], updated_at=row[9],
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
        row = self.con.execute(
            "SELECT * FROM sources WHERE id = ?", [source_id]
        ).fetchone()
        if row is None:
            return None
        return self._row_to_source(row)

    def list_sources(self, status: str | None = None) -> list[Source]:
        query = "SELECT * FROM sources WHERE 1=1"
        params: list = []
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC"
        rows = self.con.execute(query, params).fetchall()
        return [self._row_to_source(r) for r in rows]

    def _row_to_source(self, row: tuple) -> Source:
        return Source(
            id=row[0], content_path=row[1], media_type=row[2],
            metadata=_from_json(row[3]), source_hash=row[4],
            status=row[5], superseded_by=row[6],
            created_at=row[7], updated_at=row[8],
        )

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
        self, session_id: int, *, status: str = "completed", result: dict | None = None
    ) -> None:
        self.con.execute(
            """UPDATE sessions SET status = ?, result = ?,
               completed_at = current_timestamp WHERE id = ?""",
            [status, _json(result), session_id],
        )

    def get_session(self, session_id: int) -> Session | None:
        row = self.con.execute(
            "SELECT * FROM sessions WHERE id = ?", [session_id]
        ).fetchone()
        if row is None:
            return None
        return self._row_to_session(row)

    def list_sessions(self, status: str | None = None, parent_id: int | None = None) -> list[Session]:
        query = "SELECT * FROM sessions WHERE 1=1"
        params: list = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if parent_id is not None:
            query += " AND parent_session_id = ?"
            params.append(parent_id)
        query += " ORDER BY created_at DESC"
        rows = self.con.execute(query, params).fetchall()
        return [self._row_to_session(r) for r in rows]

    def _row_to_session(self, row: tuple) -> Session:
        return Session(
            id=row[0], task_description=row[1], task_type=row[2],
            parent_session_id=row[3], agent_role=row[4], skill_id=row[5],
            context_loaded=_from_json(row[6]), model_used=row[7],
            token_usage=_from_json(row[8]), status=row[9],
            result=_from_json(row[10]), created_at=row[11], completed_at=row[12],
        )

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
        row = self.con.execute(
            "SELECT * FROM extractions WHERE id = ?", [extraction_id]
        ).fetchone()
        if row is None:
            return None
        return self._row_to_extraction(row)

    def update_validation(
        self, extraction_id: int, *, status: str, validated_by: str | None = None
    ) -> None:
        self.con.execute(
            """UPDATE extractions SET validation_status = ?, validated_by = ?,
               validated_at = current_timestamp WHERE id = ?""",
            [status, validated_by, extraction_id],
        )

    def list_extractions(
        self,
        skill_id: int | None = None,
        validation_status: str | None = None,
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
        rows = self.con.execute(query, params).fetchall()
        return [self._row_to_extraction(r) for r in rows]

    def get_validated_extractions(self, skill_id: int, limit: int = 10) -> list[Extraction]:
        """Retrieval query: find prior validated extractions for a skill."""
        return self.list_extractions(
            skill_id=skill_id, validation_status="validated", limit=limit
        )

    def _row_to_extraction(self, row: tuple) -> Extraction:
        return Extraction(
            id=row[0], source_id=row[1], skill_id=row[2], session_id=row[3],
            output=_from_json(row[4]), confidence=row[5],
            validation_status=row[6], validated_by=row[7],
            validated_at=row[8], created_at=row[9],
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
        rows = self.con.execute(query, params).fetchall()
        return [self._row_to_feedback(r) for r in rows]

    def aggregate_feedback(self, skill_id: int) -> list[tuple[str, int]]:
        """Count corrections by type for a skill -- the flywheel signal."""
        rows = self.con.execute(
            """SELECT correction_type, COUNT(*) as cnt
               FROM feedback WHERE skill_id = ?
               GROUP BY correction_type ORDER BY cnt DESC""",
            [skill_id],
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    def _row_to_feedback(self, row: tuple) -> Feedback:
        return Feedback(
            id=row[0], extraction_id=row[1], session_id=row[2], skill_id=row[3],
            correction=_from_json(row[4]), correction_type=row[5],
            notes=row[6], created_by=row[7], created_at=row[8],
        )

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
        if domain:
            rows = self.con.execute(
                """SELECT * FROM rules
                   WHERE status = 'active' AND (scope = 'global' OR domain = ?)
                   ORDER BY priority DESC""",
                [domain],
            ).fetchall()
        else:
            rows = self.con.execute(
                """SELECT * FROM rules
                   WHERE status = 'active' AND scope = 'global'
                   ORDER BY priority DESC""",
            ).fetchall()
        return [self._row_to_rule(r) for r in rows]

    def list_rules(self) -> list[Rule]:
        rows = self.con.execute(
            "SELECT * FROM rules ORDER BY scope, domain, priority DESC"
        ).fetchall()
        return [self._row_to_rule(r) for r in rows]

    def _row_to_rule(self, row: tuple) -> Rule:
        return Rule(
            id=row[0], scope=row[1], domain=row[2], priority=row[3],
            content=row[4], status=row[5], created_at=row[6], updated_at=row[7],
        )
