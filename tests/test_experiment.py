"""Tests for the experiment harness: DuckDB schema, store, orchestrator.

Tests cover the dimensional model (dim_*/fact_* tables), insert-time
denormalization, view-backed aggregation queries, and the unchanged
orchestrator/provider interfaces.
"""

import pytest

from freud_schema.db import reset_schema
import duckdb
import orjson

from freud_schema.orchestrator import (
    CompletionResult,
    EchoProvider,
    OpenAICompatProvider,
    assemble_runner_context,
    get_provider,
)
from freud_schema.tables import (
    AgentRole,
    CorrectionType,
    Extraction,
    Feedback,
    Rule,
    RuleScope,
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


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


def test_schema_creates_all_tables(store):
    tables = store.con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
    ).fetchall()
    table_names = {t[0] for t in tables}
    assert "dim_skill" in table_names
    assert "dim_source" in table_names
    assert "dim_rule" in table_names
    assert "dim_sampling_config" in table_names
    assert "fact_session" in table_names
    assert "fact_trace" in table_names
    assert "fact_extraction" in table_names
    assert "fact_feedback" in table_names
    assert "fact_trace_feedback" in table_names
    assert "meta_schema_version" in table_names


def test_schema_creates_views(store):
    """All 6 analytical views are created."""
    views = store.con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_type = 'VIEW'"
    ).fetchall()
    view_names = {v[0] for v in views}
    assert "v_feedback_by_skill" in view_names
    assert "v_feedback_fields" in view_names
    assert "v_recurring_traces" in view_names
    assert "v_recurring_trace_feedback" in view_names
    assert "v_skill_feedback_patterns" in view_names
    assert "v_session_feedback_count" in view_names


def test_reset_schema(store):
    store.insert_skill(Skill(domain="test", task_type="test", content="test"))
    assert len(store.list_skills()) == 1
    reset_schema(store.con)
    assert len(store.list_skills()) == 0


def test_schema_versioning(store):
    """meta_schema_version exists after init and contains version 3."""
    from freud_schema.db import get_schema_version
    assert get_schema_version(store.con) >= 3
    row = store.con.execute(
        "SELECT version, description FROM meta_schema_version WHERE version = 3"
    ).fetchone()
    assert row is not None
    assert "Dimensional model" in row[1]


def test_init_schema_idempotent(store):
    """Running init_schema twice is safe and doesn't duplicate versions."""
    from freud_schema.db import get_schema_version, init_schema
    init_schema(store.con)
    init_schema(store.con)
    assert get_schema_version(store.con) >= 1
    count = store.con.execute(
        "SELECT COUNT(*) FROM meta_schema_version WHERE version = 1"
    ).fetchone()[0]
    assert count == 1


def test_reset_recreates_schema_version(store):
    """reset_schema drops and recreates meta_schema_version."""
    from freud_schema.db import get_schema_version
    reset_schema(store.con)
    assert get_schema_version(store.con) >= 1


def test_existence_validation_rejects_orphans(store):
    """Store-level existence checks reject orphaned references (replaces FK enforcement)."""
    # Session rejects nonexistent skill
    with pytest.raises(ValueError, match="Skill 9999 not found"):
        store.insert_session(Session(task_description="test", task_type="test", skill_id=9999))

    # Trace rejects nonexistent session
    with pytest.raises(ValueError, match="Session 9999 not found"):
        store.insert_trace(Trace(session_id=9999, trace_type=TraceType.TOOL_CALL, title="t"))

    # Extraction rejects nonexistent source (session and skill exist)
    skill_id = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    sid = store.insert_session(Session(task_description="t", task_type="t"))
    with pytest.raises(ValueError, match="Source 9999 not found"):
        store.insert_extraction(Extraction(
            source_id=9999, skill_id=skill_id, session_id=sid, output={},
        ))

    # Extraction rejects nonexistent skill (session and source exist)
    source_id = store.insert_source(Source(content_path="/f", media_type="text/plain"))
    with pytest.raises(ValueError, match="Skill 9999 not found"):
        store.insert_extraction(Extraction(
            source_id=source_id, skill_id=9999, session_id=sid, output={},
        ))

    # Feedback rejects nonexistent extraction
    with pytest.raises(ValueError, match="Extraction 9999 not found"):
        store.insert_feedback(Feedback(
            extraction_id=9999, session_id=sid, skill_id=skill_id,
            correction={"x": 1}, correction_type=CorrectionType.WRONG_VALUE,
        ))

    # Trace feedback rejects nonexistent trace
    tid = store.insert_trace(Trace(session_id=sid, trace_type=TraceType.TOOL_CALL, title="t"))
    with pytest.raises(ValueError, match="Trace 9999 not found"):
        store.insert_trace_feedback(TraceFeedback(
            trace_id=9999, session_id=sid,
            feedback_type=TraceFeedbackType.POSITIVE_SIGNAL, content="x",
        ))


def test_existence_validation_allows_null_optional_refs(store):
    """Optional references (NULL skill_id on session) skip validation."""
    sid = store.insert_session(Session(task_description="no skill", task_type="t"))
    assert sid is not None
    session = store.get_session(sid)
    assert session.skill_id is None


