"""Tests for the experiment harness: DuckDB schema, store, orchestrator.

Tests cover the dimensional model (dim_*/fact_* tables), insert-time
denormalization, view-backed aggregation queries, and the unchanged
orchestrator/provider interfaces.
"""

import duckdb
import orjson
import pytest

from freud_schema.keys import dimension_key
from freud_schema.orchestrator import (
    EchoProvider,
    assemble_runner_context,
    get_provider,
)
from freud_schema.tables import (
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
    Trace,
    TraceFeedback,
    TraceFeedbackType,
    TraceType,
    ValidationStatus,
)


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


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


def test_existence_validation_rejects_orphans(store):
    """Store-level existence checks reject orphaned references (replaces FK enforcement)."""
    bogus = "0" * 32

    # Session rejects nonexistent skill
    with pytest.raises(ValueError, match=f"Skill {bogus} not found"):
        store.insert_session(Session(task_description="test", task_type="test", skill_key=bogus))

    # Trace rejects nonexistent session
    with pytest.raises(ValueError, match=f"Session {bogus} not found"):
        store.insert_trace(Trace(session_key=bogus, trace_type=TraceType.TOOL_CALL, title="t"))

    # Extraction rejects nonexistent source (session and skill exist)
    skill_key = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    session_key = store.insert_session(Session(task_description="t", task_type="t"))
    with pytest.raises(ValueError, match=f"Source {bogus} not found"):
        store.insert_extraction(Extraction(
            source_key=bogus, skill_key=skill_key, session_key=session_key, output={},
        ))

    # Extraction rejects nonexistent skill (session and source exist)
    source_key = store.insert_source(Source(content_path="/f", media_type="text/plain"))
    with pytest.raises(ValueError, match=f"Skill {bogus} not found"):
        store.insert_extraction(Extraction(
            source_key=source_key, skill_key=bogus, session_key=session_key, output={},
        ))

    # Feedback rejects nonexistent extraction
    with pytest.raises(ValueError, match=f"Extraction {bogus} not found"):
        store.insert_feedback(Feedback(
            extraction_key=bogus, session_key=session_key, skill_key=skill_key,
            correction={"x": 1}, correction_type=CorrectionType.WRONG_VALUE,
        ))

    # Trace feedback rejects nonexistent trace
    store.insert_trace(Trace(session_key=session_key, trace_type=TraceType.TOOL_CALL, title="t"))
    with pytest.raises(ValueError, match=f"Trace {bogus} not found"):
        store.insert_trace_feedback(TraceFeedback(
            trace_key=bogus, session_key=session_key,
            feedback_type=TraceFeedbackType.POSITIVE_SIGNAL, content="x",
        ))


def test_existence_validation_allows_null_optional_refs(store):
    """Optional references (NULL skill_key on session) skip validation."""
    session_key = store.insert_session(Session(task_description="no skill", task_type="t"))
    assert session_key is not None
    session = store.get_session(session_key)
    assert session.skill_key is None


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
        Extraction(source_key="s", skill_key="k", session_key="x", output={}, validation_status="bogus")  # type: ignore[arg-type]


def test_feedback_rejects_invalid_correction_type():
    with pytest.raises(Exception):
        Feedback(
            extraction_key="e", session_key="s", skill_key="k",
            correction={}, correction_type="bogus",  # type: ignore[arg-type]
        )


def test_rule_rejects_invalid_scope():
    with pytest.raises(Exception):
        Rule(name="test-rule", content="test", scope="bogus")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# DB CHECK constraint tests
# ---------------------------------------------------------------------------


def test_check_constraint_rejects_invalid_insert(store):
    """DuckDB CHECK constraint rejects invalid enum values."""
    with pytest.raises(duckdb.ConstraintException):
        store.con.execute(
            "INSERT INTO dim_skill (skill_key, domain, task_type, content, status) "
            "VALUES ('k', 'd', 't', 'c', 'bogus')"
        )


# ---------------------------------------------------------------------------
# Skill CRUD tests
# ---------------------------------------------------------------------------


def test_insert_and_get_skill(store):
    skill = Skill(domain="arxiv", task_type="extraction", content="Extract papers")
    skill_key = store.insert_skill(skill)
    assert skill_key == dimension_key("default", "arxiv", "extraction")
    fetched = store.get_skill(skill_key)
    assert fetched is not None
    assert fetched.domain == "arxiv"
    assert fetched.status == SkillStatus.DRAFT


def test_list_skills_filter(store):
    store.insert_skill(Skill(domain="a", task_type="t", content="c", status=SkillStatus.ACTIVE))
    store.insert_skill(Skill(domain="b", task_type="t", content="c", status=SkillStatus.DRAFT))
    assert len(store.list_skills(status=SkillStatus.ACTIVE)) == 1
    assert len(store.list_skills(domain="a")) == 1


