"""Typed traces are derived from recorded reasoning, not volunteered by the agent.

The distinction is the whole design, and it is easy to collapse the two because
both end up writing `fact_trace`.

Self-reporting: the agent describes its own reasoning while running. It exists
only when someone turned it on, degrades whenever reporting is not load-bearing
for the agent's own task, and is missing for exactly the run you wanted to look
at. The design rules this out -- the trail is meant to be "recorded by default
rather than switched on when someone suspects a problem".

Derivation: a later pass reads `fact_message.thinking_text`, which was captured
for every run whether anyone was curious or not, and structures it. It is
independent of the run being described, it covers everything that was captured,
and it can be redone with a better prompt tomorrow without losing anything.

Three properties follow, and each is a test below:

- `record_source = derived`. A derived row is not a native observation and must
  never be counted as one.
- Every derived trace names the message it came from. A structured claim whose
  evidence you cannot reach is the thing this repo keeps calling a broken
  provenance chain.
- Re-deriving the same message converges instead of accumulating. A model given
  the same reasoning twice will not phrase a title identically, so a title-keyed
  row would duplicate on every pass.
"""

from __future__ import annotations

import pytest

from freud_schema import ops
from freud_schema.tables import (
    Message,
    MessageRole,
    RecordSource,
    Session,
    TraceType,
)


def _session_with_reasoning(store, thinking: str = "Chose the narrow fix over the refactor.") -> tuple[str, str]:
    """A session carrying one assistant turn whose reasoning was captured."""
    session_key = store.insert_session(Session(task_description="t", task_type="t"))
    store.insert_messages([Message(
        session_key=session_key,
        role=MessageRole.ASSISTANT,
        entry_uuid="uuid-1",
        sequence_num=0,
        content_text="Doing the narrow fix.",
        has_thinking=True,
        thinking_text=thinking,
    )])
    msg = store.list_reasoning_messages(session_key=session_key)[0]
    return session_key, msg["message_key"]


class TestDerivationIsNotObservation:
    def test_derived_traces_are_labeled_derived(self, store):
        session_key, message_key = _session_with_reasoning(store)
        result = ops.trace_add(
            store, session_key=session_key, source_message_key=message_key,
            trace_type=TraceType.DECISION_POINT,
            title="Chose narrow fix over refactor",
            reasoning="Refactor was out of scope for the ticket")
        trace = store.get_trace(result["trace_key"])
        assert trace.record_source == RecordSource.DERIVED

    def test_derivation_is_wrapped_in_a_load_run(self, store):
        """Same lineage rule as every other derivation. A derived row you cannot
        trace to the pass that produced it cannot be re-derived or retracted."""
        session_key, message_key = _session_with_reasoning(store)
        result = ops.trace_add(
            store, session_key=session_key, source_message_key=message_key,
            trace_type=TraceType.INSIGHT, title="Notation is inconsistent")
        run = store.get_load_run(result["etl_run_id"])
        assert run is not None
        assert run.operation == "trace_derive"
        assert run.rows_written == 1


class TestProvenanceReachesTheEvidence:
    def test_trace_names_the_message_it_came_from(self, store):
        session_key, message_key = _session_with_reasoning(store)
        result = ops.trace_add(
            store, session_key=session_key, source_message_key=message_key,
            trace_type=TraceType.DEAD_END, title="Abstract lacked the numbers")
        trace = store.get_trace(result["trace_key"])
        assert trace.source_message_key == message_key

    def test_unknown_source_message_is_rejected(self, store):
        """Fail closed, like every other key reference in the store."""
        session_key, _ = _session_with_reasoning(store)
        with pytest.raises(ValueError, match="not found"):
            ops.trace_add(
                store, session_key=session_key, source_message_key="0" * 32,
                trace_type=TraceType.INSIGHT, title="x")


class TestRederivationConverges:
    def test_same_message_and_position_is_idempotent(self, store):
        """Keyed on (source_message_key, sequence_order), not on the title.

        A model re-reading the same reasoning will not word a title the same way
        twice. Keying on the title would make every re-derivation pass duplicate
        the whole corpus while looking like it found new material.
        """
        session_key, message_key = _session_with_reasoning(store)
        first = ops.trace_add(
            store, session_key=session_key, source_message_key=message_key,
            trace_type=TraceType.DECISION_POINT, sequence_order=0,
            title="Chose the narrow fix")
        second = ops.trace_add(
            store, session_key=session_key, source_message_key=message_key,
            trace_type=TraceType.DECISION_POINT, sequence_order=0,
            title="Picked a narrow fix instead of refactoring")
        assert first["trace_key"] == second["trace_key"]
        assert len(store.list_traces(session_key=session_key)) == 1

    def test_distinct_positions_in_one_message_coexist(self, store):
        """One turn's reasoning often holds several steps."""
        session_key, message_key = _session_with_reasoning(store)
        for i, (tt, title) in enumerate([
            (TraceType.DECISION_POINT, "Chose the narrow fix"),
            (TraceType.DEAD_END, "Tried the config route first"),
        ]):
            ops.trace_add(
                store, session_key=session_key, source_message_key=message_key,
                trace_type=tt, sequence_order=i, title=title)
        assert len(store.list_traces(session_key=session_key)) == 2


class TestFindingTheWork:
    def test_reasoning_messages_are_discoverable(self, store):
        """The derivation pass needs to find what has reasoning but no traces
        yet, or it cannot run incrementally over a growing warehouse."""
        session_key, message_key = _session_with_reasoning(store)
        pending = store.list_reasoning_messages(session_key=session_key)
        assert [m["message_key"] for m in pending] == [message_key]
        assert pending[0]["thinking_text"]

        ops.trace_add(
            store, session_key=session_key, source_message_key=message_key,
            trace_type=TraceType.CONCLUSION, title="Shipped the narrow fix")
        assert store.list_reasoning_messages(
            session_key=session_key, underived_only=True) == []

    def test_messages_without_reasoning_are_not_offered(self, store):
        session_key = store.insert_session(Session(task_description="t"))
        store.insert_messages([Message(
            session_key=session_key, role=MessageRole.USER,
            entry_uuid="u-1", sequence_num=0, content_text="do it")])
        assert store.list_reasoning_messages(session_key=session_key) == []
