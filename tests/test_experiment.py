"""Tests for the experiment harness: DuckDB schema, store, orchestrator."""

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
    run_single,
)
from freud_schema.tables import (
    AgentRole,
    CorrectionType,
    Extraction,
    Feedback,
    Rule,
    RuleScope,
    Session,
    SessionStatus,
    Skill,
    SkillStatus,
    Source,
    SourceStatus,
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


def test_schema_versioning(store):
    """meta_schema_version exists after init and contains version 1."""
    from freud_schema.db import get_schema_version
    assert get_schema_version(store.con) >= 1
    row = store.con.execute(
        "SELECT version, description FROM meta_schema_version WHERE version = 1"
    ).fetchone()
    assert row is not None
    assert row[1] == "Initial 6-table schema"


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
            "INSERT INTO skills (domain, task_type, content, status) VALUES ('d', 't', 'c', 'bogus')"
        )


def test_fk_constraint_rejects_orphaned_reference(store):
    """FK constraint rejects references to non-existent parent rows."""
    with pytest.raises(duckdb.ConstraintException):
        store.con.execute(
            "INSERT INTO extractions (source_id, skill_id, session_id, output, validation_status) "
            "VALUES (999, 999, 999, '{}', 'pending')"
        )


# ---------------------------------------------------------------------------
# Skills CRUD
# ---------------------------------------------------------------------------


def test_insert_and_get_skill(store):
    skill = Skill(
        domain="insurance",
        task_type="extraction",
        content="Extract policy numbers from PDF documents.",
        metadata={"fields": ["policy_number", "effective_date"]},
        status=SkillStatus.ACTIVE,
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
        content="v1", status=SkillStatus.DEPRECATED,
    ))
    store.insert_skill(Skill(
        domain="insurance", task_type="extraction", version=2,
        content="v2", status=SkillStatus.ACTIVE,
    ))
    store.insert_skill(Skill(
        domain="insurance", task_type="extraction", version=3,
        content="v3", status=SkillStatus.DRAFT,
    ))

    active = store.get_active_skill("insurance", "extraction")
    assert active is not None
    assert active.version == 2
    assert active.content == "v2"


def test_list_skills_filters(store):
    store.insert_skill(Skill(domain="a", task_type="t", content="1", status=SkillStatus.ACTIVE))
    store.insert_skill(Skill(domain="b", task_type="t", content="2", status=SkillStatus.ACTIVE))
    store.insert_skill(Skill(domain="a", task_type="t", content="3", status=SkillStatus.DRAFT))

    assert len(store.list_skills()) == 3
    assert len(store.list_skills(domain="a")) == 2
    assert len(store.list_skills(status=SkillStatus.ACTIVE)) == 2
    assert len(store.list_skills(domain="a", status=SkillStatus.ACTIVE)) == 1


def test_activate_and_deprecate_skill(store):
    skill_id = store.insert_skill(Skill(domain="d", task_type="t", content="c"))
    assert store.get_skill(skill_id).status == SkillStatus.DRAFT

    store.activate_skill(skill_id)
    assert store.get_skill(skill_id).status == SkillStatus.ACTIVE

    store.deprecate_skill(skill_id)
    assert store.get_skill(skill_id).status == SkillStatus.DEPRECATED


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
    store.insert_source(Source(content_path="b.pdf", media_type="application/pdf", status=SourceStatus.ARCHIVED))
    assert len(store.list_sources()) == 2
    assert len(store.list_sources(status=SourceStatus.ACTIVE)) == 1
    assert len(store.list_sources(status=SourceStatus.ARCHIVED)) == 1


def test_get_sources_by_ids(store):
    sid1 = store.insert_source(Source(content_path="a.pdf", media_type="application/pdf"))
    sid2 = store.insert_source(Source(content_path="b.pdf", media_type="application/pdf"))
    store.insert_source(Source(content_path="c.pdf", media_type="application/pdf"))

    result = store.get_sources_by_ids([sid1, sid2])
    assert len(result) == 2
    assert sid1 in result
    assert sid2 in result

    assert store.get_sources_by_ids([]) == {}


# ---------------------------------------------------------------------------
# Sessions CRUD
# ---------------------------------------------------------------------------