def test_activate_deprecate_skill(store):
    skill_key = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    store.activate_skill(skill_key)
    assert store.get_skill(skill_key).status == SkillStatus.ACTIVE
    store.deprecate_skill(skill_key)
    assert store.get_skill(skill_key).status == SkillStatus.DEPRECATED


def test_skill_version_roundtrip(store):
    store.insert_skill(Skill(domain="d", task_type="t", content="v1", version=1, status=SkillStatus.ACTIVE))
    store.insert_skill(Skill(domain="d", task_type="t", content="v2", version=2, status=SkillStatus.ACTIVE))
    active = store.get_active_skill("d", "t")
    assert active.version == 2


def test_skill_version_must_exceed_current(store):
    """v0.17: re-adding the same (domain, task_type) requires a strictly
    greater version -- SCD-2 evolution, not a unique constraint violation."""
    store.insert_skill(Skill(domain="d", task_type="t", content="c1", version=1))
    with pytest.raises(ValueError, match="version"):
        store.insert_skill(Skill(domain="d", task_type="t", content="c2", version=1))


def test_skill_origin(store):
    skill_key = store.insert_skill(Skill(domain="d", task_type="t", content="c", origin=SkillOrigin.DATA_DERIVED))
    skill = store.get_skill(skill_key)
    assert skill.origin == SkillOrigin.DATA_DERIVED


def test_insert_derived_skill(store):
    skill_key = store.insert_derived_skill(
        Skill(domain="d", task_type="t", content="derived", version=2),
        source_session_keys=["s1", "s2"],
        source_trace_keys=["t1", "t2"],
    )
    skill = store.get_skill(skill_key)
    assert skill.origin == SkillOrigin.DATA_DERIVED
    assert skill.metadata["derived_from"]["session_keys"] == ["s1", "s2"]


def test_get_active_sub_skills(store):
    parent = store.insert_skill(Skill(domain="d", task_type="parent", content="p", status=SkillStatus.ACTIVE))
    store.insert_skill(Skill(domain="d", task_type="child1", content="c1", parent_skill_key=parent, status=SkillStatus.ACTIVE))
    store.insert_skill(Skill(domain="d", task_type="child2", content="c2", parent_skill_key=parent, status=SkillStatus.DEPRECATED))
    children = store.get_active_sub_skills(parent)
    assert len(children) == 1
    assert children[0].task_type == "child1"


# ---------------------------------------------------------------------------
# Source CRUD tests
# ---------------------------------------------------------------------------


def test_insert_and_get_source(store):
    source = Source(content_path="/tmp/test.pdf", media_type="application/pdf")
    source_key = store.insert_source(source)
    assert source_key == dimension_key("default", "/tmp/test.pdf")
    fetched = store.get_source(source_key)
    assert fetched.content_path == "/tmp/test.pdf"


def test_get_sources_by_keys(store):
    k1 = store.insert_source(Source(content_path="/a.pdf", media_type="application/pdf"))
    k2 = store.insert_source(Source(content_path="/b.pdf", media_type="application/pdf"))
    source_map = store.get_sources_by_keys([k1, k2])
    assert len(source_map) == 2
    assert source_map[k1].content_path == "/a.pdf"


# ---------------------------------------------------------------------------
# Session CRUD tests
# ---------------------------------------------------------------------------


def test_insert_and_get_session(store):
    session = Session(task_description="test", task_type="extraction")
    session_key = store.insert_session(session)
    assert len(session_key) == 32
    fetched = store.get_session(session_key)
    assert fetched.task_description == "test"


def test_session_skill_denormalization(store):
    """Session denormalizes skill attributes at insert time."""
    skill_key = store.insert_skill(Skill(domain="arxiv", task_type="extraction", content="x", version=3))
    session = Session(task_description="test", task_type="extraction", skill_key=skill_key)
    session_key = store.insert_session(session)
    fetched = store.get_session(session_key)
    assert fetched.skill_domain == "arxiv"
    assert fetched.skill_task_type == "extraction"
    assert fetched.skill_version == 3


def test_complete_session(store):
    session_key = store.insert_session(Session(task_description="t", task_type="t"))
    store.complete_session(session_key, status=SessionStatus.COMPLETED, result={"ok": True})
    session = store.get_session(session_key)
    assert session.status == SessionStatus.COMPLETED
    assert session.result == {"ok": True}
    assert session.completed_at is not None


def test_update_session_model(store):
    session_key = store.insert_session(Session(task_description="t", task_type="t"))
    store.update_session_model(session_key, "claude-sonnet-4-6")
    session = store.get_session(session_key)
    assert session.model_used == "claude-sonnet-4-6"


