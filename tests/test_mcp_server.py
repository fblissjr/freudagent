"""Tests for M16: the ops.py dispatch layer and the store-ops MCP server.

Three concerns, three test classes:

- TestOpsRoundTrip: ops.py functions round-trip against a :memory: store,
  proving the shared dispatch layer does what the CLI handlers did before
  this module existed.
- TestClassifyReadonly: the parser-level gate behind query() -- accepts
  SELECT/WITH...SELECT, rejects every write/DDL/multi-statement bypass
  attempt named in the implementation plan's risk table.
- TestGate / TestServerConstruction: the self-modification gate design
  (docs/implementation-plan.md Track H, Risk paragraph) -- rule_add/
  skill_add force non-compiling statuses regardless of input,
  proposal_approve's description carries the human-approval sentence, and
  no destructive tool (reset/ddl) is registered. These run behind
  pytest.importorskip("mcp") via the build_server fixture.
"""

from __future__ import annotations

import pytest

from freud_schema import ops
from freud_schema.mcp_server import classify_readonly
from freud_schema.tables import (
    CorrectionType,
    Extraction,
    Rule,
    RuleStatus,
    Session,
    Skill,
    SkillStatus,
    Source,
    TargetDimension,
)


# ---------------------------------------------------------------------------
# ops.py round trips
# ---------------------------------------------------------------------------


class TestOpsRoundTrip:
    def test_rule_add(self, store):
        result = ops.rule_add(store, name="no-retry", content="Stop retrying.")
        assert result["status"] == "active"
        rule = store.get_rule(result["rule_key"])
        assert rule.name == "no-retry"
        assert rule.status == RuleStatus.ACTIVE

    def test_skill_add(self, store):
        result = ops.skill_add(store, domain="d", task_type="t", content="c")
        assert result["status"] == "draft"
        skill = store.get_skill(result["skill_key"])
        assert skill.status == SkillStatus.DRAFT

    def test_source_add(self, store):
        result = ops.source_add(store, path="/f.pdf", media_type="application/pdf")
        source = store.get_source(result["source_key"])
        assert source.content_path == "/f.pdf"
        assert result["source_hash"] is None

    def test_source_add_with_hash_baseline(self, store, tmp_path):
        doc = tmp_path / "seed.txt"
        doc.write_text("hello")
        result = ops.source_add(
            store, path=str(doc), media_type="text/plain", hash_baseline=True)
        assert result["source_hash"] is not None
        source = store.get_source(result["source_key"])
        assert source.source_hash == result["source_hash"]

    def _make_extraction(self, store) -> str:
        skill_key = store.insert_skill(
            Skill(domain="d", task_type="t", content="c", status=SkillStatus.ACTIVE))
        source_key = store.insert_source(Source(content_path="/f", media_type="text/plain"))
        session_key = store.insert_session(Session(task_description="t"))
        return store.insert_extraction(Extraction(
            source_key=source_key, skill_key=skill_key, session_key=session_key,
            output={"a": 1}))

    def test_feedback_add(self, store):
        extraction_key = self._make_extraction(store)
        result = ops.feedback_add(
            store, extraction_key=extraction_key[:8],
            correction_type=CorrectionType.WRONG_VALUE,
            correction={"a": {"old": 1, "new": 2}})
        assert result["feedback_key"]
        fb = store.list_feedback()
        assert len(fb) == 1
        assert fb[0].extraction_key == extraction_key

    def test_feedback_add_unknown_extraction_raises(self, store):
        with pytest.raises(ValueError):
            ops.feedback_add(
                store, extraction_key="0" * 32,
                correction_type=CorrectionType.WRONG_VALUE, correction={})

    def test_extraction_validate_and_reject(self, store):
        key1 = self._make_extraction(store)
        result = ops.extraction_validate(store, key=key1[:8])
        assert result["validation_status"] == "validated"
        assert store.get_extraction(key1).validation_status.value == "validated"

    def test_finding_add_writes_load_run(self, store):
        from freud_schema.couch import seed_finding_types
        seed_finding_types(store)
        result = ops.finding_add(
            store, finding_type="retry_loop",
            summary="Bash: 3 identical-input call loop(s)")
        assert result["finding_key"]
        run = store.get_load_run(result["etl_run_id"])
        assert run is not None
        assert run.operation == "couch_llm"
        assert run.status.value == "completed"
        assert run.rows_written == 1

    def test_finding_add_unregistered_type_fails_closed(self, store):
        with pytest.raises(ValueError, match="not registered"):
            ops.finding_add(store, finding_type="nonexistent", summary="x")
        rows = store.con.execute(
            "SELECT status FROM meta_load_log WHERE operation = 'couch_llm'"
        ).fetchall()
        assert rows and rows[0][0] == "failed"

    def test_proposal_add_approve(self, store):
        added = ops.proposal_add(
            store, target=TargetDimension.DIM_RULE,
            natural_key={"name": "no-retry"}, content="Stop after two failures.")
        assert added["status"] == "pending"
        approved = ops.proposal_approve(
            store, key=added["proposal_key"][:8], reviewed_by="reviewer")
        assert approved["status"] == "approved"
        rule = store.get_rule(approved["resulting_dimension_key"])
        assert rule.status == RuleStatus.ACTIVE
        assert rule.content == "Stop after two failures."

    def test_proposal_add_reject(self, store):
        added = ops.proposal_add(
            store, target=TargetDimension.DIM_RULE,
            natural_key={"name": "other"}, content="x")
        rejected = ops.proposal_reject(store, key=added["proposal_key"])
        assert rejected["status"] == "rejected"
        assert store.list_rules() == []

    def test_compile_rules(self, store, tmp_path):
        store.insert_rule(Rule(name="r", content="Text.", status=RuleStatus.ACTIVE))
        result = ops.compile_rules(store, out_dir=tmp_path)
        assert result["written"] == ["r.md"]
        assert (tmp_path / "r.md").exists()

    def test_couch_run(self, store):
        result = ops.couch_run(store, include_filesystem=False)
        assert "etl_run_id" in result
        assert result["findings"] == 0

    def test_ingest_transcripts_delegates(self, store, tmp_path):
        empty_root = tmp_path / "projects"
        empty_root.mkdir()
        result = ops.ingest_transcripts(store, root=empty_root)
        assert result["sessions"] == 0
        assert result["rows_written"] == 0

    def test_ingest_events_delegates(self, store, tmp_path):
        import json
        root = tmp_path / "events"
        root.mkdir()
        (root / "s.jsonl").write_text(json.dumps(
            {"id": "e1", "type": "t", "timestamp": None,
             "actor": None, "payload": None}) + "\n")
        result = ops.ingest_events(store, root=root)
        assert result["streams"] == 1
        assert result["rows_written"] == 1