# ---------------------------------------------------------------------------
# Enum validation tests (Python layer)
# ---------------------------------------------------------------------------


def test_skill_rejects_invalid_status():
    with pytest.raises(Exception):
        Skill(domain="d", task_type="t", content="c", status="bogus")  # type: ignore[arg-type]


def test_session_rejects_invalid_status():
    with pytest.raises(Exception):
        Session(task_description="t", task_type="t", status="bogus")  # type: ignore[arg-type]


def test_session_rejects_invalid_agent_role():
    with pytest.raises(Exception):
        Session(task_description="t", task_type="t", agent_role="bogus")  # type: ignore[arg-type]


def test_extraction_rejects_invalid_validation_status():
    with pytest.raises(Exception):
        Extraction(source_id=1, skill_id=1, session_id=1, output={}, validation_status="bogus")  # type: ignore[arg-type]


def test_feedback_rejects_invalid_correction_type():
    with pytest.raises(Exception):
        Feedback(
            extraction_id=1, session_id=1, skill_id=1,
            correction={}, correction_type="bogus",  # type: ignore[arg-type]
        )


def test_rule_rejects_invalid_scope():
    with pytest.raises(Exception):
        Rule(content="test", scope="bogus")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# DB CHECK constraint tests
# ---------------------------------------------------------------------------


def test_check_constraint_rejects_invalid_insert(store):
    """DuckDB CHECK constraint rejects invalid enum values."""
    with pytest.raises(duckdb.ConstraintException):
        store.con.execute(
            "INSERT INTO dim_skill (domain, task_type, content, status) VALUES ('d', 't', 'c', 'bogus')"
        )


# ---------------------------------------------------------------------------
# Skill CRUD tests
# ---------------------------------------------------------------------------


def test_insert_and_get_skill(store):
    skill = Skill(domain="arxiv", task_type="extraction", content="Extract papers")
    skill_id = store.insert_skill(skill)
    assert skill_id >= 1
    fetched = store.get_skill(skill_id)
    assert fetched is not None
    assert fetched.domain == "arxiv"
    assert fetched.status == SkillStatus.DRAFT


def test_list_skills_filter(store):
    store.insert_skill(Skill(domain="a", task_type="t", content="c", status=SkillStatus.ACTIVE))
    store.insert_skill(Skill(domain="b", task_type="t", content="c", status=SkillStatus.DRAFT))
    assert len(store.list_skills(status=SkillStatus.ACTIVE)) == 1
    assert len(store.list_skills(domain="a")) == 1


def test_activate_deprecate_skill(store):
    sid = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    store.activate_skill(sid)
    assert store.get_skill(sid).status == SkillStatus.ACTIVE
    store.deprecate_skill(sid)
    assert store.get_skill(sid).status == SkillStatus.DEPRECATED


def test_skill_version_roundtrip(store):
    store.insert_skill(Skill(domain="d", task_type="t", content="v1", version=1, status=SkillStatus.ACTIVE))
    store.insert_skill(Skill(domain="d", task_type="t", content="v2", version=2, status=SkillStatus.ACTIVE))
    active = store.get_active_skill("d", "t")
    assert active.version == 2


def test_skill_unique_constraint(store):
    store.insert_skill(Skill(domain="d", task_type="t", content="c1", version=1))
    with pytest.raises(duckdb.ConstraintException):
        store.insert_skill(Skill(domain="d", task_type="t", content="c2", version=1))


def test_skill_origin(store):
    sid = store.insert_skill(Skill(domain="d", task_type="t", content="c", origin=SkillOrigin.DATA_DERIVED))
    skill = store.get_skill(sid)
    assert skill.origin == SkillOrigin.DATA_DERIVED


def test_insert_derived_skill(store):
    sid = store.insert_derived_skill(
        Skill(domain="d", task_type="t", content="derived", version=2),
        source_session_ids=[1, 2],
        source_trace_ids=[10, 20],
    )
    skill = store.get_skill(sid)
    assert skill.origin == SkillOrigin.DATA_DERIVED
    assert skill.metadata["derived_from"]["session_ids"] == [1, 2]


def test_get_active_sub_skills(store):
    parent = store.insert_skill(Skill(domain="d", task_type="parent", content="p", status=SkillStatus.ACTIVE))
    store.insert_skill(Skill(domain="d", task_type="child1", content="c1", parent_skill_id=parent, status=SkillStatus.ACTIVE))
    store.insert_skill(Skill(domain="d", task_type="child2", content="c2", parent_skill_id=parent, status=SkillStatus.DEPRECATED))
    children = store.get_active_sub_skills(parent)
    assert len(children) == 1
    assert children[0].task_type == "child1"


# ---------------------------------------------------------------------------
# Source CRUD tests
# ---------------------------------------------------------------------------


def test_insert_and_get_source(store):
    source = Source(content_path="/tmp/test.pdf", media_type="application/pdf")
    sid = store.insert_source(source)
    assert sid >= 1
    fetched = store.get_source(sid)
    assert fetched.content_path == "/tmp/test.pdf"


