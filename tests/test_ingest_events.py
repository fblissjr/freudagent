"""Tests for the M5 ingest adapters: IngestAdapter protocol conformance
(TranscriptAdapter, JsonlEventAdapter), mask_signature, and ingest_events()
end-to-end (the non-transcript proof that a generic event stream flows
through the same idempotent, lineage-stamped path as transcripts).

See tests/test_events.py for store-layer Event/EventType coverage
(registry validation, stream_key_for, batch-insert row-content
equivalence) -- this file covers the ingest.py layer above the store.
"""

import json
from datetime import datetime

from freud_schema.ingest import (
    IngestAdapter,
    JsonlEventAdapter,
    RawEvent,
    SourceUnit,
    TranscriptAdapter,
    ingest_events,
    mask_signature,
)
from freud_schema.tables import RecordSource


class TestMaskSignature:
    def test_masks_uuid(self):
        text = "session aaaaaaaa-1111-2222-3333-444444444444 started"
        assert "<UUID>" in mask_signature(text)
        assert "aaaaaaaa" not in mask_signature(text)

    def test_masks_long_hex(self):
        text = "commit deadbeefcafe0123 applied"
        assert "<HEX>" in mask_signature(text)

    def test_masks_numbers(self):
        text = "retry attempt 3 of 5 failed"
        assert mask_signature(text) == "retry attempt <NUM> of <NUM> failed"

    def test_masks_quoted_strings(self):
        text = 'error: "file not found" for input'
        assert mask_signature(text) == "error: <STR> for input"

    def test_short_tokens_unmasked(self):
        # Short alpha tokens and short hex-like fragments (<8 chars) are
        # NOT masked -- this is a lite/cheap normalization, not real
        # template mining (documented limitation).
        text = "ok done"
        assert mask_signature(text) == "ok done"

    def test_stable_across_variable_values(self):
        # The whole point: two structurally-identical lines with
        # different variable values collapse to the same signature.
        a = mask_signature("user 42 logged in at 09:15")
        b = mask_signature("user 99 logged in at 14:02")
        assert a == b


class TestJsonlEventAdapterConformance:
    """JsonlEventAdapter satisfies IngestAdapter's shape (structural,
    since typing.Protocol isn't enforced at runtime without @runtime_checkable)."""

    def test_conforms_to_ingest_adapter_protocol(self):
        assert isinstance(JsonlEventAdapter(), IngestAdapter)

    def test_has_normalize_hook(self):
        # normalize() is the amendment-6 hook -- optional, so it is
        # deliberately NOT part of the IngestAdapter protocol itself
        # (typing.Protocol can't express "optional method"); callers
        # probe with hasattr(), same as ingest_events() does.
        assert hasattr(JsonlEventAdapter(), "normalize")

    def test_discover_one_stream_per_file(self, tmp_path):
        (tmp_path / "a.jsonl").write_text(
            json.dumps({"id": "1", "type": "t", "timestamp": None,
                        "actor": None, "payload": None}) + "\n")
        sub = tmp_path / "nested"
        sub.mkdir()
        (sub / "b.jsonl").write_text(
            json.dumps({"id": "2", "type": "t", "timestamp": None,
                        "actor": None, "payload": None}) + "\n")
        units = JsonlEventAdapter().discover(tmp_path)
        assert {u.native_stream_id for u in units} == {"a.jsonl", "nested/b.jsonl"}

    def test_discover_missing_root_returns_empty(self, tmp_path):
        assert JsonlEventAdapter().discover(tmp_path / "nope") == []

    def test_discover_since_filters_by_mtime(self, tmp_path):
        import os
        old = tmp_path / "old.jsonl"
        old.write_text("{}\n")
        old_ts = datetime(2020, 1, 1).timestamp()
        os.utime(old, (old_ts, old_ts))
        new = tmp_path / "new.jsonl"
        new.write_text("{}\n")
        units = JsonlEventAdapter().discover(tmp_path, since=datetime(2025, 1, 1))
        assert {u.native_stream_id for u in units} == {"new.jsonl"}

    def test_parse_yields_raw_events(self, tmp_path):
        f = tmp_path / "s.jsonl"
        f.write_text("\n".join([
            json.dumps({"id": "e1", "type": "click", "timestamp": "2026-07-01T10:00:00Z",
                        "actor": "u1", "payload": {"x": 1}, "text": "clicked button"}),
            json.dumps({"id": "e2", "type": "view", "timestamp": None,
                        "actor": None, "payload": None}),
        ]) + "\n")
        unit = SourceUnit(id="s", path=f, native_stream_id="s.jsonl")
        events = list(JsonlEventAdapter().parse(unit))
        assert len(events) == 2
        assert events[0] == RawEvent(
            id="e1", type="click", timestamp=events[0].timestamp,
            actor="u1", payload={"x": 1}, content_text="clicked button")
        assert events[0].timestamp is not None
        assert events[1].id == "e2"
        assert events[1].payload is None
        assert events[1].content_text is None

    def test_parse_skips_malformed_lines(self, tmp_path):
        f = tmp_path / "s.jsonl"
        f.write_text("NOT JSON\n" + json.dumps(
            {"id": "e1", "type": "t", "timestamp": None,
             "actor": None, "payload": None}) + "\n")
        unit = SourceUnit(id="s", path=f, native_stream_id="s.jsonl")
        events = list(JsonlEventAdapter().parse(unit))
        assert len(events) == 1
        assert events[0].id == "e1"

    def test_normalize_delegates_to_mask_signature(self):
        adapter = JsonlEventAdapter()
        assert adapter.normalize("attempt 3") == mask_signature("attempt 3")


