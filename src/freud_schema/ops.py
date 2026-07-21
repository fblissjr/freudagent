"""Shared dispatch layer for every write surface (M16).

Pure functions taking (store: ExperimentStore, typed params) and returning
plain dicts (keys/status/counts -- orjson-serializable). Both the CLI
(cli.py) and the MCP store-ops server (mcp_server.py) call these; neither
surface talks to ExperimentStore directly for a write, so the two cannot
drift the way the CLI and the /couch skill's raw-INSERT exception did.

Each function does exactly what the corresponding CLI handler did before
this module existed -- the logic moved here, it was not duplicated.

Surface-specific concerns stay OUT of this module:
- CLI: argument parsing, JSON-string decoding, sys.exit on error, printing.
- MCP: JSON-RPC marshalling, the self-modification gate (mcp_server.py
  forces rule_add/skill_add to non-compiling statuses regardless of what
  a caller asks for -- that gate lives at the tool wrapper, one layer
  above these functions, so ops.py itself has no opinion about who is
  calling it).

Key-or-prefix resolution (git-short-hash style) happens here, not at each
surface, so both the CLI and MCP tools get "accepts a prefix" for free and
cannot resolve differently.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from freud_schema.keys import dimension_key
from freud_schema.store import ExperimentStore
from freud_schema.tables import (
    CorrectionType,
    FeedbackOrigin,
    FeedbackOriginKind,
    Feedback,
    Finding,
    FindingScope,
    Proposal,
    RecordSource,
    Rule,
    RuleScope,
    RuleStatus,
    Skill,
    SkillStatus,
    Source,
    TargetDimension,
    Trace,
    TraceType,
    ValidationStatus,
)


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


def rule_add(
    store: ExperimentStore,
    *,
    name: str,
    content: str,
    scope: RuleScope = RuleScope.GLOBAL,
    domain: str | None = None,
    priority: int = 0,
    tenant_id: str = "default",
    status: RuleStatus = RuleStatus.ACTIVE,
) -> dict:
    """Insert or evolve a rule. Mirrors `freud-schema rule add`."""
    rule_key = store.insert_rule(Rule(
        name=name, scope=scope, domain=domain, priority=priority,
        content=content, tenant_id=tenant_id, status=status,
    ))
    return {
        "rule_key": rule_key, "tenant_id": tenant_id, "name": name,
        "scope": scope.value, "status": status.value,
    }


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------


def skill_add(
    store: ExperimentStore,
    *,
    domain: str,
    task_type: str,
    content: str,
    version: int = 1,
    tenant_id: str = "default",
    status: SkillStatus = SkillStatus.DRAFT,
) -> dict:
    """Insert a new skill version. Mirrors `freud-schema skill add`."""
    skill_key = store.insert_skill(Skill(
        domain=domain, task_type=task_type, version=version,
        tenant_id=tenant_id, content=content, status=status,
    ))
    return {
        "skill_key": skill_key, "tenant_id": tenant_id, "domain": domain,
        "task_type": task_type, "version": version, "status": status.value,
    }


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------


def source_add(
    store: ExperimentStore,
    *,
    path: str,
    media_type: str,
    tenant_id: str = "default",
    hash_baseline: bool = True,
) -> dict:
    """Register a source. Mirrors `freud-schema source add [--no-hash]`.

    Hashing is on by default. The baseline is what couch's stale_source
    detector compares against, and the detector SKIPS sources that have none --
    so an unhashed source is not merely unmonitored, it is invisible, and the
    detector reports clean on it forever. Registering a file that cannot be
    read raises OSError (the caller decides how to surface that), which is the
    right moment to find out.

    hash_baseline=False is the escape hatch for registering a source whose
    content is not readable yet.
    """
    source_hash = None
    if hash_baseline:
        from freud_schema.couch import source_content_hash
        source_hash = source_content_hash(path)
    source_key = store.insert_source(Source(
        content_path=path, media_type=media_type,
        tenant_id=tenant_id, source_hash=source_hash,
    ))
    return {
        "source_key": source_key, "tenant_id": tenant_id, "path": path,
        "media_type": media_type, "source_hash": source_hash,
    }


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------


def trace_add(
    store: ExperimentStore,
    *,
    session_key: str,
    trace_type: TraceType,
    title: str,
    source_message_key: str | None = None,
    sequence_order: int = 0,
    depth: int = 0,
    reasoning: str | None = None,
    content: str | None = None,
    alternatives: dict | None = None,
    outcome: dict | None = None,
) -> dict:
    """Record one typed trace derived from captured reasoning.

    This is the write path for a DERIVATION pass -- a later read over
    `fact_message.thinking_text`, which was captured for every run whether
    anyone was curious at the time or not. It is not a way for an agent to
    narrate its own run. That distinction is the point: a self-reported trail
    exists only when someone turned it on, degrades whenever reporting is not
    load-bearing for the agent's own task, and is missing for exactly the run
    you wanted to look at.

    Because it is a derivation it behaves like the other ones: wrapped in its
    own load_run, written with record_source=derived, and it names the message
    it came from so the claim can be checked against the evidence.

    Re-deriving the same message and position converges on the same row rather
    than adding another -- see the key recipe in store.insert_trace.
    """
    with store.load_run("trace_derive", record_source=RecordSource.DERIVED) as stats:
        trace_key = store.insert_trace(Trace(
            session_key=session_key,
            source_message_key=source_message_key,
            trace_type=trace_type,
            title=title,
            sequence_order=sequence_order,
            depth=depth,
            reasoning=reasoning,
            content=content,
            alternatives=alternatives,
            outcome=outcome,
            record_source=RecordSource.DERIVED,
        ))
        stats.rows_written = 1
    return {
        "trace_key": trace_key, "session_key": session_key,
        "trace_type": trace_type.value,
        "source_message_key": source_message_key,
        "etl_run_id": stats.etl_run_id,
    }


def feedback_origin_add(
    store: ExperimentStore,
    *,
    origin_id: str,
    origin_kind: FeedbackOriginKind = FeedbackOriginKind.UNSPECIFIED,
    description: str | None = None,
) -> dict:
    """Register a producer of feedback. Idempotent, keyed on origin_id.

    Open vocabulary: a new person, model version or upstream system is a row,
    not a schema change. The KIND it maps to is closed, because filters are
    written against the kind.
    """
    key = store.register_feedback_origin(FeedbackOrigin(
        origin_id=origin_id, origin_kind=origin_kind, description=description))
    return {
        "feedback_origin_key": key, "origin_id": origin_id,
        "origin_kind": origin_kind.value,
    }


def feedback_add(
    store: ExperimentStore,
    *,
    extraction_key: str,
    correction_type: CorrectionType,
    correction: dict,
    notes: str | None = None,
    created_by: str | None = None,
    origin_id: str | None = None,
) -> dict:
    """Add feedback on an extraction. Mirrors `freud-schema feedback add`.

    extraction_key may be a full key or a unique prefix.

    origin_id names what produced this judgment and must already be registered
    in dim_feedback_origin (open vocabulary -- register new producers as rows).
    Omitting it records origin_kind=unspecified rather than guessing human,
    because an unattributed row must never end up in the human-only slice.
    """
    ekey = store.resolve_key("fact_extraction", extraction_key)
    ext = store.get_extraction(ekey)
    # Wrapped in its own load_run: a human judgment is not re-derivable, so it
    # is the row most worth being able to trace back to when and how it arrived.
    with store.load_run("feedback_add") as stats:
        fb_key = store.insert_feedback(Feedback(
            extraction_key=ekey,
            session_key=ext.session_key,
            skill_key=ext.skill_key,
            correction=correction,
            correction_type=correction_type,
            notes=notes,
            created_by=created_by,
            feedback_origin_key=(
                dimension_key(origin_id) if origin_id is not None else None),
            etl_run_id=stats.etl_run_id,
        ))
        stats.rows_written = 1
    return {
        "feedback_key": fb_key, "extraction_key": ekey,
        "correction_type": correction_type.value,
        "origin_id": origin_id,
        "etl_run_id": stats.etl_run_id,
    }


# ---------------------------------------------------------------------------
# Findings -- retires the /couch skill's raw-INSERT exception (M16)
# ---------------------------------------------------------------------------


def finding_add(
    store: ExperimentStore,
    *,
    finding_type: str,
    summary: str,
    scope: FindingScope = FindingScope.PROJECT,
    project_key: str | None = None,
    evidence_session_keys: list[str] | None = None,
    occurrence_count: int | None = None,
) -> dict:
    """Record one couch finding, wrapped in its own load_run.

    Registry validation happens inside store.insert_finding (finding_type
    must already exist in dim_finding_type -- open vocabulary, not an
    enum). operation='couch_llm' matches what the /couch skill's raw-INSERT
    exception used to open by hand; this op replaces that exception, so
    the LLM judgment layer now writes through the one write path like
    every SQL detector already did.
    """
    with store.load_run("couch_llm", record_source=RecordSource.DERIVED) as stats:
        finding_key = store.insert_finding(Finding(
            finding_type=finding_type,
            scope=scope,
            project_key=project_key,
            evidence_session_keys=evidence_session_keys,
            occurrence_count=occurrence_count,
            summary=summary,
            record_source=RecordSource.DERIVED,
            etl_run_id=stats.etl_run_id,
        ))
        stats.rows_written = 1
    return {
        "finding_key": finding_key, "finding_type": finding_type,
        "etl_run_id": stats.etl_run_id,
    }


# ---------------------------------------------------------------------------
# Proposals (evolve)
# ---------------------------------------------------------------------------


def proposal_add(
    store: ExperimentStore,
    *,
    target: TargetDimension,
    natural_key: dict,
    content: str,
    version: int | None = None,
    evidence: list[str] | None = None,
) -> dict:
    """Draft a proposal (pending). Mirrors `freud-schema proposal add`.

    evidence entries may be a full key or a unique prefix -- resolved to
    full keys here, before the proposal is written, so a bad or ambiguous
    key raises ValueError with no proposal row left behind. Both couch
    list and the compiled provenance footer print finding_key[:8], so an
    unresolved prefix would otherwise silently record a broken evidence
    reference that renders identically to a valid one.
    """
    resolved_evidence = (
        [store.resolve_key("fact_finding", k) for k in evidence]
        if evidence else evidence
    )
    with store.load_run("proposal_add") as stats:
        pkey = store.insert_proposal(Proposal(
            target_dimension=target,
            target_natural_key=natural_key,
            proposed_content=content,
            proposed_version=version,
            evidence_finding_keys=resolved_evidence,
            etl_run_id=stats.etl_run_id,
        ))
        stats.rows_written = 1
    return {
        "proposal_key": pkey, "status": "pending",
        "target_dimension": target.value, "etl_run_id": stats.etl_run_id,
    }


def proposal_approve(
    store: ExperimentStore,
    *,
    key: str,
    reviewed_by: str | None = None,
) -> dict:
    """Approve a pending proposal: applies it to the target dimension.

    The one step in the flywheel only a person can do. key may be a full key
    or a unique prefix. Callers that must guarantee a human clicked "allow"
    (the MCP server) enforce that at the tool layer, not here -- this
    function has no opinion about who is calling it.
    """
    pkey = store.resolve_key("fact_proposal", key)
    result_key = store.approve_proposal(pkey, reviewed_by=reviewed_by)
    return {
        "proposal_key": pkey, "status": "approved",
        "resulting_dimension_key": result_key, "reviewed_by": reviewed_by,
    }


def proposal_reject(
    store: ExperimentStore,
    *,
    key: str,
    reviewed_by: str | None = None,
    review_notes: str | None = None,
) -> dict:
    """Reject a pending proposal. No dimension change.

    review_notes is optional but worth supplying: rejection rate is one of the
    health measures, and the rate without the reason cannot tell a gate catching
    real problems from one objecting to wording.
    """
    pkey = store.resolve_key("fact_proposal", key)
    store.reject_proposal(pkey, reviewed_by=reviewed_by, review_notes=review_notes)
    return {
        "proposal_key": pkey, "status": "rejected",
        "reviewed_by": reviewed_by, "review_notes": review_notes,
    }


# ---------------------------------------------------------------------------
# Extractions
# ---------------------------------------------------------------------------


def _extraction_set_validation(
    store: ExperimentStore, *, key: str, status: ValidationStatus,
    validated_by: str | None,
) -> dict:
    ekey = store.resolve_key("fact_extraction", key)
    store.update_validation(ekey, status=status, validated_by=validated_by)
    return {"extraction_key": ekey, "validation_status": status.value}


def extraction_validate(
    store: ExperimentStore, *, key: str, validated_by: str | None = None,
) -> dict:
    """Mark an extraction validated. key may be a full key or a prefix."""
    return _extraction_set_validation(
        store, key=key, status=ValidationStatus.VALIDATED, validated_by=validated_by)


def extraction_reject(
    store: ExperimentStore, *, key: str, validated_by: str | None = None,
) -> dict:
    """Mark an extraction rejected. key may be a full key or a prefix."""
    return _extraction_set_validation(
        store, key=key, status=ValidationStatus.REJECTED, validated_by=validated_by)


# ---------------------------------------------------------------------------
# Compile / couch (analyze) / ingest
# ---------------------------------------------------------------------------


def compile_rules(
    store: ExperimentStore,
    *,
    out_dir: str | Path,
    scope: RuleScope | None = None,
    tenant_id: str = "default",
) -> dict:
    """Render current active rules to <out_dir>/<name>.md. Delegates to
    materialize.compile_rules; returns {written, removed, blocked}."""
    from freud_schema.materialize import compile_rules as _compile_rules
    return _compile_rules(store, out_dir, scope=scope, tenant_id=tenant_id)


def couch_run(store: ExperimentStore, *, include_filesystem: bool = True) -> dict:
    """Run every deterministic detector. Delegates to couch.run_couch;
    returns {etl_run_id, findings}."""
    from freud_schema.couch import run_couch
    return run_couch(store, include_filesystem=include_filesystem)


def ingest_transcripts(
    store: ExperimentStore,
    *,
    root: str | Path | None = None,
    project: str | None = None,
    since: datetime | None = None,
) -> dict:
    """Ingest Claude Code transcripts. Delegates to ingest.ingest_transcripts;
    returns {sessions, etl_run_id, rows_read, rows_written, rows_skipped}."""
    from freud_schema.ingest import ingest_transcripts as _ingest_transcripts
    return _ingest_transcripts(store, root=root, project=project, since=since)


def ingest_events(
    store: ExperimentStore,
    *,
    root: str | Path,
    stream_type: str | None = None,
    since: datetime | None = None,
) -> dict:
    """Ingest a generic JSONL event stream (M5). Delegates to
    ingest.ingest_events; returns {streams, etl_run_id, rows_read,
    rows_written, rows_skipped}."""
    from freud_schema.ingest import ingest_events as _ingest_events
    return _ingest_events(store, root=root, stream_type=stream_type, since=since)
