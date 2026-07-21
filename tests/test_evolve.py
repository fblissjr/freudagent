"""Tests for the evolve stage (Phase 3): proposal lifecycle + rollback.

Approval is the one step only a person can do (flywheel step 1.3.2):
it creates the new SCD-2 dimension version and records which findings
justified it. Rollback is the symmetric operation: flip is_current back,
no destructive undo.
"""

import pytest

from freud_schema import ops
from freud_schema.couch import seed_finding_types
from freud_schema.tables import (
    Finding,
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
        rule_key = store.approve_proposal(pkey, reviewed_by="reviewer")
        rule = store.get_rule(rule_key)
        assert rule is not None
        assert rule.name == "no-retry-loops"
        assert rule.priority == 5
        assert rule.status == RuleStatus.ACTIVE
        assert "identical failing" in rule.content

    def test_approve_records_outcome(self, store):
        pkey = store.insert_proposal(_rule_proposal())
        rule_key = store.approve_proposal(pkey, reviewed_by="reviewer")
        p = store.get_proposal(pkey)
        assert p.status == ProposalStatus.APPROVED
        assert p.resulting_dimension_key == rule_key
        assert p.reviewed_by == "reviewer"
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
        store.reject_proposal(pkey, reviewed_by="reviewer")
        p = store.get_proposal(pkey)
        assert p.status == ProposalStatus.REJECTED
        assert p.resulting_dimension_key is None
        assert store.list_rules() == []

    def test_reject_records_why_not_only_who(self, store):
        """Rejection rate is a headline health measure; the reason is the part
        that makes it actionable.

        Without notes you can see that 3 of 20 proposals were rejected and have
        no way to tell whether the gate caught a real problem or someone
        objected to the wording. A rate with no content cannot distinguish a
        working gate from a picky one.
        """
        pkey = store.insert_proposal(_rule_proposal())
        store.reject_proposal(
            pkey, reviewed_by="reviewer",
            review_notes="evidence is three sessions from one project",
        )
        p = store.get_proposal(pkey)
        assert p.status == ProposalStatus.REJECTED
        assert p.review_notes == "evidence is three sessions from one project"

    def test_reject_notes_are_optional(self, store):
        pkey = store.insert_proposal(_rule_proposal())
        store.reject_proposal(pkey, reviewed_by="reviewer")
        assert store.get_proposal(pkey).review_notes is None

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


class TestProposalAddEvidenceResolution:
    """ops.proposal_add must resolve --evidence finding keys/prefixes to
    their full 32-char keys before writing the proposal (bug: couch list
    and the compiled provenance footer both truncate to finding_key[:8],
    so an unresolved 8-char prefix silently records a broken reference
    that renders identically to a valid one)."""

    def _rule_kwargs(self, **evidence_kwargs) -> dict:
        return dict(
            target=TargetDimension.DIM_RULE,
            natural_key={"name": "no-retry-loops"},
            content="Stop after two identical failing tool calls.",
            **evidence_kwargs,
        )

    def test_full_key_round_trips_unchanged(self, store):
        seed_finding_types(store)
        finding = ops.finding_add(store, finding_type="retry_loop", summary="s")
        full_key = finding["finding_key"]
        assert len(full_key) == 32

        added = ops.proposal_add(store, **self._rule_kwargs(evidence=[full_key]))
        p = store.get_proposal(added["proposal_key"])
        assert p.evidence_finding_keys == [full_key]

    def test_prefix_resolves_to_stored_full_key(self, store):
        seed_finding_types(store)
        finding = ops.finding_add(store, finding_type="retry_loop", summary="s")
        full_key = finding["finding_key"]
        prefix = full_key[:8]
        assert prefix != full_key

        added = ops.proposal_add(store, **self._rule_kwargs(evidence=[prefix]))
        p = store.get_proposal(added["proposal_key"])
        assert p.evidence_finding_keys == [full_key]
        assert len(p.evidence_finding_keys[0]) == 32

    def test_nonexistent_evidence_key_raises_and_writes_nothing(self, store):
        with pytest.raises(ValueError):
            ops.proposal_add(store, **self._rule_kwargs(evidence=["0" * 32]))
        assert store.list_proposals() == []

    def test_ambiguous_prefix_raises_and_writes_nothing(self, store):
        seed_finding_types(store)
        # Insert findings with a fixed finding_type/summary and only the
        # etl_run_id salt varying, until two resulting finding_keys share
        # a 1-char prefix. finding_key = dimension_key(finding_type,
        # scope, project_key, summary, etl_run_id) is a sha256/32 hex
        # digest, so its leading character has only 16 possible values --
        # by the pigeonhole principle, 17 distinct salts are guaranteed to
        # produce a collision. This is a deterministic property of
        # keys.dimension_key, not luck: the same 20 salts produce the
        # same keys and the same collision on every run.
        seen: dict[str, str] = {}
        collision_prefix = None
        for i in range(20):
            key = store.insert_finding(Finding(
                finding_type="retry_loop", summary="collision probe",
                etl_run_id=f"collision-salt-{i}"))
            prefix = key[0]
            if prefix in seen:
                collision_prefix = prefix
                break
            seen[prefix] = key
        assert collision_prefix is not None, (
            "no 1-char prefix collision in 20 tries -- pigeonhole guarantee violated")

        with pytest.raises(ValueError, match="Ambiguous"):
            ops.proposal_add(store, **self._rule_kwargs(evidence=[collision_prefix]))
        assert store.list_proposals() == []

    def test_evidence_none_unchanged(self, store):
        added = ops.proposal_add(store, **self._rule_kwargs(evidence=None))
        p = store.get_proposal(added["proposal_key"])
        assert p.evidence_finding_keys is None

    def test_evidence_empty_list_unchanged(self, store):
        added = ops.proposal_add(store, **self._rule_kwargs(evidence=[]))
        p = store.get_proposal(added["proposal_key"])
        assert p.evidence_finding_keys == []