# ---------------------------------------------------------------------------
# classify_readonly: the parser-level gate behind query()
# ---------------------------------------------------------------------------


class TestClassifyReadonlyAccepts:
    def test_plain_select(self):
        classify_readonly("SELECT 1")

    def test_with_select(self):
        classify_readonly("WITH t AS (SELECT 1) SELECT * FROM t")


class TestClassifyReadonlyRejects:
    """Each bypass-attempt class gets its own test (implementation plan,
    M16 risk table: 'Read-only SQL classification bypassed via CTE/
    ATTACH/COPY/PRAGMA smuggling')."""

    def test_rejects_insert(self):
        with pytest.raises(ValueError):
            classify_readonly("INSERT INTO dim_rule (rule_key) VALUES ('x')")

    def test_rejects_update(self):
        with pytest.raises(ValueError):
            classify_readonly("UPDATE dim_rule SET name = 'x'")

    def test_rejects_delete(self):
        with pytest.raises(ValueError):
            classify_readonly("DELETE FROM dim_rule")

    def test_rejects_create_table(self):
        with pytest.raises(ValueError):
            classify_readonly("CREATE TABLE foo (a INTEGER)")

    def test_rejects_drop(self):
        with pytest.raises(ValueError):
            classify_readonly("DROP TABLE dim_rule")

    def test_rejects_attach(self):
        with pytest.raises(ValueError):
            classify_readonly("ATTACH 'evil.db' AS evil")

    def test_rejects_copy(self):
        with pytest.raises(ValueError):
            classify_readonly("COPY (SELECT 1) TO 'out.csv'")

    def test_rejects_pragma(self):
        with pytest.raises(ValueError):
            classify_readonly("PRAGMA memory_limit='1GB'")

    def test_rejects_export_database(self):
        with pytest.raises(ValueError):
            classify_readonly("EXPORT DATABASE 'out_dir'")

    def test_rejects_multi_statement_smuggling(self):
        """The bypass attempt named explicitly in the plan: a SELECT that
        looks innocent followed by a write, joined by a semicolon."""
        with pytest.raises(ValueError):
            classify_readonly("SELECT 1; DROP TABLE dim_rule")

    def test_rejects_unparseable_sql(self):
        with pytest.raises(ValueError):
            classify_readonly("SELECT 1 FROM (")


# ---------------------------------------------------------------------------
# Gate design: self-modification without human approval
# ---------------------------------------------------------------------------


@pytest.fixture
def build_server():
    """The FastMCP server factory, behind an mcp-extra skip -- server
    construction and tool-wrapper tests only run when the mcp extra is
    installed (uv sync --extra dev covers CI; see pyproject.toml)."""
    pytest.importorskip("mcp")
    from freud_schema.mcp_server import build_server as _build_server
    return _build_server


def _tool_fn(server, name: str):
    tool = server._tool_manager.get_tool(name)
    assert tool is not None, f"no tool registered named {name!r}"
    return tool.fn


