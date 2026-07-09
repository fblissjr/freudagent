"""Tests for the couch: SQL-only finding detection (Phase 2a).

Each finding type gets a fixture shaped to trigger it, plus a
below-threshold neighbor that must NOT fire -- false-positive guards
are the point of typed findings.
"""

import pytest

from freud_schema.couch import (
    SQL_FINDING_TYPES,
    run_couch,
    seed_finding_types,
    source_content_hash,
)
from freud_schema.tables import (
    DetectionMethod,
    FindingScope,
    Message,
    MessageRole,
    Project,
    RecordSource,
    Session,
    Source,
    ToolUse,
)


@pytest.fixture
def warehouse(store):
    """A small warehouse exhibiting every SQL finding pattern."""
    pkey = store.ensure_project(Project(project_path="/repo/alpha"))
    quiet = store.ensure_project(Project(project_path="/repo/quiet"))
    skey = store.insert_session(Session(
        native_session_id="sess-1", project_key=pkey,
        record_source=RecordSource.TRANSCRIPT_INGEST))
    qkey = store.insert_session(Session(
        native_session_id="sess-q", project_key=quiet,
        record_source=RecordSource.TRANSCRIPT_INGEST))

    def tool(n, session, project, name, inp, err=False, result=None):
        store.insert_tool_use(ToolUse(
            session_key=session, project_key=project, tool_use_id=f"t{n}",
            tool_name=name, tool_input=inp, is_error=err, result_text=result))

    # Retry loop: same tool + identical input 4x in one session
    for i in range(4):
        tool(f"retry{i}", skey, pkey, "Bash", {"command": "make build"}, err=True)
    # Error cluster: WebFetch 30 uses, 12 errors (40%)
    for i in range(30):
        tool(f"wf{i}", skey, pkey, "WebFetch", {"url": f"https://x/{i}"},
             err=i < 12, result="fetch failed" if i < 12 else "ok")
    # Below-threshold neighbor: Read 30 uses, 1 error -- must not fire
    for i in range(30):
        tool(f"rd{i}", skey, pkey, "Read", {"file_path": f"f{i}"}, err=i == 0)
    # Permission friction: 3 denials on Write
    for i in range(3):
        tool(f"pw{i}", skey, pkey, "Write", {"file_path": f"w{i}"},
             err=True, result="The user doesn't want to proceed with this tool use")
    # Interruptions: 3 in project alpha, 1 in quiet (below threshold)
    for i in range(3):
        store.insert_message(Message(
            session_key=skey, project_key=pkey, role=MessageRole.USER,
            entry_uuid=f"int{i}",
            content_text="[Request interrupted by user]"))
    store.insert_message(Message(
        session_key=qkey, project_key=quiet, role=MessageRole.USER,
        entry_uuid="intq", content_text="[Request interrupted by user]"))
    return {"pkey": pkey, "quiet": quiet, "skey": skey}


class TestSeed:
    def test_seed_registers_all_types(self, store):
        seed_finding_types(store)
        registered = {ft.finding_type for ft in store.list_finding_types()}
        assert set(SQL_FINDING_TYPES) <= registered
        assert "user_correction_pattern" in registered  # llm-detected, seeded too

    def test_seed_idempotent(self, store):
        seed_finding_types(store)
        seed_finding_types(store)
        counts = store.con.execute(
            "SELECT finding_type, COUNT(*) FROM dim_finding_type "
            "GROUP BY finding_type HAVING COUNT(*) > 1").fetchall()
        assert counts == []