def test_list_sessions_with_filters(store):
    store.insert_session(Session(task_description="a", task_type="t", status=SessionStatus.RUNNING))
    session_key2 = store.insert_session(Session(task_description="b", task_type="t"))
    store.complete_session(session_key2, status=SessionStatus.COMPLETED)
    completed = store.list_sessions(status=SessionStatus.COMPLETED)
    assert len(completed) == 1
    assert completed[0].task_description == "b"


# ---------------------------------------------------------------------------
# Trace CRUD tests + denormalization
# ---------------------------------------------------------------------------


def test_insert_trace_denormalizes_skill(store):
    """Trace denormalizes skill attributes from its session."""
    skill_key = store.insert_skill(Skill(domain="arxiv", task_type="extraction", content="x"))
    session_key = store.insert_session(Session(task_description="t", task_type="t", skill_key=skill_key))
    trace = Trace(session_key=session_key, trace_type=TraceType.DECISION_POINT, title="Choose approach")
    trace_key = store.insert_trace(trace)
    fetched = store.get_trace(trace_key)
    assert fetched.skill_key == skill_key
    assert fetched.skill_domain == "arxiv"
    assert fetched.skill_task_type == "extraction"


def test_get_session_traces(store):
    session_key = store.insert_session(Session(task_description="t", task_type="t"))
    store.insert_trace(Trace(session_key=session_key, trace_type=TraceType.DECISION_POINT, title="a", depth=0))
    store.insert_trace(Trace(session_key=session_key, trace_type=TraceType.PATH_TAKEN, title="b", depth=1))
    traces = store.get_session_traces(session_key)
    assert len(traces) == 2
    assert traces[0].title == "a"
    assert traces[1].title == "b"


def test_count_traces_by_type(store):
    session_key = store.insert_session(Session(task_description="t", task_type="t"))
    store.insert_trace(Trace(session_key=session_key, trace_type=TraceType.TOOL_CALL, title="t1"))
    store.insert_trace(Trace(session_key=session_key, trace_type=TraceType.TOOL_CALL, title="t2"))
    store.insert_trace(Trace(session_key=session_key, trace_type=TraceType.DECISION_POINT, title="d1"))
    counts = store.count_traces_by_type(session_key)
    assert counts[0] == ("tool_call", 2)


def test_delete_session_traces(store):
    session_key = store.insert_session(Session(task_description="t", task_type="t"))
    trace_key = store.insert_trace(Trace(session_key=session_key, trace_type=TraceType.TOOL_CALL, title="t"))
    store.insert_trace_feedback(TraceFeedback(
        trace_key=trace_key, session_key=session_key, feedback_type=TraceFeedbackType.POSITIVE_SIGNAL,
        content="good",
    ))
    count = store.delete_session_traces(session_key)
    assert count == 1
    assert store.get_session_traces(session_key) == []
    assert store.list_trace_feedback(session_key=session_key) == []


# ---------------------------------------------------------------------------
# Extraction tests + denormalization
# ---------------------------------------------------------------------------


def test_insert_extraction_denormalizes(store):
    """Extraction denormalizes both source and skill attributes."""
    skill_key = store.insert_skill(Skill(domain="arxiv", task_type="extraction", content="x", version=2))
    source_key = store.insert_source(Source(content_path="/test.pdf", media_type="application/pdf"))
    session_key = store.insert_session(Session(task_description="t", task_type="t"))
    ext = Extraction(source_key=source_key, skill_key=skill_key, session_key=session_key, output={"title": "Paper"})
    extraction_key = store.insert_extraction(ext)
    fetched = store.get_extraction(extraction_key)
    assert fetched.source_path == "/test.pdf"
    assert fetched.source_media_type == "application/pdf"
    assert fetched.skill_domain == "arxiv"
    assert fetched.skill_task_type == "extraction"
    assert fetched.skill_version == 2


def test_validate_extraction(store):
    skill_key = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    source_key = store.insert_source(Source(content_path="/f", media_type="text/plain"))
    session_key = store.insert_session(Session(task_description="t", task_type="t"))
    extraction_key = store.insert_extraction(Extraction(
        source_key=source_key, skill_key=skill_key, session_key=session_key, output={"a": 1},
    ))
    store.update_validation(extraction_key, status=ValidationStatus.VALIDATED, validated_by="tester")
    fetched = store.get_extraction(extraction_key)
    assert fetched.validation_status == ValidationStatus.VALIDATED
    assert fetched.validated_by == "tester"


def test_list_extractions(store):
    skill_key = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    source_key = store.insert_source(Source(content_path="/f", media_type="text/plain"))
    session_key = store.insert_session(Session(task_description="t", task_type="t"))
    store.insert_extraction(Extraction(
        source_key=source_key, skill_key=skill_key, session_key=session_key, output={},
    ))
    assert len(store.list_extractions()) == 1
    assert len(store.list_extractions(skill_key=skill_key)) == 1
    assert len(store.list_extractions(skill_key="0" * 32)) == 0


