"""Tests for the experiment harness: DuckDB schema, store, orchestrator."""

import pytest

from freud_schema.db import connect, reset_schema
from freud_schema.orchestrator import assemble_runner_context, run_subtask, run_task
from freud_schema.store import ExperimentStore
from freud_schema.tables import (
    Extraction,
    Feedback,
    Rule,
    Session,
    Skill,
    Source,
    Subtask,
    TaskPlan,
)


@pytest.fixture
def store():
    """In-memory DuckDB store for each test."""
    con = connect(":memory:")
    s = ExperimentStore(con)
    yield s
    con.close()


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


def test_schema_creates_all_tables(store):
    tables = store.con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
    ).fetchall()
    table_names = {t[0] for t in tables}
    assert "skills" in table_names
    assert "sources" in table_names
    assert "extractions" in table_names
    assert "sessions" in table_names
    assert "feedback" in table_names
    assert "rules" in table_names


def test_reset_schema(store):
    store.insert_skill(Skill(domain="test", task_type="test", content="test"))
    assert len(store.list_skills()) == 1
    reset_schema(store.con)
    assert len(store.list_skills()) == 0


# ---------------------------------------------------------------------------
# Skills CRUD
# ---------------------------------------------------------------------------


def test_insert_and_get_skill(store):
    skill = Skill(
        domain="insurance",
        task_type="extraction",
        content="Extract policy numbers from PDF documents.",
        metadata={"fields": ["policy_number", "effective_date"]},
        status="active",
    )
    skill_id = store.insert_skill(skill)
    assert skill_id >= 1

    fetched = store.get_skill(skill_id)
    assert fetched is not None
    assert fetched.domain == "insurance"
    assert fetched.metadata == {"fields": ["policy_number", "effective_date"]}


def test_get_active_skill(store):
    store.insert_skill(Skill(
        domain="insurance", task_type="extraction", version=1,
        content="v1", status="deprecated",
    ))
    store.insert_skill(Skill(
        domain="insurance", task_type="extraction", version=2,
        content="v2", status="active",
    ))
    store.insert_skill(Skill(
        domain="insurance", task_type="extraction", version=3,
        content="v3", status="draft",
    ))

    active = store.get_active_skill("insurance", "extraction")
    assert active is not None
    assert active.version == 2
    assert active.content == "v2"


def test_list_skills_filters(store):
    store.insert_skill(Skill(domain="a", task_type="t", content="1", status="active"))
    store.insert_skill(Skill(domain="b", task_type="t", content="2", status="active"))
    store.insert_skill(Skill(domain="a", task_type="t", content="3", status="draft"))

    assert len(store.list_skills()) == 3
    assert len(store.list_skills(domain="a")) == 2
    assert len(store.list_skills(status="active")) == 2
    assert len(store.list_skills(domain="a", status="active")) == 1


def test_activate_and_deprecate_skill(store):
    skill_id = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    assert store.get_skill(skill_id).status == "draft"

    store.activate_skill(skill_id)
    assert store.get_skill(skill_id).status == "active"

    store.deprecate_skill(skill_id)
    assert store.get_skill(skill_id).status == "deprecated"


# ---------------------------------------------------------------------------
# Sources CRUD
# ---------------------------------------------------------------------------


def test_insert_and_get_source(store):
    source = Source(
        content_path="/data/policy_001.pdf",
        media_type="application/pdf",
        metadata={"domain": "insurance", "owner": "acme"},
        source_hash="abc123",
    )
    source_id = store.insert_source(source)
    fetched = store.get_source(source_id)
    assert fetched is not None
    assert fetched.content_path == "/data/policy_001.pdf"
    assert fetched.metadata["owner"] == "acme"


def test_list_sources_filters(store):
    store.insert_source(Source(content_path="a.pdf", media_type="application/pdf"))
    store.insert_source(Source(content_path="b.pdf", media_type="application/pdf", status="archived"))
    assert len(store.list_sources()) == 2
    assert len(store.list_sources(status="active")) == 1


# ---------------------------------------------------------------------------
# Sessions CRUD
# ---------------------------------------------------------------------------