class TestRunCouch:
    def test_detects_all_four_patterns(self, store, warehouse):
        stats = run_couch(store)
        types = {f.finding_type for f in store.list_findings()}
        assert types == {"retry_loop", "tool_error_cluster",
                         "permission_friction", "interruption_hotspot"}
        assert stats["findings"] == len(store.list_findings())

    def test_retry_loop_evidence(self, store, warehouse):
        run_couch(store)
        f = store.list_findings(finding_type="retry_loop")[0]
        assert f.project_key == warehouse["pkey"]
        assert warehouse["skey"] in f.evidence_session_keys
        assert "Bash" in f.summary
        assert f.occurrence_count >= 4

    def test_error_cluster_thresholds(self, store, warehouse):
        run_couch(store)
        clusters = store.list_findings(finding_type="tool_error_cluster")
        tools = {c.summary.split(":")[0] for c in clusters}
        assert any("WebFetch" in c.summary for c in clusters)
        # Read (3% error rate) must not fire
        assert not any("Read" in t for t in tools)

    def test_interruption_threshold(self, store, warehouse):
        run_couch(store)
        hits = store.list_findings(finding_type="interruption_hotspot")
        assert len(hits) == 1
        assert hits[0].project_key == warehouse["pkey"]  # quiet project below threshold

    def test_permission_friction(self, store, warehouse):
        run_couch(store)
        f = store.list_findings(finding_type="permission_friction")[0]
        assert "Write" in f.summary
        assert f.occurrence_count == 3

    def test_summaries_contain_no_input_content(self, store, warehouse):
        """Scrubbed by construction: summaries are built from tool names
        and counts, never from tool inputs, file paths, or message text."""
        run_couch(store)
        for f in store.list_findings():
            assert "make build" not in f.summary
            assert "/repo/" not in f.summary
            assert "https://" not in f.summary

    def test_rerun_appends_new_run_findings(self, store, warehouse):
        """Findings are append-only trend data: each run records what it
        saw, keyed by etl_run_id."""
        s1 = run_couch(store)
        s2 = run_couch(store)
        assert s1["etl_run_id"] != s2["etl_run_id"]
        assert s2["findings"] == s1["findings"]
        assert len(store.list_findings()) == s1["findings"] + s2["findings"]

    def test_empty_warehouse_yields_nothing(self, store):
        stats = run_couch(store)
        assert stats["findings"] == 0
        assert store.list_findings() == []


class TestStaleSource:
    """The hybrid detector: warehouse baseline vs current file bytes."""

    def _register(self, store, path, with_hash=True):
        return store.insert_source(Source(
            content_path=str(path), media_type="text/plain",
            source_hash=source_content_hash(path) if with_hash else None))

    def test_seed_registers_hybrid_type(self, store):
        seed_finding_types(store)
        ft = store.get_finding_type("stale_source")
        assert ft is not None
        assert ft.detection_method == DetectionMethod.HYBRID

    def test_mutated_source_fires(self, store, tmp_path):
        doc = tmp_path / "seed-doc.txt"
        doc.write_text("original corpus content")
        self._register(store, doc)
        doc.write_text("the upstream document changed")
        run_couch(store)
        hits = store.list_findings(finding_type="stale_source")
        assert len(hits) == 1
        assert hits[0].scope == FindingScope.GLOBAL
        assert hits[0].project_key is None

    def test_summary_carries_basename_never_directory(self, store, tmp_path):
        doc = tmp_path / "seed-doc.txt"
        doc.write_text("original")
        self._register(store, doc)
        doc.write_text("changed")
        run_couch(store)
        summary = store.list_findings(finding_type="stale_source")[0].summary
        assert "seed-doc.txt" in summary
        assert str(tmp_path) not in summary  # privacy: no directory paths

    def test_unchanged_source_does_not_fire(self, store, tmp_path):
        doc = tmp_path / "stable.txt"
        doc.write_text("stable content")
        self._register(store, doc)
        run_couch(store)
        assert store.list_findings(finding_type="stale_source") == []

    def test_no_baseline_hash_is_skipped(self, store, tmp_path):
        doc = tmp_path / "unhashed.txt"
        doc.write_text("original")
        self._register(store, doc, with_hash=False)
        doc.write_text("changed")
        run_couch(store)
        assert store.list_findings(finding_type="stale_source") == []

    def test_missing_file_is_skipped(self, store, tmp_path):
        doc = tmp_path / "gone.txt"
        doc.write_text("original")
        self._register(store, doc)
        doc.unlink()
        run_couch(store)
        assert store.list_findings(finding_type="stale_source") == []

    def test_warehouse_only_skips_filesystem(self, store, tmp_path):
        doc = tmp_path / "seed-doc.txt"
        doc.write_text("original")
        self._register(store, doc)
        doc.write_text("changed")
        run_couch(store, include_filesystem=False)
        assert store.list_findings(finding_type="stale_source") == []