def test_extraction_with_feedback(store):
    skill_key = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    source_key = store.insert_source(Source(content_path="/f", media_type="text/plain"))
    session_key = store.insert_session(Session(task_description="t", task_type="t"))
    extraction_key = store.insert_extraction(Extraction(
        source_key=source_key, skill_key=skill_key, session_key=session_key, output={},
    ))
    store.insert_feedback(Feedback(
        extraction_key=extraction_key, session_key=session_key, skill_key=skill_key,
        correction={"fix": "it"}, correction_type=CorrectionType.WRONG_VALUE,
    ))
    result = store.get_extraction_with_feedback(extraction_key)
    assert result is not None
    assert len(result["feedback"]) == 1


# ---------------------------------------------------------------------------
# Feedback tests + denormalization
# ---------------------------------------------------------------------------


def test_insert_feedback_denormalizes(store):
    """Feedback denormalizes skill and source attributes."""
    skill_key = store.insert_skill(Skill(domain="arxiv", task_type="extraction", content="x", version=2))
    source_key = store.insert_source(Source(content_path="/paper.pdf", media_type="application/pdf"))
    session_key = store.insert_session(Session(task_description="t", task_type="t"))
    extraction_key = store.insert_extraction(Extraction(
        source_key=source_key, skill_key=skill_key, session_key=session_key, output={},
    ))
    fb = Feedback(
        extraction_key=extraction_key, session_key=session_key, skill_key=skill_key,
        correction={"title": {"old": "a", "new": "b"}},
        correction_type=CorrectionType.WRONG_VALUE,
    )
    store.insert_feedback(fb)
    fetched = store.list_feedback(skill_key=skill_key)
    assert len(fetched) == 1
    f = fetched[0]
    assert f.skill_domain == "arxiv"
    assert f.skill_task_type == "extraction"
    assert f.skill_version == 2
    assert f.source_key == source_key
    assert f.source_path == "/paper.pdf"


def test_aggregate_feedback_uses_views(store):
    """aggregate_feedback returns view-backed results."""
    skill_key = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    source_key = store.insert_source(Source(content_path="/f", media_type="text/plain"))
    session_key = store.insert_session(Session(task_description="t", task_type="t"))
    extraction_key = store.insert_extraction(Extraction(
        source_key=source_key, skill_key=skill_key, session_key=session_key, output={},
    ))
    for _ in range(3):
        store.insert_feedback(Feedback(
            extraction_key=extraction_key, session_key=session_key, skill_key=skill_key,
            correction={"title": "fix"}, correction_type=CorrectionType.WRONG_VALUE,
        ))
    store.insert_feedback(Feedback(
        extraction_key=extraction_key, session_key=session_key, skill_key=skill_key,
        correction={"field": "fix"}, correction_type=CorrectionType.MISSING_FIELD,
    ))
    agg = store.aggregate_feedback(skill_key)
    assert len(agg) == 2
    assert agg[0]["correction_type"] == "wrong_value"
    assert agg[0]["count"] == 3
    assert "title" in agg[0]["fields"]


def test_aggregate_feedback_with_examples(store):
    skill_key = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    source_key = store.insert_source(Source(content_path="/f", media_type="text/plain"))
    session_key = store.insert_session(Session(task_description="t", task_type="t"))
    extraction_key = store.insert_extraction(Extraction(
        source_key=source_key, skill_key=skill_key, session_key=session_key, output={},
    ))
    store.insert_feedback(Feedback(
        extraction_key=extraction_key, session_key=session_key, skill_key=skill_key,
        correction={"x": 1}, correction_type=CorrectionType.WRONG_VALUE,
    ))
    agg = store.aggregate_feedback(skill_key, include_examples=True, max_examples=2)
    assert len(agg) == 1
    assert len(agg[0]["examples"]) == 1
    assert agg[0]["examples"][0] == {"x": 1}


# ---------------------------------------------------------------------------
# Trace feedback tests + denormalization
# ---------------------------------------------------------------------------


def test_insert_trace_feedback_denormalizes(store):
    """Trace feedback denormalizes trace and skill attributes."""
    skill_key = store.insert_skill(Skill(domain="arxiv", task_type="extraction", content="x"))
    session_key = store.insert_session(Session(task_description="t", task_type="t", skill_key=skill_key))
    trace_key = store.insert_trace(Trace(
        session_key=session_key, trace_type=TraceType.DEAD_END, title="Bad approach",
    ))
    tf = TraceFeedback(
        trace_key=trace_key, session_key=session_key,
        feedback_type=TraceFeedbackType.DEAD_END_CONFIRMATION,
        content="Yes this was a dead end",
    )
    store.insert_trace_feedback(tf)
    fetched = store.list_trace_feedback(session_key=session_key)
    assert len(fetched) == 1
    f = fetched[0]
    assert f.trace_type == "dead_end"
    assert f.trace_title == "Bad approach"
    assert f.skill_key == skill_key
    assert f.skill_domain == "arxiv"


