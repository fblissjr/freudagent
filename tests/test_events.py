"""Store-layer tests for the generic event grain (M5): dim_event_type
registry, fact_event inserts, the stream_key_for recipe, and the
spill-to-JSON bulk insert path's row-content equivalence.

What's under test here (store.py), distinct from tests/test_ingest_events.py
(ingest.py adapters and ingest_events() orchestration):
- register_event_type/get_event_type/list_event_types mirror the
  finding_type registry methods exactly.
- insert_events registry-validates event_type before writing (open
  vocabulary, same fail-closed pattern as insert_finding).
- insert_events enforces a single-stream batch, sibling of the
  single-session guard on insert_messages/insert_tool_uses.
- stream_key_for/event_key_for are named recipes, not re-derived formulas.
- The JSON-spill bulk insert (_bulk_insert_json, shared by insert_messages/
  insert_tool_uses/insert_events) round-trips None/NULL, timestamps, JSON
  columns, unicode, and embedded newlines/quotes byte-for-byte -- this is
  the row-content equivalence the fresh-ingest speed optimization (BACKLOG
  "fresh-ingest insert speed") must preserve versus the old per-row
  executemany path.
"""

from datetime import datetime

import pytest

from freud_schema.keys import dimension_key
from freud_schema.tables import (
    Event,
    EventType,
    Message,
    MessageRole,
    RecordSource,
    Session,
    ToolUse,
)


class TestEventTypeRegistry:
    def test_register_event_type(self, store):
        key = store.register_event_type(
            EventType(event_type="order_placed", description="A new order"))
        assert key == dimension_key("order_placed")
        # idempotent re-register
        assert store.register_event_type(
            EventType(event_type="order_placed")) == key

    def test_get_and_list_event_types(self, store):
        store.register_event_type(EventType(
            event_type="order_placed", schema_hint={"amount": "number"}))
        store.register_event_type(EventType(event_type="order_shipped"))
        found = store.get_event_type("order_placed")
        assert found is not None
        assert found.schema_hint == {"amount": "number"}
        assert found.record_source == RecordSource.NATIVE
        all_types = store.list_event_types()
        assert {t.event_type for t in all_types} == {"order_placed", "order_shipped"}

    def test_get_unregistered_event_type_returns_none(self, store):
        assert store.get_event_type("nonexistent") is None


class TestEventRegistryValidation:
    def test_unregistered_event_type_raises(self, store):
        with pytest.raises(ValueError, match="not registered"):
            store.insert_events([Event(
                stream_key=store.stream_key_for(RecordSource.EVENT_INGEST, "s1"),
                native_event_id="e1", event_type="unregistered_thing",
            )])

    def test_unregistered_event_type_writes_nothing(self, store):
        with pytest.raises(ValueError):
            store.insert_events([Event(
                stream_key=store.stream_key_for(RecordSource.EVENT_INGEST, "s1"),
                native_event_id="e1", event_type="unregistered_thing",
            )])
        assert store.con.execute(
            "SELECT COUNT(*) FROM fact_event").fetchone()[0] == 0

    def test_registered_event_type_inserts(self, store):
        store.register_event_type(EventType(event_type="order_placed"))
        stream_key = store.stream_key_for(RecordSource.EVENT_INGEST, "s1")
        written = store.insert_events([Event(
            stream_key=stream_key, native_event_id="e1",
            event_type="order_placed", payload={"amount": 5},
        )])
        assert written == 1
        rows = store.list_events(stream_key=stream_key)
        assert len(rows) == 1
        assert rows[0].event_type == "order_placed"
        assert rows[0].payload == {"amount": 5}


class TestStreamKeyRecipe:
    def test_stream_key_for_deterministic(self, store):
        key = store.stream_key_for(RecordSource.EVENT_INGEST, "stream1")
        assert key == dimension_key(RecordSource.EVENT_INGEST.value, "stream1")
        # same inputs -> same key, no lookup needed
        assert store.stream_key_for(RecordSource.EVENT_INGEST, "stream1") == key

    def test_event_key_for_deterministic(self, store):
        key = store.event_key_for("streamkey123", "e1")
        assert key == dimension_key("streamkey123", "e1")


class TestInsertEventsGuards:
    def _register(self, store) -> None:
        store.register_event_type(EventType(event_type="t"))

    def test_mixed_stream_batch_raises(self, store):
        self._register(store)
        s1 = store.stream_key_for(RecordSource.EVENT_INGEST, "stream1")
        s2 = store.stream_key_for(RecordSource.EVENT_INGEST, "stream2")
        with pytest.raises(ValueError, match="single stream_key"):
            store.insert_events([
                Event(stream_key=s1, native_event_id="e1", event_type="t"),
                Event(stream_key=s2, native_event_id="e2", event_type="t"),
            ])

    def test_empty_batch_is_noop(self, store):
        assert store.insert_events([]) == 0

    def test_insert_event_singleton_delegates(self, store):
        self._register(store)
        stream_key = store.stream_key_for(RecordSource.EVENT_INGEST, "s1")
        key = store.insert_event(Event(stream_key=stream_key, event_type="t"))
        assert store.get_event(key) is not None

    def test_idempotent_reinsert_skips(self, store):
        self._register(store)
        stream_key = store.stream_key_for(RecordSource.EVENT_INGEST, "s1")
        ev = Event(stream_key=stream_key, native_event_id="e1", event_type="t")
        assert store.insert_events([ev]) == 1
        assert store.insert_events([ev]) == 0
        count = store.con.execute("SELECT COUNT(*) FROM fact_event").fetchone()[0]
        assert count == 1


