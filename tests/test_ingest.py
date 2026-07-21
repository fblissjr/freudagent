"""Tests for transcript discovery and ingestion (Phase 1: ingest).

Fixture layout mirrors the real ~/.claude/projects structure verified
on disk 2026-07-07:

    <root>/<encoded-project>/<session-uuid>.jsonl          root sessions
    <root>/<encoded-project>/<session-uuid>/subagents/
        agent-<id>.jsonl                                   subagent sessions
        agent-<id>.meta.json                               {agentType, description, toolUseId}

The idempotency tests are Phase 1's falsifiable milestone: re-running
ingestion against unchanged files writes zero rows, verified via
meta_load_log counts, not just table counts.
"""

import json
import os
from datetime import datetime

import pytest

from freud_schema.discovery import discover_sessions
from freud_schema.ingest import ingest_transcripts
from freud_schema.keys import dimension_key
from freud_schema.tables import AgentRole, RecordSource, SessionStatus

UUID_A = "aaaaaaaa-1111-2222-3333-444444444444"
UUID_B = "bbbbbbbb-1111-2222-3333-444444444444"
# Real subagent transcripts carry the PARENT's sessionId internally
# (verified 100% on disk 2026-07-07), so the fixture mirrors that; the
# ingester must derive subagent identity from the path, not the field.
SUB_SESSION_ID = UUID_A
AGENT_ID = "abc123def456"
SUB_NATIVE_ID = f"{UUID_A}/agent-{AGENT_ID}"


def _env(session_id: str, uuid: str, ts: str, **over) -> dict:
    base = {
        "sessionId": session_id, "uuid": uuid, "parentUuid": None,
        "timestamp": ts, "cwd": "/repo/alpha", "gitBranch": "main",
        "version": "2.5.0", "userType": "external", "isSidechain": False,
    }
    base.update(over)
    return base


def _root_session_lines() -> list[str]:
    lines = [
        {"type": "summary", "summary": "A session about testing", "leafUuid": "u4"},
        {"type": "user", **_env(UUID_A, "u1", "2026-07-01T10:00:00Z"),
         "message": {"role": "user", "content": [
             {"type": "text", "text": "Please run the tests and fix failures"}]}},
        {"type": "assistant", **_env(UUID_A, "u2", "2026-07-01T10:00:05Z", parentUuid="u1"),
         "message": {"id": "msg_1", "role": "assistant", "model": "claude-fable-5",
                     "stop_reason": "tool_use",
                     "usage": {"input_tokens": 100, "output_tokens": 20},
                     "content": [
                         {"type": "text", "text": "Running tests now."},
                         {"type": "tool_use", "id": "toolu_X", "name": "Bash",
                          "input": {"command": "pytest"}}]}},
        {"type": "user", **_env(UUID_A, "u3", "2026-07-01T10:00:10Z", parentUuid="u2"),
         "message": {"role": "user", "content": [
             {"type": "tool_result", "tool_use_id": "toolu_X",
              "content": "2 passed", "is_error": False}]}},
        {"type": "assistant", **_env(UUID_A, "u4", "2026-07-01T10:00:15Z", parentUuid="u3"),
         "message": {"id": "msg_2", "role": "assistant", "model": "claude-fable-5",
                     "stop_reason": "end_turn",
                     "usage": {"input_tokens": 150, "output_tokens": 30},
                     "content": [{"type": "text", "text": "All tests pass."},
                                 {"type": "thinking", "thinking": "done", "signature": "s"}]}},
        {"type": "system", **_env(UUID_A, "u5", "2026-07-01T10:00:16Z"),
         "subtype": "turn_duration", "durationMs": 16000},
    ]
    return [json.dumps(line) for line in lines]


def _subagent_lines() -> list[str]:
    lines = [
        {"type": "user", **_env(SUB_SESSION_ID, "s1", "2026-07-01T10:00:06Z",
                                isSidechain=True, agentId=AGENT_ID),
         "message": {"role": "user", "content": "Explore the codebase"}},
        {"type": "assistant", **_env(SUB_SESSION_ID, "s2", "2026-07-01T10:00:08Z",
                                     isSidechain=True, agentId=AGENT_ID, parentUuid="s1"),
         "message": {"id": "msg_s", "role": "assistant", "model": "claude-sonnet-5",
                     "stop_reason": "end_turn",
                     "usage": {"input_tokens": 50, "output_tokens": 10},
                     "content": [{"type": "text", "text": "Found it."}]}},
    ]
    return [json.dumps(line) for line in lines]