def test_get_sources_by_ids(store):
    s1 = store.insert_source(Source(content_path="/a.pdf", media_type="application/pdf"))
    s2 = store.insert_source(Source(content_path="/b.pdf", media_type="application/pdf"))
    source_map = store.get_sources_by_ids([s1, s2])
    assert len(source_map) == 2
    assert source_map[s1].content_path == "/a.pdf"


# ---------------------------------------------------------------------------
# Session CRUD tests
# ---------------------------------------------------------------------------


def test_insert_and_get_session(store):
    session = Session(task_description="test", task_type="extraction")
    sid = store.insert_session(session)
    assert sid >= 1
    fetched = store.get_session(sid)
    assert fetched.task_description == "test"


def test_session_skill_denormalization(store):
    """Session denormalizes skill attributes at insert time."""
    skill_id = store.insert_skill(Skill(domain="arxiv", task_type="extraction", content="x", version=3))
    session = Session(task_description="test", task_type="extraction", skill_id=skill_id)
    sid = store.insert_session(session)
    fetched = store.get_session(sid)
    assert fetched.skill_domain == "arxiv"
    assert fetched.skill_task_type == "extraction"
    assert fetched.skill_version == 3


def test_complete_session(store):
    sid = store.insert_session(Session(task_description="t", task_type="t"))
    store.complete_session(sid, status=SessionStatus.COMPLETED, result={"ok": True})
    session = store.get_session(sid)
    assert session.status == SessionStatus.COMPLETED
    assert session.result == {"ok": True}
    assert session.completed_at is not None


def test_update_session_model(store):
    sid = store.insert_session(Session(task_description="t", task_type="t"))
    store.update_session_model(sid, "claude-sonnet-4-6")
    session = store.get_session(sid)
    assert session.model_used == "claude-sonnet-4-6"


def test_list_sessions_with_filters(store):
    store.insert_session(Session(task_description="a", task_type="t", status=SessionStatus.RUNNING))
    sid2 = store.insert_session(Session(task_description="b", task_type="t"))
    store.complete_session(sid2, status=SessionStatus.COMPLETED)
    completed = store.list_sessions(status=SessionStatus.COMPLETED)
    assert len(completed) == 1
    assert completed[0].task_description == "b"


# ---------------------------------------------------------------------------
# Trace CRUD tests + denormalization
# ---------------------------------------------------------------------------


def test_insert_trace_denormalizes_skill(store):
    """Trace denormalizes skill attributes from its session."""
    skill_id = store.insert_skill(Skill(domain="arxiv", task_type="extraction", content="x"))
    sid = store.insert_session(Session(task_description="t", task_type="t", skill_id=skill_id))
    trace = Trace(session_id=sid, trace_type=TraceType.DECISION_POINT, title="Choose approach")
    tid = store.insert_trace(trace)
    fetched = store.get_trace(tid)
    assert fetched.skill_id == skill_id
    assert fetched.skill_domain == "arxiv"
    assert fetched.skill_task_type == "extraction"


def test_get_session_traces(store):
    sid = store.insert_session(Session(task_description="t", task_type="t"))
    store.insert_trace(Trace(session_id=sid, trace_type=TraceType.DECISION_POINT, title="a", depth=0))
    store.insert_trace(Trace(session_id=sid, trace_type=TraceType.PATH_TAKEN, title="b", depth=1))
    traces = store.get_session_traces(sid)
    assert len(traces) == 2
    assert traces[0].title == "a"
    assert traces[1].title == "b"


def test_count_traces_by_type(store):
    sid = store.insert_session(Session(task_description="t", task_type="t"))
    store.insert_trace(Trace(session_id=sid, trace_type=TraceType.TOOL_CALL, title="t1"))
    store.insert_trace(Trace(session_id=sid, trace_type=TraceType.TOOL_CALL, title="t2"))
    store.insert_trace(Trace(session_id=sid, trace_type=TraceType.DECISION_POINT, title="d1"))
    counts = store.count_traces_by_type(sid)
    assert counts[0] == ("tool_call", 2)


def test_delete_session_traces(store):
    sid = store.insert_session(Session(task_description="t", task_type="t"))
    tid = store.insert_trace(Trace(session_id=sid, trace_type=TraceType.TOOL_CALL, title="t"))
    store.insert_trace_feedback(TraceFeedback(
        trace_id=tid, session_id=sid, feedback_type=TraceFeedbackType.POSITIVE_SIGNAL,
        content="good",
    ))
    count = store.delete_session_traces(sid)
    assert count == 1
    assert store.get_session_traces(sid) == []
    assert store.list_trace_feedback(session_id=sid) == []


# ---------------------------------------------------------------------------
# Extraction tests + denormalization
# ---------------------------------------------------------------------------


def test_insert_extraction_denormalizes(store):
    """Extraction denormalizes both source and skill attributes."""
    skill_id = store.insert_skill(Skill(domain="arxiv", task_type="extraction", content="x", version=2))
    source_id = store.insert_source(Source(content_path="/test.pdf", media_type="application/pdf"))
    sid = store.insert_session(Session(task_description="t", task_type="t"))
    ext = Extraction(source_id=source_id, skill_id=skill_id, session_id=sid, output={"title": "Paper"})
    eid = store.insert_extraction(ext)
    fetched = store.get_extraction(eid)
    assert fetched.source_path == "/test.pdf"
    assert fetched.source_media_type == "application/pdf"
    assert fetched.skill_domain == "arxiv"
    assert fetched.skill_task_type == "extraction"
    assert fetched.skill_version == 2