class TestBulkInsertJsonEquivalence:
    """Row-content equivalence for the spill-to-JSON bulk insert path
    (_bulk_insert_json, shared by insert_messages/insert_tool_uses/
    insert_events) -- asserted against expected literals per the M5 spec's
    equivalence requirement, covering None/NULL, timestamps, JSON columns,
    unicode, and embedded newlines/quotes in text."""

    def test_event_round_trip_edge_cases(self, store):
        store.register_event_type(EventType(event_type="weird"))
        stream_key = store.stream_key_for(RecordSource.EVENT_INGEST, "s1")
        ts = datetime(2026, 7, 1, 10, 30, 45)
        ev = Event(
            stream_key=stream_key, native_event_id="e1", event_type="weird",
            occurred_at=ts, actor="user-42",
            payload={"nested": {"a": [1, 2, 3]}, "note": "say \"hi\"\nline2"},
            content_text="hello \"world\"\nline2 with 'quotes' and unicode éè日本語",
            signature="<STR>", sequence_num=3,
        )
        store.insert_events([ev])
        row = store.get_event(store.event_key_for(stream_key, "e1"))
        assert row is not None
        assert row.stream_key == stream_key
        assert row.native_event_id == "e1"
        assert row.event_type == "weird"
        assert row.occurred_at == ts
        assert row.actor == "user-42"
        assert row.payload == {"nested": {"a": [1, 2, 3]},
                               "note": "say \"hi\"\nline2"}
        assert row.content_text == (
            "hello \"world\"\nline2 with 'quotes' and unicode éè日本語")
        assert row.signature == "<STR>"
        assert row.sequence_num == 3
        assert row.record_source == RecordSource.EVENT_INGEST

    def test_event_none_fields_round_trip_as_null(self, store):
        store.register_event_type(EventType(event_type="bare"))
        stream_key = store.stream_key_for(RecordSource.EVENT_INGEST, "s1")
        store.insert_events([Event(
            stream_key=stream_key, native_event_id="e1", event_type="bare")])
        row = store.get_event(store.event_key_for(stream_key, "e1"))
        assert row.occurred_at is None
        assert row.actor is None
        assert row.payload is None
        assert row.content_text is None
        assert row.signature is None
        assert row.sequence_num == 0

    def test_message_round_trip_edge_cases(self, store):
        skey = store.insert_session(Session(
            native_session_id="cc-1", record_source=RecordSource.TRANSCRIPT_INGEST))
        ts = datetime(2026, 7, 1, 9, 0, 0)
        msg = Message(
            session_key=skey, role=MessageRole.ASSISTANT, entry_uuid="u1",
            parent_uuid="u0", sequence_num=2, occurred_at=ts,
            content_text="line1\nline2 with \"quotes\" and unicode éè",
            has_thinking=True, stop_reason="end_turn",
            input_tokens=100, output_tokens=None,
            is_meta=False, is_sidechain=True,
        )
        store.insert_messages([msg])
        row = store._fetchone(
            "SELECT * FROM fact_message WHERE message_key = ?",
            [store.message_key_for(skey, "u1")],
        )
        assert row["content_text"] == "line1\nline2 with \"quotes\" and unicode éè"
        assert row["has_thinking"] is True
        assert row["is_sidechain"] is True
        assert row["is_meta"] is False
        assert row["input_tokens"] == 100
        assert row["output_tokens"] is None
        assert row["occurred_at"] == ts
        assert row["parent_uuid"] == "u0"
        assert row["stop_reason"] == "end_turn"

    def test_tool_use_round_trip_edge_cases(self, store):
        skey = store.insert_session(Session(
            native_session_id="cc-2", record_source=RecordSource.TRANSCRIPT_INGEST))
        tu = ToolUse(
            session_key=skey, tool_use_id="toolu_1", tool_name="Bash",
            tool_input={"command": "echo \"hi\"\necho done", "nested": [1, None, "x"]},
            is_error=False,
            result_text="line1\nline2 with 'quotes' and unicode日本語",
            sequence_num=1,
        )
        store.insert_tool_uses([tu])
        row = store._fetchone(
            "SELECT * FROM fact_tool_use WHERE tool_use_key = ?",
            [dimension_key(skey, "toolu_1")],
        )
        assert row["tool_input"] == {
            "command": "echo \"hi\"\necho done", "nested": [1, None, "x"]}
        assert row["is_error"] is False
        assert row["result_text"] == "line1\nline2 with 'quotes' and unicode日本語"
        assert row["sequence_num"] == 1

    def test_tool_use_none_fields_round_trip_as_null(self, store):
        skey = store.insert_session(Session(
            native_session_id="cc-3", record_source=RecordSource.TRANSCRIPT_INGEST))
        tu = ToolUse(session_key=skey, tool_use_id="toolu_2", tool_name="Read")
        store.insert_tool_uses([tu])
        row = store._fetchone(
            "SELECT * FROM fact_tool_use WHERE tool_use_key = ?",
            [dimension_key(skey, "toolu_2")],
        )
        assert row["tool_input"] is None
        assert row["is_error"] is None
        assert row["result_text"] is None
        assert row["message_key"] is None
        assert row["occurred_at"] is None