def _second_project_lines() -> list[str]:
    lines = [
        {"type": "user", **_env(UUID_B, "b1", "2026-06-01T09:00:00Z", cwd="/repo/beta"),
         "message": {"role": "user", "content": "Beta project question"}},
        {"type": "assistant", **_env(UUID_B, "b2", "2026-06-01T09:00:05Z",
                                     cwd="/repo/beta", parentUuid="b1"),
         "message": {"id": "msg_b", "role": "assistant", "model": "claude-fable-5",
                     "stop_reason": "end_turn",
                     "usage": {"input_tokens": 10, "output_tokens": 5},
                     "content": [{"type": "text", "text": "Beta answer"}]}},
    ]
    return [json.dumps(line) for line in lines]


@pytest.fixture
def projects_root(tmp_path):
    root = tmp_path / "projects"
    alpha = root / "-Users-x-repo-alpha"
    alpha.mkdir(parents=True)
    (alpha / f"{UUID_A}.jsonl").write_text("\n".join(_root_session_lines()) + "\n")
    subdir = alpha / UUID_A / "subagents"
    subdir.mkdir(parents=True)
    (subdir / f"agent-{AGENT_ID}.jsonl").write_text("\n".join(_subagent_lines()) + "\n")
    (subdir / f"agent-{AGENT_ID}.meta.json").write_text(json.dumps(
        {"agentType": "Explore", "description": "Explore the codebase",
         "toolUseId": "toolu_SPAWN"}))
    beta = root / "-Users-x-repo-beta"
    beta.mkdir(parents=True)
    (beta / f"{UUID_B}.jsonl").write_text("\n".join(_second_project_lines()) + "\n")
    # Make beta's file older for --since tests
    old = datetime(2026, 6, 1, 9, 0).timestamp()
    os.utime(beta / f"{UUID_B}.jsonl", (old, old))
    return root


class TestDiscovery:
    def test_finds_roots_and_nested_subagents(self, projects_root):
        found = discover_sessions(projects_root)
        assert len(found) == 3
        roots = [f for f in found if f.parent_native_session_id is None]
        subs = [f for f in found if f.parent_native_session_id is not None]
        assert {f.path.stem for f in roots} == {UUID_A, UUID_B}
        assert len(subs) == 1
        sub = subs[0]
        assert sub.parent_native_session_id == UUID_A
        assert sub.agent_id == AGENT_ID
        assert sub.meta["agentType"] == "Explore"

    def test_project_filter(self, projects_root):
        found = discover_sessions(projects_root, project="alpha")
        assert len(found) == 2  # root A + its subagent
        assert all("alpha" in str(f.path) for f in found)

    def test_since_filter(self, projects_root):
        found = discover_sessions(projects_root, since=datetime(2026, 6, 15))
        stems = {f.path.stem for f in found}
        assert UUID_B not in {s for s in stems}
        assert any(UUID_A in s for s in stems)

    def test_missing_meta_is_none(self, projects_root):
        sub = [f for f in discover_sessions(projects_root)
               if f.parent_native_session_id][0]
        (sub.path.parent / f"agent-{AGENT_ID}.meta.json").unlink()
        found = [f for f in discover_sessions(projects_root)
                 if f.parent_native_session_id]
        assert found[0].meta is None


