"""Store-layer tests for v0.17 semantics.

What's new versus the CRUD tests in test_experiment.py:
- SCD Type 2 evolution on dimensions (close current row, insert new).
- Registry dimensions with idempotent registration.
- finding_type registry validation (open vocabulary, store-enforced).
- Idempotent message/tool_use inserts -- the primitive Phase 1's
  re-ingest guarantee is built on.
- meta_load_log run lifecycle.
"""

import pytest

from freud_schema.keys import dimension_key
from freud_schema.tables import (
    FacetType,
    Finding,
    FindingType,
    Message,
    MessageRole,
    Project,
    Proposal,
    ProposalStatus,
    RecordSource,
    Rule,
    Session,
    SessionStatus,
    Skill,
    SkillStatus,
    Source,
    TargetDimension,
    ToolUse,
)


def _skill(**over) -> Skill:
    base = dict(domain="freud", task_type="extraction",
                content="Extract things.", status=SkillStatus.ACTIVE)
    base.update(over)
    return Skill(**base)


class TestScd2Skills:
    def test_insert_returns_entity_key(self, store):
        key = store.insert_skill(_skill())
        assert key == dimension_key("freud", "extraction")

    def test_new_version_closes_prior_row(self, store):
        key = store.insert_skill(_skill())
        store.insert_skill(_skill(version=2, content="Extract better."))
        rows = store.con.execute(
            "SELECT version, is_current, effective_to FROM dim_skill "
            "WHERE skill_key = ? ORDER BY version", [key]).fetchall()
        assert len(rows) == 2
        v1, v2 = rows
        assert v1[1] is False and v1[2] is not None  # closed
        assert v2[1] is True and v2[2] is None       # open

    def test_get_skill_returns_current(self, store):
        key = store.insert_skill(_skill())
        store.insert_skill(_skill(version=2, content="v2"))
        skill = store.get_skill(key)
        assert skill.version == 2
        assert skill.is_current is True

    def test_get_skill_by_version(self, store):
        key = store.insert_skill(_skill())
        store.insert_skill(_skill(version=2, content="v2"))
        old = store.get_skill(key, version=1)
        assert old.version == 1
        assert old.is_current is False

    def test_version_must_be_monotonic(self, store):
        store.insert_skill(_skill(version=2))
        with pytest.raises(ValueError, match="version"):
            store.insert_skill(_skill(version=2))
        with pytest.raises(ValueError, match="version"):
            store.insert_skill(_skill(version=1))

    def test_deprecate_is_scd2_evolution(self, store):
        key = store.insert_skill(_skill())
        store.deprecate_skill(key)
        current = store.get_skill(key)
        assert current.status == SkillStatus.DEPRECATED
        assert current.version == 1  # status change, not a version bump
        history = store.con.execute(
            "SELECT COUNT(*) FROM dim_skill WHERE skill_key = ?", [key]).fetchone()
        assert history[0] == 2  # closed active row + current deprecated row

    def test_get_active_skill_uses_current_row(self, store):
        store.insert_skill(_skill())
        found = store.get_active_skill("freud", "extraction")
        assert found is not None
        store.deprecate_skill(found.skill_key)
        assert store.get_active_skill("freud", "extraction") is None

    def test_list_skills_defaults_to_current_only(self, store):
        store.insert_skill(_skill())
        store.insert_skill(_skill(version=2))
        assert len(store.list_skills(domain="freud")) == 1
        assert len(store.list_skills(domain="freud", include_history=True)) == 2


class TestScd2SourcesAndRules:
    def test_source_readd_identical_is_noop(self, store):
        s = Source(content_path="/data/a.pdf", media_type="application/pdf")
        key1 = store.insert_source(s)
        key2 = store.insert_source(s)
        assert key1 == key2
        count = store.con.execute(
            "SELECT COUNT(*) FROM dim_source WHERE source_key = ?", [key1]).fetchone()
        assert count[0] == 1

    def test_source_readd_changed_evolves(self, store):
        key = store.insert_source(
            Source(content_path="/data/a.pdf", media_type="application/pdf"))
        store.insert_source(
            Source(content_path="/data/a.pdf", media_type="application/pdf",
                   source_hash="abc123"))
        rows = store.con.execute(
            "SELECT is_current FROM dim_source WHERE source_key = ? "
            "ORDER BY effective_from", [key]).fetchall()
        assert len(rows) == 2
        current = store.get_source(key)
        assert current.source_hash == "abc123"

    def test_rule_keyed_by_name_and_evolves(self, store):
        key = store.insert_rule(Rule(name="no-emoji", content="No emojis."))
        assert key == dimension_key("no-emoji")
        store.insert_rule(Rule(name="no-emoji", content="Absolutely no emojis."))
        rows = store.con.execute(
            "SELECT COUNT(*) FROM dim_rule WHERE rule_key = ?", [key]).fetchone()
        assert rows[0] == 2
        active = store.get_rules()
        assert len(active) == 1
        assert active[0].content == "Absolutely no emojis."


