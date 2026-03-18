"""CRUD operations and retrieval queries for the experiment harness.

Dimensional model: dimension tables (dim_*) hold reference data, fact
tables (fact_*) hold events with denormalized dimension attributes.
Views handle aggregation queries. No FK constraints -- existence
validation done in the store layer.

All queries are parameterized. JSON fields are serialized with orjson
on write and deserialized on read via automatic type detection from
DuckDB's cursor.description (type_code == "JSON").
"""

from __future__ import annotations

from datetime import datetime

import duckdb
import orjson

from freud_schema.db import init_schema
from freud_schema.tables import (
    Extraction,
    Feedback,
    Rule,
    RuleScope,
    RuleStatus,
    SamplingConfig,
    SamplingStrategy,
    Session,
    SessionStatus,
    Skill,
    SkillOrigin,
    SkillStatus,
    Source,
    SourceStatus,
    Trace,
    TraceFeedback,
    TraceFeedbackType,
    TraceType,
    ValidationStatus,
)


def _json(val: dict | list | None) -> str | None:
    """Serialize a dict or list to JSON string for DuckDB, or None."""
    if val is None:
        return None
    return orjson.dumps(val).decode()


def _from_json(val: str | None) -> dict | list | None:
    """Deserialize a JSON string from DuckDB, or None."""
    if val is None:
        return None
    return orjson.loads(val)