def test_validate_extraction(store):
    skill_id = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    source_id = store.insert_source(Source(content_path="/f", media_type="text/plain"))
    sid = store.insert_session(Session(task_description="t", task_type="t"))
    eid = store.insert_extraction(Extraction(
        source_id=source_id, skill_id=skill_id, session_id=sid, output={"a": 1},
    ))
    store.update_validation(eid, status=ValidationStatus.VALIDATED, validated_by="tester")
    fetched = store.get_extraction(eid)
    assert fetched.validation_status == ValidationStatus.VALIDATED
    assert fetched.validated_by == "tester"


def test_list_extractions(store):
    skill_id = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    source_id = store.insert_source(Source(content_path="/f", media_type="text/plain"))
    sid = store.insert_session(Session(task_description="t", task_type="t"))
    store.insert_extraction(Extraction(
        source_id=source_id, skill_id=skill_id, session_id=sid, output={},
    ))
    assert len(store.list_extractions()) == 1
    assert len(store.list_extractions(skill_id=skill_id)) == 1
    assert len(store.list_extractions(skill_id=9999)) == 0


def test_extraction_with_feedback(store):
    skill_id = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    source_id = store.insert_source(Source(content_path="/f", media_type="text/plain"))
    sid = store.insert_session(Session(task_description="t", task_type="t"))
    eid = store.insert_extraction(Extraction(
        source_id=source_id, skill_id=skill_id, session_id=sid, output={},
    ))
    store.insert_feedback(Feedback(
        extraction_id=eid, session_id=sid, skill_id=skill_id,
        correction={"fix": "it"}, correction_type=CorrectionType.WRONG_VALUE,
    ))
    result = store.get_extraction_with_feedback(eid)
    assert result is not None
    assert len(result["feedback"]) == 1


# ---------------------------------------------------------------------------
# Feedback tests + denormalization
# ---------------------------------------------------------------------------


def test_insert_feedback_denormalizes(store):
    """Feedback denormalizes skill and source attributes."""
    skill_id = store.insert_skill(Skill(domain="arxiv", task_type="extraction", content="x", version=2))
    source_id = store.insert_source(Source(content_path="/paper.pdf", media_type="application/pdf"))
    sid = store.insert_session(Session(task_description="t", task_type="t"))
    eid = store.insert_extraction(Extraction(
        source_id=source_id, skill_id=skill_id, session_id=sid, output={},
    ))
    fb = Feedback(
        extraction_id=eid, session_id=sid, skill_id=skill_id,
        correction={"title": {"old": "a", "new": "b"}},
        correction_type=CorrectionType.WRONG_VALUE,
    )
    fid = store.insert_feedback(fb)
    fetched = store.list_feedback(skill_id=skill_id)
    assert len(fetched) == 1
    f = fetched[0]
    assert f.skill_domain == "arxiv"
    assert f.skill_task_type == "extraction"
    assert f.skill_version == 2
    assert f.source_id == source_id
    assert f.source_path == "/paper.pdf"


def test_aggregate_feedback_uses_views(store):
    """aggregate_feedback returns view-backed results."""
    skill_id = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    source_id = store.insert_source(Source(content_path="/f", media_type="text/plain"))
    sid = store.insert_session(Session(task_description="t", task_type="t"))
    eid = store.insert_extraction(Extraction(
        source_id=source_id, skill_id=skill_id, session_id=sid, output={},
    ))
    for _ in range(3):
        store.insert_feedback(Feedback(
            extraction_id=eid, session_id=sid, skill_id=skill_id,
            correction={"title": "fix"}, correction_type=CorrectionType.WRONG_VALUE,
        ))
    store.insert_feedback(Feedback(
        extraction_id=eid, session_id=sid, skill_id=skill_id,
        correction={"field": "fix"}, correction_type=CorrectionType.MISSING_FIELD,
    ))
    agg = store.aggregate_feedback(skill_id)
    assert len(agg) == 2
    assert agg[0]["correction_type"] == "wrong_value"
    assert agg[0]["count"] == 3
    assert "title" in agg[0]["fields"]


def test_aggregate_feedback_with_examples(store):
    skill_id = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    source_id = store.insert_source(Source(content_path="/f", media_type="text/plain"))
    sid = store.insert_session(Session(task_description="t", task_type="t"))
    eid = store.insert_extraction(Extraction(
        source_id=source_id, skill_id=skill_id, session_id=sid, output={},
    ))
    store.insert_feedback(Feedback(
        extraction_id=eid, session_id=sid, skill_id=skill_id,
        correction={"x": 1}, correction_type=CorrectionType.WRONG_VALUE,
    ))
    agg = store.aggregate_feedback(skill_id, include_examples=True, max_examples=2)
    assert len(agg) == 1
    assert len(agg[0]["examples"]) == 1
    assert agg[0]["examples"][0] == {"x": 1}