class TestTranscriptAdapterConformance:
    """TranscriptAdapter conforms to IngestAdapter's shape but is not the
    write path ingest_transcripts() uses (see ingest.py module docstring
    and tests/test_ingest.py for the actual write-path tests)."""

    def test_conforms_to_ingest_adapter_protocol(self):
        assert isinstance(TranscriptAdapter(), IngestAdapter)

    def _write_fixture(self, tmp_path):
        root = tmp_path / "projects"
        proj = root / "-Users-x-repo"
        proj.mkdir(parents=True)
        session_id = "cccccccc-1111-2222-3333-444444444444"
        lines = [
            {"type": "user", "sessionId": session_id, "uuid": "u1",
             "parentUuid": None, "timestamp": "2026-07-01T10:00:00Z",
             "cwd": "/repo", "isSidechain": False,
             "message": {"role": "user", "content": "Hello there"}},
            {"type": "assistant", "sessionId": session_id, "uuid": "u2",
             "parentUuid": "u1", "timestamp": "2026-07-01T10:00:05Z",
             "cwd": "/repo", "isSidechain": False,
             "message": {"id": "m1", "role": "assistant", "model": "claude-fable-5",
                         "content": [{"type": "text", "text": "Hi!"}]}},
        ]
        f = proj / f"{session_id}.jsonl"
        f.write_text("\n".join(json.dumps(l) for l in lines) + "\n")
        return root

    def test_discover_matches_discover_sessions(self, tmp_path):
        root = self._write_fixture(tmp_path)
        units = TranscriptAdapter().discover(root)
        assert len(units) == 1
        assert units[0].path.suffix == ".jsonl"

    def test_parse_yields_user_and_assistant_events(self, tmp_path):
        root = self._write_fixture(tmp_path)
        unit = TranscriptAdapter().discover(root)[0]
        events = list(TranscriptAdapter().parse(unit))
        types = [e.type for e in events]
        assert types == ["user_message", "assistant_message"]
        assert events[0].content_text == "Hello there"
        assert events[1].content_text == "Hi!"
        assert events[1].payload == {"model": "claude-fable-5"}