def test_insert_and_complete_session(store):
    session = Session(
        task_description="Extract from policy",
        task_type="extraction",
        agent_role=AgentRole.SUBAGENT,
        model_used="claude-sonnet-4-6",
    )
    session_id = store.insert_session(session)
    assert store.get_session(session_id).status == SessionStatus.RUNNING

    store.complete_session(session_id, status=SessionStatus.COMPLETED, result={"output": "done"})
    completed = store.get_session(session_id)
    assert completed.status == SessionStatus.COMPLETED
    assert completed.result == {"output": "done"}
    assert completed.completed_at is not None


# ---------------------------------------------------------------------------
# Extractions CRUD
# ---------------------------------------------------------------------------


def test_insert_and_validate_extraction(store):
    # Setup dependencies
    skill_id = store.insert_skill(Skill(domain="d", task_type="t", content="c", status=SkillStatus.ACTIVE))
    source_id = store.insert_source(Source(content_path="a.pdf", media_type="application/pdf"))
    session_id = store.insert_session(Session(
        task_description="test", task_type="test", agent_role=AgentRole.SUBAGENT,
    ))

    ext = Extraction(
        source_id=source_id, skill_id=skill_id, session_id=session_id,
        output={"policy_number": "XX-1234567"},
        confidence=0.95,
    )
    ext_id = store.insert_extraction(ext)
    fetched = store.get_extraction(ext_id)
    assert fetched.output == {"policy_number": "XX-1234567"}
    assert fetched.validation_status == ValidationStatus.PENDING

    store.update_validation(ext_id, status=ValidationStatus.VALIDATED, validated_by="human")
    validated = store.get_extraction(ext_id)
    assert validated.validation_status == ValidationStatus.VALIDATED
    assert validated.validated_by == "human"


def test_get_validated_extractions(store):
    skill_id = store.insert_skill(Skill(domain="d", task_type="t", content="c", status=SkillStatus.ACTIVE))
    source_id = store.insert_source(Source(content_path="a.pdf", media_type="application/pdf"))
    session_id = store.insert_session(Session(
        task_description="test", task_type="test", agent_role=AgentRole.SUBAGENT,
    ))

    for i in range(3):
        ext_id = store.insert_extraction(Extraction(
            source_id=source_id, skill_id=skill_id, session_id=session_id,
            output={"i": i},
        ))
        if i < 2:
            store.update_validation(ext_id, status=ValidationStatus.VALIDATED)

    validated = store.get_validated_extractions(skill_id)
    assert len(validated) == 2


# ---------------------------------------------------------------------------
# Feedback CRUD
# ---------------------------------------------------------------------------


def test_insert_and_aggregate_feedback(store):
    skill_id = store.insert_skill(Skill(domain="d", task_type="t", content="c", status=SkillStatus.ACTIVE))
    source_id = store.insert_source(Source(content_path="a.pdf", media_type="application/pdf"))
    session_id = store.insert_session(Session(
        task_description="test", task_type="test", agent_role=AgentRole.SUBAGENT,
    ))
    ext_id = store.insert_extraction(Extraction(
        source_id=source_id, skill_id=skill_id, session_id=session_id,
        output={"field": "value"},
    ))

    store.insert_feedback(Feedback(
        extraction_id=ext_id, session_id=session_id, skill_id=skill_id,
        correction={"field": {"before": "wrong", "after": "right"}},
        correction_type=CorrectionType.WRONG_VALUE,
        created_by="reviewer",
    ))
    store.insert_feedback(Feedback(
        extraction_id=ext_id, session_id=session_id, skill_id=skill_id,
        correction={"field": {"before": "wrong", "after": "right"}},
        correction_type=CorrectionType.WRONG_VALUE,
    ))
    store.insert_feedback(Feedback(
        extraction_id=ext_id, session_id=session_id, skill_id=skill_id,
        correction={"new_field": "added"},
        correction_type=CorrectionType.MISSING_FIELD,
    ))

    agg = store.aggregate_feedback(skill_id)
    assert len(agg) == 2
    assert agg[0] == ("wrong_value", 2)
    assert agg[1] == ("missing_field", 1)


# ---------------------------------------------------------------------------
# Rules CRUD
# ---------------------------------------------------------------------------