class TestIngest:
    def test_sessions_ingested(self, store, projects_root):
        stats = ingest_transcripts(store, root=projects_root)
        assert stats["sessions"] == 3
        # All three files must land as DISTINCT session rows even though
        # the subagent file shares the parent's internal sessionId.
        assert store.count_rows("fact_session") == 3
        key_a = dimension_key(RecordSource.TRANSCRIPT_INGEST.value, UUID_A)
        session = store.get_session(key_a)
        assert session is not None
        assert session.record_source == RecordSource.TRANSCRIPT_INGEST
        assert session.agent_role == AgentRole.ORCHESTRATOR
        assert session.status == SessionStatus.COMPLETED
        assert session.task_description.startswith("Please run the tests")
        assert session.model_used == "claude-fable-5"
        assert session.completed_at is not None
        assert session.project_key == dimension_key("/repo/alpha")

    def test_subagent_linkage_and_meta(self, store, projects_root):
        ingest_transcripts(store, root=projects_root)
        # Identity from the path, NOT the internal sessionId (which is the
        # parent's) -- otherwise subagent sessions collapse into parents.
        sub_key = dimension_key(RecordSource.TRANSCRIPT_INGEST.value, SUB_NATIVE_ID)
        sub = store.get_session(sub_key)
        assert sub is not None
        assert sub.agent_role == AgentRole.SUBAGENT
        assert sub.parent_session_key == dimension_key(
            RecordSource.TRANSCRIPT_INGEST.value, UUID_A)
        assert sub.task_type == "Explore"
        assert sub.task_description == "Explore the codebase"

    def test_projects_registered(self, store, projects_root):
        ingest_transcripts(store, root=projects_root)
        paths = {p.project_path for p in store.list_projects()}
        assert "/repo/alpha" in paths
        assert "/repo/beta" in paths

    def test_messages_ingested(self, store, projects_root):
        ingest_transcripts(store, root=projects_root)
        key_a = dimension_key(RecordSource.TRANSCRIPT_INGEST.value, UUID_A)
        rows = store.con.execute(
            "SELECT role, content_text, has_thinking, input_tokens, stop_reason "
            "FROM fact_message WHERE session_key = ? ORDER BY sequence_num",
            [key_a]).fetchall()
        # tool_result-only user entry still lands as a message row (empty text)
        assert len(rows) == 4
        assert rows[0][0] == "user"
        assert "Please run the tests" in rows[0][1]
        final = rows[-1]
        assert final[2] is True          # has_thinking on the last assistant turn
        assert final[3] == 150           # input_tokens
        assert final[4] == "end_turn"

    def test_tool_use_joined_with_result(self, store, projects_root):
        ingest_transcripts(store, root=projects_root)
        key_a = dimension_key(RecordSource.TRANSCRIPT_INGEST.value, UUID_A)
        row = store.con.execute(
            "SELECT tool_name, tool_input, is_error, result_text, message_key "
            "FROM fact_tool_use WHERE session_key = ?", [key_a]).fetchone()
        assert row[0] == "Bash"
        assert json.loads(row[1])["command"] == "pytest"
        assert row[2] is False
        assert row[3] == "2 passed"
        assert row[4] is not None

    def test_load_log_recorded(self, store, projects_root):
        stats = ingest_transcripts(store, root=projects_root)
        run = store.get_load_run(stats["etl_run_id"])
        assert run.status == SessionStatus.COMPLETED
        assert run.rows_read > 0
        assert run.rows_written > 0
        assert run.rows_skipped == 0

    def test_reingest_is_idempotent(self, store, projects_root):
        ingest_transcripts(store, root=projects_root)
        counts_before = {
            t: store.con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("fact_session", "fact_message", "fact_tool_use", "dim_project")
        }
        stats = ingest_transcripts(store, root=projects_root)
        run = store.get_load_run(stats["etl_run_id"])
        assert run.rows_written == 0
        assert run.rows_skipped > 0
        counts_after = {
            t: store.con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("fact_session", "fact_message", "fact_tool_use", "dim_project")
        }
        assert counts_after == counts_before

    def test_appended_entries_ingest_incrementally(self, store, projects_root):
        """A resumed session grows its file; re-ingest picks up only new rows."""
        ingest_transcripts(store, root=projects_root)
        new_line = json.dumps(
            {"type": "user", **_env(UUID_A, "u9", "2026-07-01T11:00:00Z"),
             "message": {"role": "user", "content": "One more thing"}})
        f = projects_root / "-Users-x-repo-alpha" / f"{UUID_A}.jsonl"
        f.write_text(f.read_text() + new_line + "\n")
        stats = ingest_transcripts(store, root=projects_root)
        run = store.get_load_run(stats["etl_run_id"])
        assert run.rows_written == 1

    def test_malformed_lines_skipped(self, store, projects_root):
        f = projects_root / "-Users-x-repo-beta" / f"{UUID_B}.jsonl"
        f.write_text("NOT JSON AT ALL\n" + f.read_text())
        stats = ingest_transcripts(store, root=projects_root)
        assert stats["sessions"] == 3  # still ingests everything else