# ---------------------------------------------------------------------------
# Trace feedback tests + denormalization
# ---------------------------------------------------------------------------


def test_insert_trace_feedback_denormalizes(store):
    """Trace feedback denormalizes trace and skill attributes."""
    skill_id = store.insert_skill(Skill(domain="arxiv", task_type="extraction", content="x"))
    sid = store.insert_session(Session(task_description="t", task_type="t", skill_id=skill_id))
    tid = store.insert_trace(Trace(
        session_id=sid, trace_type=TraceType.DEAD_END, title="Bad approach",
    ))
    tf = TraceFeedback(
        trace_id=tid, session_id=sid,
        feedback_type=TraceFeedbackType.DEAD_END_CONFIRMATION,
        content="Yes this was a dead end",
    )
    tfid = store.insert_trace_feedback(tf)
    fetched = store.list_trace_feedback(session_id=sid)
    assert len(fetched) == 1
    f = fetched[0]
    assert f.trace_type == "dead_end"
    assert f.trace_title == "Bad approach"
    assert f.skill_id == skill_id
    assert f.skill_domain == "arxiv"


def test_aggregate_trace_feedback(store):
    """aggregate_trace_feedback works without joins."""
    sid = store.insert_session(Session(task_description="t", task_type="t"))
    tid = store.insert_trace(Trace(session_id=sid, trace_type=TraceType.DEAD_END, title="t"))
    store.insert_trace_feedback(TraceFeedback(
        trace_id=tid, session_id=sid,
        feedback_type=TraceFeedbackType.DEAD_END_CONFIRMATION, content="a",
    ))
    store.insert_trace_feedback(TraceFeedback(
        trace_id=tid, session_id=sid,
        feedback_type=TraceFeedbackType.POSITIVE_SIGNAL, content="b",
    ))
    agg = store.aggregate_trace_feedback(sid)
    assert len(agg) == 2


# ---------------------------------------------------------------------------
# Rule CRUD tests
# ---------------------------------------------------------------------------


def test_insert_and_get_rules(store):
    store.insert_rule(Rule(content="Always validate", priority=10))
    store.insert_rule(Rule(
        content="Domain rule", scope=RuleScope.DOMAIN_SPECIFIC, domain="arxiv", priority=5,
    ))
    global_rules = store.get_rules()
    assert len(global_rules) == 1
    domain_rules = store.get_rules(domain="arxiv")
    assert len(domain_rules) == 2


# ---------------------------------------------------------------------------
# Sampling config tests
# ---------------------------------------------------------------------------


def test_sampling_config_crud(store):
    cid = store.insert_sampling_config(SamplingConfig(
        strategy=SamplingStrategy.RECENT, max_samples=5,
    ))
    config = store.get_sampling_config()
    assert config is not None
    assert config.max_samples == 5


def test_sampling_config_priority(store):
    store.insert_sampling_config(SamplingConfig(
        strategy=SamplingStrategy.RECENT, max_samples=3,
    ))
    store.insert_sampling_config(SamplingConfig(
        domain="arxiv", task_type="extraction",
        strategy=SamplingStrategy.HIGH_FEEDBACK, max_samples=5,
    ))
    config = store.get_sampling_config(domain="arxiv", task_type="extraction")
    assert config.strategy == SamplingStrategy.HIGH_FEEDBACK


# ---------------------------------------------------------------------------
# Prior run sampling tests
# ---------------------------------------------------------------------------


def test_sample_prior_sessions_recent(store):
    skill_id = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    for i in range(5):
        sid = store.insert_session(Session(
            task_description=f"run-{i}", task_type="t", skill_id=skill_id,
        ))
        store.complete_session(sid, status=SessionStatus.COMPLETED)
    samples = store.sample_prior_sessions(skill_id=skill_id, max_samples=3)
    assert len(samples) == 3


def test_sample_prior_sessions_excludes_running(store):
    skill_id = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    store.insert_session(Session(task_description="running", task_type="t", skill_id=skill_id))
    samples = store.sample_prior_sessions(skill_id=skill_id)
    assert len(samples) == 0


def test_sample_prior_sessions_excludes_ids(store):
    skill_id = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    sid = store.insert_session(Session(task_description="t", task_type="t", skill_id=skill_id))
    store.complete_session(sid, status=SessionStatus.COMPLETED)
    samples = store.sample_prior_sessions(skill_id=skill_id, exclude_session_ids=[sid])
    assert len(samples) == 0


def test_sample_stratified_outcome(store):
    skill_id = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    for i in range(3):
        sid = store.insert_session(Session(task_description=f"ok-{i}", task_type="t", skill_id=skill_id))
        store.complete_session(sid, status=SessionStatus.COMPLETED)
    sid = store.insert_session(Session(task_description="fail", task_type="t", skill_id=skill_id))
    store.complete_session(sid, status=SessionStatus.FAILED)
    samples = store.sample_prior_sessions(
        skill_id=skill_id, strategy=SamplingStrategy.STRATIFIED_OUTCOME, max_samples=3,
    )
    assert len(samples) == 3
    statuses = {s.status for s in samples}
    assert SessionStatus.FAILED in statuses
    assert SessionStatus.COMPLETED in statuses