class TestGate:
    def test_rule_add_forces_inactive_even_when_active_requested(self, store, build_server):
        server = build_server(store)
        rule_add = _tool_fn(server, "rule_add")
        result = rule_add(name="r", content="c", status="active")
        assert result["status"] == "inactive"
        assert store.get_rule(result["rule_key"]).status == RuleStatus.INACTIVE

    def test_skill_add_forces_draft_even_when_active_requested(self, store, build_server):
        server = build_server(store)
        skill_add = _tool_fn(server, "skill_add")
        result = skill_add(domain="d", task_type="t", content="c", status="active")
        assert result["status"] == "draft"
        assert store.get_skill(result["skill_key"]).status == SkillStatus.DRAFT

    def test_gated_rule_does_not_compile(self, store, build_server, tmp_path):
        server = build_server(store)
        rule_add = _tool_fn(server, "rule_add")
        compile_tool = _tool_fn(server, "compile")
        rule_add(name="r", content="c", status="active")
        result = compile_tool(out_dir=str(tmp_path))
        assert result["written"] == []
        assert list(tmp_path.iterdir()) == []

    def test_full_flywheel_turn_through_tools_only(self, store, build_server, tmp_path):
        """rule_add (stays inactive) -> proposal_add -> proposal_approve
        -> compile writes the file. No raw store access, tools only."""
        server = build_server(store)
        rule_add = _tool_fn(server, "rule_add")
        proposal_add = _tool_fn(server, "proposal_add")
        proposal_approve = _tool_fn(server, "proposal_approve")
        compile_tool = _tool_fn(server, "compile")

        created = rule_add(name="no-retry-loops", content="Stop after two failures.")
        assert created["status"] == "inactive"

        proposal = proposal_add(
            target="dim_rule", natural_key={"name": "no-retry-loops"},
            content="Stop after two identical failing tool calls.")
        assert proposal["status"] == "pending"

        approved = proposal_approve(key=proposal["proposal_key"], reviewed_by="reviewer")
        assert approved["status"] == "approved"

        compiled = compile_tool(out_dir=str(tmp_path))
        assert compiled["written"] == ["no-retry-loops.md"]
        assert (tmp_path / "no-retry-loops.md").exists()

    def test_proposal_approve_requires_reviewed_by_argument(self, store, build_server):
        """reviewed_by has no default -- calling without it is a TypeError
        at the Python level (FastMCP would reject it as a missing required
        field before it ever reached this function)."""
        server = build_server(store)
        proposal_approve = _tool_fn(server, "proposal_approve")
        with pytest.raises(TypeError):
            proposal_approve(key="anything")


# ---------------------------------------------------------------------------
# Server construction
# ---------------------------------------------------------------------------


class TestServerConstruction:
    def test_registers_expected_tool_names(self, store, build_server):
        server = build_server(store)
        names = {t.name for t in server._tool_manager.list_tools()}
        expected = {
            "query", "rule_add", "skill_add", "source_add", "feedback_add",
            "finding_add", "extraction_validate", "extraction_reject",
            "proposal_add", "proposal_reject", "proposal_approve",
            "couch_run", "compile", "ingest_transcripts", "ingest_events",
        }
        assert expected <= names

    def test_proposal_approve_description_is_the_human_approval_gate(self, store, build_server):
        server = build_server(store)
        tool = server._tool_manager.get_tool("proposal_approve")
        assert tool.description.startswith(
            "HUMAN APPROVAL GATE — never allowlist this tool; "
            "every call must surface the permission prompt."
        )

    def test_no_destructive_tools_registered(self, store, build_server):
        server = build_server(store)
        names = {t.name for t in server._tool_manager.list_tools()}
        for name in names:
            lowered = name.lower()
            assert "reset" not in lowered
            assert "ddl" not in lowered

    def test_ingest_events_tool_round_trip(self, store, build_server, tmp_path):
        import json
        root = tmp_path / "events"
        root.mkdir()
        (root / "s.jsonl").write_text(json.dumps(
            {"id": "e1", "type": "t", "timestamp": None,
             "actor": None, "payload": None}) + "\n")
        server = build_server(store)
        ingest_events = _tool_fn(server, "ingest_events")
        result = ingest_events(root=str(root))
        assert result["streams"] == 1
        assert result["rows_written"] == 1
        assert store.get_event_type("t") is not None


class TestClassifyReadonlyPragmaHole:
    """Regression: DuckDB types read-only PRAGMAs (and SHOW/DESCRIBE) as
    SELECT via pragma-table-function rewriting, so parser type alone let
    PRAGMA through. The first-token allowlist closes it."""

    def test_pragma_database_list_rejected(self):
        with pytest.raises(ValueError, match="not allowed"):
            classify_readonly("PRAGMA database_list")

    def test_pragma_with_leading_comment_rejected(self):
        with pytest.raises(ValueError, match="not allowed"):
            classify_readonly("-- harmless comment\nPRAGMA database_list")

    def test_call_rejected(self):
        with pytest.raises(ValueError):
            classify_readonly("CALL pragma_database_list()")

    def test_set_rejected(self):
        with pytest.raises(ValueError):
            classify_readonly("SET memory_limit='1GB'")

    def test_show_tables_allowed(self):
        classify_readonly("SHOW TABLES")

    def test_describe_allowed(self):
        classify_readonly("DESCRIBE dim_rule")

    def test_from_first_syntax_allowed(self):
        classify_readonly("FROM dim_rule SELECT rule_key")

    def test_parenthesized_select_allowed(self):
        classify_readonly("(SELECT 1)")
