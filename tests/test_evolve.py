"""Tests for the evolve stage (Phase 3): proposal lifecycle + rollback.

Approval is the one human atom in the flywheel (flywheel atom 1.3.2):
it creates the new SCD-2 dimension version and records which findings
justified it. Rollback is the symmetric operation: flip is_current back,
no destructive undo.
"""

import pytest

from freud_schema.tables import (
    Proposal,
    ProposalStatus,
    Rule,
    RuleStatus,
    Skill,
    SkillOrigin,
    SkillStatus,
    TargetDimension,
)


def _rule_proposal(**over) -> Proposal:
    base = dict(
        target_dimension=TargetDimension.DIM_RULE,
        target_natural_key={"name": "no-retry-loops", "priority": 5},
        proposed_content="Stop after two identical failing tool calls; change approach.",
        evidence_finding_keys=["f-abc", "f-def"],
    )
    base.update(over)
    return Proposal(**base)


class TestApproveRuleProposal:
    def test_approve_creates_rule(self, store):
        pkey = store.insert_proposal(_rule_proposal())
        rule_key = store.approve_proposal(pkey, reviewed_by="fred")
        rule = store.get_rule(rule_key)
        assert rule is not None
        assert rule.name == "no-retry-loops"
        assert rule.priority == 5
        assert rule.status == RuleStatus.ACTIVE
        assert "identical failing" in rule.content

    def test_approve_records_outcome(self, store):
        pkey = store.insert_proposal(_rule_proposal())
        rule_key = store.approve_proposal(pkey, reviewed_by="fred")
        p = store.get_proposal(pkey)
        assert p.status == ProposalStatus.APPROVED
        assert p.resulting_dimension_key == rule_key
        assert p.reviewed_by == "fred"
        assert p.reviewed_at is not None

    def test_approve_evolves_existing_rule(self, store):
        store.insert_rule(Rule(name="no-retry-loops", content="Old text."))
        pkey = store.insert_proposal(_rule_proposal())
        rule_key = store.approve_proposal(pkey)
        history = store.con.execute(
            "SELECT COUNT(*) FROM dim_rule WHERE rule_key = ?", [rule_key]).fetchone()
        assert history[0] == 2  # old row closed, new row current
        assert store.get_rule(rule_key).content.startswith("Stop after")

    def test_approve_requires_pending(self, store):
        pkey = store.insert_proposal(_rule_proposal())
        store.approve_proposal(pkey)
        with pytest.raises(ValueError, match="pending"):
            store.approve_proposal(pkey)

    def test_approve_missing_proposal_raises(self, store):
        with pytest.raises(ValueError, match="not found"):
            store.approve_proposal("0" * 32)

    def test_rule_proposal_requires_name(self, store):
        pkey = store.insert_proposal(_rule_proposal(target_natural_key={}))
        with pytest.raises(ValueError, match="name"):
            store.approve_proposal(pkey)


class TestApproveSkillProposal:
    def test_approve_bumps_skill_version(self, store):
        store.insert_skill(Skill(domain="freud", task_type="extraction",
                                 content="v1", status=SkillStatus.ACTIVE))
        pkey = store.insert_proposal(Proposal(
            target_dimension=TargetDimension.DIM_SKILL,
            target_natural_key={"domain": "freud", "task_type": "extraction"},
            proposed_content="v2: extract with more care",
            evidence_finding_keys=["f-1"]))
        skill_key = store.approve_proposal(pkey)
        skill = store.get_skill(skill_key)
        assert skill.version == 2
        assert skill.status == SkillStatus.ACTIVE
        assert skill.origin == SkillOrigin.DATA_DERIVED
        old = store.get_skill(skill_key, version=1)
        assert old.is_current is False

    def test_approve_creates_new_skill_entity(self, store):
        pkey = store.insert_proposal(Proposal(
            target_dimension=TargetDimension.DIM_SKILL,
            target_natural_key={"domain": "taxes", "task_type": "extraction"},
            proposed_content="Extract 1099 fields"))
        skill_key = store.approve_proposal(pkey)
        assert store.get_skill(skill_key).version == 1


class TestReject:
    def test_reject_changes_nothing_downstream(self, store):
        pkey = store.insert_proposal(_rule_proposal())
        store.reject_proposal(pkey, reviewed_by="fred")
        p = store.get_proposal(pkey)
        assert p.status == ProposalStatus.REJECTED
        assert p.resulting_dimension_key is None
        assert store.list_rules() == []

    def test_reject_requires_pending(self, store):
        pkey = store.insert_proposal(_rule_proposal())
        store.reject_proposal(pkey)
        with pytest.raises(ValueError, match="pending"):
            store.reject_proposal(pkey)


class TestRollback:
    def test_rollback_reopens_prior_version(self, store):
        key = store.insert_rule(Rule(name="r", content="v1 text"))
        store.insert_rule(Rule(name="r", content="v2 text"))
        assert store.get_rule(key).content == "v2 text"
        store.rollback_dimension("dim_rule", key)
        current = store.get_rule(key)
        assert current.content == "v1 text"
        assert current.is_current is True
        assert current.effective_to is None
        open_rows = store.con.execute(
            "SELECT COUNT(*) FROM dim_rule WHERE rule_key = ? AND is_current",
            [key]).fetchone()
        assert open_rows[0] == 1

    def test_rollback_without_history_raises(self, store):
        key = store.insert_rule(Rule(name="only", content="v1"))
        with pytest.raises(ValueError, match="prior"):
            store.rollback_dimension("dim_rule", key)

    def test_rollback_rejects_non_scd2_table(self, store):
        with pytest.raises(ValueError, match="SCD-2"):
            store.rollback_dimension("dim_project", "x")