def test_sample_high_feedback(store):
    skill_id = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    source_id = store.insert_source(Source(content_path="/f", media_type="text/plain"))
    # Session with more feedback should rank higher
    sid1 = store.insert_session(Session(task_description="s1", task_type="t", skill_id=skill_id))
    store.complete_session(sid1, status=SessionStatus.COMPLETED)
    eid1 = store.insert_extraction(Extraction(
        source_id=source_id, skill_id=skill_id, session_id=sid1, output={},
    ))
    for _ in range(3):
        store.insert_feedback(Feedback(
            extraction_id=eid1, session_id=sid1, skill_id=skill_id,
            correction={"x": 1}, correction_type=CorrectionType.WRONG_VALUE,
        ))
    sid2 = store.insert_session(Session(task_description="s2", task_type="t", skill_id=skill_id))
    store.complete_session(sid2, status=SessionStatus.COMPLETED)
    samples = store.sample_prior_sessions(
        skill_id=skill_id, strategy=SamplingStrategy.HIGH_FEEDBACK, max_samples=2,
    )
    assert len(samples) == 2
    assert samples[0].id == sid1  # more feedback -> first


def test_sample_stratified_feedback(store):
    skill_id = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    source_id = store.insert_source(Source(content_path="/f", media_type="text/plain"))
    sid1 = store.insert_session(Session(task_description="s1", task_type="t", skill_id=skill_id))
    store.complete_session(sid1, status=SessionStatus.COMPLETED)
    eid1 = store.insert_extraction(Extraction(
        source_id=source_id, skill_id=skill_id, session_id=sid1, output={},
    ))
    store.insert_feedback(Feedback(
        extraction_id=eid1, session_id=sid1, skill_id=skill_id,
        correction={"x": 1}, correction_type=CorrectionType.WRONG_VALUE,
    ))
    sid2 = store.insert_session(Session(task_description="s2", task_type="t", skill_id=skill_id))
    store.complete_session(sid2, status=SessionStatus.COMPLETED)
    eid2 = store.insert_extraction(Extraction(
        source_id=source_id, skill_id=skill_id, session_id=sid2, output={},
    ))
    store.insert_feedback(Feedback(
        extraction_id=eid2, session_id=sid2, skill_id=skill_id,
        correction={"y": 2}, correction_type=CorrectionType.MISSING_FIELD,
    ))
    samples = store.sample_prior_sessions(
        skill_id=skill_id, strategy=SamplingStrategy.STRATIFIED_FEEDBACK, max_samples=3,
    )
    assert len(samples) == 2  # one per correction type


# ---------------------------------------------------------------------------
# View-backed pattern detection tests
# ---------------------------------------------------------------------------


def test_get_skills_with_feedback_patterns(store):
    skill_id = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    source_id = store.insert_source(Source(content_path="/f", media_type="text/plain"))
    sid = store.insert_session(Session(task_description="t", task_type="t"))
    eid = store.insert_extraction(Extraction(
        source_id=source_id, skill_id=skill_id, session_id=sid, output={},
    ))
    for _ in range(3):
        store.insert_feedback(Feedback(
            extraction_id=eid, session_id=sid, skill_id=skill_id,
            correction={"x": 1}, correction_type=CorrectionType.WRONG_VALUE,
        ))
    results = store.get_skills_with_feedback_patterns(min_feedback_count=3)
    assert len(results) == 1
    assert results[0]["skill"].id == skill_id
    assert results[0]["total_feedback"] == 3


def test_get_recurring_traces(store):
    skill_id = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    sid1 = store.insert_session(Session(task_description="s1", task_type="t", skill_id=skill_id))
    sid2 = store.insert_session(Session(task_description="s2", task_type="t", skill_id=skill_id))
    store.insert_trace(Trace(session_id=sid1, trace_type=TraceType.DEAD_END, title="Hit wall"))
    store.insert_trace(Trace(session_id=sid2, trace_type=TraceType.DEAD_END, title="Hit wall"))
    store.insert_trace(Trace(session_id=sid1, trace_type=TraceType.DEAD_END, title="Unique"))
    patterns = store.get_recurring_traces(skill_id, TraceType.DEAD_END, min_occurrences=2)
    assert len(patterns) == 1
    assert patterns[0]["title"] == "Hit wall"
    assert patterns[0]["count"] == 2
    assert len(patterns[0]["session_ids"]) == 2


def test_get_recurring_trace_feedback(store):
    skill_id = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    sid1 = store.insert_session(Session(task_description="s1", task_type="t", skill_id=skill_id))
    sid2 = store.insert_session(Session(task_description="s2", task_type="t", skill_id=skill_id))
    tid1 = store.insert_trace(Trace(session_id=sid1, trace_type=TraceType.DEAD_END, title="Bad path"))
    tid2 = store.insert_trace(Trace(session_id=sid2, trace_type=TraceType.DEAD_END, title="Bad path"))
    store.insert_trace_feedback(TraceFeedback(
        trace_id=tid1, session_id=sid1,
        feedback_type=TraceFeedbackType.DEAD_END_CONFIRMATION, content="yes",
    ))
    store.insert_trace_feedback(TraceFeedback(
        trace_id=tid2, session_id=sid2,
        feedback_type=TraceFeedbackType.DEAD_END_CONFIRMATION, content="yes",
    ))
    patterns = store.get_recurring_trace_feedback(skill_id, min_occurrences=2)
    assert len(patterns) == 1
    assert patterns[0]["trace_title"] == "Bad path"


