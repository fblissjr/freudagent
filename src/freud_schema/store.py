"""CRUD operations and retrieval queries for the meta-harness (v0.17).

Dimensional model access layer. Key scheme: sha256/32 hash surrogate keys
(keys.dimension_key). Key generation policy:

- SCD-2 dimensions: entity key from natural key parts (e.g. skill_key =
  dimension_key(domain, task_type)). All history rows share the key;
  is_current/effective ranges distinguish versions.
- Ingested facts (messages, tool uses, facets, findings): fully
  deterministic keys, so re-ingestion computes the same keys and skips
  existing rows -- idempotency is a property of key generation, not a
  separate mechanism.
- Native facts (extractions, feedback): uuid-salted keys, because the
  event is intrinsically unique and never re-ingested.

SCD-2 semantics: any attribute change closes the current row
(effective_to, is_current=false) and inserts a new current row. Rows
never mutate. Exception: fact_session is an accumulating snapshot --
status/result/completed_at update in place as the session progresses.

finding_type is registry-validated against dim_finding_type here (no
CHECK constraint) so new finding vocabularies are data, not DDL.

All queries are parameterized. JSON fields are serialized with orjson
on write and deserialized on read via automatic type detection from
DuckDB's cursor.description (type_code == "JSON").
"""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

import duckdb
import orjson