def test_insert_and_complete_session(store):
    session = Session(
        task_description="Extract from policy",
        task_type="extraction",
        agent_role="subagent",
        model_used="claude-sonnet-4-6",
    )
    session_id = store.insert_session(session)
    assert store.get_session(session_id).status == "running"

    store.complete_session(session_id, status="completed", result={"output": "done"})
    completed = store.get_session(session_id)
    assert completed.status == "completed"
    assert completed.result == {"output": "done"}
    assert completed.completed_at is not None


# ---------------------------------------------------------------------------
# Extractions CRUD
# ---------------------------------------------------------------------------


def test_insert_and_validate_extraction(store):
    # Setup dependencies
    skill_id = store.insert_skill(Skill(domain="d", task_type="t", content="c", status="active"))
    source_id = store.insert_source(Source(content_path="a.pdf", media_type="application/pdf"))
    session_id = store.insert_session(Session(
        task_description="test", task_type="test", agent_role="subagent",
    ))

    ext = Extraction(
        source_id=source_id, skill_id=skill_id, session_id=session_id,
        output={"policy_number": "XX-1234567"},
        confidence=0.95,
    )
    ext_id = store.insert_extraction(ext)
    fetched = store.get_extraction(ext_id)
    assert fetched.output == {"policy_number": "XX-1234567"}
    assert fetched.validation_status == "pending"

    store.update_validation(ext_id, status="validated", validated_by="human")
    validated = store.get_extraction(ext_id)
    assert validated.validation_status == "validated"
    assert validated.validated_by == "human"


def test_get_validated_extractions(store):
    skill_id = store.insert_skill(Skill(domain="d", task_type="t", content="c", status="active"))
    source_id = store.insert_source(Source(content_path="a.pdf", media_type="application/pdf"))
    session_id = store.insert_session(Session(
        task_description="test", task_type="test", agent_role="subagent",
    ))

    for i in range(3):
        ext_id = store.insert_extraction(Extraction(
            source_id=source_id, skill_id=skill_id, session_id=session_id,
            output={"i": i},
        ))
        if i < 2:
            store.update_validation(ext_id, status="validated")

    validated = store.get_validated_extractions(skill_id)
    assert len(validated) == 2


# ---------------------------------------------------------------------------
# Feedback CRUD
# ---------------------------------------------------------------------------


def test_insert_and_aggregate_feedback(store):
    skill_id = store.insert_skill(Skill(domain="d", task_type="t", content="c", status="active"))
    source_id = store.insert_source(Source(content_path="a.pdf", media_type="application/pdf"))
    session_id = store.insert_session(Session(
        task_description="test", task_type="test", agent_role="subagent",
    ))
    ext_id = store.insert_extraction(Extraction(
        source_id=source_id, skill_id=skill_id, session_id=session_id,
        output={"field": "value"},
    ))

    store.insert_feedback(Feedback(
        extraction_id=ext_id, session_id=session_id, skill_id=skill_id,
        correction={"field": {"before": "wrong", "after": "right"}},
        correction_type="wrong_value",
        created_by="reviewer",
    ))
    store.insert_feedback(Feedback(
        extraction_id=ext_id, session_id=session_id, skill_id=skill_id,
        correction={"field": {"before": "wrong", "after": "right"}},
        correction_type="wrong_value",
    ))
    store.insert_feedback(Feedback(
        extraction_id=ext_id, session_id=session_id, skill_id=skill_id,
        correction={"new_field": "added"},
        correction_type="missing_field",
    ))

    agg = store.aggregate_feedback(skill_id)
    assert len(agg) == 2
    assert agg[0] == ("wrong_value", 2)
    assert agg[1] == ("missing_field", 1)


# ---------------------------------------------------------------------------
# Rules CRUD
# ---------------------------------------------------------------------------


def test_rules_global_and_domain(store):
    store.insert_rule(Rule(scope="global", content="Output valid JSON", priority=10))
    store.insert_rule(Rule(scope="global", content="Never fabricate data", priority=5))
    store.insert_rule(Rule(scope="domain-specific", domain="insurance", content="Use ISO dates", priority=3))
    store.insert_rule(Rule(scope="domain-specific", domain="medical", content="HIPAA compliance", priority=1))

    global_rules = store.get_rules()
    assert len(global_rules) == 2

    insurance_rules = store.get_rules(domain="insurance")
    assert len(insurance_rules) == 3  # 2 global + 1 domain-specific

    medical_rules = store.get_rules(domain="medical")
    assert len(medical_rules) == 3  # 2 global + 1 medical