# ---------------------------------------------------------------------------
# Rich session retrieval tests
# ---------------------------------------------------------------------------


def test_get_session_with_context(store):
    skill_id = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    source_id = store.insert_source(Source(content_path="/f", media_type="text/plain"))
    sid = store.insert_session(Session(task_description="t", task_type="t", skill_id=skill_id))
    store.insert_trace(Trace(session_id=sid, trace_type=TraceType.TOOL_CALL, title="t"))
    eid = store.insert_extraction(Extraction(
        source_id=source_id, skill_id=skill_id, session_id=sid, output={"a": 1},
    ))
    store.insert_feedback(Feedback(
        extraction_id=eid, session_id=sid, skill_id=skill_id,
        correction={"a": {"old": 1, "new": 2}}, correction_type=CorrectionType.WRONG_VALUE,
    ))
    ctx = store.get_session_with_context(sid)
    assert ctx is not None
    assert len(ctx["traces"]) == 1
    assert len(ctx["extractions"]) == 1
    assert len(ctx["feedback"]) == 1


# ---------------------------------------------------------------------------
# Orchestrator tests
# ---------------------------------------------------------------------------


def test_echo_provider():
    provider = EchoProvider()
    result = provider.complete("system", "user")
    data = orjson.loads(result.content)
    assert data["model"] == "echo"
    assert data["system_prompt"] == "system"


def test_get_provider_echo():
    provider = get_provider("echo")
    assert isinstance(provider, EchoProvider)


def test_get_provider_unknown():
    with pytest.raises(ValueError, match="Unknown provider"):
        get_provider("nonexistent")


def test_assemble_runner_context(store):
    skill_id = store.insert_skill(Skill(domain="d", task_type="t", content="Do the thing", status=SkillStatus.ACTIVE))
    store.activate_skill(skill_id)
    source_id = store.insert_source(Source(content_path="/test.pdf", media_type="application/pdf"))
    store.insert_rule(Rule(content="Be careful", priority=10))
    system, user = assemble_runner_context(
        store, skill_id=skill_id, source_ids=[source_id], task_params="Extract data",
    )
    assert "Be careful" in system
    assert "Do the thing" in system
    assert "/test.pdf" in user
    assert "Extract data" in user


def test_assemble_context_with_feedback_summary(store):
    skill_id = store.insert_skill(Skill(domain="d", task_type="t", content="Do the thing"))
    source_id = store.insert_source(Source(content_path="/f", media_type="text/plain"))
    sid = store.insert_session(Session(task_description="t", task_type="t"))
    eid = store.insert_extraction(Extraction(
        source_id=source_id, skill_id=skill_id, session_id=sid, output={},
    ))
    store.insert_feedback(Feedback(
        extraction_id=eid, session_id=sid, skill_id=skill_id,
        correction={"field": "fix"}, correction_type=CorrectionType.WRONG_VALUE,
    ))
    system, _user = assemble_runner_context(
        store, skill_id=skill_id, source_ids=[], include_feedback_summary=True,
    )
    assert "Feedback Patterns" in system
    assert "wrong_value" in system


def test_assemble_context_with_prior_runs(store):
    skill_id = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    sid = store.insert_session(Session(task_description="old run", task_type="t", skill_id=skill_id))
    store.complete_session(sid, status=SessionStatus.COMPLETED)
    store.insert_trace(Trace(
        session_id=sid, trace_type=TraceType.DECISION_POINT, title="Chose method",
    ))
    prior_runs = store.get_sessions_with_context([sid])
    system, _ = assemble_runner_context(
        store, skill_id=skill_id, source_ids=[], prior_runs=prior_runs,
    )
    assert "Prior Runs" in system
    assert "Chose method" in system


def test_prior_runs_filters_signal_traces(store):
    """_format_prior_runs only includes signal-bearing traces, skips tool_call/path_taken."""
    skill_id = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    sid = store.insert_session(Session(task_description="run", task_type="t", skill_id=skill_id))
    store.complete_session(sid, status=SessionStatus.COMPLETED)
    # Insert a mix of signal and mechanical traces
    store.insert_trace(Trace(session_id=sid, trace_type=TraceType.DECISION_POINT, title="Key decision"))
    store.insert_trace(Trace(session_id=sid, trace_type=TraceType.TOOL_CALL, title="Read file"))
    store.insert_trace(Trace(session_id=sid, trace_type=TraceType.TOOL_CALL, title="Write file"))
    store.insert_trace(Trace(session_id=sid, trace_type=TraceType.PATH_TAKEN, title="Chose path A"))
    store.insert_trace(Trace(session_id=sid, trace_type=TraceType.DEAD_END, title="Hit wall"))
    store.insert_trace(Trace(session_id=sid, trace_type=TraceType.INSIGHT, title="Realized pattern"))
    prior_runs = store.get_sessions_with_context([sid])
    system, _ = assemble_runner_context(
        store, skill_id=skill_id, source_ids=[], prior_runs=prior_runs,
    )
    # Signal traces included
    assert "Key decision" in system
    assert "Hit wall" in system
    assert "Realized pattern" in system
    # Mechanical traces filtered out
    assert "Read file" not in system
    assert "Write file" not in system
    assert "Chose path A" not in system
    # Summary count present
    assert "3 of 6" in system


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