class TestRegistries:
    def test_ensure_project_idempotent(self, store):
        p = Project(project_path="/repo/freudagent", project_name="freudagent")
        key1 = store.ensure_project(p)
        key2 = store.ensure_project(p)
        assert key1 == key2 == dimension_key("/repo/freudagent")
        count = store.con.execute("SELECT COUNT(*) FROM dim_project").fetchone()
        assert count[0] == 1

    def test_register_facet_type_versions_add_rows(self, store):
        k1 = store.register_facet_type(FacetType(facet_id="session_purpose"))
        k2 = store.register_facet_type(
            FacetType(facet_id="session_purpose", prompt_version=2))
        assert k1 != k2
        # Re-registering the same version is a no-op
        assert store.register_facet_type(
            FacetType(facet_id="session_purpose")) == k1
        count = store.con.execute("SELECT COUNT(*) FROM dim_facet_type").fetchone()
        assert count[0] == 2

    def test_register_finding_type(self, store):
        key = store.register_finding_type(
            FindingType(finding_type="retry_loop",
                        description="Same tool, similar args, repeated"))
        assert key == dimension_key("retry_loop")
        assert store.register_finding_type(
            FindingType(finding_type="retry_loop")) == key


class TestFindingsRegistryValidation:
    def test_unregistered_finding_type_raises(self, store):
        with pytest.raises(ValueError, match="not registered"):
            store.insert_finding(Finding(
                finding_type="unregistered_thing", summary="s"))

    def test_registered_finding_type_inserts(self, store):
        store.register_finding_type(FindingType(finding_type="retry_loop"))
        key = store.insert_finding(Finding(
            finding_type="retry_loop", summary="Bash retried 5x",
            evidence_session_keys=["abc"], occurrence_count=5))
        found = store.get_finding(key)
        assert found.finding_type == "retry_loop"
        assert found.finding_type_key == dimension_key("retry_loop")
        assert found.evidence_session_keys == ["abc"]


class TestIdempotentIngestPrimitives:
    def _session_key(self, store) -> str:
        return store.insert_session(Session(
            native_session_id="cc-uuid-1",
            record_source=RecordSource.TRANSCRIPT_INGEST,
        ))

    def test_message_insert_skips_duplicates(self, store):
        skey = self._session_key(store)
        msg = Message(session_key=skey, role=MessageRole.USER,
                      entry_uuid="e1", content_text="hello")
        k1 = store.insert_message(msg)
        k2 = store.insert_message(msg)
        assert k1 == k2 == dimension_key(skey, "e1")
        count = store.con.execute("SELECT COUNT(*) FROM fact_message").fetchone()
        assert count[0] == 1

    def test_tool_use_insert_skips_duplicates(self, store):
        skey = self._session_key(store)
        tu = ToolUse(session_key=skey, tool_use_id="toolu_1", tool_name="Bash",
                     tool_input={"command": "ls"})
        k1 = store.insert_tool_use(tu)
        k2 = store.insert_tool_use(tu)
        assert k1 == k2 == dimension_key(skey, "toolu_1")
        count = store.con.execute("SELECT COUNT(*) FROM fact_tool_use").fetchone()
        assert count[0] == 1

    def test_session_key_is_deterministic(self, store):
        skey = self._session_key(store)
        assert skey == dimension_key(
            RecordSource.TRANSCRIPT_INGEST.value, "cc-uuid-1")


class TestProposalsAndLoadLog:
    def test_proposal_lifecycle_fields(self, store):
        key = store.insert_proposal(Proposal(
            target_dimension=TargetDimension.DIM_RULE,
            target_natural_key={"name": "no-emoji"},
            proposed_content="No emojis, ever.",
            evidence_finding_keys=["f1", "f2"]))
        p = store.get_proposal(key)
        assert p.status == ProposalStatus.PENDING
        assert p.evidence_finding_keys == ["f1", "f2"]
        pending = store.list_proposals(status=ProposalStatus.PENDING)
        assert len(pending) == 1

    def test_load_run_lifecycle(self, store):
        run_id = store.start_load_run(
            "ingest_transcripts", record_source=RecordSource.TRANSCRIPT_INGEST)
        store.complete_load_run(
            run_id, status=SessionStatus.COMPLETED,
            rows_read=100, rows_written=90, rows_skipped=10)
        run = store.get_load_run(run_id)
        assert run.status == SessionStatus.COMPLETED
        assert run.rows_written == 90
        assert run.rows_skipped == 10
        assert run.completed_at is not None


class TestPrefixResolution:
    def test_resolve_key_prefix(self, store):
        key = store.insert_skill(_skill())
        assert store.resolve_key("dim_skill", key[:8]) == key

    def test_resolve_key_ambiguous_raises(self, store):
        store.insert_skill(_skill())
        store.insert_skill(_skill(task_type="translation"))
        with pytest.raises(ValueError, match="[Aa]mbiguous"):
            store.resolve_key("dim_skill", "")

    def test_resolve_key_missing_raises(self, store):
        with pytest.raises(ValueError, match="[Nn]o .*match"):
            store.resolve_key("dim_skill", "ffffffff")