class TestIngestEventsEndToEnd:
    def _write_stream(self, tmp_path, name, rows):
        f = tmp_path / name
        f.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        return f

    def test_streams_ingest_and_register_types(self, store, tmp_path):
        self._write_stream(tmp_path, "orders.jsonl", [
            {"id": "e1", "type": "order_placed", "timestamp": "2026-07-01T10:00:00Z",
             "actor": "user-1", "payload": {"amount": 9.99}, "text": "order abc-123-def"},
            {"id": "e2", "type": "order_shipped", "timestamp": "2026-07-01T11:00:00Z",
             "actor": "system", "payload": {"carrier": "UPS"}},
        ])
        stats = ingest_events(store, root=tmp_path)
        assert stats["streams"] == 1
        assert stats["rows_read"] == 2
        assert stats["rows_written"] == 2
        assert stats["rows_skipped"] == 0

        types = {t.event_type for t in store.list_event_types()}
        assert types == {"order_placed", "order_shipped"}
        registered = store.get_event_type("order_placed")
        assert registered.record_source == RecordSource.EVENT_INGEST

        stream_key = store.stream_key_for(RecordSource.EVENT_INGEST, "orders.jsonl")
        rows = store.list_events(stream_key=stream_key)
        assert len(rows) == 2
        placed = next(r for r in rows if r.event_type == "order_placed")
        assert placed.payload == {"amount": 9.99}
        assert placed.signature is not None  # masked via JsonlEventAdapter.normalize
        assert "<NUM>" in placed.signature or "<HEX>" in placed.signature

    def test_load_log_recorded(self, store, tmp_path):
        self._write_stream(tmp_path, "s.jsonl", [
            {"id": "e1", "type": "t", "timestamp": None, "actor": None, "payload": None},
        ])
        stats = ingest_events(store, root=tmp_path)
        run = store.get_load_run(stats["etl_run_id"])
        assert run.operation == "ingest_events"
        assert run.status.value == "completed"
        assert run.rows_read == 1
        assert run.rows_written == 1
        assert run.rows_skipped == 0

    def test_reingest_is_idempotent(self, store, tmp_path):
        self._write_stream(tmp_path, "s.jsonl", [
            {"id": "e1", "type": "t", "timestamp": None, "actor": None, "payload": None},
            {"id": "e2", "type": "t", "timestamp": None, "actor": None, "payload": None},
        ])
        ingest_events(store, root=tmp_path)
        before = store.con.execute("SELECT COUNT(*) FROM fact_event").fetchone()[0]
        stats = ingest_events(store, root=tmp_path)
        assert stats["rows_written"] == 0
        assert stats["rows_skipped"] == 2
        after = store.con.execute("SELECT COUNT(*) FROM fact_event").fetchone()[0]
        assert after == before

    def test_grown_file_ingests_only_delta(self, store, tmp_path):
        f = self._write_stream(tmp_path, "s.jsonl", [
            {"id": "e1", "type": "t", "timestamp": None, "actor": None, "payload": None},
        ])
        ingest_events(store, root=tmp_path)
        f.write_text(f.read_text() + json.dumps(
            {"id": "e2", "type": "t", "timestamp": None,
             "actor": None, "payload": None}) + "\n")
        stats = ingest_events(store, root=tmp_path)
        assert stats["rows_written"] == 1
        assert stats["rows_skipped"] == 1  # e1 re-read, skipped

    def test_since_filters_streams(self, store, tmp_path):
        import os
        old = self._write_stream(tmp_path, "old.jsonl", [
            {"id": "e1", "type": "t", "timestamp": None, "actor": None, "payload": None},
        ])
        old_ts = datetime(2020, 1, 1).timestamp()
        os.utime(old, (old_ts, old_ts))
        stats = ingest_events(store, root=tmp_path, since=datetime(2025, 1, 1))
        assert stats["streams"] == 0
        assert stats["rows_written"] == 0

    def test_couch_detectors_unaffected(self, store, tmp_path):
        """Couch's SQL detectors read the typed tables (fact_message/
        fact_tool_use), not fact_event -- events ingesting must not
        surface as findings."""
        from freud_schema.couch import run_couch

        self._write_stream(tmp_path, "s.jsonl", [
            {"id": "e1", "type": "t", "timestamp": None, "actor": None, "payload": None},
        ])
        ingest_events(store, root=tmp_path)
        result = run_couch(store, include_filesystem=False)
        assert result["findings"] == 0