def test_aggregate_trace_feedback(store):
    """aggregate_trace_feedback works without joins."""
    session_key = store.insert_session(Session(task_description="t", task_type="t"))
    trace_key = store.insert_trace(Trace(session_key=session_key, trace_type=TraceType.DEAD_END, title="t"))
    store.insert_trace_feedback(TraceFeedback(
        trace_key=trace_key, session_key=session_key,
        feedback_type=TraceFeedbackType.DEAD_END_CONFIRMATION, content="a",
    ))
    store.insert_trace_feedback(TraceFeedback(
        trace_key=trace_key, session_key=session_key,
        feedback_type=TraceFeedbackType.POSITIVE_SIGNAL, content="b",
    ))
    agg = store.aggregate_trace_feedback(session_key)
    assert len(agg) == 2


# ---------------------------------------------------------------------------
# Rule CRUD tests
# ---------------------------------------------------------------------------


def test_insert_and_get_rules(store):
    store.insert_rule(Rule(name="always-validate", content="Always validate", priority=10))
    store.insert_rule(Rule(
        name="arxiv-domain-rule", content="Domain rule",
        scope=RuleScope.DOMAIN_SPECIFIC, domain="arxiv", priority=5,
    ))
    global_rules = store.get_rules()
    assert len(global_rules) == 1
    domain_rules = store.get_rules(domain="arxiv")
    assert len(domain_rules) == 2


# ---------------------------------------------------------------------------
# Sampling config tests
# ---------------------------------------------------------------------------