def test_rules_global_and_domain(store):
    store.insert_rule(Rule(scope=RuleScope.GLOBAL, content="Output valid JSON", priority=10))
    store.insert_rule(Rule(scope=RuleScope.GLOBAL, content="Never fabricate data", priority=5))
    store.insert_rule(Rule(scope=RuleScope.DOMAIN_SPECIFIC, domain="insurance", content="Use ISO dates", priority=3))
    store.insert_rule(Rule(scope=RuleScope.DOMAIN_SPECIFIC, domain="medical", content="HIPAA compliance", priority=1))

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
    store.insert_rule(Rule(scope=RuleScope.GLOBAL, content="Output valid JSON", priority=10))
    skill_id = store.insert_skill(Skill(
        domain="insurance", task_type="extraction",
        content="Extract policy numbers.\nFormat: XX-XXXXXXX",
        status=SkillStatus.ACTIVE,
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
# Mock provider for testing
# ---------------------------------------------------------------------------


class _MockProvider:
    """Mock provider that returns a fixed extraction."""

    def __init__(self, content: str = '{"policy_number": "XX-1234567", "effective_date": "2026-01-01"}',
                 input_tokens: int | None = None,
                 output_tokens: int | None = None,
                 model: str | None = None):
        self._content = content
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens
        self._model = model

    def complete(self, system: str, user: str) -> CompletionResult:
        return CompletionResult(
            content=self._content,
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
            model=self._model,
        )


_mock_provider = _MockProvider()


# ---------------------------------------------------------------------------
# Single-shot execution (run_single)
# ---------------------------------------------------------------------------


def test_run_single(store):
    skill_id = store.insert_skill(Skill(
        domain="insurance", task_type="extraction",
        content="Extract policy fields", status=SkillStatus.ACTIVE,
    ))
    source_id = store.insert_source(Source(
        content_path="/data/policy.pdf", media_type="application/pdf",
    ))

    extraction = run_single(
        store,
        skill_id=skill_id,
        source_id=source_id,
        provider=_mock_provider,
        model_name="mock",
    )
    assert extraction is not None
    assert "policy_number" in extraction.output["raw"]

    # Should have created 1 session
    sessions = store.list_sessions()
    assert len(sessions) == 1
    assert sessions[0].agent_role == AgentRole.SUBAGENT


def test_run_single_model_failure(store):
    skill_id = store.insert_skill(Skill(
        domain="d", task_type="t", content="c", status=SkillStatus.ACTIVE,
    ))
    source_id = store.insert_source(Source(
        content_path="a.pdf", media_type="application/pdf",
    ))

    class _FailingProvider:
        def complete(self, system: str, user: str) -> CompletionResult:
            raise RuntimeError("API error")

    result = run_single(
        store,
        skill_id=skill_id,
        source_id=source_id,
        provider=_FailingProvider(),
    )
    assert result is None

    # Session should be marked as failed
    sessions = store.list_sessions(status=SessionStatus.FAILED)
    assert len(sessions) == 1


# ---------------------------------------------------------------------------
# Built-in providers
# ---------------------------------------------------------------------------


def test_echo_provider():
    provider = EchoProvider()
    result = provider.complete("You are a helpful assistant.", "Extract policy numbers.")
    assert result.model == "echo"
    parsed = orjson.loads(result.content)
    assert parsed["model"] == "echo"
    assert "helpful assistant" in parsed["system_prompt"]
    assert "Extract policy" in parsed["user_message"]


def test_get_provider_echo():
    provider = get_provider("echo")
    result = provider.complete("sys", "user")
    assert isinstance(result, CompletionResult)
    parsed = orjson.loads(result.content)
    assert parsed["model"] == "echo"


def test_get_provider_local():
    """Factory returns OpenAICompatProvider for 'local'."""
    provider = get_provider("local", model_name="test-model", base_url="http://localhost:9999")
    assert isinstance(provider, OpenAICompatProvider)


def test_get_provider_unknown():
    with pytest.raises(ValueError, match="Unknown provider"):
        get_provider("nonexistent")


def test_run_single_with_echo_provider(store):
    """End-to-end: run with echo provider, verify context assembly in output."""
    store.insert_rule(Rule(scope=RuleScope.GLOBAL, content="Always output valid JSON"))
    skill_id = store.insert_skill(Skill(
        domain="legal", task_type="extraction",
        content="Extract party names from contracts.", status=SkillStatus.ACTIVE,
    ))
    source_id = store.insert_source(Source(
        content_path="/data/contract.pdf", media_type="application/pdf",
    ))

    echo = EchoProvider()
    extraction = run_single(
        store,
        skill_id=skill_id,
        source_id=source_id,
        provider=echo,
        domain="legal",
        model_name="echo",
    )
    assert extraction is not None

    # The echo provider output should contain the assembled context
    raw = extraction.output["raw"]
    parsed = orjson.loads(raw)
    assert "Always output valid JSON" in parsed["system_prompt"]
    assert "Extract party names" in parsed["system_prompt"]
    assert "contract.pdf" in parsed["user_message"]


# ---------------------------------------------------------------------------
# Provider populates token_usage and model_used
# ---------------------------------------------------------------------------


def test_provider_populates_token_usage(store):
    """Provider returning token counts populates session.token_usage."""
    skill_id = store.insert_skill(Skill(
        domain="d", task_type="t", content="c", status=SkillStatus.ACTIVE,
    ))
    source_id = store.insert_source(Source(
        content_path="a.pdf", media_type="application/pdf",
    ))

    token_provider = _MockProvider(
        content='{"result": "ok"}',
        input_tokens=150,
        output_tokens=42,
        model="test-model-v1",
    )

    run_single(
        store,
        skill_id=skill_id,
        source_id=source_id,
        provider=token_provider,
        model_name="fallback",
    )

    # Find the session
    sessions = store.list_sessions()
    assert len(sessions) == 1
    session = sessions[0]
    assert session.token_usage == {"input_tokens": 150, "output_tokens": 42}


def test_provider_populates_model_used(store):
    """session.model_used comes from CompletionResult.model, not caller string."""
    skill_id = store.insert_skill(Skill(
        domain="d", task_type="t", content="c", status=SkillStatus.ACTIVE,
    ))
    source_id = store.insert_source(Source(
        content_path="a.pdf", media_type="application/pdf",
    ))

    model_provider = _MockProvider(
        content='{"result": "ok"}',
        model="claude-3-5-sonnet-20241022",
    )

    run_single(
        store,
        skill_id=skill_id,
        source_id=source_id,
        provider=model_provider,
        model_name="anthropic",
    )

    sessions = store.list_sessions()
    assert len(sessions) == 1
    assert sessions[0].model_used == "claude-3-5-sonnet-20241022"


def test_openai_compat_provider_request_format(store):
    """Verify the HTTP request body structure for OpenAICompatProvider."""
    import unittest.mock as mock

    mock_response = mock.MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "hello"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        "model": "qwen2.5-coder-1.5b",
    }
    mock_response.raise_for_status = mock.MagicMock()

    provider = get_provider("local", model_name="qwen2.5-coder-1.5b", base_url="http://localhost:8080")

    # Patch the httpx client's post method
    with mock.patch.object(provider._client, "post", return_value=mock_response) as mock_post:
        result = provider.complete("system prompt", "user message")

    # Verify request format
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    body = call_kwargs.kwargs["json"] if "json" in call_kwargs.kwargs else call_kwargs[1]["json"]
    assert body["model"] == "qwen2.5-coder-1.5b"
    assert body["messages"][0] == {"role": "system", "content": "system prompt"}
    assert body["messages"][1] == {"role": "user", "content": "user message"}
    assert body["stream"] is False

    # Verify response parsing
    assert result.content == "hello"
    assert result.input_tokens == 10
    assert result.output_tokens == 5
    assert result.model == "qwen2.5-coder-1.5b"


# ---------------------------------------------------------------------------
# Preset integration (archetypes wired into execution)
# ---------------------------------------------------------------------------


def test_assemble_runner_context_with_preset(store):
    """Preset injects archetype system prompt into context assembly."""
    skill_id = store.insert_skill(Skill(
        domain="test", task_type="extraction",
        content="Test skill content.", status=SkillStatus.ACTIVE,
    ))
    source_id = store.insert_source(Source(
        content_path="/data/test.pdf", media_type="application/pdf",
    ))

    system_prompt, user_message = assemble_runner_context(
        store,
        skill_id=skill_id,
        source_ids=[source_id],
        domain="test",
        preset="careful-executor",
    )

    # Archetype content should appear in system prompt
    assert "Operating Principles" in system_prompt
    assert "Structural" in system_prompt
    # Skill content should still be there
    assert "Test skill content" in system_prompt
    # Source should be in user message
    assert "test.pdf" in user_message


def test_assemble_runner_context_without_preset(store):
    """Without preset, no archetype content in system prompt."""
    skill_id = store.insert_skill(Skill(
        domain="test", task_type="extraction",
        content="Test skill content.", status=SkillStatus.ACTIVE,
    ))

    system_prompt, _user_message = assemble_runner_context(
        store,
        skill_id=skill_id,
        source_ids=[],
        domain="test",
    )

    assert "Operating Principles" not in system_prompt
    assert "Test skill content" in system_prompt


def test_run_single_with_preset(store):
    """run_single with preset passes archetype context through to echo output."""
    skill_id = store.insert_skill(Skill(
        domain="test", task_type="extraction",
        content="Extract test data.", status=SkillStatus.ACTIVE,
    ))
    source_id = store.insert_source(Source(
        content_path="/data/test.pdf", media_type="application/pdf",
    ))

    echo = EchoProvider()
    extraction = run_single(
        store,
        skill_id=skill_id,
        source_id=source_id,
        provider=echo,
        domain="test",
        model_name="echo",
        preset="careful-executor",
    )
    assert extraction is not None

    raw = extraction.output["raw"]
    parsed = orjson.loads(raw)
    # Archetype fragments should be in the system prompt
    assert "Operating Principles" in parsed["system_prompt"]
    assert "structural-triad" in parsed["system_prompt"]
    # Skill content still present
    assert "Extract test data" in parsed["system_prompt"]


# ---------------------------------------------------------------------------
# CLI command tests (skill deprecate/activate, session show, skill --version)
# ---------------------------------------------------------------------------


def test_cli_skill_deprecate_activate(tmp_path):
    """CLI skill deprecate/activate change status end-to-end."""
    from freud_schema.cli import main
    db = str(tmp_path / "test.duckdb")
    main(["--db", db, "db", "init"])
    main(["--db", db, "skill", "add", "--domain", "d", "--task-type", "t",
          "--content", "c", "--status", "active"])
    # deprecate skill 1
    main(["--db", db, "skill", "deprecate", "1"])
    from freud_schema.db import connect
    from freud_schema.store import ExperimentStore
    store = ExperimentStore(connect(db))
    skill = store.get_skill(1)
    assert skill is not None
    assert skill.status == SkillStatus.DEPRECATED
    # activate it back
    main(["--db", db, "skill", "activate", "1"])
    store = ExperimentStore(connect(db))
    skill = store.get_skill(1)
    assert skill is not None
    assert skill.status == SkillStatus.ACTIVE


def test_cli_session_show(tmp_path, capsys):
    """CLI session show prints full session details."""
    from freud_schema.cli import main
    db = str(tmp_path / "test.duckdb")
    main(["--db", db, "db", "init"])
    main(["--db", db, "skill", "add", "--domain", "d", "--task-type", "t",
          "--content", "c", "--status", "active"])
    main(["--db", db, "source", "add", "--path", "a.pdf", "--media-type", "application/pdf"])
    main(["--db", db, "run", "--domain", "d", "--task-type", "t", "--model", "echo"])
    # now show the session created by the run
    main(["--db", db, "session", "show", "1"])
    out = capsys.readouterr().out
    assert "Session: 1" in out
    assert "Model:" in out
    assert "Status:" in out


def test_cli_skill_deprecate_nonexistent():
    """skill deprecate on nonexistent ID exits with error."""
    from freud_schema.cli import main
    with pytest.raises(SystemExit):
        main(["--db", ":memory:", "skill", "deprecate", "999"])


def test_cli_skill_activate_nonexistent():
    """skill activate on nonexistent ID exits with error."""
    from freud_schema.cli import main
    with pytest.raises(SystemExit):
        main(["--db", ":memory:", "skill", "activate", "999"])


def test_cli_session_show_nonexistent():
    """session show on nonexistent ID exits with error."""
    from freud_schema.cli import main
    with pytest.raises(SystemExit):
        main(["--db", ":memory:", "session", "show", "999"])


def test_skill_version_roundtrip(store):
    """Skills inserted with a specific version preserve it."""
    skill_id = store.insert_skill(Skill(
        domain="arxiv", task_type="extraction", version=2,
        content="v2 content", status=SkillStatus.ACTIVE,
    ))
    fetched = store.get_skill(skill_id)
    assert fetched.version == 2


def test_run_single_with_invalid_preset(store):
    """Invalid preset raises ValueError."""
    skill_id = store.insert_skill(Skill(
        domain="test", task_type="extraction",
        content="content", status=SkillStatus.ACTIVE,
    ))
    source_id = store.insert_source(Source(
        content_path="/data/test.pdf", media_type="application/pdf",
    ))

    echo = EchoProvider()
    with pytest.raises(ValueError, match="Unknown preset"):
        run_single(
            store,
            skill_id=skill_id,
            source_id=source_id,
            provider=echo,
            preset="nonexistent-preset",
        )