from freud_schema.db import init_schema
from freud_schema.keys import dimension_key, hash_diff
from freud_schema.tables import (
    Event,
    EventType,
    Extraction,
    FacetType,
    Feedback,
    Finding,
    FindingType,
    LoadRun,
    Message,
    Project,
    Proposal,
    ProposalStatus,
    RecordSource,
    Rule,
    RuleScope,
    RuleStatus,
    SamplingConfig,
    SamplingStrategy,
    Session,
    SessionFacet,
    SessionStatus,
    Skill,
    SkillOrigin,
    SkillStatus,
    Source,
    SourceStatus,
    TargetDimension,
    Tenant,
    ToolUse,
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


@dataclass
class LoadRunStats:
    """Mutable counters a load_run scope yields to its caller. A small
    object rather than a dict so counter typos raise AttributeError
    instead of silently logging zeros to meta_load_log."""

    etl_run_id: str
    rows_read: int = 0
    rows_written: int = 0
    rows_skipped: int = 0


# Table -> key column mapping. Doubles as the identifier allowlist for
# resolve_key(), so no caller-provided string ever lands in SQL unchecked.
_KEY_COLUMNS: dict[str, str] = {
    "dim_skill": "skill_key",
    "dim_source": "source_key",
    "dim_rule": "rule_key",
    "dim_sampling_config": "config_key",
    "dim_project": "project_key",
    "dim_tenant": "tenant_key",
    "dim_facet_type": "facet_type_key",
    "dim_finding_type": "finding_type_key",
    "fact_session": "session_key",
    "fact_trace": "trace_key",
    "fact_extraction": "extraction_key",
    "fact_feedback": "feedback_key",
    "fact_trace_feedback": "trace_feedback_key",
    "fact_message": "message_key",
    "fact_tool_use": "tool_use_key",
    "fact_session_facets": "facet_row_key",
    "fact_finding": "finding_key",
    "fact_proposal": "proposal_key",
    "dim_event_type": "event_type_key",
    "fact_event": "event_key",
}

# The four SCD-2 dims whose natural key now leads with tenant_id.
# resolve_key() scopes prefix resolution to a tenant only for these.
_TENANT_SCOPED_DIMS: frozenset[str] = frozenset(
    {"dim_skill", "dim_rule", "dim_source", "dim_sampling_config"}
)

# Column -> DuckDB type maps for the spill-to-JSON bulk insert path
# (_bulk_insert_json): fresh-ingest volumes dominate cost in the per-row
# executemany loop, so these three ingestion-scale tables (fact_message,
# fact_tool_use, fact_event) load via a single read_json INSERT instead
# (BACKLOG "fresh-ingest insert speed", ~300-600x measured). Column order
# here is what drives both the spilled JSONL keys and the INSERT/SELECT
# column list, so it must exactly match each table's DDL column set.
_MESSAGE_JSON_TYPES: dict[str, str] = {
    "message_key": "VARCHAR", "session_key": "VARCHAR", "project_key": "VARCHAR",
    "role": "VARCHAR", "entry_uuid": "VARCHAR", "parent_uuid": "VARCHAR",
    "sequence_num": "INTEGER", "occurred_at": "TIMESTAMP", "content_text": "VARCHAR",
    "has_thinking": "BOOLEAN", "stop_reason": "VARCHAR", "input_tokens": "INTEGER",
    "output_tokens": "INTEGER", "is_meta": "BOOLEAN", "is_sidechain": "BOOLEAN",
    "tenant_key": "VARCHAR", "record_source": "VARCHAR", "etl_run_id": "VARCHAR",
}

_TOOL_USE_JSON_TYPES: dict[str, str] = {
    "tool_use_key": "VARCHAR", "session_key": "VARCHAR", "project_key": "VARCHAR",
    "message_key": "VARCHAR", "tool_use_id": "VARCHAR", "tool_name": "VARCHAR",
    "tool_input": "JSON", "is_error": "BOOLEAN", "result_text": "VARCHAR",
    "sequence_num": "INTEGER", "occurred_at": "TIMESTAMP",
    "tenant_key": "VARCHAR", "record_source": "VARCHAR", "etl_run_id": "VARCHAR",
}

_EVENT_JSON_TYPES: dict[str, str] = {
    "event_key": "VARCHAR", "stream_key": "VARCHAR", "native_event_id": "VARCHAR",
    "event_type": "VARCHAR", "occurred_at": "TIMESTAMP", "actor": "VARCHAR",
    "payload": "JSON", "content_text": "VARCHAR", "signature": "VARCHAR",
    "sequence_num": "INTEGER",
    "tenant_key": "VARCHAR", "record_source": "VARCHAR", "etl_run_id": "VARCHAR",
}


class ExperimentStore:
    """Data access layer for the meta-harness."""

    def __init__(self, con: duckdb.DuckDBPyConnection):
        self.con = con
        self._session_skill_cache: dict[str, dict] = {}
        # Pure hash, no DB read -- the tenant that fact rows fall back to
        # when no skill/model tenant is available.
        self._default_tenant_key = dimension_key("default")
        init_schema(con)

    def close(self) -> None:
        self.con.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    @contextmanager
    def transaction(self):
        """Explicit transaction scope for bulk writes (e.g. one transcript
        file per transaction during ingestion). Rolls back on exception."""
        self.con.execute("BEGIN TRANSACTION")
        try:
            yield
            self.con.execute("COMMIT")
        except BaseException:
            self.con.execute("ROLLBACK")
            raise

    def count_rows(self, table: str) -> int:
        """Row count for a schema table (allowlisted, used for load stats)."""
        if table not in _KEY_COLUMNS and table not in ("meta_load_log",):
            raise ValueError(f"Unknown table: {table}")
        return self.con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

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
    # Internal: key plumbing (replaces FK enforcement)
    # -------------------------------------------------------------------

    def _key_exists(self, table: str, key: str) -> bool:
        key_col = _KEY_COLUMNS[table]
        row = self.con.execute(
            f"SELECT 1 FROM {table} WHERE {key_col} = ? LIMIT 1", [key],
        ).fetchone()
        return row is not None

    def _require(self, table: str, key: str, label: str) -> None:
        """Raise ValueError if a referenced entity doesn't exist.

        Called at insert boundaries to catch orphaned references that
        FKs would have rejected. Only used when no denormalization fetch
        will validate the reference as a side effect.
        """
        if not self._key_exists(table, key):
            raise ValueError(f"{label} {key} not found")

    def resolve_key(self, table: str, prefix: str, tenant_id: str | None = None) -> str:
        """Resolve a key prefix to a full key, git-short-hash style.

        Raises ValueError if the prefix matches nothing or more than one
        key. The key column is derived from the schema's own table->key
        mapping, never interpolated from caller strings.

        tenant_id, when given, scopes resolution to that tenant -- but
        only for the four tenant-keyed SCD-2 dims (_TENANT_SCOPED_DIMS);
        every other table ignores the param, preserving existing callers.
        """
        key_col = _KEY_COLUMNS.get(table)
        if key_col is None:
            raise ValueError(f"Unknown table: {table}")
        # Escape LIKE metacharacters: a prefix containing % or _ must match
        # literally, not as a wildcard (keys are hex, but input is user-typed).
        escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = (f"SELECT DISTINCT {key_col} FROM {table} "
                 f"WHERE {key_col} LIKE ? ESCAPE '\\'")
        params: list = [escaped + "%"]
        if tenant_id is not None and table in _TENANT_SCOPED_DIMS:
            query += " AND tenant_id = ?"
            params.append(tenant_id)
        query += " LIMIT 2"
        rows = self.con.execute(query, params).fetchall()
        if not rows:
            raise ValueError(f"No {table} match for key prefix '{prefix}'")
        if len(rows) > 1:
            raise ValueError(f"Ambiguous key prefix '{prefix}' for {table}")
        return rows[0][0]

    # -------------------------------------------------------------------
    # Internal: SCD-2 machinery
    # -------------------------------------------------------------------

    def _current_row(self, table: str, key: str) -> dict | None:
        key_col = _KEY_COLUMNS[table]
        return self._fetchone(
            f"SELECT * FROM {table} WHERE {key_col} = ? AND is_current", [key],
        )

    def _scd2_unchanged_or_close(self, table: str, key: str, new_hash: str) -> bool:
        """Shared SCD-2 insert guard: True if a current row exists with the
        same content hash (caller should no-op); otherwise closes any
        current row and returns False (caller inserts the new version)."""
        current = self._current_row(table, key)
        if current is not None:
            if current["hash_diff"] == new_hash:
                return True
            self._close_current(table, key)
        return False

    def _close_current(self, table: str, key: str) -> None:
        key_col = _KEY_COLUMNS[table]
        self.con.execute(
            f"""UPDATE {table} SET is_current = FALSE,
                effective_to = current_timestamp
                WHERE {key_col} = ? AND is_current""",
            [key],
        )

    def _resolve_skill_attrs(
        self,
        skill_key: str,
        domain: str | None = None,
        task_type: str | None = None,
        version: int | None = None,
    ) -> tuple[str | None, str | None, int | None, str | None]:
        """Resolve skill domain/task_type/version/tenant_key from the
        current row.

        Validates existence: raises ValueError if skill_key has no row.
        Skips the fetch if domain is already provided (caller pre-filled);
        tenant_key is None in that case -- the caller falls back to its
        own model.tenant_key or the default tenant.
        """
        if domain is not None:
            return domain, task_type, version, None
        skill = self.get_skill(skill_key)
        if skill is None:
            raise ValueError(f"Skill {skill_key} not found")
        return (skill.domain, skill.task_type, skill.version,
                self.tenant_key_for(skill.tenant_id))

    # -------------------------------------------------------------------
    # Internal: session skill attribute cache (for bulk trace inserts)
    # -------------------------------------------------------------------

    def _get_session_skill_attrs(self, session_key: str) -> dict | None:
        """Get session's skill attributes, cached for bulk trace inserts."""
        if session_key in self._session_skill_cache:
            return self._session_skill_cache[session_key]
        d = self._fetchone(
            "SELECT skill_key, skill_domain, skill_task_type, tenant_key "
            "FROM fact_session WHERE session_key = ?",
            [session_key],
        )
        if d:
            self._session_skill_cache[session_key] = d
        return d

    # -------------------------------------------------------------------
    # Skills (dim_skill, SCD-2)
    # -------------------------------------------------------------------

    def _write_skill_row(self, key: str, skill: Skill) -> None:
        """The one place a dim_skill row (and its hash recipe) is written.
        Both version bumps (insert_skill) and status evolutions delegate
        here so the column list and hash fields cannot drift apart."""
        self.con.execute(
            """INSERT INTO dim_skill (skill_key, tenant_id, domain, task_type, version,
               content, metadata, parent_skill_key, status, origin, activation_conditions,
               hash_diff, record_source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [key, skill.tenant_id, skill.domain, skill.task_type, skill.version,
             skill.content, _json(skill.metadata), skill.parent_skill_key, skill.status,
             skill.origin, _json(skill.activation_conditions),
             hash_diff(content=skill.content, status=skill.status.value,
                       version=skill.version, origin=skill.origin.value,
                       metadata=_json(skill.metadata),
                       parent_skill_key=skill.parent_skill_key,
                       activation_conditions=_json(skill.activation_conditions)),
             skill.record_source],
        )

    def insert_skill(self, skill: Skill) -> str:
        """Insert a new skill version. Entity key: (tenant_id, domain, task_type).

        If a current row exists for the entity, the new version must
        exceed it; the current row is closed and the new one becomes
        current. Status changes without a version bump go through
        activate_skill/deprecate_skill instead.
        """
        key = dimension_key(skill.tenant_id, skill.domain, skill.task_type)
        current = self._current_row("dim_skill", key)
        if current is not None and skill.version <= current["version"]:
            raise ValueError(
                f"Skill {skill.domain}/{skill.task_type} version must exceed "
                f"current version {current['version']} (got {skill.version})"
            )
        if current is not None:
            self._close_current("dim_skill", key)
        self.ensure_tenant(Tenant(tenant_id=skill.tenant_id))
        self._write_skill_row(key, skill)
        return key

    def get_skill(self, skill_key: str, version: int | None = None) -> Skill | None:
        """Fetch a skill: the current row by default, or a specific version."""
        if version is None:
            d = self._current_row("dim_skill", skill_key)
        else:
            d = self._fetchone(
                """SELECT * FROM dim_skill WHERE skill_key = ? AND version = ?
                   ORDER BY effective_from DESC LIMIT 1""",
                [skill_key, version],
            )
        return Skill(**d) if d else None

    def get_active_skill(
        self, domain: str, task_type: str, tenant_id: str = "default",
    ) -> Skill | None:
        """Find the current skill for a tenant + domain + task_type, if active."""
        skill = self.get_skill(dimension_key(tenant_id, domain, task_type))
        if skill is not None and skill.status == SkillStatus.ACTIVE:
            return skill
        return None

    def list_skills(
        self,
        domain: str | None = None,
        status: SkillStatus | None = None,
        origin: SkillOrigin | None = None,
        parent_skill_key: str | None = None,
        include_history: bool = False,
    ) -> list[Skill]:
        query = "SELECT * FROM dim_skill WHERE 1=1"
        params: list = []
        if not include_history:
            query += " AND is_current"
        if domain:
            query += " AND domain = ?"
            params.append(domain)
        if status:
            query += " AND status = ?"
            params.append(status)
        if origin:
            query += " AND origin = ?"
            params.append(origin)
        if parent_skill_key is not None:
            query += " AND parent_skill_key = ?"
            params.append(parent_skill_key)
        query += " ORDER BY domain, task_type, version DESC"
        return [Skill(**d) for d in self._fetchall(query, params)]

    def _evolve_skill_status(self, skill_key: str, status: SkillStatus) -> None:
        """SCD-2 status change: close current row, insert copy with new status."""
        current = self._current_row("dim_skill", skill_key)
        if current is None:
            raise ValueError(f"Skill {skill_key} not found")
        if current["status"] == status.value:
            return  # already there; no history noise
        self._close_current("dim_skill", skill_key)
        self._write_skill_row(skill_key, Skill(**{**current, "status": status}))

    def activate_skill(self, skill_key: str) -> None:
        self._evolve_skill_status(skill_key, SkillStatus.ACTIVE)

    def deprecate_skill(self, skill_key: str) -> None:
        self._evolve_skill_status(skill_key, SkillStatus.DEPRECATED)

    def get_active_sub_skills(self, parent_skill_key: str) -> list[Skill]:
        """Get current active skills with the given parent_skill_key."""
        return [Skill(**d) for d in self._fetchall(
            """SELECT * FROM dim_skill
               WHERE parent_skill_key = ? AND status = ? AND is_current
               ORDER BY version DESC""",
            [parent_skill_key, SkillStatus.ACTIVE],
        )]

    def insert_derived_skill(
        self,
        skill: Skill,
        *,
        source_session_keys: list[str],
        source_trace_keys: list[str],
    ) -> str:
        """Insert a data-derived skill with provenance tracking.

        Inherits the parent skill's tenant_id (a derived skill lives in
        whatever tenant produced it, not whatever default the caller
        happened to construct the model with).
        """
        tenant_id = skill.tenant_id
        if skill.parent_skill_key:
            parent = self.get_skill(skill.parent_skill_key)
            if parent is not None:
                tenant_id = parent.tenant_id
        skill = skill.model_copy(update={
            "tenant_id": tenant_id,
            "origin": SkillOrigin.DATA_DERIVED,
            "record_source": RecordSource.DERIVED,
            "metadata": {
                **(skill.metadata or {}),
                "derived_from": {
                    "session_keys": source_session_keys,
                    "trace_keys": source_trace_keys,
                },
            },
        })
        return self.insert_skill(skill)

    # -------------------------------------------------------------------
    # Sources (dim_source, SCD-2)
    # -------------------------------------------------------------------

    def insert_source(self, source: Source) -> str:
        """Register a source. Entity key: (tenant_id, content_path).

        Idempotent: re-adding an identical source is a no-op; a changed
        one (new hash, status, metadata) evolves the SCD-2 row.
        """
        key = dimension_key(source.tenant_id, source.content_path)
        new_hash = hash_diff(
            content_path=source.content_path, media_type=source.media_type,
            metadata=_json(source.metadata), source_hash=source.source_hash,
            status=source.status.value, superseded_by_key=source.superseded_by_key,
        )
        if self._scd2_unchanged_or_close("dim_source", key, new_hash):
            return key
        self.ensure_tenant(Tenant(tenant_id=source.tenant_id))
        self.con.execute(
            """INSERT INTO dim_source (source_key, tenant_id, content_path, media_type,
               metadata, source_hash, status, superseded_by_key, hash_diff, record_source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [key, source.tenant_id, source.content_path, source.media_type,
             _json(source.metadata), source.source_hash, source.status,
             source.superseded_by_key, new_hash, source.record_source],
        )
        return key

    def get_source(self, source_key: str) -> Source | None:
        d = self._current_row("dim_source", source_key)
        return Source(**d) if d else None

    def get_sources_by_keys(self, source_keys: list[str]) -> dict[str, Source]:
        """Bulk fetch current sources by key. Returns {key: Source} map."""
        if not source_keys:
            return {}
        placeholders = ", ".join("?" for _ in source_keys)
        return {
            d["source_key"]: Source(**d)
            for d in self._fetchall(
                f"SELECT * FROM dim_source WHERE source_key IN ({placeholders})"
                " AND is_current",
                source_keys,
            )
        }

    def list_sources(self, status: SourceStatus | None = None) -> list[Source]:
        query = "SELECT * FROM dim_source WHERE is_current"
        params: list = []
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC"
        return [Source(**d) for d in self._fetchall(query, params)]

    # -------------------------------------------------------------------
    # Rules (dim_rule, SCD-2)
    # -------------------------------------------------------------------

    def insert_rule(self, rule: Rule) -> str:
        """Insert or evolve a rule. Entity key: (tenant_id, name) -- name
        also doubles as the compile target filename. Identical re-adds
        are no-ops."""
        key = dimension_key(rule.tenant_id, rule.name)
        new_hash = hash_diff(
            name=rule.name, scope=rule.scope.value, domain=rule.domain,
            priority=rule.priority, content=rule.content, status=rule.status.value,
        )
        if self._scd2_unchanged_or_close("dim_rule", key, new_hash):
            return key
        self.ensure_tenant(Tenant(tenant_id=rule.tenant_id))
        self.con.execute(
            """INSERT INTO dim_rule (rule_key, tenant_id, name, scope, domain, priority,
               content, status, hash_diff, record_source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [key, rule.tenant_id, rule.name, rule.scope, rule.domain, rule.priority,
             rule.content, rule.status, new_hash, rule.record_source],
        )
        return key

    def get_rule(self, rule_key: str) -> Rule | None:
        d = self._current_row("dim_rule", rule_key)
        return Rule(**d) if d else None

    def get_rules(self, domain: str | None = None, tenant_id: str = "default") -> list[Rule]:
        """Load current active rules for a tenant: global + domain-specific,
        by priority."""
        query = "SELECT * FROM dim_rule WHERE status = ? AND is_current AND tenant_id = ?"
        params: list = [RuleStatus.ACTIVE, tenant_id]
        if domain:
            query += " AND (scope = ? OR domain = ?)"
            params.extend([RuleScope.GLOBAL, domain])
        else:
            query += " AND scope = ?"
            params.append(RuleScope.GLOBAL)
        query += " ORDER BY priority DESC"
        return [Rule(**d) for d in self._fetchall(query, params)]

    def list_rules(self, include_history: bool = False) -> list[Rule]:
        query = "SELECT * FROM dim_rule"
        if not include_history:
            query += " WHERE is_current"
        query += " ORDER BY scope, domain, priority DESC"
        return [Rule(**d) for d in self._fetchall(query)]

    # -------------------------------------------------------------------
    # Sampling Configs (dim_sampling_config, SCD-2)
    # -------------------------------------------------------------------

    def insert_sampling_config(self, config: SamplingConfig) -> str:
        """Insert or evolve a sampling config. Entity key:
        (tenant_id, domain, task_type)."""
        key = dimension_key(config.tenant_id, config.domain, config.task_type)
        new_hash = hash_diff(
            domain=config.domain, task_type=config.task_type,
            strategy=config.strategy.value, parameters=_json(config.parameters),
            max_samples=config.max_samples, status=config.status.value,
        )
        if self._scd2_unchanged_or_close("dim_sampling_config", key, new_hash):
            return key
        self.ensure_tenant(Tenant(tenant_id=config.tenant_id))
        self.con.execute(
            """INSERT INTO dim_sampling_config (config_key, tenant_id, domain, task_type,
               strategy, parameters, max_samples, status, hash_diff, record_source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [key, config.tenant_id, config.domain, config.task_type, config.strategy,
             _json(config.parameters), config.max_samples, config.status,
             new_hash, config.record_source],
        )
        return key

    def get_sampling_config(
        self,
        domain: str | None = None,
        task_type: str | None = None,
        tenant_id: str = "default",
    ) -> SamplingConfig | None:
        """Find the best-matching current active sampling config for a tenant.
        Priority: exact domain+task_type > domain-only > global (NULL domain).
        """
        d = self._fetchone(
            """SELECT * FROM dim_sampling_config WHERE status = ? AND is_current
               AND tenant_id = ?
               AND (domain = ? OR domain IS NULL)
               AND (task_type = ? OR task_type IS NULL)
               ORDER BY (domain IS NOT NULL)::int + (task_type IS NOT NULL)::int DESC
               LIMIT 1""",
            [RuleStatus.ACTIVE, tenant_id, domain, task_type],
        )
        return SamplingConfig(**d) if d else None

    def list_sampling_configs(self) -> list[SamplingConfig]:
        """List current sampling configs."""
        return [SamplingConfig(**d) for d in self._fetchall(
            "SELECT * FROM dim_sampling_config WHERE is_current "
            "ORDER BY domain, task_type"
        )]

    # -------------------------------------------------------------------
    # Registry dimensions (append-only)
    # -------------------------------------------------------------------

    @staticmethod
    def tenant_key_for(tenant_id: str) -> str:
        """The tenant-key recipe, named -- consumers that must reference a
        tenant without an ensure_tenant round trip use this instead of
        re-deriving the formula."""
        return dimension_key(tenant_id)

    def ensure_tenant(self, tenant: Tenant) -> str:
        """Register a tenant if unseen; idempotent. Key: tenant_id."""
        key = self.tenant_key_for(tenant.tenant_id)
        if not self._key_exists("dim_tenant", key):
            self.con.execute(
                """INSERT INTO dim_tenant (tenant_key, tenant_id, display_name,
                   record_source) VALUES (?, ?, ?, ?)""",
                [key, tenant.tenant_id, tenant.display_name, tenant.record_source],
            )
        return key

    def get_tenant(self, tenant_key: str) -> Tenant | None:
        d = self._fetchone(
            "SELECT * FROM dim_tenant WHERE tenant_key = ?", [tenant_key])
        return Tenant(**d) if d else None

    def list_tenants(self) -> list[Tenant]:
        return [Tenant(**d) for d in self._fetchall(
            "SELECT * FROM dim_tenant ORDER BY tenant_id")]

    def ensure_project(self, project: Project) -> str:
        """Register a project if unseen; idempotent. Key: project_path."""
        key = dimension_key(project.project_path)
        if not self._key_exists("dim_project", key):
            self.con.execute(
                """INSERT INTO dim_project (project_key, project_path, project_name,
                   record_source) VALUES (?, ?, ?, ?)""",
                [key, project.project_path, project.project_name,
                 project.record_source],
            )
        return key

    def get_project(self, project_key: str) -> Project | None:
        d = self._fetchone(
            "SELECT * FROM dim_project WHERE project_key = ?", [project_key])
        return Project(**d) if d else None

    def list_projects(self) -> list[Project]:
        return [Project(**d) for d in self._fetchall(
            "SELECT * FROM dim_project ORDER BY project_path")]

    def register_facet_type(self, facet: FacetType) -> str:
        """Register a facet type version; idempotent per (facet_id, prompt_version).

        Bumping prompt_version adds a row -- registry entries are never
        overwritten, so old facet values stay interpretable.
        """
        key = dimension_key(facet.facet_id, facet.prompt_version)
        if not self._key_exists("dim_facet_type", key):
            self.con.execute(
                """INSERT INTO dim_facet_type (facet_type_key, facet_id, tier, method,
                   output_type, prompt_text, prompt_version, description, record_source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [key, facet.facet_id, facet.tier, facet.method, facet.output_type,
                 facet.prompt_text, facet.prompt_version, facet.description,
                 facet.record_source],
            )
        return key

    def get_facet_type(self, facet_id: str, prompt_version: int = 1) -> FacetType | None:
        d = self._fetchone(
            "SELECT * FROM dim_facet_type WHERE facet_type_key = ?",
            [dimension_key(facet_id, prompt_version)],
        )
        return FacetType(**d) if d else None

    def list_facet_types(self) -> list[FacetType]:
        return [FacetType(**d) for d in self._fetchall(
            "SELECT * FROM dim_facet_type ORDER BY tier, facet_id, prompt_version")]

    def register_finding_type(self, ft: FindingType) -> str:
        """Register a finding vocabulary entry; idempotent. Key: finding_type.

        This registry is what validates fact_finding.finding_type -- new
        vocabularies are rows here, never enum edits.
        """
        key = dimension_key(ft.finding_type)
        if not self._key_exists("dim_finding_type", key):
            self.con.execute(
                """INSERT INTO dim_finding_type (finding_type_key, finding_type,
                   description, detection_method, record_source)
                   VALUES (?, ?, ?, ?, ?)""",
                [key, ft.finding_type, ft.description, ft.detection_method,
                 ft.record_source],
            )
        return key

    def get_finding_type(self, finding_type: str) -> FindingType | None:
        d = self._fetchone(
            "SELECT * FROM dim_finding_type WHERE finding_type_key = ?",
            [dimension_key(finding_type)],
        )
        return FindingType(**d) if d else None

    def list_finding_types(self) -> list[FindingType]:
        return [FindingType(**d) for d in self._fetchall(
            "SELECT * FROM dim_finding_type ORDER BY finding_type")]

    def register_event_type(self, et: EventType) -> str:
        """Register an event vocabulary entry; idempotent. Key: event_type.

        Mirrors register_finding_type -- fact_event.event_type is
        registry-validated the same way fact_finding.finding_type is (open
        vocabulary, no CHECK constraint).
        """
        key = dimension_key(et.event_type)
        if not self._key_exists("dim_event_type", key):
            self.con.execute(
                """INSERT INTO dim_event_type (event_type_key, event_type,
                   description, schema_hint, record_source)
                   VALUES (?, ?, ?, ?, ?)""",
                [key, et.event_type, et.description, _json(et.schema_hint),
                 et.record_source],
            )
        return key

    def get_event_type(self, event_type: str) -> EventType | None:
        d = self._fetchone(
            "SELECT * FROM dim_event_type WHERE event_type_key = ?",
            [dimension_key(event_type)],
        )
        return EventType(**d) if d else None

    def list_event_types(self) -> list[EventType]:
        return [EventType(**d) for d in self._fetchall(
            "SELECT * FROM dim_event_type ORDER BY event_type")]

    # -------------------------------------------------------------------
    # Sessions (fact_session, accumulating snapshot)
    # -------------------------------------------------------------------

    @staticmethod
    def session_key_for(record_source: RecordSource, native_session_id: str) -> str:
        """The session-key recipe, named. Consumers that must reference a
        session they did not insert (e.g. ingest linking subagents to
        parents) use this instead of re-deriving the formula."""
        return dimension_key(record_source.value, native_session_id)

    def insert_session(self, session: Session) -> str:
        """Insert a session. Key: (record_source, native_session_id).

        Native runs get a generated native_session_id; ingested sessions
        carry the harness's own id, so re-ingesting the same transcript
        resolves to the same key and skips the insert.
        """
        native_id = session.native_session_id or uuid4().hex
        key = self.session_key_for(session.record_source, native_id)
        if self._key_exists("fact_session", key):
            return key
        # Denormalize skill attributes (validates existence as side effect)
        skill_domain = session.skill_domain
        skill_task_type = session.skill_task_type
        skill_version = session.skill_version
        skill_tenant_key = None
        if session.skill_key is not None:
            skill_domain, skill_task_type, skill_version, skill_tenant_key = (
                self._resolve_skill_attrs(
                    session.skill_key, skill_domain, skill_task_type, skill_version,
                )
            )
        tenant_key = skill_tenant_key or session.tenant_key or self._default_tenant_key
        self.con.execute(
            """INSERT INTO fact_session (session_key, native_session_id, project_key,
               task_description, task_type, parent_session_key, agent_role,
               skill_key, skill_domain, skill_task_type, skill_version,
               context_loaded, model_used, token_usage, status,
               sampled_session_keys, tenant_key, record_source, etl_run_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [key, native_id, session.project_key,
             session.task_description, session.task_type,
             session.parent_session_key, session.agent_role,
             session.skill_key, skill_domain, skill_task_type, skill_version,
             _json(session.context_loaded), session.model_used,
             _json(session.token_usage), session.status,
             _json(session.sampled_session_keys), tenant_key,
             session.record_source, session.etl_run_id],
        )
        # Cache skill attrs for subsequent trace inserts
        self._session_skill_cache[key] = {
            "skill_key": session.skill_key,
            "skill_domain": skill_domain,
            "skill_task_type": skill_task_type,
            "tenant_key": tenant_key,
        }
        return key

    def complete_session(
        self,
        session_key: str,
        *,
        status: SessionStatus = SessionStatus.COMPLETED,
        result: dict | None = None,
        token_usage: dict | None = None,
    ) -> None:
        self.con.execute(
            """UPDATE fact_session SET status = ?, result = ?, token_usage = ?,
               completed_at = current_timestamp WHERE session_key = ?""",
            [status, _json(result), _json(token_usage), session_key],
        )

    def update_session_progress(
        self,
        session_key: str,
        *,
        completed_at: datetime | None = None,
        model_used: str | None = None,
    ) -> None:
        """Accumulating-snapshot update from ingestion: a transcript's end
        time and last-seen model advance as a resumed session grows.
        Unlike complete_session, timestamps come from the transcript, not
        the wall clock, and result/token_usage are left untouched."""
        sets, params = [], []
        if completed_at is not None:
            sets.append("completed_at = ?")
            params.append(completed_at)
        if model_used is not None:
            sets.append("model_used = ?")
            params.append(model_used)
        if not sets:
            return
        params.append(session_key)
        self.con.execute(
            f"UPDATE fact_session SET {', '.join(sets)} WHERE session_key = ?",
            params,
        )

    def update_session_model(self, session_key: str, model_used: str) -> None:
        """Update the model_used field from a provider response."""
        self.con.execute(
            "UPDATE fact_session SET model_used = ? WHERE session_key = ?",
            [model_used, session_key],
        )

    def get_session(self, session_key: str) -> Session | None:
        d = self._fetchone(
            "SELECT * FROM fact_session WHERE session_key = ?", [session_key])
        return Session(**d) if d else None

    def list_sessions(
        self,
        status: SessionStatus | None = None,
        parent_key: str | None = None,
        skill_key: str | None = None,
        record_source: RecordSource | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        limit: int | None = None,
    ) -> list[Session]:
        query = "SELECT * FROM fact_session WHERE 1=1"
        params: list = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if parent_key is not None:
            query += " AND parent_session_key = ?"
            params.append(parent_key)
        if skill_key is not None:
            query += " AND skill_key = ?"
            params.append(skill_key)
        if record_source is not None:
            query += " AND record_source = ?"
            params.append(record_source)
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

    def insert_trace(self, trace: Trace) -> str:
        """Insert a trace node. Denormalizes skill attrs from session.

        Key: (session_key, depth, sequence_order, title) -- deterministic,
        so bulk re-imports of the same trace buffer are idempotent.
        """
        key = dimension_key(trace.session_key, trace.depth,
                            trace.sequence_order, trace.title)
        if self._key_exists("fact_trace", key):
            return key
        skill_key = trace.skill_key
        skill_domain = trace.skill_domain
        skill_task_type = trace.skill_task_type
        tenant_key = trace.tenant_key
        if skill_key is None:
            attrs = self._get_session_skill_attrs(trace.session_key)
            if attrs is None:
                raise ValueError(f"Session {trace.session_key} not found")
            skill_key = attrs.get("skill_key")
            skill_domain = attrs.get("skill_domain")
            skill_task_type = attrs.get("skill_task_type")
            if tenant_key is None:
                tenant_key = attrs.get("tenant_key")
        tenant_key = tenant_key or self._default_tenant_key
        self.con.execute(
            """INSERT INTO fact_trace (trace_key, session_key, parent_trace_key,
               trace_type, depth, sequence_order, title, content, reasoning,
               alternatives, outcome, child_session_key, duration_ms,
               skill_key, skill_domain, skill_task_type, tenant_key,
               record_source, etl_run_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [key, trace.session_key, trace.parent_trace_key, trace.trace_type,
             trace.depth, trace.sequence_order, trace.title, trace.content,
             trace.reasoning, _json(trace.alternatives), _json(trace.outcome),
             trace.child_session_key, trace.duration_ms,
             skill_key, skill_domain, skill_task_type, tenant_key,
             trace.record_source, trace.etl_run_id],
        )
        return key

    def get_trace(self, trace_key: str) -> Trace | None:
        """Fetch a single trace node by key."""
        d = self._fetchone(
            "SELECT * FROM fact_trace WHERE trace_key = ?", [trace_key])
        return Trace(**d) if d else None

    def get_session_traces(self, session_key: str) -> list[Trace]:
        """Get all trace nodes for a session, ordered for tree rendering."""
        return [Trace(**d) for d in self._fetchall(
            "SELECT * FROM fact_trace WHERE session_key = ? "
            "ORDER BY depth, sequence_order",
            [session_key],
        )]

    def get_trace_children(self, parent_trace_key: str) -> list[Trace]:
        """Get immediate children of a trace node."""
        return [Trace(**d) for d in self._fetchall(
            "SELECT * FROM fact_trace WHERE parent_trace_key = ? "
            "ORDER BY sequence_order",
            [parent_trace_key],
        )]

    def count_traces_by_type(self, session_key: str) -> list[tuple[str, int]]:
        """Count traces by type for a session -- summary statistics."""
        rows = self.con.execute(
            """SELECT trace_type, COUNT(*) as cnt
               FROM fact_trace WHERE session_key = ?
               GROUP BY trace_type ORDER BY cnt DESC""",
            [session_key],
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    def delete_session_traces(self, session_key: str) -> int:
        """Delete all traces for a session. Returns count deleted.
        Also deletes fact_trace_feedback referencing these traces."""
        row = self.con.execute(
            "SELECT COUNT(*) FROM fact_trace WHERE session_key = ?", [session_key],
        ).fetchone()
        count = row[0] if row else 0
        # Delete trace feedback first (no FK but maintain referential integrity)
        self.con.execute(
            "DELETE FROM fact_trace_feedback WHERE trace_key IN "
            "(SELECT trace_key FROM fact_trace WHERE session_key = ?)",
            [session_key],
        )
        self.con.execute(
            "DELETE FROM fact_trace WHERE session_key = ?", [session_key])
        return count

    # -------------------------------------------------------------------
    # Trace Feedback (fact_trace_feedback)
    # -------------------------------------------------------------------

    def insert_trace_feedback(self, tf: TraceFeedback) -> str:
        """Insert feedback on a specific trace node. Denormalizes trace + skill attrs."""
        trace_type = tf.trace_type
        trace_title = tf.trace_title
        skill_key = tf.skill_key
        skill_domain = tf.skill_domain
        skill_task_type = tf.skill_task_type
        tenant_key = tf.tenant_key
        if trace_type is None:
            trace = self.get_trace(tf.trace_key)
            if trace is None:
                raise ValueError(f"Trace {tf.trace_key} not found")
            trace_type = trace.trace_type
            trace_title = trace.title
            skill_key = trace.skill_key
            skill_domain = trace.skill_domain
            skill_task_type = trace.skill_task_type
            if tenant_key is None:
                tenant_key = trace.tenant_key
        tenant_key = tenant_key or self._default_tenant_key
        key = dimension_key(tf.trace_key, uuid4().hex)
        self.con.execute(
            """INSERT INTO fact_trace_feedback (trace_feedback_key, trace_key,
               session_key, feedback_type, content, correction, created_by,
               trace_type, trace_title, skill_key, skill_domain, skill_task_type,
               tenant_key, record_source, etl_run_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [key, tf.trace_key, tf.session_key, tf.feedback_type,
             tf.content, _json(tf.correction), tf.created_by,
             trace_type, trace_title, skill_key, skill_domain, skill_task_type,
             tenant_key, tf.record_source, tf.etl_run_id],
        )
        return key

    def list_trace_feedback(
        self,
        *,
        trace_key: str | None = None,
        session_key: str | None = None,
        feedback_type: TraceFeedbackType | None = None,
    ) -> list[TraceFeedback]:
        """List trace feedback, filterable by trace, session, or type."""
        query = "SELECT * FROM fact_trace_feedback WHERE 1=1"
        params: list = []
        if trace_key is not None:
            query += " AND trace_key = ?"
            params.append(trace_key)
        if session_key is not None:
            query += " AND session_key = ?"
            params.append(session_key)
        if feedback_type is not None:
            query += " AND feedback_type = ?"
            params.append(feedback_type)
        query += " ORDER BY created_at DESC"
        return [TraceFeedback(**d) for d in self._fetchall(query, params)]

    def aggregate_trace_feedback(
        self,
        session_key: str,
    ) -> list[tuple[str, int]]:
        """Count trace feedback by type for a session. No join needed."""
        rows = self.con.execute(
            """SELECT feedback_type, COUNT(*)
               FROM fact_trace_feedback
               WHERE session_key = ?
               GROUP BY feedback_type ORDER BY COUNT(*) DESC""",
            [session_key],
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    def get_trace_with_feedback(self, trace_key: str) -> dict | None:
        """Fetch a trace with all its feedback records."""
        trace = self.get_trace(trace_key)
        if trace is None:
            return None
        feedback = self.list_trace_feedback(trace_key=trace_key)
        return {"trace": trace, "feedback": feedback}

    # -------------------------------------------------------------------
    # Extractions (fact_extraction)
    # -------------------------------------------------------------------

    def insert_extraction(self, extraction: Extraction) -> str:
        self._require("fact_session", extraction.session_key, "Session")
        # Denormalize source attributes (validates existence as side effect)
        source_path = extraction.source_path
        source_media_type = extraction.source_media_type
        if source_path is None:
            source = self.get_source(extraction.source_key)
            if source is None:
                raise ValueError(f"Source {extraction.source_key} not found")
            source_path = source.content_path
            source_media_type = source.media_type
        # Denormalize skill attributes (validates existence as side effect)
        skill_domain, skill_task_type, skill_version, skill_tenant_key = (
            self._resolve_skill_attrs(
                extraction.skill_key, extraction.skill_domain,
                extraction.skill_task_type, extraction.skill_version,
            )
        )
        tenant_key = skill_tenant_key or extraction.tenant_key or self._default_tenant_key
        # uuid-salted: native event, intrinsically unique, never re-ingested
        key = dimension_key(extraction.session_key, extraction.source_key,
                            uuid4().hex)
        self.con.execute(
            """INSERT INTO fact_extraction (extraction_key, session_key, output,
               confidence, validation_status, source_key, source_path,
               source_media_type, skill_key, skill_domain, skill_task_type,
               skill_version, tenant_key, record_source, etl_run_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [key, extraction.session_key, _json(extraction.output),
             extraction.confidence, extraction.validation_status,
             extraction.source_key, source_path, source_media_type,
             extraction.skill_key, skill_domain, skill_task_type, skill_version,
             tenant_key, extraction.record_source, extraction.etl_run_id],
        )
        return key

    def get_extraction(self, extraction_key: str) -> Extraction | None:
        d = self._fetchone(
            "SELECT * FROM fact_extraction WHERE extraction_key = ?",
            [extraction_key])
        return Extraction(**d) if d else None

    def update_validation(
        self,
        extraction_key: str,
        *,
        status: ValidationStatus,
        validated_by: str | None = None,
    ) -> None:
        self.con.execute(
            """UPDATE fact_extraction SET validation_status = ?, validated_by = ?,
               validated_at = current_timestamp WHERE extraction_key = ?""",
            [status, validated_by, extraction_key],
        )

    def list_extractions(
        self,
        skill_key: str | None = None,
        validation_status: ValidationStatus | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        limit: int = 50,
    ) -> list[Extraction]:
        query = "SELECT * FROM fact_extraction WHERE 1=1"
        params: list = []
        if skill_key is not None:
            query += " AND skill_key = ?"
            params.append(skill_key)
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

    def get_validated_extractions(self, skill_key: str, limit: int = 10) -> list[Extraction]:
        """Retrieval query: find prior validated extractions for a skill."""
        return self.list_extractions(
            skill_key=skill_key, validation_status=ValidationStatus.VALIDATED,
            limit=limit,
        )

    def get_extraction_with_feedback(self, extraction_key: str) -> dict | None:
        """Fetch extraction with all its feedback records."""
        extraction = self.get_extraction(extraction_key)
        if extraction is None:
            return None
        feedback = [Feedback(**d) for d in self._fetchall(
            "SELECT * FROM fact_feedback WHERE extraction_key = ? ORDER BY created_at",
            [extraction_key],
        )]
        return {"extraction": extraction, "feedback": feedback}

    # -------------------------------------------------------------------
    # Feedback (fact_feedback)
    # -------------------------------------------------------------------

    def insert_feedback(self, fb: Feedback) -> str:
        # Denormalize skill attributes (validates existence as side effect)
        skill_domain, skill_task_type, skill_version, skill_tenant_key = (
            self._resolve_skill_attrs(
                fb.skill_key, fb.skill_domain, fb.skill_task_type, fb.skill_version,
            )
        )
        tenant_key = skill_tenant_key or fb.tenant_key or self._default_tenant_key
        # Denormalize source attributes from extraction (validates existence)
        source_key = fb.source_key
        source_path = fb.source_path
        if source_key is None:
            ext = self.get_extraction(fb.extraction_key)
            if ext is None:
                raise ValueError(f"Extraction {fb.extraction_key} not found")
            source_key = ext.source_key
            source_path = ext.source_path
            if source_path is None:
                source = self.get_source(ext.source_key)
                if source:
                    source_path = source.content_path
        # uuid-salted: native event, intrinsically unique, never re-ingested
        key = dimension_key(fb.extraction_key, uuid4().hex)
        self.con.execute(
            """INSERT INTO fact_feedback (feedback_key, extraction_key, session_key,
               correction, correction_type, notes, created_by,
               skill_key, skill_domain, skill_task_type, skill_version,
               source_key, source_path, tenant_key, record_source, etl_run_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [key, fb.extraction_key, fb.session_key,
             _json(fb.correction), fb.correction_type, fb.notes, fb.created_by,
             fb.skill_key, skill_domain, skill_task_type, skill_version,
             source_key, source_path, tenant_key, fb.record_source, fb.etl_run_id],
        )
        return key

    def list_feedback(self, skill_key: str | None = None) -> list[Feedback]:
        query = "SELECT * FROM fact_feedback WHERE 1=1"
        params: list = []
        if skill_key is not None:
            query += " AND skill_key = ?"
            params.append(skill_key)
        query += " ORDER BY created_at DESC"
        return [Feedback(**d) for d in self._fetchall(query, params)]

    def aggregate_feedback(
        self,
        skill_key: str,
        *,
        include_examples: bool = False,
        max_examples: int = 3,
    ) -> list[dict]:
        """Count corrections by type for a skill, with field-level detail.

        Uses v_feedback_by_skill and v_feedback_fields views.
        Returns: [{"correction_type": str, "count": int, "fields": [str], "examples": [dict]}]
        """
        type_rows = self._fetchall(
            """SELECT correction_type, correction_count as cnt
               FROM v_feedback_by_skill
               WHERE skill_key = ?
               ORDER BY correction_count DESC""",
            [skill_key],
        )

        field_rows = self._fetchall(
            "SELECT correction_type, field_name FROM v_feedback_fields "
            "WHERE skill_key = ?",
            [skill_key],
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
                       WHERE skill_key = ? AND correction_type = ?
                       ORDER BY created_at DESC LIMIT ?""",
                    [skill_key, ct, max_examples],
                )
                entry["examples"] = [r["correction"] for r in example_rows]
            results.append(entry)

        return results

    # -------------------------------------------------------------------
    # Messages and tool uses (fact_message, fact_tool_use) -- ingested grain
    # -------------------------------------------------------------------

    def insert_message(self, msg: Message) -> str:
        """Insert a transcript message. Key: (session_key, entry_uuid) --
        deterministic; re-ingestion skips existing rows.

        Delegates to insert_messages: one write path per table, so the
        column list cannot drift between single and batch inserts."""
        if msg.entry_uuid is None:
            msg = msg.model_copy(update={"entry_uuid": uuid4().hex})
        self.insert_messages([msg])
        return self.message_key_for(msg.session_key, msg.entry_uuid)

    def insert_tool_use(self, tu: ToolUse) -> str:
        """Insert a tool use. Key: (session_key, tool_use_id) --
        deterministic; re-ingestion skips existing rows. Delegates to
        insert_tool_uses (one write path per table)."""
        if tu.tool_use_id is None:
            tu = tu.model_copy(update={"tool_use_id": uuid4().hex})
        self.insert_tool_uses([tu])
        return dimension_key(tu.session_key, tu.tool_use_id)

    def _existing_keys(self, table: str, group_col: str, group_val: str) -> set[str]:
        """Existing keys for one grouping value -- session_key for
        messages/tool_uses, stream_key for events. The batched existence
        check is what makes unchanged re-ingest cheap (per-row round trips
        are the ingestion hot path's dominant cost). group_col comes from
        internal call sites only, never caller input."""
        key_col = _KEY_COLUMNS[table]
        return {d[key_col] for d in self._fetchall(
            f"SELECT {key_col} FROM {table} WHERE {group_col} = ?",
            [group_val],
        )}

    def _bulk_insert_json(
        self, table: str, col_types: dict[str, str], rows: list[dict],
    ) -> None:
        """Spill rows to a temp newline-delimited JSON file and load with
        one `read_json` INSERT -- the fresh-ingest speed fix (BACKLOG
        "fresh-ingest insert speed"; measured ~300-600x over per-row
        executemany at ingest volumes on a 50k-row fixture). orjson
        serializes nested dict/list values as native JSON (not
        double-encoded strings) and datetimes as ISO 8601, both of which
        `columns=` type-casts correctly on read. table/col_types come from
        internal call sites only (never caller input) -- same trust
        boundary as the rest of this file's f-string SQL. The temp
        directory is always cleaned up, success or failure, via
        TemporaryDirectory's context manager.
        """
        if not rows:
            return
        columns = list(col_types.keys())
        with tempfile.TemporaryDirectory() as tmpdir:
            spill_path = os.path.join(tmpdir, "spill.jsonl")
            with open(spill_path, "wb") as f:
                for row in rows:
                    f.write(orjson.dumps(row))
                    f.write(b"\n")
            cols_sql = ", ".join(columns)
            types_sql = ", ".join(f"'{c}': '{col_types[c]}'" for c in columns)
            self.con.execute(
                f"""INSERT INTO {table} ({cols_sql})
                    SELECT {cols_sql} FROM read_json(?, format='newline_delimited',
                    columns={{{types_sql}}})""",
                [spill_path],
            )

    @staticmethod
    def message_key_for(session_key: str, entry_uuid: str) -> str:
        """The message-key recipe, named -- the sibling of session_key_for."""
        return dimension_key(session_key, entry_uuid)

    @staticmethod
    def _require_single_session(rows, label: str) -> str:
        """Batch inserts dedupe against ONE session's existing keys; a
        mixed-session batch would silently duplicate rows from the others."""
        session_keys = {r.session_key for r in rows}
        if len(session_keys) != 1:
            raise ValueError(f"{label} batch must contain a single session_key, "
                             f"got {len(session_keys)}")
        return session_keys.pop()

    def insert_messages(self, msgs: list[Message]) -> dict[str, str]:
        """Bulk insert for one session's messages: one existing-key fetch,
        then a single spill-to-JSON insert for the misses only -- the
        batched existence check is what makes unchanged re-ingest cheap.

        Skips keys already present (same semantics as insert_message);
        raises on mixed-session batches. Returns {entry_uuid: message_key}
        for every input row, so callers can reference message keys without
        re-deriving the recipe.
        """
        if not msgs:
            return {}
        session_key = self._require_single_session(msgs, "insert_messages")
        existing = self._existing_keys("fact_message", "session_key", session_key)
        key_map: dict[str, str] = {}
        rows = []
        for m in msgs:
            key = self.message_key_for(m.session_key, m.entry_uuid or uuid4().hex)
            if m.entry_uuid:
                key_map[m.entry_uuid] = key
            if key in existing:
                continue
            existing.add(key)  # dedupe within the batch too
            rows.append({
                "message_key": key, "session_key": m.session_key,
                "project_key": m.project_key, "role": m.role,
                "entry_uuid": m.entry_uuid, "parent_uuid": m.parent_uuid,
                "sequence_num": m.sequence_num, "occurred_at": m.occurred_at,
                "content_text": m.content_text, "has_thinking": m.has_thinking,
                "stop_reason": m.stop_reason, "input_tokens": m.input_tokens,
                "output_tokens": m.output_tokens, "is_meta": m.is_meta,
                "is_sidechain": m.is_sidechain,
                "tenant_key": m.tenant_key or self._default_tenant_key,
                "record_source": m.record_source, "etl_run_id": m.etl_run_id,
            })
        self._bulk_insert_json("fact_message", _MESSAGE_JSON_TYPES, rows)
        return key_map

    def insert_tool_uses(self, tus: list[ToolUse]) -> int:
        """Bulk insert for one session's tool uses; see insert_messages.
        Returns the number of rows actually written."""
        if not tus:
            return 0
        session_key = self._require_single_session(tus, "insert_tool_uses")
        existing = self._existing_keys("fact_tool_use", "session_key", session_key)
        rows = []
        for tu in tus:
            key = dimension_key(tu.session_key, tu.tool_use_id or uuid4().hex)
            if key in existing:
                continue
            existing.add(key)
            rows.append({
                "tool_use_key": key, "session_key": tu.session_key,
                "project_key": tu.project_key, "message_key": tu.message_key,
                "tool_use_id": tu.tool_use_id, "tool_name": tu.tool_name,
                "tool_input": tu.tool_input, "is_error": tu.is_error,
                "result_text": tu.result_text, "sequence_num": tu.sequence_num,
                "occurred_at": tu.occurred_at,
                "tenant_key": tu.tenant_key or self._default_tenant_key,
                "record_source": tu.record_source, "etl_run_id": tu.etl_run_id,
            })
        self._bulk_insert_json("fact_tool_use", _TOOL_USE_JSON_TYPES, rows)
        return len(rows)

    # -------------------------------------------------------------------
    # Events (fact_event) -- generic event grain (M5)
    # -------------------------------------------------------------------

    @staticmethod
    def stream_key_for(record_source: RecordSource, native_stream_id: str) -> str:
        """The stream-key recipe, named -- the generalization of
        session_key_for for non-transcript event sources."""
        return dimension_key(record_source.value, native_stream_id)

    @staticmethod
    def event_key_for(stream_key: str, native_event_id: str) -> str:
        """The event-key recipe, named -- sibling of message_key_for."""
        return dimension_key(stream_key, native_event_id)

    @staticmethod
    def _require_single_stream(rows, label: str) -> str:
        """Batch inserts dedupe against ONE stream's existing keys; a
        mixed-stream batch would silently duplicate rows from the others.
        Sibling of _require_single_session."""
        stream_keys = {r.stream_key for r in rows}
        if len(stream_keys) != 1:
            raise ValueError(f"{label} batch must contain a single stream_key, "
                             f"got {len(stream_keys)}")
        return stream_keys.pop()

    def insert_events(self, events: list[Event]) -> int:
        """Bulk insert for one stream's events -- sibling of
        insert_messages/insert_tool_uses (batched existence check, then a
        spill-to-JSON insert for the misses only). event_type is
        registry-validated against dim_event_type before any row is
        written (open vocabulary, same pattern as finding_type) -- fails
        closed on an unregistered type. Raises on mixed-stream batches.
        Returns the number of rows actually written.
        """
        if not events:
            return 0
        stream_key = self._require_single_stream(events, "insert_events")
        for et in {e.event_type for e in events}:
            if self.get_event_type(et) is None:
                raise ValueError(
                    f"event_type '{et}' is not registered in dim_event_type -- "
                    f"register it first (it's a row, not an enum)"
                )
        existing = self._existing_keys("fact_event", "stream_key", stream_key)
        rows = []
        for ev in events:
            key = self.event_key_for(ev.stream_key, ev.native_event_id or uuid4().hex)
            if key in existing:
                continue
            existing.add(key)
            rows.append({
                "event_key": key, "stream_key": ev.stream_key,
                "native_event_id": ev.native_event_id, "event_type": ev.event_type,
                "occurred_at": ev.occurred_at, "actor": ev.actor,
                "payload": ev.payload, "content_text": ev.content_text,
                "signature": ev.signature, "sequence_num": ev.sequence_num,
                "tenant_key": ev.tenant_key or self._default_tenant_key,
                "record_source": ev.record_source, "etl_run_id": ev.etl_run_id,
            })
        self._bulk_insert_json("fact_event", _EVENT_JSON_TYPES, rows)
        return len(rows)

    def insert_event(self, ev: Event) -> str:
        """Insert a single event. Delegates to insert_events (one write
        path per table, sibling of insert_message/insert_tool_use)."""
        if ev.native_event_id is None:
            ev = ev.model_copy(update={"native_event_id": uuid4().hex})
        self.insert_events([ev])
        return self.event_key_for(ev.stream_key, ev.native_event_id)

    def get_event(self, event_key: str) -> Event | None:
        d = self._fetchone(
            "SELECT * FROM fact_event WHERE event_key = ?", [event_key])
        return Event(**d) if d else None

    def list_events(
        self,
        stream_key: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[Event]:
        query = "SELECT * FROM fact_event WHERE 1=1"
        params: list = []
        if stream_key is not None:
            query += " AND stream_key = ?"
            params.append(stream_key)
        if event_type is not None:
            query += " AND event_type = ?"
            params.append(event_type)
        query += " ORDER BY occurred_at DESC LIMIT ?"
        params.append(limit)
        return [Event(**d) for d in self._fetchall(query, params)]

    # -------------------------------------------------------------------
    # Session facets (fact_session_facets)
    # -------------------------------------------------------------------

    def insert_session_facet(self, facet: SessionFacet) -> str:
        """Insert a facet value. Registry-validated: the (facet_id,
        prompt_version) must be registered in dim_facet_type first.
        Key is deterministic -- re-running a populator is idempotent."""
        facet_type_key = facet.facet_type_key or dimension_key(
            facet.facet_id, facet.prompt_version)
        self._require("dim_facet_type", facet_type_key,
                      f"Facet type {facet.facet_id} v{facet.prompt_version}")
        key = dimension_key(facet.session_key, facet.facet_id, facet.prompt_version)
        if self._key_exists("fact_session_facets", key):
            return key
        self.con.execute(
            """INSERT INTO fact_session_facets (facet_row_key, session_key,
               facet_type_key, facet_id, prompt_version, value_text, value_numeric,
               value_bool, value_json, is_fallback, extraction_metadata,
               tenant_key, record_source, etl_run_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [key, facet.session_key, facet_type_key, facet.facet_id,
             facet.prompt_version, facet.value_text, facet.value_numeric,
             facet.value_bool, _json(facet.value_json), facet.is_fallback,
             _json(facet.extraction_metadata),
             facet.tenant_key or self._default_tenant_key,
             facet.record_source, facet.etl_run_id],
        )
        return key

    def get_session_facets(self, session_key: str) -> list[SessionFacet]:
        return [SessionFacet(**d) for d in self._fetchall(
            "SELECT * FROM fact_session_facets WHERE session_key = ? "
            "ORDER BY facet_id, prompt_version",
            [session_key],
        )]

    # -------------------------------------------------------------------
    # Findings (fact_finding) -- registry-validated open vocabulary
    # -------------------------------------------------------------------

    def insert_finding(self, finding: Finding) -> str:
        """Insert a couch finding. finding_type must be registered in
        dim_finding_type (decided 2026-07-07: registry, not enum)."""
        ft = self.get_finding_type(finding.finding_type)
        if ft is None:
            raise ValueError(
                f"finding_type '{finding.finding_type}' is not registered in "
                f"dim_finding_type -- register it first (it's a row, not an enum)"
            )
        key = dimension_key(finding.finding_type, finding.scope.value,
                            finding.project_key, finding.summary,
                            finding.etl_run_id)
        if self._key_exists("fact_finding", key):
            return key
        self.con.execute(
            """INSERT INTO fact_finding (finding_key, finding_type, finding_type_key,
               scope, project_key, evidence_session_keys, occurrence_count, summary,
               tenant_key, record_source, etl_run_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [key, finding.finding_type, ft.finding_type_key, finding.scope,
             finding.project_key, _json(finding.evidence_session_keys),
             finding.occurrence_count, finding.summary,
             finding.tenant_key or self._default_tenant_key,
             finding.record_source, finding.etl_run_id],
        )
        return key

    def get_finding(self, finding_key: str) -> Finding | None:
        d = self._fetchone(
            "SELECT * FROM fact_finding WHERE finding_key = ?", [finding_key])
        return Finding(**d) if d else None

    def list_findings(
        self,
        finding_type: str | None = None,
        scope: str | None = None,
        project_key: str | None = None,
        limit: int = 100,
    ) -> list[Finding]:
        query = "SELECT * FROM fact_finding WHERE 1=1"
        params: list = []
        if finding_type is not None:
            query += " AND finding_type = ?"
            params.append(finding_type)
        if scope is not None:
            query += " AND scope = ?"
            params.append(scope)
        if project_key is not None:
            query += " AND project_key = ?"
            params.append(project_key)
        query += " ORDER BY detected_at DESC LIMIT ?"
        params.append(limit)
        return [Finding(**d) for d in self._fetchall(query, params)]

    # -------------------------------------------------------------------
    # Proposals (fact_proposal)
    # -------------------------------------------------------------------

    def insert_proposal(self, proposal: Proposal) -> str:
        key = dimension_key(proposal.target_dimension.value,
                            proposal.target_key, uuid4().hex)
        self.con.execute(
            """INSERT INTO fact_proposal (proposal_key, target_dimension, target_key,
               target_natural_key, proposed_content, proposed_version, status,
               evidence_finding_keys, review_notes, tenant_key, record_source,
               etl_run_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [key, proposal.target_dimension, proposal.target_key,
             _json(proposal.target_natural_key), proposal.proposed_content,
             proposal.proposed_version, proposal.status,
             _json(proposal.evidence_finding_keys), proposal.review_notes,
             proposal.tenant_key or self._default_tenant_key,
             proposal.record_source, proposal.etl_run_id],
        )
        return key

    def get_proposal(self, proposal_key: str) -> Proposal | None:
        d = self._fetchone(
            "SELECT * FROM fact_proposal WHERE proposal_key = ?", [proposal_key])
        return Proposal(**d) if d else None

    def get_approving_proposal(self, resulting_dimension_key: str) -> Proposal | None:
        """Latest approved proposal that produced a dimension entity --
        the provenance lookup the compiler stamps into artifacts."""
        d = self._fetchone(
            """SELECT * FROM fact_proposal
               WHERE resulting_dimension_key = ? AND status = ?
               ORDER BY reviewed_at DESC LIMIT 1""",
            [resulting_dimension_key, ProposalStatus.APPROVED],
        )
        return Proposal(**d) if d else None

    def list_proposals(
        self,
        status: ProposalStatus | None = None,
        limit: int = 100,
    ) -> list[Proposal]:
        query = "SELECT * FROM fact_proposal WHERE 1=1"
        params: list = []
        if status is not None:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return [Proposal(**d) for d in self._fetchall(query, params)]

    def approve_proposal(self, proposal_key: str, *, reviewed_by: str | None = None) -> str:
        """Approve a pending proposal: apply it to the target dimension
        (SCD-2 evolution) and record the resulting dimension key. This
        is the one step in the flywheel only a person can do -- nothing
        calls it automatically.

        Returns the entity key of the evolved/created dimension row.
        """
        p = self.get_proposal(proposal_key)
        if p is None:
            raise ValueError(f"Proposal {proposal_key} not found")
        if p.status != ProposalStatus.PENDING:
            raise ValueError(f"Proposal {proposal_key} is not pending ({p.status.value})")
        nk = p.target_natural_key or {}
        tenant_id = nk.get("tenant_id", "default")

        if p.target_dimension == TargetDimension.DIM_RULE:
            if not nk.get("name"):
                raise ValueError("Rule proposal requires target_natural_key.name")
            result_key = self.insert_rule(Rule(
                name=nk["name"],
                tenant_id=tenant_id,
                scope=RuleScope(nk.get("scope", RuleScope.GLOBAL.value)),
                domain=nk.get("domain"),
                priority=nk.get("priority", 0),
                content=p.proposed_content,
                status=RuleStatus.ACTIVE,
                record_source=RecordSource.DERIVED,
            ))
        elif p.target_dimension == TargetDimension.DIM_SKILL:
            if not nk.get("domain") or not nk.get("task_type"):
                raise ValueError(
                    "Skill proposal requires target_natural_key.domain and .task_type")
            current = self.get_skill(dimension_key(tenant_id, nk["domain"], nk["task_type"]))
            version = p.proposed_version or (current.version + 1 if current else 1)
            result_key = self.insert_skill(Skill(
                domain=nk["domain"], task_type=nk["task_type"], version=version,
                tenant_id=tenant_id,
                content=p.proposed_content, status=SkillStatus.ACTIVE,
                origin=SkillOrigin.DATA_DERIVED,
                record_source=RecordSource.DERIVED,
            ))
        else:  # TargetDimension.DIM_SAMPLING_CONFIG
            cfg = _from_json(p.proposed_content)
            if not isinstance(cfg, dict) or "strategy" not in cfg:
                raise ValueError(
                    "Sampling-config proposal requires proposed_content as JSON "
                    "with a strategy field")
            result_key = self.insert_sampling_config(SamplingConfig(
                domain=nk.get("domain"), task_type=nk.get("task_type"),
                tenant_id=tenant_id,
                strategy=SamplingStrategy(cfg["strategy"]),
                parameters=cfg.get("parameters", {}),
                max_samples=cfg.get("max_samples", 3),
                record_source=RecordSource.DERIVED,
            ))

        self.con.execute(
            """UPDATE fact_proposal SET status = ?, resulting_dimension_key = ?,
               reviewed_by = ?, reviewed_at = current_timestamp
               WHERE proposal_key = ?""",
            [ProposalStatus.APPROVED, result_key, reviewed_by, proposal_key],
        )
        return result_key

    def reject_proposal(
        self,
        proposal_key: str,
        *,
        reviewed_by: str | None = None,
        review_notes: str | None = None,
    ) -> None:
        """Reject a pending proposal. No dimension change, no compile.

        review_notes is what makes the rejection rate readable later: the rate
        alone cannot tell a gate catching real problems from one objecting to
        wording.
        """
        p = self.get_proposal(proposal_key)
        if p is None:
            raise ValueError(f"Proposal {proposal_key} not found")
        if p.status != ProposalStatus.PENDING:
            raise ValueError(f"Proposal {proposal_key} is not pending ({p.status.value})")
        self.con.execute(
            """UPDATE fact_proposal SET status = ?, reviewed_by = ?,
               review_notes = ?, reviewed_at = current_timestamp
               WHERE proposal_key = ?""",
            [ProposalStatus.REJECTED, reviewed_by, review_notes, proposal_key],
        )

    # -------------------------------------------------------------------
    # SCD-2 rollback
    # -------------------------------------------------------------------

    _SCD2_TABLES = ("dim_skill", "dim_source", "dim_rule", "dim_sampling_config")

    def rollback_dimension(self, table: str, key: str) -> None:
        """Roll an entity back one SCD-2 version: close the current row,
        reopen the most recently closed one. Symmetric with evolution --
        no destructive undo, the rolled-back row stays in history.
        Recompile after rolling back to update materialized files."""
        if table not in self._SCD2_TABLES:
            raise ValueError(f"{table} is not an SCD-2 dimension")
        key_col = _KEY_COLUMNS[table]
        prior = self._fetchone(
            f"""SELECT effective_from FROM {table}
                WHERE {key_col} = ? AND NOT is_current
                ORDER BY effective_from DESC LIMIT 1""",
            [key],
        )
        if prior is None:
            raise ValueError(f"{table} {key} has no prior version to roll back to")
        self._close_current(table, key)
        self.con.execute(
            f"""UPDATE {table} SET is_current = TRUE, effective_to = NULL
                WHERE {key_col} = ? AND effective_from = ?""",
            [key, prior["effective_from"]],
        )

    # -------------------------------------------------------------------
    # Load log (meta_load_log)
    # -------------------------------------------------------------------

    def start_load_run(
        self,
        operation: str,
        *,
        record_source: RecordSource = RecordSource.NATIVE,
    ) -> str:
        """Open a load-log row for an ingestion/compile run; returns etl_run_id."""
        etl_run_id = uuid4().hex
        self.con.execute(
            """INSERT INTO meta_load_log (etl_run_id, operation, status, record_source)
               VALUES (?, ?, ?, ?)""",
            [etl_run_id, operation, SessionStatus.RUNNING, record_source],
        )
        return etl_run_id

    def complete_load_run(
        self,
        etl_run_id: str,
        *,
        status: SessionStatus = SessionStatus.COMPLETED,
        rows_read: int = 0,
        rows_written: int = 0,
        rows_skipped: int = 0,
        error: str | None = None,
    ) -> None:
        self.con.execute(
            """UPDATE meta_load_log SET status = ?, completed_at = current_timestamp,
               rows_read = ?, rows_written = ?, rows_skipped = ?, error = ?
               WHERE etl_run_id = ?""",
            [status, rows_read, rows_written, rows_skipped, error, etl_run_id],
        )

    def get_load_run(self, etl_run_id: str) -> LoadRun | None:
        d = self._fetchone(
            "SELECT * FROM meta_load_log WHERE etl_run_id = ?", [etl_run_id])
        return LoadRun(**d) if d else None

    @contextmanager
    def load_run(
        self,
        operation: str,
        *,
        record_source: RecordSource = RecordSource.NATIVE,
    ):
        """Load-run lifecycle scope shared by every analysis/ingest
        operation: opens a meta_load_log row, yields a LoadRunStats the
        caller mutates, and closes the row completed -- or failed with the
        error -- on exit. Counters accumulated before a failure are
        recorded either way: per-file transactions mean earlier writes are
        durable, and the ledger must not understate them."""
        etl_run_id = self.start_load_run(operation, record_source=record_source)
        stats = LoadRunStats(etl_run_id=etl_run_id)
        try:
            yield stats
        except Exception as e:
            self.complete_load_run(
                etl_run_id, status=SessionStatus.FAILED,
                rows_read=stats.rows_read, rows_written=stats.rows_written,
                rows_skipped=stats.rows_skipped,
                error=f"{type(e).__name__}: {e}")
            raise
        self.complete_load_run(
            etl_run_id, status=SessionStatus.COMPLETED,
            rows_read=stats.rows_read, rows_written=stats.rows_written,
            rows_skipped=stats.rows_skipped)

    # -------------------------------------------------------------------
    # Couch view queries (the store owns all SQL; couch.py owns thresholds)
    # -------------------------------------------------------------------

    def query_retry_loops(self, min_attempts: int) -> list[dict]:
        """Per (project, tool): identical-input call loops at or above the
        threshold, aggregated from v_retry_loops."""
        return self._fetchall(
            """SELECT project_key, tool_name,
                      COUNT(*) as loops,
                      MAX(attempts) as max_attempts,
                      SUM(attempts) as total_attempts,
                      LIST(DISTINCT session_key) as session_keys
               FROM v_retry_loops
               WHERE attempts >= ?
               GROUP BY project_key, tool_name""",
            [min_attempts],
        )

    def query_tool_error_clusters(
        self, min_uses: int, min_error_pct: float,
    ) -> list[dict]:
        return self._fetchall(
            """SELECT project_key, tool_name, uses, errors, error_pct,
                      error_session_keys
               FROM v_tool_error_clusters
               WHERE uses >= ? AND error_pct >= ?""",
            [min_uses, min_error_pct],
        )

    def query_interruption_hotspots(self, min_interruptions: int) -> list[dict]:
        return self._fetchall(
            """SELECT project_key, interruptions, session_count, session_keys
               FROM v_interruption_hotspots
               WHERE interruptions >= ?""",
            [min_interruptions],
        )

    def query_permission_friction(self, min_denials: int) -> list[dict]:
        return self._fetchall(
            """SELECT project_key, tool_name, denials, session_count, session_keys
               FROM v_permission_friction
               WHERE denials >= ?""",
            [min_denials],
        )

    # -------------------------------------------------------------------
    # Prior Run Sampling
    # -------------------------------------------------------------------

    def sample_prior_sessions(
        self,
        *,
        skill_key: str,
        strategy: SamplingStrategy = SamplingStrategy.RECENT,
        max_samples: int = 3,
        exclude_session_keys: list[str] | None = None,
    ) -> list[Session]:
        """Sample completed/failed sessions for context injection.

        Only samples completed or failed sessions (not running).
        Excludes sessions in exclude_session_keys (prevents self-sampling).
        """
        exclude = exclude_session_keys or []

        # Build reusable WHERE clause pieces
        where = "skill_key = ? AND status IN (?, ?)"
        base_params: list = [skill_key, SessionStatus.COMPLETED, SessionStatus.FAILED]
        if exclude:
            placeholders = ", ".join("?" for _ in exclude)
            where += f" AND session_key NOT IN ({placeholders})"
            base_params.extend(exclude)

        if strategy == SamplingStrategy.RECENT:
            return [Session(**d) for d in self._fetchall(
                f"SELECT * FROM fact_session WHERE {where} "
                f"ORDER BY created_at DESC LIMIT ?",
                base_params + [max_samples],
            )]

        if strategy == SamplingStrategy.RANDOM:
            return [Session(**d) for d in self._fetchall(
                f"SELECT * FROM fact_session WHERE {where} ORDER BY random() LIMIT ?",
                base_params + [max_samples],
            )]

        if strategy == SamplingStrategy.HIGH_FEEDBACK:
            # Use v_session_feedback_count view
            hf_where = "s.skill_key = ? AND s.status IN (?, ?)"
            hf_params: list = [skill_key, SessionStatus.COMPLETED, SessionStatus.FAILED]
            if exclude:
                hf_phs = ", ".join("?" for _ in exclude)
                hf_where += f" AND s.session_key NOT IN ({hf_phs})"
                hf_params.extend(exclude)
            return [Session(**d) for d in self._fetchall(
                f"""SELECT s.* FROM fact_session s
                    LEFT JOIN v_session_feedback_count v
                        ON v.session_key = s.session_key AND v.skill_key = s.skill_key
                    WHERE {hf_where}
                    ORDER BY COALESCE(v.feedback_count, 0) DESC
                    LIMIT ?""",
                hf_params + [max_samples],
            )]

        if strategy == SamplingStrategy.STRATIFIED_OUTCOME:
            def _fetch_by_status(st: SessionStatus) -> list[Session]:
                so_where = "skill_key = ? AND status = ?"
                so_params: list = [skill_key, st]
                if exclude:
                    so_phs = ", ".join("?" for _ in exclude)
                    so_where += f" AND session_key NOT IN ({so_phs})"
                    so_params.extend(exclude)
                return [Session(**d) for d in self._fetchall(
                    f"SELECT * FROM fact_session WHERE {so_where} "
                    f"ORDER BY created_at DESC LIMIT ?",
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
            # Use denormalized skill_key on fact_feedback
            sf_params: list = [skill_key, SessionStatus.COMPLETED, SessionStatus.FAILED]
            sf_where = "f.skill_key = ? AND s.status IN (?, ?)"
            if exclude:
                sf_phs = ", ".join("?" for _ in exclude)
                sf_where += f" AND s.session_key NOT IN ({sf_phs})"
                sf_params.extend(exclude)
            type_sessions = self.con.execute(
                f"""WITH ranked AS (
                        SELECT f.correction_type, s.session_key,
                               ROW_NUMBER() OVER (
                                   PARTITION BY f.correction_type
                                   ORDER BY s.created_at DESC
                               ) as rn
                        FROM fact_feedback f
                        JOIN fact_session s ON f.session_key = s.session_key
                        WHERE {sf_where}
                    )
                    SELECT session_key FROM ranked WHERE rn = 1""",
                sf_params,
            ).fetchall()

            seen: set[str] = set()
            session_keys: list[str] = []
            for (skey,) in type_sessions:
                if skey not in seen:
                    session_keys.append(skey)
                    seen.add(skey)
                if len(session_keys) >= max_samples:
                    break

            if not session_keys:
                return []
            placeholders = ", ".join("?" for _ in session_keys)
            return [Session(**d) for d in self._fetchall(
                f"SELECT * FROM fact_session WHERE session_key IN ({placeholders})",
                session_keys,
            )]

        return []

    # -------------------------------------------------------------------
    # Rich Session Retrieval
    # -------------------------------------------------------------------

    def get_session_with_context(self, session_key: str) -> dict | None:
        """Fetch a session with its traces, extractions, feedback, and trace feedback."""
        session = self.get_session(session_key)
        if session is None:
            return None

        traces = self.get_session_traces(session_key)
        extractions = [Extraction(**d) for d in self._fetchall(
            "SELECT * FROM fact_extraction WHERE session_key = ? ORDER BY created_at",
            [session_key],
        )]
        feedback = [Feedback(**d) for d in self._fetchall(
            "SELECT * FROM fact_feedback WHERE session_key = ? ORDER BY created_at",
            [session_key],
        )]
        trace_feedback = self.list_trace_feedback(session_key=session_key)

        return {
            "session": session,
            "traces": traces,
            "extractions": extractions,
            "feedback": feedback,
            "trace_feedback": trace_feedback,
        }

    def get_sessions_with_context(self, session_keys: list[str]) -> list[dict]:
        """Bulk version of get_session_with_context."""
        return [
            ctx for skey in session_keys
            if (ctx := self.get_session_with_context(skey)) is not None
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
        query = """SELECT DISTINCT skill_key, total_feedback
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
            skey = row["skill_key"]
            skill = self.get_skill(skey)
            if skill is None:
                continue
            patterns = self._fetchall(
                """SELECT correction_type, pattern_count
                   FROM v_skill_feedback_patterns
                   WHERE skill_key = ?
                   ORDER BY pattern_count DESC""",
                [skey],
            )
            results.append({
                "skill": skill,
                "patterns": [(r["correction_type"], r["pattern_count"]) for r in patterns],
                "total_feedback": row["total_feedback"],
            })

        return results

    def get_recurring_traces(
        self,
        skill_key: str,
        trace_type: TraceType,
        min_occurrences: int = 2,
    ) -> list[dict]:
        """Find recurring traces via v_recurring_traces view. No join needed."""
        rows = self._fetchall(
            """SELECT title, occurrence_count, session_keys, example_trace_key
               FROM v_recurring_traces
               WHERE skill_key = ? AND trace_type = ?
                 AND occurrence_count >= ?
               ORDER BY occurrence_count DESC""",
            [skill_key, trace_type, min_occurrences],
        )
        return [
            {
                "title": r["title"],
                "count": r["occurrence_count"],
                "session_keys": r["session_keys"],
                "example_trace_key": r["example_trace_key"],
            }
            for r in rows
        ]

    def get_recurring_trace_feedback(
        self,
        skill_key: str,
        min_occurrences: int = 2,
    ) -> list[dict]:
        """Find recurring trace feedback via v_recurring_trace_feedback view."""
        rows = self._fetchall(
            """SELECT feedback_type, trace_title, occurrence_count, session_keys
               FROM v_recurring_trace_feedback
               WHERE skill_key = ? AND occurrence_count >= ?
               ORDER BY occurrence_count DESC""",
            [skill_key, min_occurrences],
        )
        return [
            {
                "feedback_type": r["feedback_type"],
                "trace_title": r["trace_title"],
                "count": r["occurrence_count"],
                "session_keys": r["session_keys"],
            }
            for r in rows
        ]