# ---------------------------------------------------------------------------
# Context assembly
# ---------------------------------------------------------------------------


def test_assemble_runner_context(store):
    store.insert_rule(Rule(scope="global", content="Output valid JSON", priority=10))
    skill_id = store.insert_skill(Skill(
        domain="insurance", task_type="extraction",
        content="Extract policy numbers.\nFormat: XX-XXXXXXX",
        status="active",
    ))
    source_id = store.insert_source(Source(
        content_path="/data/policy.pdf", media_type="application/pdf",
    ))

    system_prompt, user_message = assemble_runner_context(
        store,
        skill_id=skill_id,
        source_ids=[source_id],
        domain="insurance",
        task_params="Extract structured fields.",
    )

    assert "Output valid JSON" in system_prompt
    assert "Extract policy numbers" in system_prompt
    assert "policy.pdf" in user_message
    assert "Extract structured fields" in user_message


# ---------------------------------------------------------------------------
# Orchestrator end-to-end
# ---------------------------------------------------------------------------


def _mock_model(system_prompt: str, user_message: str) -> str:
    """Mock model that returns a fixed extraction."""
    return '{"policy_number": "XX-1234567", "effective_date": "2026-01-01"}'


def test_run_subtask(store):
    skill_id = store.insert_skill(Skill(
        domain="insurance", task_type="extraction",
        content="Extract policy fields", status="active",
    ))
    source_id = store.insert_source(Source(
        content_path="/data/policy.pdf", media_type="application/pdf",
    ))

    subtask = Subtask(
        type="extraction",
        skill_query={"domain": "insurance", "task_type": "extraction"},
        source_ids=[source_id],
    )
    extraction = run_subtask(store, subtask, model_fn=_mock_model, model_name="mock")
    assert extraction is not None
    assert "policy_number" in extraction.output["raw"]


def test_run_task_with_dependencies(store):
    store.insert_skill(Skill(
        domain="insurance", task_type="extraction",
        content="Extract policy fields", status="active",
    ))
    store.insert_skill(Skill(
        domain="insurance", task_type="validation",
        content="Validate extraction", status="active",
    ))
    source_id = store.insert_source(Source(
        content_path="/data/policy.pdf", media_type="application/pdf",
    ))

    plan = TaskPlan(subtasks=[
        Subtask(
            type="extraction",
            skill_query={"domain": "insurance", "task_type": "extraction"},
            source_ids=[source_id],
        ),
        Subtask(
            type="validation",
            skill_query={"domain": "insurance", "task_type": "validation"},
            source_ids=[source_id],
            depends_on=[0],
        ),
    ])

    extractions = run_task(
        store, plan,
        model_fn=_mock_model,
        task_description="Process insurance policy",
        model_name="mock",
    )
    assert len(extractions) == 2

    # Verify sessions were created
    sessions = store.list_sessions()
    assert len(sessions) >= 3  # 1 orchestrator + 2 subagent


def test_run_subtask_missing_skill(store):
    subtask = Subtask(
        type="extraction",
        skill_query={"domain": "nonexistent", "task_type": "nope"},
        source_ids=[],
    )
    result = run_subtask(store, subtask, model_fn=_mock_model)
    assert result is None


def test_run_subtask_model_failure(store):
    store.insert_skill(Skill(
        domain="d", task_type="t", content="c", status="active",
    ))
    source_id = store.insert_source(Source(
        content_path="a.pdf", media_type="application/pdf",
    ))

    def failing_model(system_prompt: str, user_message: str) -> str:
        raise RuntimeError("API error")

    subtask = Subtask(
        type="extraction",
        skill_query={"domain": "d", "task_type": "t"},
        source_ids=[source_id],
    )
    result = run_subtask(store, subtask, model_fn=failing_model)
    assert result is None

    # Session should be marked as failed
    sessions = store.list_sessions(status="failed")
    assert len(sessions) == 1