class ExperimentStore:
    """Data access layer for the experiment harness."""

    def __init__(self, con: duckdb.DuckDBPyConnection):
        self.con = con
        self._session_skill_cache: dict[int, dict] = {}
        init_schema(con)

    def close(self) -> None:
        self.con.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

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
    # Internal: existence validation (replaces FK enforcement)
    # -------------------------------------------------------------------

    def _require(self, table: str, entity_id: int, label: str) -> None:
        """Raise ValueError if a referenced entity doesn't exist.

        Called at insert boundaries to catch orphaned references that
        FKs would have rejected. Only used when no denormalization fetch
        will validate the reference as a side effect.
        """
        row = self.con.execute(
            f"SELECT 1 FROM {table} WHERE id = ?", [entity_id],
        ).fetchone()
        if row is None:
            raise ValueError(f"{label} {entity_id} not found")

    def _resolve_skill_attrs(
        self,
        skill_id: int,
        domain: str | None = None,
        task_type: str | None = None,
        version: int | None = None,
    ) -> tuple[str | None, str | None, int | None]:
        """Resolve skill domain/task_type/version, fetching from dim_skill if needed.

        Validates existence: raises ValueError if skill_id doesn't exist.
        Skips the fetch if domain is already provided (caller pre-filled).
        """
        if domain is not None:
            return domain, task_type, version
        skill = self.get_skill(skill_id)
        if skill is None:
            raise ValueError(f"Skill {skill_id} not found")
        return skill.domain, skill.task_type, skill.version

    # -------------------------------------------------------------------
    # Internal: session skill attribute cache (for bulk trace inserts)
    # -------------------------------------------------------------------

    def _get_session_skill_attrs(self, session_id: int) -> dict | None:
        """Get session's skill attributes, cached for bulk trace inserts."""
        if session_id in self._session_skill_cache:
            return self._session_skill_cache[session_id]
        d = self._fetchone(
            "SELECT skill_id, skill_domain, skill_task_type FROM fact_session WHERE id = ?",
            [session_id],
        )
        if d:
            self._session_skill_cache[session_id] = d
        return d

    # -------------------------------------------------------------------
    # Skills (dim_skill)
    # -------------------------------------------------------------------

    def insert_skill(self, skill: Skill) -> int:
        result = self.con.execute(
            """INSERT INTO dim_skill (domain, task_type, version, content, metadata,
               parent_skill_id, status, origin, activation_conditions)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               RETURNING id""",
            [skill.domain, skill.task_type, skill.version, skill.content,
             _json(skill.metadata), skill.parent_skill_id, skill.status,
             skill.origin, _json(skill.activation_conditions)],
        ).fetchone()
        return result[0]

    def get_skill(self, skill_id: int) -> Skill | None:
        d = self._fetchone("SELECT * FROM dim_skill WHERE id = ?", [skill_id])
        return Skill(**d) if d else None

    def get_active_skill(self, domain: str, task_type: str) -> Skill | None:
        """Find the latest active skill for a domain + task_type."""
        d = self._fetchone(
            """SELECT * FROM dim_skill
               WHERE domain = ? AND task_type = ? AND status = ?
               ORDER BY version DESC LIMIT 1""",
            [domain, task_type, SkillStatus.ACTIVE],
        )
        return Skill(**d) if d else None

    def list_skills(
        self,
        domain: str | None = None,
        status: SkillStatus | None = None,
        origin: SkillOrigin | None = None,
        parent_skill_id: int | None = None,
    ) -> list[Skill]:
        query = "SELECT * FROM dim_skill WHERE 1=1"
        params: list = []
        if domain:
            query += " AND domain = ?"
            params.append(domain)
        if status:
            query += " AND status = ?"
            params.append(status)
        if origin:
            query += " AND origin = ?"
            params.append(origin)
        if parent_skill_id is not None:
            query += " AND parent_skill_id = ?"
            params.append(parent_skill_id)
        query += " ORDER BY domain, task_type, version DESC"
        return [Skill(**d) for d in self._fetchall(query, params)]

    def activate_skill(self, skill_id: int) -> None:
        self.con.execute(
            "UPDATE dim_skill SET status = ?, updated_at = current_timestamp WHERE id = ?",
            [SkillStatus.ACTIVE, skill_id],
        )

    def deprecate_skill(self, skill_id: int) -> None:
        self.con.execute(
            "UPDATE dim_skill SET status = ?, updated_at = current_timestamp WHERE id = ?",
            [SkillStatus.DEPRECATED, skill_id],
        )

    def get_active_sub_skills(self, parent_skill_id: int) -> list[Skill]:
        """Get active skills with the given parent_skill_id."""
        return [Skill(**d) for d in self._fetchall(
            """SELECT * FROM dim_skill
               WHERE parent_skill_id = ? AND status = ?
               ORDER BY version DESC""",
            [parent_skill_id, SkillStatus.ACTIVE],
        )]

    def insert_derived_skill(
        self,
        skill: Skill,
        *,
        source_session_ids: list[int],
        source_trace_ids: list[int],
    ) -> int:
        """Insert a data-derived skill with provenance tracking."""
        skill = skill.model_copy(update={
            "origin": SkillOrigin.DATA_DERIVED,
            "metadata": {
                **(skill.metadata or {}),
                "derived_from": {
                    "session_ids": source_session_ids,
                    "trace_ids": source_trace_ids,
                },
            },
        })
        return self.insert_skill(skill)

    # -------------------------------------------------------------------
    # Sources (dim_source)
    # -------------------------------------------------------------------

    def insert_source(self, source: Source) -> int:
        result = self.con.execute(
            """INSERT INTO dim_source (content_path, media_type, metadata, source_hash, status)
               VALUES (?, ?, ?, ?, ?)
               RETURNING id""",
            [source.content_path, source.media_type, _json(source.metadata),
             source.source_hash, source.status],
        ).fetchone()
        return result[0]

    def get_source(self, source_id: int) -> Source | None:
        d = self._fetchone("SELECT * FROM dim_source WHERE id = ?", [source_id])
        return Source(**d) if d else None

    def get_sources_by_ids(self, source_ids: list[int]) -> dict[int, Source]:
        """Bulk fetch sources by ID. Returns {id: Source} map."""
        if not source_ids:
            return {}
        placeholders = ", ".join("?" for _ in source_ids)
        return {
            d["id"]: Source(**d)
            for d in self._fetchall(
                f"SELECT * FROM dim_source WHERE id IN ({placeholders})",
                source_ids,
            )
        }

    def list_sources(self, status: SourceStatus | None = None) -> list[Source]:
        query = "SELECT * FROM dim_source WHERE 1=1"
        params: list = []
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC"
        return [Source(**d) for d in self._fetchall(query, params)]

    # -------------------------------------------------------------------
    # Sessions (fact_session)
    # -------------------------------------------------------------------

    def insert_session(self, session: Session) -> int:
        # Denormalize skill attributes (validates existence as side effect)
        skill_domain = session.skill_domain
        skill_task_type = session.skill_task_type
        skill_version = session.skill_version
        if session.skill_id is not None:
            skill_domain, skill_task_type, skill_version = self._resolve_skill_attrs(
                session.skill_id, skill_domain, skill_task_type, skill_version,
            )
        result = self.con.execute(
            """INSERT INTO fact_session (task_description, task_type, parent_session_id,
               agent_role, skill_id, skill_domain, skill_task_type, skill_version,
               context_loaded, model_used, token_usage, status, sampled_session_ids)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               RETURNING id""",
            [session.task_description, session.task_type, session.parent_session_id,
             session.agent_role, session.skill_id, skill_domain, skill_task_type,
             skill_version, _json(session.context_loaded), session.model_used,
             _json(session.token_usage), session.status,
             _json(session.sampled_session_ids)],
        ).fetchone()
        sid = result[0]
        # Cache skill attrs for subsequent trace inserts
        self._session_skill_cache[sid] = {
            "skill_id": session.skill_id,
            "skill_domain": skill_domain,
            "skill_task_type": skill_task_type,
        }
        return sid

    def complete_session(
        self,
        session_id: int,
        *,
        status: SessionStatus = SessionStatus.COMPLETED,
        result: dict | None = None,
        token_usage: dict | None = None,
    ) -> None:
        self.con.execute(
            """UPDATE fact_session SET status = ?, result = ?, token_usage = ?,
               completed_at = current_timestamp WHERE id = ?""",
            [status, _json(result), _json(token_usage), session_id],
        )

    def update_session_model(self, session_id: int, model_used: str) -> None:
        """Update the model_used field from a provider response."""
        self.con.execute(
            "UPDATE fact_session SET model_used = ? WHERE id = ?",
            [model_used, session_id],
        )

    def get_session(self, session_id: int) -> Session | None:
        d = self._fetchone("SELECT * FROM fact_session WHERE id = ?", [session_id])
        return Session(**d) if d else None

    def list_sessions(
        self,
        status: SessionStatus | None = None,
        parent_id: int | None = None,
        skill_id: int | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        limit: int | None = None,
    ) -> list[Session]:
        query = "SELECT * FROM fact_session WHERE 1=1"
        params: list = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if parent_id is not None:
            query += " AND parent_session_id = ?"
            params.append(parent_id)
        if skill_id is not None:
            query += " AND skill_id = ?"
            params.append(skill_id)
        if created_after is not None:
            query += " AND created_at >= ?"
            params.append(created_after)
        if created_before is not None:
            query += " AND created_at <= ?"
            params.append(created_before)
        query += " ORDER BY created_at DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        return [Session(**d) for d in self._fetchall(query, params)]

    # -------------------------------------------------------------------
    # Traces (fact_trace)
    # -------------------------------------------------------------------

    def insert_trace(self, trace: Trace) -> int:
        """Insert a trace node. Denormalizes skill attrs from session."""
        skill_id = trace.skill_id
        skill_domain = trace.skill_domain
        skill_task_type = trace.skill_task_type
        if skill_id is None:
            attrs = self._get_session_skill_attrs(trace.session_id)
            if attrs is None:
                raise ValueError(f"Session {trace.session_id} not found")
            skill_id = attrs.get("skill_id")
            skill_domain = attrs.get("skill_domain")
            skill_task_type = attrs.get("skill_task_type")
        result = self.con.execute(
            """INSERT INTO fact_trace (session_id, parent_trace_id, trace_type, depth,
               sequence_order, title, content, reasoning, alternatives, outcome,
               child_session_id, duration_ms, skill_id, skill_domain, skill_task_type)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               RETURNING id""",
            [trace.session_id, trace.parent_trace_id, trace.trace_type,
             trace.depth, trace.sequence_order, trace.title, trace.content,
             trace.reasoning, _json(trace.alternatives), _json(trace.outcome),
             trace.child_session_id, trace.duration_ms,
             skill_id, skill_domain, skill_task_type],
        ).fetchone()
        return result[0]

    def get_trace(self, trace_id: int) -> Trace | None:
        """Fetch a single trace node by id."""
        d = self._fetchone("SELECT * FROM fact_trace WHERE id = ?", [trace_id])
        return Trace(**d) if d else None

    def get_session_traces(self, session_id: int) -> list[Trace]:
        """Get all trace nodes for a session, ordered for tree rendering."""
        return [Trace(**d) for d in self._fetchall(
            "SELECT * FROM fact_trace WHERE session_id = ? ORDER BY depth, sequence_order",
            [session_id],
        )]

    def get_trace_children(self, parent_trace_id: int) -> list[Trace]:
        """Get immediate children of a trace node."""
        return [Trace(**d) for d in self._fetchall(
            "SELECT * FROM fact_trace WHERE parent_trace_id = ? ORDER BY sequence_order",
            [parent_trace_id],
        )]

    def count_traces_by_type(self, session_id: int) -> list[tuple[str, int]]:
        """Count traces by type for a session -- summary statistics."""
        rows = self.con.execute(
            """SELECT trace_type, COUNT(*) as cnt
               FROM fact_trace WHERE session_id = ?
               GROUP BY trace_type ORDER BY cnt DESC""",
            [session_id],
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    def delete_session_traces(self, session_id: int) -> int:
        """Delete all traces for a session. Returns count deleted.
        Also deletes fact_trace_feedback referencing these traces."""
        row = self.con.execute(
            "SELECT COUNT(*) FROM fact_trace WHERE session_id = ?", [session_id],
        ).fetchone()
        count = row[0] if row else 0
        # Delete trace feedback first (no FK but maintain referential integrity)
        self.con.execute(
            "DELETE FROM fact_trace_feedback WHERE trace_id IN (SELECT id FROM fact_trace WHERE session_id = ?)",
            [session_id],
        )
        self.con.execute("DELETE FROM fact_trace WHERE session_id = ?", [session_id])
        return count

    # -------------------------------------------------------------------
    # Trace Feedback (fact_trace_feedback)
    # -------------------------------------------------------------------

    def insert_trace_feedback(self, tf: TraceFeedback) -> int:
        """Insert feedback on a specific trace node. Denormalizes trace + skill attrs."""
        trace_type = tf.trace_type
        trace_title = tf.trace_title
        skill_id = tf.skill_id
        skill_domain = tf.skill_domain
        skill_task_type = tf.skill_task_type
        if trace_type is None:
            trace = self.get_trace(tf.trace_id)
            if trace is None:
                raise ValueError(f"Trace {tf.trace_id} not found")
            trace_type = trace.trace_type
            trace_title = trace.title
            skill_id = trace.skill_id
            skill_domain = trace.skill_domain
            skill_task_type = trace.skill_task_type
        result = self.con.execute(
            """INSERT INTO fact_trace_feedback (trace_id, session_id, feedback_type,
               content, correction, created_by,
               trace_type, trace_title, skill_id, skill_domain, skill_task_type)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               RETURNING id""",
            [tf.trace_id, tf.session_id, tf.feedback_type,
             tf.content, _json(tf.correction), tf.created_by,
             trace_type, trace_title, skill_id, skill_domain, skill_task_type],
        ).fetchone()
        return result[0]

    def list_trace_feedback(
        self,
        *,
        trace_id: int | None = None,
        session_id: int | None = None,
        feedback_type: TraceFeedbackType | None = None,
    ) -> list[TraceFeedback]:
        """List trace feedback, filterable by trace, session, or type."""
        query = "SELECT * FROM fact_trace_feedback WHERE 1=1"
        params: list = []
        if trace_id is not None:
            query += " AND trace_id = ?"
            params.append(trace_id)
        if session_id is not None:
            query += " AND session_id = ?"
            params.append(session_id)
        if feedback_type is not None:
            query += " AND feedback_type = ?"
            params.append(feedback_type)
        query += " ORDER BY created_at DESC"
        return [TraceFeedback(**d) for d in self._fetchall(query, params)]

    def aggregate_trace_feedback(
        self,
        session_id: int,
    ) -> list[tuple[str, int]]:
        """Count trace feedback by type for a session. No join needed."""
        rows = self.con.execute(
            """SELECT feedback_type, COUNT(*)
               FROM fact_trace_feedback
               WHERE session_id = ?
               GROUP BY feedback_type ORDER BY COUNT(*) DESC""",
            [session_id],
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    def get_trace_with_feedback(self, trace_id: int) -> dict | None:
        """Fetch a trace with all its feedback records."""
        trace = self.get_trace(trace_id)
        if trace is None:
            return None
        feedback = self.list_trace_feedback(trace_id=trace_id)
        return {"trace": trace, "feedback": feedback}

    # -------------------------------------------------------------------
    # Extractions (fact_extraction)
    # -------------------------------------------------------------------

    def insert_extraction(self, extraction: Extraction) -> int:
        self._require("fact_session", extraction.session_id, "Session")
        # Denormalize source attributes (validates existence as side effect)
        source_path = extraction.source_path
        source_media_type = extraction.source_media_type
        if source_path is None:
            source = self.get_source(extraction.source_id)
            if source is None:
                raise ValueError(f"Source {extraction.source_id} not found")
            source_path = source.content_path
            source_media_type = source.media_type
        # Denormalize skill attributes (validates existence as side effect)
        skill_domain, skill_task_type, skill_version = self._resolve_skill_attrs(
            extraction.skill_id, extraction.skill_domain,
            extraction.skill_task_type, extraction.skill_version,
        )
        result = self.con.execute(
            """INSERT INTO fact_extraction (session_id, output, confidence, validation_status,
               source_id, source_path, source_media_type,
               skill_id, skill_domain, skill_task_type, skill_version)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               RETURNING id""",
            [extraction.session_id, _json(extraction.output), extraction.confidence,
             extraction.validation_status,
             extraction.source_id, source_path, source_media_type,
             extraction.skill_id, skill_domain, skill_task_type, skill_version],
        ).fetchone()
        return result[0]

    def get_extraction(self, extraction_id: int) -> Extraction | None:
        d = self._fetchone("SELECT * FROM fact_extraction WHERE id = ?", [extraction_id])
        return Extraction(**d) if d else None

    def update_validation(
        self,
        extraction_id: int,
        *,
        status: ValidationStatus,
        validated_by: str | None = None,
    ) -> None:
        self.con.execute(
            """UPDATE fact_extraction SET validation_status = ?, validated_by = ?,
               validated_at = current_timestamp WHERE id = ?""",
            [status, validated_by, extraction_id],
        )

    def list_extractions(
        self,
        skill_id: int | None = None,
        validation_status: ValidationStatus | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        limit: int = 50,
    ) -> list[Extraction]:
        query = "SELECT * FROM fact_extraction WHERE 1=1"
        params: list = []
        if skill_id is not None:
            query += " AND skill_id = ?"
            params.append(skill_id)
        if validation_status:
            query += " AND validation_status = ?"
            params.append(validation_status)
        if created_after is not None:
            query += " AND created_at >= ?"
            params.append(created_after)
        if created_before is not None:
            query += " AND created_at <= ?"
            params.append(created_before)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return [Extraction(**d) for d in self._fetchall(query, params)]

    def get_validated_extractions(self, skill_id: int, limit: int = 10) -> list[Extraction]:
        """Retrieval query: find prior validated extractions for a skill."""
        return self.list_extractions(
            skill_id=skill_id, validation_status=ValidationStatus.VALIDATED, limit=limit
        )

    def get_extraction_with_feedback(self, extraction_id: int) -> dict | None:
        """Fetch extraction with all its feedback records."""
        extraction = self.get_extraction(extraction_id)
        if extraction is None:
            return None
        feedback = [Feedback(**d) for d in self._fetchall(
            "SELECT * FROM fact_feedback WHERE extraction_id = ? ORDER BY created_at",
            [extraction_id],
        )]
        return {"extraction": extraction, "feedback": feedback}

    # -------------------------------------------------------------------
    # Feedback (fact_feedback)
    # -------------------------------------------------------------------

    def insert_feedback(self, fb: Feedback) -> int:
        # Denormalize skill attributes (validates existence as side effect)
        skill_domain, skill_task_type, skill_version = self._resolve_skill_attrs(
            fb.skill_id, fb.skill_domain, fb.skill_task_type, fb.skill_version,
        )
        # Denormalize source attributes from extraction (validates existence as side effect)
        source_id = fb.source_id
        source_path = fb.source_path
        if source_id is None:
            ext = self.get_extraction(fb.extraction_id)
            if ext is None:
                raise ValueError(f"Extraction {fb.extraction_id} not found")
            source_id = ext.source_id
            source_path = ext.source_path
            if source_path is None:
                source = self.get_source(ext.source_id)
                if source:
                    source_path = source.content_path
        result = self.con.execute(
            """INSERT INTO fact_feedback (extraction_id, session_id, skill_id,
               correction, correction_type, notes, created_by,
               skill_domain, skill_task_type, skill_version,
               source_id, source_path)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               RETURNING id""",
            [fb.extraction_id, fb.session_id, fb.skill_id,
             _json(fb.correction), fb.correction_type, fb.notes, fb.created_by,
             skill_domain, skill_task_type, skill_version,
             source_id, source_path],
        ).fetchone()
        return result[0]

    def list_feedback(self, skill_id: int | None = None) -> list[Feedback]:
        query = "SELECT * FROM fact_feedback WHERE 1=1"
        params: list = []
        if skill_id is not None:
            query += " AND skill_id = ?"
            params.append(skill_id)
        query += " ORDER BY created_at DESC"
        return [Feedback(**d) for d in self._fetchall(query, params)]

    def aggregate_feedback(
        self,
        skill_id: int,
        *,
        include_examples: bool = False,
        max_examples: int = 3,
    ) -> list[dict]:
        """Count corrections by type for a skill, with field-level detail.

        Uses v_feedback_by_skill and v_feedback_fields views.
        Returns: [{"correction_type": str, "count": int, "fields": [str], "examples": [dict]}]
        """
        # Get correction type counts from view
        type_rows = self._fetchall(
            """SELECT correction_type, correction_count as cnt
               FROM v_feedback_by_skill
               WHERE skill_id = ?
               ORDER BY correction_count DESC""",
            [skill_id],
        )

        # Get field-level detail from view
        field_rows = self._fetchall(
            "SELECT correction_type, field_name FROM v_feedback_fields WHERE skill_id = ?",
            [skill_id],
        )
        fields_by_type: dict[str, list[str]] = {}
        for row in field_rows:
            ct = row["correction_type"]
            if ct not in fields_by_type:
                fields_by_type[ct] = []
            fields_by_type[ct].append(row["field_name"])

        results = []
        for row in type_rows:
            ct = row["correction_type"]
            fields = sorted(fields_by_type.get(ct, []))
            entry: dict = {
                "correction_type": ct,
                "count": row["cnt"],
                "fields": fields,
                "examples": [],
            }
            if include_examples:
                example_rows = self._fetchall(
                    """SELECT correction FROM fact_feedback
                       WHERE skill_id = ? AND correction_type = ?
                       ORDER BY created_at DESC LIMIT ?""",
                    [skill_id, ct, max_examples],
                )
                entry["examples"] = [r["correction"] for r in example_rows]
            results.append(entry)

        return results

    # -------------------------------------------------------------------
    # Rules (dim_rule)
    # -------------------------------------------------------------------

    def insert_rule(self, rule: Rule) -> int:
        result = self.con.execute(
            """INSERT INTO dim_rule (scope, domain, priority, content, status)
               VALUES (?, ?, ?, ?, ?)
               RETURNING id""",
            [rule.scope, rule.domain, rule.priority, rule.content, rule.status],
        ).fetchone()
        return result[0]

    def get_rules(self, domain: str | None = None) -> list[Rule]:
        """Load active rules: global + domain-specific, ordered by priority."""
        query = "SELECT * FROM dim_rule WHERE status = ?"
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
            "SELECT * FROM dim_rule ORDER BY scope, domain, priority DESC"
        )]

    # -------------------------------------------------------------------
    # Sampling Configs (dim_sampling_config)
    # -------------------------------------------------------------------

    def insert_sampling_config(self, config: SamplingConfig) -> int:
        """Insert a sampling configuration."""
        result = self.con.execute(
            """INSERT INTO dim_sampling_config (domain, task_type, strategy,
               parameters, max_samples, status)
               VALUES (?, ?, ?, ?, ?, ?)
               RETURNING id""",
            [config.domain, config.task_type, config.strategy,
             _json(config.parameters), config.max_samples, config.status],
        ).fetchone()
        return result[0]

    def get_sampling_config(
        self,
        domain: str | None = None,
        task_type: str | None = None,
    ) -> SamplingConfig | None:
        """Find the best-matching active sampling config.
        Priority: exact domain+task_type > domain-only > global (NULL domain).
        """
        d = self._fetchone(
            """SELECT * FROM dim_sampling_config WHERE status = ?
               AND (domain = ? OR domain IS NULL)
               AND (task_type = ? OR task_type IS NULL)
               ORDER BY (domain IS NOT NULL)::int + (task_type IS NOT NULL)::int DESC
               LIMIT 1""",
            [RuleStatus.ACTIVE, domain, task_type],
        )
        return SamplingConfig(**d) if d else None

    def list_sampling_configs(self) -> list[SamplingConfig]:
        """List all sampling configs."""
        return [SamplingConfig(**d) for d in self._fetchall(
            "SELECT * FROM dim_sampling_config ORDER BY domain, task_type"
        )]

    # -------------------------------------------------------------------
    # Prior Run Sampling
    # -------------------------------------------------------------------

    def sample_prior_sessions(
        self,
        *,
        skill_id: int,
        strategy: SamplingStrategy = SamplingStrategy.RECENT,
        max_samples: int = 3,
        exclude_session_ids: list[int] | None = None,
    ) -> list[Session]:
        """Sample completed/failed sessions for context injection.

        Only samples completed or failed sessions (not running).
        Excludes sessions in exclude_session_ids (prevents self-sampling).
        """
        exclude = exclude_session_ids or []

        # Build reusable WHERE clause pieces
        where = "skill_id = ? AND status IN (?, ?)"
        base_params: list = [skill_id, SessionStatus.COMPLETED, SessionStatus.FAILED]
        if exclude:
            placeholders = ", ".join("?" for _ in exclude)
            where += f" AND id NOT IN ({placeholders})"
            base_params.extend(exclude)

        if strategy == SamplingStrategy.RECENT:
            return [Session(**d) for d in self._fetchall(
                f"SELECT * FROM fact_session WHERE {where} ORDER BY created_at DESC LIMIT ?",
                base_params + [max_samples],
            )]

        if strategy == SamplingStrategy.RANDOM:
            return [Session(**d) for d in self._fetchall(
                f"SELECT * FROM fact_session WHERE {where} ORDER BY random() LIMIT ?",
                base_params + [max_samples],
            )]

        if strategy == SamplingStrategy.HIGH_FEEDBACK:
            # Use v_session_feedback_count view
            hf_where = "s.skill_id = ? AND s.status IN (?, ?)"
            hf_params: list = [skill_id, SessionStatus.COMPLETED, SessionStatus.FAILED]
            if exclude:
                hf_phs = ", ".join("?" for _ in exclude)
                hf_where += f" AND s.id NOT IN ({hf_phs})"
                hf_params.extend(exclude)
            return [Session(**d) for d in self._fetchall(
                f"""SELECT s.* FROM fact_session s
                    LEFT JOIN v_session_feedback_count v
                        ON v.session_id = s.id AND v.skill_id = s.skill_id
                    WHERE {hf_where}
                    ORDER BY COALESCE(v.feedback_count, 0) DESC
                    LIMIT ?""",
                hf_params + [max_samples],
            )]

        if strategy == SamplingStrategy.STRATIFIED_OUTCOME:
            def _fetch_by_status(st: SessionStatus) -> list[Session]:
                so_where = "skill_id = ? AND status = ?"
                so_params: list = [skill_id, st]
                if exclude:
                    so_phs = ", ".join("?" for _ in exclude)
                    so_where += f" AND id NOT IN ({so_phs})"
                    so_params.extend(exclude)
                return [Session(**d) for d in self._fetchall(
                    f"SELECT * FROM fact_session WHERE {so_where} ORDER BY created_at DESC LIMIT ?",
                    so_params + [max_samples],
                )]

            completed = _fetch_by_status(SessionStatus.COMPLETED)
            failed = _fetch_by_status(SessionStatus.FAILED)

            if not completed and not failed:
                return []
            if not failed:
                return completed[:max_samples]
            if not completed:
                return failed[:max_samples]

            n_failed = max(1, round(max_samples * len(failed) / (len(completed) + len(failed))))
            n_completed = max_samples - n_failed
            return completed[:n_completed] + failed[:n_failed]

        if strategy == SamplingStrategy.STRATIFIED_FEEDBACK:
            # Use denormalized skill_id on fact_feedback
            sf_params: list = [skill_id, SessionStatus.COMPLETED, SessionStatus.FAILED]
            sf_where = "f.skill_id = ? AND s.status IN (?, ?)"
            if exclude:
                sf_phs = ", ".join("?" for _ in exclude)
                sf_where += f" AND s.id NOT IN ({sf_phs})"
                sf_params.extend(exclude)
            type_sessions = self.con.execute(
                f"""WITH ranked AS (
                        SELECT f.correction_type, s.id as session_id,
                               ROW_NUMBER() OVER (
                                   PARTITION BY f.correction_type
                                   ORDER BY s.created_at DESC
                               ) as rn
                        FROM fact_feedback f
                        JOIN fact_session s ON f.session_id = s.id
                        WHERE {sf_where}
                    )
                    SELECT session_id FROM ranked WHERE rn = 1""",
                sf_params,
            ).fetchall()

            seen: set[int] = set()
            session_ids: list[int] = []
            for (sid,) in type_sessions:
                if sid not in seen:
                    session_ids.append(sid)
                    seen.add(sid)
                if len(session_ids) >= max_samples:
                    break

            if not session_ids:
                return []
            placeholders = ", ".join("?" for _ in session_ids)
            return [Session(**d) for d in self._fetchall(
                f"SELECT * FROM fact_session WHERE id IN ({placeholders})",
                session_ids,
            )]

        return []

    # -------------------------------------------------------------------
    # Rich Session Retrieval
    # -------------------------------------------------------------------

    def get_session_with_context(self, session_id: int) -> dict | None:
        """Fetch a session with its traces, extractions, feedback, and trace feedback."""
        session = self.get_session(session_id)
        if session is None:
            return None

        traces = self.get_session_traces(session_id)
        extractions = [Extraction(**d) for d in self._fetchall(
            "SELECT * FROM fact_extraction WHERE session_id = ? ORDER BY created_at",
            [session_id],
        )]
        feedback = [Feedback(**d) for d in self._fetchall(
            "SELECT * FROM fact_feedback WHERE session_id = ? ORDER BY created_at",
            [session_id],
        )]
        trace_feedback = self.list_trace_feedback(session_id=session_id)

        return {
            "session": session,
            "traces": traces,
            "extractions": extractions,
            "feedback": feedback,
            "trace_feedback": trace_feedback,
        }

    def get_sessions_with_context(self, session_ids: list[int]) -> list[dict]:
        """Bulk version of get_session_with_context."""
        return [
            ctx for sid in session_ids
            if (ctx := self.get_session_with_context(sid)) is not None
        ]

    # -------------------------------------------------------------------
    # Pattern Detection (Skill Evolution) -- view-backed
    # -------------------------------------------------------------------

    def get_skills_with_feedback_patterns(
        self,
        domain: str | None = None,
        min_feedback_count: int = 3,
    ) -> list[dict]:
        """Find skills with recurring feedback patterns above threshold.
        Uses v_skill_feedback_patterns view.
        Returns [{"skill": Skill, "patterns": [(correction_type, count)], "total_feedback": int}].
        """
        query = """SELECT DISTINCT skill_id, total_feedback
                   FROM v_skill_feedback_patterns
                   WHERE total_feedback >= ?"""
        params: list = [min_feedback_count]
        if domain:
            query += " AND skill_domain = ?"
            params.append(domain)
        query += " ORDER BY total_feedback DESC"

        skill_totals = self._fetchall(query, params)

        results = []
        for row in skill_totals:
            sid = row["skill_id"]
            skill = self.get_skill(sid)
            if skill is None:
                continue
            patterns = self._fetchall(
                """SELECT correction_type, pattern_count
                   FROM v_skill_feedback_patterns
                   WHERE skill_id = ?
                   ORDER BY pattern_count DESC""",
                [sid],
            )
            results.append({
                "skill": skill,
                "patterns": [(r["correction_type"], r["pattern_count"]) for r in patterns],
                "total_feedback": row["total_feedback"],
            })

        return results

    def get_recurring_traces(
        self,
        skill_id: int,
        trace_type: TraceType,
        min_occurrences: int = 2,
    ) -> list[dict]:
        """Find recurring traces via v_recurring_traces view. No join needed."""
        rows = self._fetchall(
            """SELECT title, occurrence_count, session_ids, example_trace_id
               FROM v_recurring_traces
               WHERE skill_id = ? AND trace_type = ?
                 AND occurrence_count >= ?
               ORDER BY occurrence_count DESC""",
            [skill_id, trace_type, min_occurrences],
        )
        return [
            {
                "title": r["title"],
                "count": r["occurrence_count"],
                "session_ids": r["session_ids"],
                "example_trace_id": r["example_trace_id"],
            }
            for r in rows
        ]

    def get_recurring_trace_feedback(
        self,
        skill_id: int,
        min_occurrences: int = 2,
    ) -> list[dict]:
        """Find recurring trace feedback via v_recurring_trace_feedback view."""
        rows = self._fetchall(
            """SELECT feedback_type, trace_title, occurrence_count, session_ids
               FROM v_recurring_trace_feedback
               WHERE skill_id = ? AND occurrence_count >= ?
               ORDER BY occurrence_count DESC""",
            [skill_id, min_occurrences],
        )
        return [
            {
                "feedback_type": r["feedback_type"],
                "trace_title": r["trace_title"],
                "count": r["occurrence_count"],
                "session_ids": r["session_ids"],
            }
            for r in rows
        ]
