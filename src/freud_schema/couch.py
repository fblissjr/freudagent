"""The couch: analysis passes over the warehouse producing typed findings
(Phase 2 of the meta-harness plan).

Two layers, split by what needs inference:

- SQL layer (this module): deterministic detectors implemented as views
  in db.py (v_retry_loops, v_tool_error_clusters, v_interruption_hotspots,
  v_permission_friction). run_couch() applies thresholds and writes
  evidence-linked fact_finding rows. No model calls -- run it as often
  as you like.
- LLM layer (the /couch skill, .claude/skills/couch.md): findings that
  need judgment (user_correction_pattern). The harness fans out
  subagents over warehouse queries and writes findings via MCP; this
  library deliberately contains no model calls (no-orchestration rule).

Privacy: summaries are built from tool names, counts, and rates only --
never from tool inputs, message text, file paths, or URLs. Findings feed
Phase 3's compile step, which writes committed files, so summaries are
scrubbed by construction rather than by a later pass.

Findings are append-only trend data: each run records what it saw,
keyed by (finding_type, scope, project_key, summary, etl_run_id), so
"did this pattern shrink after the rule landed" is a plain query.
"""

from __future__ import annotations

from freud_schema.store import ExperimentStore
from freud_schema.tables import (
    DetectionMethod,
    Finding,
    FindingScope,
    FindingType,
    RecordSource,
    SessionStatus,
)

# Thresholds are deliberately conservative: a finding should be worth a
# human's review time. Tune per domain via new registry rows, not code.
RETRY_MIN_ATTEMPTS = 3
ERROR_CLUSTER_MIN_USES = 20
ERROR_CLUSTER_MIN_PCT = 15.0
INTERRUPTION_MIN = 3
PERMISSION_MIN_DENIALS = 3

SQL_FINDING_TYPES: dict[str, str] = {
    "retry_loop": "Same tool called with identical input 3+ times in one session",
    "tool_error_cluster": "A tool failing at an elevated rate within a project",
    "interruption_hotspot": "Repeated mid-turn user interruptions within a project",
    "permission_friction": "Repeated permission denials for the same tool in a project",
}

LLM_FINDING_TYPES: dict[str, str] = {
    "user_correction_pattern": "User corrected or redirected the agent in freeform "
                               "conversation (judged, not pattern-matched)",
    "recurring_dead_end": "The same dead end hit across sessions (from native "
                          "trace data or judged from transcripts)",
}


def seed_finding_types(store: ExperimentStore) -> None:
    """Register the couch's finding vocabulary. Idempotent -- new
    vocabularies are rows, never enum edits."""
    for name, desc in SQL_FINDING_TYPES.items():
        store.register_finding_type(FindingType(
            finding_type=name, description=desc,
            detection_method=DetectionMethod.SQL,
            record_source=RecordSource.DERIVED))
    for name, desc in LLM_FINDING_TYPES.items():
        store.register_finding_type(FindingType(
            finding_type=name, description=desc,
            detection_method=DetectionMethod.LLM,
            record_source=RecordSource.DERIVED))


def _insert(store, etl_run_id, finding_type, project_key, summary,
            evidence, count) -> str:
    return store.insert_finding(Finding(
        finding_type=finding_type,
        scope=FindingScope.PROJECT,
        project_key=project_key,
        evidence_session_keys=sorted(set(evidence)),
        occurrence_count=count,
        summary=summary,
        record_source=RecordSource.DERIVED,
        etl_run_id=etl_run_id,
    ))


def _detect_retry_loops(store, etl_run_id) -> int:
    """One finding per (project, tool): N identical-input loops, worst case."""
    rows = store._fetchall(
        """SELECT project_key, tool_name,
                  COUNT(*) as loops,
                  MAX(attempts) as max_attempts,
                  SUM(attempts) as total_attempts,
                  LIST(DISTINCT session_key) as session_keys
           FROM v_retry_loops
           WHERE attempts >= ?
           GROUP BY project_key, tool_name""",
        [RETRY_MIN_ATTEMPTS],
    )
    for r in rows:
        _insert(store, etl_run_id, "retry_loop", r["project_key"],
                f"{r['tool_name']}: {r['loops']} identical-input call loop(s) "
                f"across {len(r['session_keys'])} session(s), "
                f"worst {r['max_attempts']} attempts",
                r["session_keys"], r["total_attempts"])
    return len(rows)


def _detect_error_clusters(store, etl_run_id) -> int:
    rows = store._fetchall(
        """SELECT project_key, tool_name, uses, errors, error_pct, error_session_keys
           FROM v_tool_error_clusters
           WHERE uses >= ? AND error_pct >= ?""",
        [ERROR_CLUSTER_MIN_USES, ERROR_CLUSTER_MIN_PCT],
    )
    for r in rows:
        _insert(store, etl_run_id, "tool_error_cluster", r["project_key"],
                f"{r['tool_name']}: {r['errors']}/{r['uses']} calls failed "
                f"({r['error_pct']}%)",
                r["error_session_keys"] or [], r["errors"])
    return len(rows)


def _detect_interruptions(store, etl_run_id) -> int:
    rows = store._fetchall(
        """SELECT project_key, interruptions, session_count, session_keys
           FROM v_interruption_hotspots
           WHERE interruptions >= ?""",
        [INTERRUPTION_MIN],
    )
    for r in rows:
        _insert(store, etl_run_id, "interruption_hotspot", r["project_key"],
                f"{r['interruptions']} mid-turn interruptions across "
                f"{r['session_count']} session(s)",
                r["session_keys"], r["interruptions"])
    return len(rows)


def _detect_permission_friction(store, etl_run_id) -> int:
    rows = store._fetchall(
        """SELECT project_key, tool_name, denials, session_count, session_keys
           FROM v_permission_friction
           WHERE denials >= ?""",
        [PERMISSION_MIN_DENIALS],
    )
    for r in rows:
        _insert(store, etl_run_id, "permission_friction", r["project_key"],
                f"{r['tool_name']}: {r['denials']} permission denials across "
                f"{r['session_count']} session(s)",
                r["session_keys"], r["denials"])
    return len(rows)


_DETECTORS = (
    _detect_retry_loops,
    _detect_error_clusters,
    _detect_interruptions,
    _detect_permission_friction,
)


def run_couch(store: ExperimentStore) -> dict:
    """Run every SQL detector and record findings. Returns
    {etl_run_id, findings}. Registry seeding is included (idempotent)."""
    seed_finding_types(store)
    etl_run_id = store.start_load_run(
        "couch_sql", record_source=RecordSource.DERIVED)
    total = 0
    try:
        with store.transaction():
            for detector in _DETECTORS:
                total += detector(store, etl_run_id)
    except Exception as e:
        store.complete_load_run(
            etl_run_id, status=SessionStatus.FAILED,
            error=f"{type(e).__name__}: {e}")
        raise
    store.complete_load_run(
        etl_run_id, status=SessionStatus.COMPLETED, rows_written=total)
    return {"etl_run_id": etl_run_id, "findings": total}