def test_cli_db_ddl():
    """freud-schema db ddl outputs SQL without touching the database."""
    from freud_schema.cli import main
    import io
    import sys
    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    try:
        main(["db", "ddl"])
    finally:
        sys.stdout = old_stdout
    output = buf.getvalue()
    assert "dim_skill" in output
    assert "fact_session" in output
    assert "v_feedback_by_skill" in output


def test_cli_db_status(tmp_path):
    from freud_schema.cli import main
    import io
    import sys
    db = str(tmp_path / "test.duckdb")
    main(["--db", db, "db", "init"])
    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    try:
        main(["--db", db, "db", "status"])
    finally:
        sys.stdout = old_stdout
    output = buf.getvalue()
    assert "dim_skill" in output
    assert "fact_session" in output
    assert "Schema version:" in output


def test_cli_skill_add_list(tmp_path):
    from freud_schema.cli import main
    import io
    import sys
    db = str(tmp_path / "test.duckdb")
    main(["--db", db, "skill", "add", "--domain", "test", "--task-type", "t", "--content", "Do it"])
    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    try:
        main(["--db", db, "skill", "list"])
    finally:
        sys.stdout = old_stdout
    output = buf.getvalue()
    assert "test/t" in output


def test_cli_skill_deprecate(tmp_path):
    from freud_schema.cli import main
    db = str(tmp_path / "test.duckdb")
    main(["--db", db, "skill", "add", "--domain", "d", "--task-type", "t", "--content", "c"])
    main(["--db", db, "skill", "deprecate", "1"])


def test_cli_skill_deprecate_nonexistent(tmp_path):
    from freud_schema.cli import main
    db = str(tmp_path / "test.duckdb")
    main(["--db", db, "db", "init"])
    with pytest.raises(SystemExit):
        main(["--db", db, "skill", "deprecate", "999"])


def test_cli_source_add_list(tmp_path):
    from freud_schema.cli import main
    import io
    import sys
    db = str(tmp_path / "test.duckdb")
    main(["--db", db, "source", "add", "--path", "/test.pdf", "--media-type", "application/pdf"])
    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    try:
        main(["--db", db, "source", "list"])
    finally:
        sys.stdout = old_stdout
    assert "/test.pdf" in buf.getvalue()


def test_cli_rule_add_list(tmp_path):
    from freud_schema.cli import main
    import io
    import sys
    db = str(tmp_path / "test.duckdb")
    main(["--db", db, "rule", "add", "--content", "Be careful"])
    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    try:
        main(["--db", db, "rule", "list"])
    finally:
        sys.stdout = old_stdout
    assert "Be careful" in buf.getvalue()


def test_cli_feedback_add(tmp_path):
    from freud_schema.cli import main
    db = str(tmp_path / "test.duckdb")
    main(["--db", db, "skill", "add", "--domain", "d", "--task-type", "t", "--content", "c"])
    main(["--db", db, "source", "add", "--path", "/f", "--media-type", "text/plain"])
    # Insert a session and extraction via store (CLI doesn't expose session/extraction add)
    from freud_schema.db import connect
    from freud_schema.store import ExperimentStore
    with ExperimentStore(connect(db)) as store:
        sid = store.insert_session(Session(task_description="t", task_type="t"))
        store.insert_extraction(Extraction(
            source_id=1, skill_id=1, session_id=sid, output={"a": 1},
        ))
    main(["--db", db, "feedback", "add",
          "--extraction-id", "1", "--type", "wrong_value",
          "--correction", '{"a": {"old": 1, "new": 2}}'])


def test_cli_session_list(tmp_path):
    from freud_schema.cli import main
    import io
    import sys
    db = str(tmp_path / "test.duckdb")
    main(["--db", db, "db", "init"])
    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    try:
        main(["--db", db, "session", "list"])
    finally:
        sys.stdout = old_stdout
    assert "No sessions" in buf.getvalue()


def test_cli_session_show(tmp_path):
    from freud_schema.cli import main
    from freud_schema.db import connect
    from freud_schema.store import ExperimentStore
    db = str(tmp_path / "test.duckdb")
    with ExperimentStore(connect(db)) as store:
        sid = store.insert_session(Session(task_description="test task", task_type="extraction"))
    import io
    import sys
    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    try:
        main(["--db", db, "session", "show", str(sid)])
    finally:
        sys.stdout = old_stdout
    assert "test task" in buf.getvalue()


def test_cli_session_show_nonexistent(tmp_path):
    from freud_schema.cli import main
    db = str(tmp_path / "test.duckdb")
    main(["--db", db, "db", "init"])
    with pytest.raises(SystemExit):
        main(["--db", db, "session", "show", "999"])