def test_sampling_config_crud(store):
    store.insert_sampling_config(SamplingConfig(
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
    skill_key = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    for i in range(5):
        session_key = store.insert_session(Session(
            task_description=f"run-{i}", task_type="t", skill_key=skill_key,
        ))
        store.complete_session(session_key, status=SessionStatus.COMPLETED)
    samples = store.sample_prior_sessions(skill_key=skill_key, max_samples=3)
    assert len(samples) == 3


def test_sample_prior_sessions_excludes_running(store):
    skill_key = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    store.insert_session(Session(task_description="running", task_type="t", skill_key=skill_key))
    samples = store.sample_prior_sessions(skill_key=skill_key)
    assert len(samples) == 0


def test_sample_prior_sessions_excludes_keys(store):
    skill_key = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    session_key = store.insert_session(Session(task_description="t", task_type="t", skill_key=skill_key))
    store.complete_session(session_key, status=SessionStatus.COMPLETED)
    samples = store.sample_prior_sessions(skill_key=skill_key, exclude_session_keys=[session_key])
    assert len(samples) == 0


def test_sample_stratified_outcome(store):
    skill_key = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    for i in range(3):
        session_key = store.insert_session(Session(task_description=f"ok-{i}", task_type="t", skill_key=skill_key))
        store.complete_session(session_key, status=SessionStatus.COMPLETED)
    session_key = store.insert_session(Session(task_description="fail", task_type="t", skill_key=skill_key))
    store.complete_session(session_key, status=SessionStatus.FAILED)
    samples = store.sample_prior_sessions(
        skill_key=skill_key, strategy=SamplingStrategy.STRATIFIED_OUTCOME, max_samples=3,
    )
    assert len(samples) == 3
    statuses = {s.status for s in samples}
    assert SessionStatus.FAILED in statuses
    assert SessionStatus.COMPLETED in statuses


def test_sample_high_feedback(store):
    skill_key = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    source_key = store.insert_source(Source(content_path="/f", media_type="text/plain"))
    # Session with more feedback should rank higher
    session_key1 = store.insert_session(Session(task_description="s1", task_type="t", skill_key=skill_key))
    store.complete_session(session_key1, status=SessionStatus.COMPLETED)
    extraction_key1 = store.insert_extraction(Extraction(
        source_key=source_key, skill_key=skill_key, session_key=session_key1, output={},
    ))
    for _ in range(3):
        store.insert_feedback(Feedback(
            extraction_key=extraction_key1, session_key=session_key1, skill_key=skill_key,
            correction={"x": 1}, correction_type=CorrectionType.WRONG_VALUE,
        ))
    session_key2 = store.insert_session(Session(task_description="s2", task_type="t", skill_key=skill_key))
    store.complete_session(session_key2, status=SessionStatus.COMPLETED)
    samples = store.sample_prior_sessions(
        skill_key=skill_key, strategy=SamplingStrategy.HIGH_FEEDBACK, max_samples=2,
    )
    assert len(samples) == 2
    assert samples[0].session_key == session_key1  # more feedback -> first


def test_sample_stratified_feedback(store):
    skill_key = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    source_key = store.insert_source(Source(content_path="/f", media_type="text/plain"))
    session_key1 = store.insert_session(Session(task_description="s1", task_type="t", skill_key=skill_key))
    store.complete_session(session_key1, status=SessionStatus.COMPLETED)
    extraction_key1 = store.insert_extraction(Extraction(
        source_key=source_key, skill_key=skill_key, session_key=session_key1, output={},
    ))
    store.insert_feedback(Feedback(
        extraction_key=extraction_key1, session_key=session_key1, skill_key=skill_key,
        correction={"x": 1}, correction_type=CorrectionType.WRONG_VALUE,
    ))
    session_key2 = store.insert_session(Session(task_description="s2", task_type="t", skill_key=skill_key))
    store.complete_session(session_key2, status=SessionStatus.COMPLETED)
    extraction_key2 = store.insert_extraction(Extraction(
        source_key=source_key, skill_key=skill_key, session_key=session_key2, output={},
    ))
    store.insert_feedback(Feedback(
        extraction_key=extraction_key2, session_key=session_key2, skill_key=skill_key,
        correction={"y": 2}, correction_type=CorrectionType.MISSING_FIELD,
    ))
    samples = store.sample_prior_sessions(
        skill_key=skill_key, strategy=SamplingStrategy.STRATIFIED_FEEDBACK, max_samples=3,
    )
    assert len(samples) == 2  # one per correction type


# ---------------------------------------------------------------------------
# View-backed pattern detection tests
# ---------------------------------------------------------------------------


def test_get_skills_with_feedback_patterns(store):
    skill_key = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    source_key = store.insert_source(Source(content_path="/f", media_type="text/plain"))
    session_key = store.insert_session(Session(task_description="t", task_type="t"))
    extraction_key = store.insert_extraction(Extraction(
        source_key=source_key, skill_key=skill_key, session_key=session_key, output={},
    ))
    for _ in range(3):
        store.insert_feedback(Feedback(
            extraction_key=extraction_key, session_key=session_key, skill_key=skill_key,
            correction={"x": 1}, correction_type=CorrectionType.WRONG_VALUE,
        ))
    results = store.get_skills_with_feedback_patterns(min_feedback_count=3)
    assert len(results) == 1
    assert results[0]["skill"].skill_key == skill_key
    assert results[0]["total_feedback"] == 3


def test_get_recurring_traces(store):
    skill_key = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    session_key1 = store.insert_session(Session(task_description="s1", task_type="t", skill_key=skill_key))
    session_key2 = store.insert_session(Session(task_description="s2", task_type="t", skill_key=skill_key))
    store.insert_trace(Trace(session_key=session_key1, trace_type=TraceType.DEAD_END, title="Hit wall"))
    store.insert_trace(Trace(session_key=session_key2, trace_type=TraceType.DEAD_END, title="Hit wall"))
    store.insert_trace(Trace(session_key=session_key1, trace_type=TraceType.DEAD_END, title="Unique"))
    patterns = store.get_recurring_traces(skill_key, TraceType.DEAD_END, min_occurrences=2)
    assert len(patterns) == 1
    assert patterns[0]["title"] == "Hit wall"
    assert patterns[0]["count"] == 2
    assert len(patterns[0]["session_keys"]) == 2


def test_get_recurring_trace_feedback(store):
    skill_key = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    session_key1 = store.insert_session(Session(task_description="s1", task_type="t", skill_key=skill_key))
    session_key2 = store.insert_session(Session(task_description="s2", task_type="t", skill_key=skill_key))
    trace_key1 = store.insert_trace(Trace(session_key=session_key1, trace_type=TraceType.DEAD_END, title="Bad path"))
    trace_key2 = store.insert_trace(Trace(session_key=session_key2, trace_type=TraceType.DEAD_END, title="Bad path"))
    store.insert_trace_feedback(TraceFeedback(
        trace_key=trace_key1, session_key=session_key1,
        feedback_type=TraceFeedbackType.DEAD_END_CONFIRMATION, content="yes",
    ))
    store.insert_trace_feedback(TraceFeedback(
        trace_key=trace_key2, session_key=session_key2,
        feedback_type=TraceFeedbackType.DEAD_END_CONFIRMATION, content="yes",
    ))
    patterns = store.get_recurring_trace_feedback(skill_key, min_occurrences=2)
    assert len(patterns) == 1
    assert patterns[0]["trace_title"] == "Bad path"


# ---------------------------------------------------------------------------
# Rich session retrieval tests
# ---------------------------------------------------------------------------


def test_get_session_with_context(store):
    skill_key = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    source_key = store.insert_source(Source(content_path="/f", media_type="text/plain"))
    session_key = store.insert_session(Session(task_description="t", task_type="t", skill_key=skill_key))
    store.insert_trace(Trace(session_key=session_key, trace_type=TraceType.TOOL_CALL, title="t"))
    extraction_key = store.insert_extraction(Extraction(
        source_key=source_key, skill_key=skill_key, session_key=session_key, output={"a": 1},
    ))
    store.insert_feedback(Feedback(
        extraction_key=extraction_key, session_key=session_key, skill_key=skill_key,
        correction={"a": {"old": 1, "new": 2}}, correction_type=CorrectionType.WRONG_VALUE,
    ))
    ctx = store.get_session_with_context(session_key)
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
    skill_key = store.insert_skill(Skill(domain="d", task_type="t", content="Do the thing", status=SkillStatus.ACTIVE))
    store.activate_skill(skill_key)
    source_key = store.insert_source(Source(content_path="/test.pdf", media_type="application/pdf"))
    store.insert_rule(Rule(name="be-careful", content="Be careful", priority=10))
    system, user = assemble_runner_context(
        store, skill_key=skill_key, source_keys=[source_key], task_params="Extract data",
    )
    assert "Be careful" in system
    assert "Do the thing" in system
    assert "/test.pdf" in user
    assert "Extract data" in user


@pytest.mark.parametrize("status", [SkillStatus.DRAFT, SkillStatus.DEPRECATED])
def test_assemble_context_excludes_non_active_skill(store, status):
    """A skill that is not active must never reach an assembled prompt.

    This is the assembly half of the self-modification gate. `skill_add` forces
    `draft` regardless of what a caller asks for, precisely so that a session
    cannot write a skill that loads into its own future context. That guarantee
    is only real if the assembly path also refuses to render non-active skills --
    otherwise the gate stops the status and not the effect.

    Deprecated is covered by the same rule for a different reason: retiring a
    skill has to actually stop it being used, or deprecation means nothing.
    """
    skill_key = store.insert_skill(Skill(
        domain="d", task_type="t", content="NON_ACTIVE_SKILL_MARKER", status=status,
    ))
    system, _ = assemble_runner_context(store, skill_key=skill_key, source_keys=[])
    assert "NON_ACTIVE_SKILL_MARKER" not in system, (
        f"a {status.value} skill was rendered into the system prompt"
    )


def test_assemble_context_includes_active_skill(store):
    """Positive control for the test above -- the filter must not reject everything."""
    skill_key = store.insert_skill(Skill(
        domain="d", task_type="t", content="ACTIVE_SKILL_MARKER",
        status=SkillStatus.ACTIVE,
    ))
    system, _ = assemble_runner_context(store, skill_key=skill_key, source_keys=[])
    assert "ACTIVE_SKILL_MARKER" in system


def test_assemble_context_with_feedback_summary(store):
    skill_key = store.insert_skill(Skill(domain="d", task_type="t", content="Do the thing"))
    source_key = store.insert_source(Source(content_path="/f", media_type="text/plain"))
    session_key = store.insert_session(Session(task_description="t", task_type="t"))
    extraction_key = store.insert_extraction(Extraction(
        source_key=source_key, skill_key=skill_key, session_key=session_key, output={},
    ))
    store.insert_feedback(Feedback(
        extraction_key=extraction_key, session_key=session_key, skill_key=skill_key,
        correction={"field": "fix"}, correction_type=CorrectionType.WRONG_VALUE,
    ))
    system, _user = assemble_runner_context(
        store, skill_key=skill_key, source_keys=[], include_feedback_summary=True,
    )
    assert "Feedback Patterns" in system
    assert "wrong_value" in system


def test_assemble_context_with_prior_runs(store):
    skill_key = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    session_key = store.insert_session(Session(task_description="old run", task_type="t", skill_key=skill_key))
    store.complete_session(session_key, status=SessionStatus.COMPLETED)
    store.insert_trace(Trace(
        session_key=session_key, trace_type=TraceType.DECISION_POINT, title="Chose method",
    ))
    prior_runs = store.get_sessions_with_context([session_key])
    system, _ = assemble_runner_context(
        store, skill_key=skill_key, source_keys=[], prior_runs=prior_runs,
    )
    assert "Prior Runs" in system
    assert "Chose method" in system


def test_prior_runs_filters_signal_traces(store):
    """_format_prior_runs only includes signal-bearing traces, skips tool_call/path_taken."""
    skill_key = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    session_key = store.insert_session(Session(task_description="run", task_type="t", skill_key=skill_key))
    store.complete_session(session_key, status=SessionStatus.COMPLETED)
    # Insert a mix of signal and mechanical traces
    store.insert_trace(Trace(session_key=session_key, trace_type=TraceType.DECISION_POINT, title="Key decision"))
    store.insert_trace(Trace(session_key=session_key, trace_type=TraceType.TOOL_CALL, title="Read file"))
    store.insert_trace(Trace(session_key=session_key, trace_type=TraceType.TOOL_CALL, title="Write file"))
    store.insert_trace(Trace(session_key=session_key, trace_type=TraceType.PATH_TAKEN, title="Chose path A"))
    store.insert_trace(Trace(session_key=session_key, trace_type=TraceType.DEAD_END, title="Hit wall"))
    store.insert_trace(Trace(session_key=session_key, trace_type=TraceType.INSIGHT, title="Realized pattern"))
    prior_runs = store.get_sessions_with_context([session_key])
    system, _ = assemble_runner_context(
        store, skill_key=skill_key, source_keys=[], prior_runs=prior_runs,
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
    skill_key = dimension_key("default", "d", "t")
    main(["--db", db, "skill", "deprecate", skill_key[:8]])


def test_cli_skill_deprecate_nonexistent(tmp_path):
    from freud_schema.cli import main
    db = str(tmp_path / "test.duckdb")
    main(["--db", db, "db", "init"])
    with pytest.raises(SystemExit):
        main(["--db", db, "skill", "deprecate", "999"])


def test_cli_ingest_events(tmp_path):
    from freud_schema.cli import main
    import io
    import json
    import sys
    db = str(tmp_path / "test.duckdb")
    events_root = tmp_path / "events"
    events_root.mkdir()
    (events_root / "s.jsonl").write_text(json.dumps(
        {"id": "e1", "type": "t", "timestamp": None,
         "actor": None, "payload": None}) + "\n")
    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    try:
        main(["--db", db, "ingest", "events", "--root", str(events_root)])
    finally:
        sys.stdout = old_stdout
    output = buf.getvalue()
    assert "streams:" in output
    assert "rows written:" in output
    with duckdb.connect(db) as con:
        assert con.execute("SELECT COUNT(*) FROM fact_event").fetchone()[0] == 1
        assert con.execute(
            "SELECT COUNT(*) FROM dim_event_type WHERE event_type = 't'"
        ).fetchone()[0] == 1


def test_cli_source_add_list(tmp_path):
    from freud_schema.cli import main
    import io
    import sys
    db = str(tmp_path / "test.duckdb")
    main(["--db", db, "source", "add", "--path", "/test.pdf", "--media-type", "application/pdf", "--no-hash"])
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
    main(["--db", db, "rule", "add", "--name", "be-careful", "--content", "Be careful"])
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
    main(["--db", db, "source", "add", "--path", "/f", "--media-type", "text/plain", "--no-hash"])
    # Insert a session and extraction via store (CLI doesn't expose session/extraction add)
    from freud_schema.db import connect
    from freud_schema.store import ExperimentStore
    skill_key = dimension_key("default", "d", "t")
    source_key = dimension_key("default", "/f")
    with ExperimentStore(connect(db)) as store:
        session_key = store.insert_session(Session(task_description="t", task_type="t"))
        extraction_key = store.insert_extraction(Extraction(
            source_key=source_key, skill_key=skill_key, session_key=session_key, output={"a": 1},
        ))
    main(["--db", db, "feedback", "add",
          "--extraction-key", extraction_key, "--type", "wrong_value",
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
        session_key = store.insert_session(Session(task_description="test task", task_type="extraction"))
    import io
    import sys
    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    try:
        main(["--db", db, "session", "show", session_key])
    finally:
        sys.stdout = old_stdout
    assert "test task" in buf.getvalue()


def test_cli_session_show_nonexistent(tmp_path):
    from freud_schema.cli import main
    db = str(tmp_path / "test.duckdb")
    main(["--db", db, "db", "init"])
    with pytest.raises(SystemExit):
        main(["--db", db, "session", "show", "999"])


def test_cli_proposal_add_bad_evidence_key_exits_cleanly(tmp_path):
    """A bad --evidence key (no matching finding) must exit(1) with a
    readable message on stderr, matching the approve/reject branches'
    ValueError-wrapping convention -- not dump a raw traceback."""
    from freud_schema.cli import main
    import io
    import sys
    db = str(tmp_path / "test.duckdb")
    main(["--db", db, "db", "init"])
    buf = io.StringIO()
    old_stderr = sys.stderr
    sys.stderr = buf
    try:
        with pytest.raises(SystemExit) as exc_info:
            main(["--db", db, "proposal", "add", "--target", "dim_rule",
                  "--natural-key", '{"name": "no-retry"}', "--content", "c",
                  "--evidence", "0" * 32])
    finally:
        sys.stderr = old_stderr
    assert exc_info.value.code == 1
    output = buf.getvalue()
    assert output.strip()
    assert "Traceback" not in output
