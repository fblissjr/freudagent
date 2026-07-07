"""Tests for the materialize stage (Phase 3): the compiler (the ego).

Contract: .claude/ files are build output. Every compiled file carries a
do-not-edit header, a source line naming the dimension row, and a
provenance footer naming the approving proposal and its findings. The
privacy gate is fail-closed: a file containing a home path or the OS
username is not written, period. Rollback = flip is_current + recompile,
so recompilation must also REMOVE managed files whose rules went away --
without ever touching unmanaged files.

The planted leak strings below are test fixtures for the gate itself.
"""

import getpass

import duckdb
import pytest

from freud_schema.materialize import COMPILED_MARKER, compile_rules
from freud_schema.store import ExperimentStore
from freud_schema.tables import Proposal, Rule, RuleStatus, TargetDimension


@pytest.fixture
def store():
    with ExperimentStore(duckdb.connect(":memory:")) as s:
        yield s


def _approve_rule(store, name="no-retry-loops",
                  content="Stop after two identical failing tool calls.",
                  evidence=("f-abc123", "f-def456")) -> str:
    pkey = store.insert_proposal(Proposal(
        target_dimension=TargetDimension.DIM_RULE,
        target_natural_key={"name": name},
        proposed_content=content,
        evidence_finding_keys=list(evidence)))
    store.approve_proposal(pkey, reviewed_by="fred")
    return pkey


class TestCompile:
    def test_writes_rule_file_with_header_and_provenance(self, store, tmp_path):
        pkey = _approve_rule(store)
        result = compile_rules(store, tmp_path)
        assert result["written"] == ["no-retry-loops.md"]
        body = (tmp_path / "no-retry-loops.md").read_text()
        assert body.startswith(COMPILED_MARKER)
        assert "do not edit" in body
        assert "dim_rule" in body
        assert "Stop after two identical failing tool calls." in body
        assert pkey[:8] in body          # approving proposal
        assert "f-abc123"[:8] in body    # evidence finding keys

    def test_hand_authored_rule_compiles_without_provenance(self, store, tmp_path):
        store.insert_rule(Rule(name="hand-rule", content="Handwritten."))
        compile_rules(store, tmp_path)
        body = (tmp_path / "hand-rule.md").read_text()
        assert body.startswith(COMPILED_MARKER)
        assert "provenance" not in body

    def test_inactive_rules_not_written(self, store, tmp_path):
        store.insert_rule(Rule(name="off", content="x", status=RuleStatus.INACTIVE))
        result = compile_rules(store, tmp_path)
        assert result["written"] == []
        assert not (tmp_path / "off.md").exists()

    def test_recompile_removes_managed_file_for_deactivated_rule(self, store, tmp_path):
        store.insert_rule(Rule(name="temp-rule", content="x"))
        compile_rules(store, tmp_path)
        assert (tmp_path / "temp-rule.md").exists()
        store.insert_rule(Rule(name="temp-rule", content="x",
                               status=RuleStatus.INACTIVE))
        result = compile_rules(store, tmp_path)
        assert result["removed"] == ["temp-rule.md"]
        assert not (tmp_path / "temp-rule.md").exists()

    def test_unmanaged_files_never_touched(self, store, tmp_path):
        (tmp_path / "hand-written.md").write_text("# Mine\nDo not delete.")
        _approve_rule(store)
        result = compile_rules(store, tmp_path)
        assert (tmp_path / "hand-written.md").read_text() == "# Mine\nDo not delete."
        assert "hand-written.md" not in result["removed"]

    def test_rollback_then_recompile_restores_old_content(self, store, tmp_path):
        key = store.insert_rule(Rule(name="r", content="v1 text"))
        store.insert_rule(Rule(name="r", content="v2 text"))
        compile_rules(store, tmp_path)
        assert "v2 text" in (tmp_path / "r.md").read_text()
        store.rollback_dimension("dim_rule", key)
        compile_rules(store, tmp_path)
        assert "v1 text" in (tmp_path / "r.md").read_text()

    def test_deterministic_output(self, store, tmp_path):
        _approve_rule(store)
        compile_rules(store, tmp_path)
        first = (tmp_path / "no-retry-loops.md").read_text()
        compile_rules(store, tmp_path)
        assert (tmp_path / "no-retry-loops.md").read_text() == first


class TestPrivacyGate:
    def test_home_path_blocks_file(self, store, tmp_path):
        _approve_rule(store, name="leaky",
                      content="Read /Users/someone/secrets before acting.")  # path-privacy: ignore
        result = compile_rules(store, tmp_path)
        assert not (tmp_path / "leaky.md").exists()
        assert len(result["blocked"]) == 1
        assert result["blocked"][0]["file"] == "leaky.md"

    def test_username_blocks_file(self, store, tmp_path):
        _approve_rule(store, name="leaky-user",
                      content=f"Ask {getpass.getuser()} before deleting.")
        result = compile_rules(store, tmp_path)
        assert not (tmp_path / "leaky-user.md").exists()
        assert len(result["blocked"]) == 1

    def test_blocked_file_is_not_removed_if_previously_compiled(self, store, tmp_path):
        """Fail-closed means don't propagate the leak AND don't destroy
        the last good compile."""
        key = store.insert_rule(Rule(name="r", content="clean v1"))
        compile_rules(store, tmp_path)
        store.insert_rule(Rule(name="r", content="dirty /home/someone v2"))  # path-privacy: ignore
        result = compile_rules(store, tmp_path)
        assert len(result["blocked"]) == 1
        assert "clean v1" in (tmp_path / "r.md").read_text()  # last good survives
        assert key  # silence unused warning; rollback covered elsewhere

    def test_clean_files_still_written_alongside_blocked(self, store, tmp_path):
        _approve_rule(store, name="clean", content="All good.")
        _approve_rule(store, name="dirty", content="See /home/x/notes.")  # path-privacy: ignore
        result = compile_rules(store, tmp_path)
        assert result["written"] == ["clean.md"]
        assert [b["file"] for b in result["blocked"]] == ["dirty.md"]
