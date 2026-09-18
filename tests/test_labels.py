"""Labels on messages: fact_message_facets, the label ingest, and the two
label detectors.

A label is a typed answer to a registered question about one ingested
user message, from a model, a person, a rule or a synthetic answer key.
The contracts under test:

- labels land only on real user messages; everything else is rejected
  and counted by reason, never written partially
- choice values are slugs, so reply text cannot reach the table through
  a label (and so cannot reach a finding summary built from one)
- a probability on a non-model label is refused -- that row would
  contaminate the slice models are measured against
- re-ingesting a file writes nothing; a relabel under a new model
  version is a new row, not a skip
- a question's definition cannot change under the same version
- the detectors count recurrence across sessions per labeler, and model
  labels below the probability floor do not count
"""

from __future__ import annotations

import hashlib
import io
import json
import sys

import orjson
import pytest

from freud_schema.couch import LABEL_MIN_PROBABILITY, run_couch
from freud_schema.ingest import (
    ingest_labels,
    ingest_transcripts,
    options_hash,
    register_label_questions,
)
from freud_schema.tables import LabelerKind, LabelUnit, MessageFacet, RecordSource

PROJECT_DIR = "-repo-ledger"
SESSION_A = "aaaaaaaa-0000-0000-0000-00000000000a"
SESSION_B = "bbbbbbbb-0000-0000-0000-00000000000b"
REPLY_TEXT = "No, run the tests before committing, not after."


def _env(session_id: str, uuid: str, ts: str, **over) -> dict:
    base = {
        "sessionId": session_id, "uuid": uuid, "parentUuid": None,
        "timestamp": ts, "cwd": "/repo/ledger", "gitBranch": "main",
        "version": "2.5.0", "userType": "external", "isSidechain": False,
    }
    base.update(over)
    return base


def _session_lines(sid: str, day: str) -> list[str]:
    """A typed prompt, an assistant turn with a tool call, a corrective
    typed reply, a second assistant turn, an interruption marker, then the
    user-role entries a person did not type: a meta entry, slash-command
    output, a hook reminder and a compact summary."""
    p = sid[0]
    lines = [
        {"type": "user", **_env(sid, f"{p}-u1", f"{day}T10:00:00Z"),
         "message": {"role": "user", "content": "Commit the parser fix."}},
        {"type": "assistant", **_env(sid, f"{p}-a1", f"{day}T10:00:05Z", parentUuid=f"{p}-u1"),
         "message": {"id": f"msg_{p}1", "role": "assistant", "model": "claude-fable-5",
                     "stop_reason": "tool_use",
                     "usage": {"input_tokens": 10, "output_tokens": 5},
                     "content": [
                         {"type": "text", "text": "Committing now."},
                         {"type": "tool_use", "id": f"toolu_{p}", "name": "Bash",
                          "input": {"command": "git commit -am fix"}}]}},
        {"type": "user", **_env(sid, f"{p}-t1", f"{day}T10:00:06Z", parentUuid=f"{p}-a1"),
         "message": {"role": "user", "content": [
             {"type": "tool_result", "tool_use_id": f"toolu_{p}",
              "content": "1 file changed", "is_error": False}]}},
        {"type": "assistant", **_env(sid, f"{p}-a2", f"{day}T10:00:07Z", parentUuid=f"{p}-t1"),
         "message": {"id": f"msg_{p}2", "role": "assistant", "model": "claude-fable-5",
                     "stop_reason": "end_turn",
                     "usage": {"input_tokens": 10, "output_tokens": 5},
                     "content": [{"type": "text", "text": "Committed. Running tests next."}]}},
        {"type": "user", **_env(sid, f"{p}-u2", f"{day}T10:01:00Z", parentUuid=f"{p}-a2"),
         "message": {"role": "user", "content": REPLY_TEXT}},
        {"type": "user", **_env(sid, f"{p}-i1", f"{day}T10:02:00Z", parentUuid=f"{p}-u2"),
         "message": {"role": "user", "content": [
             {"type": "text", "text": "[Request interrupted by user]"}]}},
        {"type": "user", **_env(sid, f"{p}-m1", f"{day}T10:03:00Z", isMeta=True),
         "message": {"role": "user", "content": "Caveat: local command output follows."}},
        {"type": "user", **_env(sid, f"{p}-c1", f"{day}T10:03:10Z"),
         "message": {"role": "user", "content": "<local-command-stdout>Total cost: $0.10</local-command-stdout>"}},
        {"type": "user", **_env(sid, f"{p}-r1", f"{day}T10:03:20Z"),
         "message": {"role": "user", "content": "<system-reminder>hook ran</system-reminder>"}},
        {"type": "user", **_env(sid, f"{p}-b1", f"{day}T10:03:25Z"),
         "message": {"role": "user", "content": "<bash-input>git status</bash-input>"}},
        {"type": "user", **_env(sid, f"{p}-b2", f"{day}T10:03:26Z"),
         "message": {"role": "user", "content": "<bash-stdout>clean</bash-stdout><bash-stderr></bash-stderr>"}},
        {"type": "user", **_env(sid, f"{p}-s1", f"{day}T10:03:30Z", isCompactSummary=True),
         "message": {"role": "user", "content": "This session is being continued from a previous conversation."}},
    ]
    return [json.dumps(line) for line in lines]


def _subagent_lines(parent_sid: str, day: str) -> list[str]:
    """A subagent transcript: its "user" is the orchestrating agent, and it
    carries the parent's sessionId, as real ones do."""
    lines = [
        {"type": "user", **_env(parent_sid, "sub-u1", f"{day}T10:00:30Z",
                                isSidechain=True, agentId="ag1"),
         "message": {"role": "user", "content": "Find the retry-count reads."}},
        {"type": "assistant", **_env(parent_sid, "sub-a1", f"{day}T10:00:40Z",
                                     isSidechain=True, agentId="ag1", parentUuid="sub-u1"),
         "message": {"id": "msg_sub", "role": "assistant", "model": "claude-fable-5",
                     "stop_reason": "end_turn",
                     "usage": {"input_tokens": 10, "output_tokens": 5},
                     "content": [{"type": "text", "text": "Two call sites."}]}},
        {"type": "user", **_env(parent_sid, "sub-u2", f"{day}T10:00:50Z",
                                isSidechain=True, agentId="ag1", parentUuid="sub-a1"),
         "message": {"role": "user", "content": "Check the second one too."}},
    ]
    return [json.dumps(line) for line in lines]


@pytest.fixture
def ingested(store, tmp_path):
    """A store holding two sessions of one project, ingested."""
    proj = tmp_path / "projects" / PROJECT_DIR
    proj.mkdir(parents=True)
    (proj / f"{SESSION_A}.jsonl").write_text("\n".join(_session_lines(SESSION_A, "2026-06-01")) + "\n")
    (proj / f"{SESSION_B}.jsonl").write_text("\n".join(_session_lines(SESSION_B, "2026-06-02")) + "\n")
    sub = proj / SESSION_A / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-ag1.jsonl").write_text("\n".join(_subagent_lines(SESSION_A, "2026-06-01")) + "\n")
    ingest_transcripts(store, root=tmp_path / "projects")
    return store


QUESTIONS = [
    {"question_id": "user_response", "question_version": "v1", "type": "choice",
     "text": "How does the reply respond to the assistant turn?",
     "options": [["approve", "accepts it"], ["correct", "says it is wrong"],
                 ["other", "none of the above"]]},
    {"question_id": "correction_kind", "question_version": "v1", "type": "choice",
     "text": "What kind of correction is it?",
     "options": [["process", "how the work was done"], ["fact", "something untrue"],
                 ["other", "none of the above"]]},
    {"question_id": "rule_violated", "question_version": "v1", "type": "choice",
     "text": "Which rule in force does the reply point at?", "options": None},
    {"question_id": "frustration", "question_version": "v1", "type": "score",
     "text": "How frustrated is the reply?", "options": None},
]


def _write_jsonl(path, rows) -> str:
    path.write_text("".join(orjson.dumps(r).decode() + "\n" for r in rows))
    return str(path)


def _label(sid: str, question_id: str, value, *, kind="model", labeler="jev",
           version="jev-1.13.0", probability=0.95, user=None, assistant=None,
           **over) -> dict:
    p = sid[0]
    row = {
        "unit_type": "exchange", "source": "test-corpus",
        "native_session_id": sid,
        "user_entry_uuid": user or f"{p}-u2",
        "assistant_entry_uuid": assistant or f"{p}-a2",
        "question_id": question_id, "question_version": "v1",
        "options_hash": None, "labeler_kind": kind, "labeler": labeler,
        "labeler_version": version if kind == "model" else None,
        "value": value,
        "probability": probability if kind == "model" else None,
        "probabilities": None, "confidence": None,
        "input_content_hash": "a" * 64 if kind == "model" else None,
        "state_truncated": False, "labeled_at": "2026-09-18T12:00:00Z",
    }
    row.update(over)
    return row


def _correction_labels(kind="model", labeler="jev", probability=0.95, **over) -> list[dict]:
    rows = []
    for sid in (SESSION_A, SESSION_B):
        rows.append(_label(sid, "user_response", "correct", kind=kind,
                           labeler=labeler, probability=probability, **over))
        rows.append(_label(sid, "correction_kind", "process", kind=kind,
                           labeler=labeler, probability=probability, **over))
    return rows


@pytest.fixture
def questions_file(tmp_path):
    return _write_jsonl(tmp_path / "questions.jsonl", QUESTIONS)


# ---------------------------------------------------------------------------
# options_hash
# ---------------------------------------------------------------------------


class TestOptionsHash:
    def test_matches_the_agreed_serialization(self):
        """Compact separators, non-ASCII kept, UTF-8 -- spelled out as the
        exact bytes, so this checks the recipe rather than itself."""
        pairs = [["approve", "accepts it"],
                 ["none", "the reply points at no listed rule — naïve 日本"]]
        expected_bytes = ('[["approve","accepts it"],["none","the reply points at '
                          'no listed rule — naïve 日本"]]').encode("utf-8")
        assert options_hash(pairs) == hashlib.sha256(expected_bytes).hexdigest()

    def test_order_matters(self):
        assert options_hash([["a", "x"], ["b", "y"]]) != options_hash([["b", "y"], ["a", "x"]])


# ---------------------------------------------------------------------------
# Question registration
# ---------------------------------------------------------------------------


class TestQuestions:
    def test_registers_with_version_parsed(self, store, questions_file):
        assert register_label_questions(store, questions_file) == 4
        ft = store.get_facet_type("user_response", 1)
        assert ft is not None
        assert ft.output_type.value == "text"
        assert "How does the reply respond" in ft.prompt_text
        assert store.get_facet_type("frustration", 1).output_type.value == "numeric"

    def test_idempotent(self, store, questions_file):
        register_label_questions(store, questions_file)
        assert register_label_questions(store, questions_file) == 0

    def test_changed_definition_under_same_version_is_refused(self, store, tmp_path, questions_file):
        register_label_questions(store, questions_file)
        edited = [dict(QUESTIONS[0], text="Reworded question")]
        with pytest.raises(ValueError, match="bump question_version"):
            register_label_questions(store, _write_jsonl(tmp_path / "q2.jsonl", edited))

    def test_questions_after_label_only_registration_are_accepted(self, ingested, tmp_path, questions_file):
        ingest_labels(ingested, path=_write_jsonl(
            tmp_path / "l.jsonl", [_label(SESSION_A, "user_response", "correct")]))
        assert register_label_questions(ingested, questions_file) == 3

    def test_bad_question_row_raises(self, store, tmp_path):
        bad = [{"question_id": "has spaces", "question_version": "v1", "type": "choice"}]
        with pytest.raises(ValueError, match="slug question_id"):
            register_label_questions(store, _write_jsonl(tmp_path / "q.jsonl", bad))


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------


class TestIngestLabels:
    def test_writes_labels_on_typed_replies(self, ingested, tmp_path, questions_file):
        path = _write_jsonl(tmp_path / "labels.jsonl", _correction_labels())
        stats = ingest_labels(ingested, path=path, questions=questions_file)
        assert stats["rows_written"] == 4
        assert stats["rejected"] == {}
        rows = ingested.list_message_facets(facet_id="user_response")
        assert {r.value_text for r in rows} == {"correct"}
        assert all(r.project_key is not None for r in rows)
        assert all(r.record_source == RecordSource.LABEL_INGEST for r in rows)
        assert all(r.labeler_kind == LabelerKind.MODEL for r in rows)

    def test_reingest_writes_nothing(self, ingested, tmp_path, questions_file):
        path = _write_jsonl(tmp_path / "labels.jsonl", _correction_labels())
        ingest_labels(ingested, path=path, questions=questions_file)
        again = ingest_labels(ingested, path=path, questions=questions_file)
        assert again["rows_written"] == 0
        assert again["rows_existing"] == 4
        assert ingested.count_rows("fact_message_facets") == 4

    def test_new_model_version_is_a_new_row(self, ingested, tmp_path, questions_file):
        ingest_labels(ingested, path=_write_jsonl(tmp_path / "l1.jsonl", _correction_labels()),
                      questions=questions_file)
        stats = ingest_labels(
            ingested, path=_write_jsonl(tmp_path / "l2.jsonl",
                                        _correction_labels(labeler_version="jev-1.14.0")))
        assert stats["rows_written"] == 4

    def test_load_log_recorded(self, ingested, tmp_path, questions_file):
        stats = ingest_labels(ingested, path=_write_jsonl(tmp_path / "l.jsonl", _correction_labels()),
                              questions=questions_file)
        run = ingested.get_load_run(stats["etl_run_id"])
        assert run.operation == "ingest_labels"
        assert run.rows_written == 4
        assert run.record_source == RecordSource.LABEL_INGEST

    @pytest.mark.parametrize("row,reason", [
        (_label(SESSION_A, "user_response", "correct", user="no-such-uuid"), "unknown_message"),
        (_label(SESSION_A, "user_response", "correct", user="a-t1"), "no_text"),
        (_label(SESSION_A, "user_response", "correct", user="a-m1"), "meta_entry"),
        (_label(SESSION_A, "user_response", "correct", user="a-s1"), "compact_summary"),
        (_label(SESSION_A, "user_response", "correct", user="a-c1"), "injected_text"),
        (_label(SESSION_A, "user_response", "correct", user="a-r1"), "injected_text"),
        (_label(SESSION_A, "user_response", "correct", user="a-i1"), "injected_text"),
        (_label(SESSION_A, "user_response", "correct", user="a-b1"), "injected_text"),
        (_label(SESSION_A, "user_response", "correct", user="a-b2"), "injected_text"),
        (_label(SESSION_A, "user_response", "correct")
         | {"native_session_id": f"{SESSION_A}/agent-ag1",
            "user_entry_uuid": "sub-u2", "assistant_entry_uuid": "sub-a1"},
         "subagent_message"),
        (_label(SESSION_A, "user_response", "correct", user="a-u1")
         | {"assistant_entry_uuid": None}, "no_assistant_turn"),
        (_label(SESSION_A, "user_response", "correct", user="a-a1"), "not_user_message"),
        (_label(SESSION_A, "user_response", "correct", assistant="no-such-uuid"), "unknown_context"),
        (_label(SESSION_A, "user_response", REPLY_TEXT), "bad_value"),
        (_label(SESSION_A, "user_response", "correct", kind="human", labeler="owner")
         | {"probability": 0.9}, "probability_on_non_model"),
        (_label(SESSION_A, "user_response", "correct", probability=1.5), "bad_probability"),
        (_label(SESSION_A, "user_response", "correct", unit_type="session"), "bad_unit_type"),
        (_label(SESSION_A, "user_response", "correct", labeler_kind="llm"), "bad_labeler_kind"),
        (_label(SESSION_A, "user_response", "correct", question_version="1.0"), "bad_question"),
        (_label(SESSION_A, "user_response", "correct", options_hash="short"), "bad_hash"),
        (_label(SESSION_A, "frustration", "very"), "bad_value"),
        (_label(SESSION_A, "user_response", "correct", probability=None), "missing_probability"),
        (_label(SESSION_A, "user_response", "correct", labeled_at=1758200000), "bad_labeled_at"),
        (_label(SESSION_A, "user_response", "correct", labeled_at="yesterday"), "bad_labeled_at"),
    ])
    def test_rejects_and_counts_by_reason(self, ingested, tmp_path, questions_file, row, reason):
        stats = ingest_labels(ingested, path=_write_jsonl(tmp_path / "l.jsonl", [row]),
                              questions=questions_file)
        assert stats["rows_written"] == 0
        assert stats["rejected"] == {reason: 1}
        assert ingested.count_rows("fact_message_facets") == 0

    def test_reply_text_cannot_enter_through_a_label(self, ingested, tmp_path, questions_file):
        """The slug rule is what keeps finding summaries clean: a label
        value carrying reply text is refused, not truncated."""
        ingest_labels(ingested, path=_write_jsonl(
            tmp_path / "l.jsonl", [_label(SESSION_A, "correction_kind", REPLY_TEXT)]),
            questions=questions_file)
        found = ingested.con.execute(
            "SELECT COUNT(*) FROM fact_message_facets WHERE value_text LIKE '%tests before%'"
        ).fetchone()[0]
        assert found == 0

    def test_malformed_line_counted(self, ingested, tmp_path, questions_file):
        path = tmp_path / "l.jsonl"
        path.write_text("{not json\n" + orjson.dumps(
            _label(SESSION_A, "user_response", "correct")).decode() + "\n")
        stats = ingest_labels(ingested, path=str(path), questions=questions_file)
        assert stats["rows_written"] == 1
        assert stats["rejected"] == {"malformed": 1}

    def test_interrupt_unit_on_marker_message(self, ingested, tmp_path, questions_file):
        row = _label(SESSION_A, "interrupted", "yes", kind="rule", labeler="keyword",
                     unit_type="interrupt", user="a-i1")
        stats = ingest_labels(ingested, path=_write_jsonl(tmp_path / "l.jsonl", [row]),
                              questions=questions_file)
        assert stats["rows_written"] == 1
        (label,) = ingested.list_message_facets(facet_id="interrupted")
        assert label.unit_type == LabelUnit.INTERRUPT
        assert label.probability is None

    def test_rejected_rows_register_no_questions(self, ingested, tmp_path):
        before = len(ingested.list_facet_types())
        stats = ingest_labels(ingested, path=_write_jsonl(
            tmp_path / "l.jsonl", [_label(SESSION_A, "novel_question", "x", user="no-such-uuid")]))
        assert stats["rejected"] == {"unknown_message": 1}
        assert len(ingested.list_facet_types()) == before

    def test_unregistered_question_is_registered_from_the_value(self, ingested, tmp_path):
        stats = ingest_labels(ingested, path=_write_jsonl(
            tmp_path / "l.jsonl", [_label(SESSION_A, "frustration", 2)]))
        assert stats["rows_written"] == 1
        ft = ingested.get_facet_type("frustration", 1)
        assert ft.output_type.value == "numeric"
        assert ft.prompt_text is None


class TestStoreFailsClosed:
    def _facet(self, store, uuid="a-u2", facet_id="user_response"):
        sk = store.session_key_for(RecordSource.TRANSCRIPT_INGEST, SESSION_A)
        return MessageFacet(
            unit_type=LabelUnit.EXCHANGE, session_key=sk,
            message_key=store.message_key_for(sk, uuid), facet_id=facet_id,
            labeler_kind=LabelerKind.HUMAN, labeler="owner", value_text="correct")

    def test_unregistered_question_raises(self, ingested):
        with pytest.raises(ValueError, match="not registered"):
            ingested.insert_message_facet(self._facet(ingested))

    def test_non_user_message_raises(self, ingested, questions_file):
        register_label_questions(ingested, questions_file)
        with pytest.raises(ValueError, match="not a user message"):
            ingested.insert_message_facet(self._facet(ingested, uuid="a-a1"))


# ---------------------------------------------------------------------------
# View and detectors
# ---------------------------------------------------------------------------


class TestLabeledExchangesView:
    def test_one_row_per_reply_per_labeler(self, ingested, tmp_path, questions_file):
        rows = _correction_labels() + _correction_labels(kind="human", labeler="owner")
        ingest_labels(ingested, path=_write_jsonl(tmp_path / "l.jsonl", rows),
                      questions=questions_file)
        pivot = ingested.con.execute(
            """SELECT labeler, user_response, correction_kind, user_response_p
               FROM v_labeled_exchanges ORDER BY labeler, session_key""").fetchall()
        assert [(r[0], r[1], r[2]) for r in pivot] == [
            ("jev", "correct", "process"), ("jev", "correct", "process"),
            ("owner", "correct", "process"), ("owner", "correct", "process"),
        ]
        assert [r[3] for r in pivot if r[0] == "owner"] == [None, None]


class TestLabelDetectors:
    def _findings(self, store, finding_type):
        return store.list_findings(finding_type=finding_type)

    def test_recurring_model_correction_is_a_finding(self, ingested, tmp_path, questions_file):
        ingest_labels(ingested, path=_write_jsonl(tmp_path / "l.jsonl", _correction_labels()),
                      questions=questions_file)
        run_couch(ingested, include_filesystem=False)
        (f,) = self._findings(ingested, "labeled_correction_recurring")
        assert f.occurrence_count == 2
        assert len(f.evidence_session_keys) == 2
        assert f.summary.startswith("process:")
        assert f"labeled by jev (model, p>={LABEL_MIN_PROBABILITY})" in f.summary
        assert "tests before" not in f.summary

    def test_below_probability_floor_does_not_count(self, ingested, tmp_path, questions_file):
        low = LABEL_MIN_PROBABILITY - 0.1
        ingest_labels(ingested, path=_write_jsonl(
            tmp_path / "l.jsonl", _correction_labels(probability=low)),
            questions=questions_file)
        run_couch(ingested, include_filesystem=False)
        assert self._findings(ingested, "labeled_correction_recurring") == []

    def test_newer_labeler_version_replaces_the_older(self, ingested, tmp_path, questions_file):
        """jev-1.13 calls both replies process corrections; jev-1.14, later,
        calls session A's reply an approval. Only the latest label per
        labeler counts, so one conversation remains and nothing recurs."""
        old = _correction_labels(labeler_version="jev-1.13.0", labeled_at="2026-09-01T00:00:00Z")
        new = [_label(SESSION_A, "user_response", "approve", version="jev-1.14.0",
                      labeled_at="2026-09-10T00:00:00Z")]
        ingest_labels(ingested, path=_write_jsonl(tmp_path / "l.jsonl", old + new),
                      questions=questions_file)
        run_couch(ingested, include_filesystem=False)
        assert self._findings(ingested, "labeled_correction_recurring") == []

    def test_model_label_without_probability_does_not_pass_the_floor(self, ingested, questions_file):
        """The ingest refuses these; the detector must not count one that
        arrives another way as if it were certain."""
        register_label_questions(ingested, questions_file)
        for sid in (SESSION_A, SESSION_B):
            sk = ingested.session_key_for(RecordSource.TRANSCRIPT_INGEST, sid)
            for qid, value in (("user_response", "correct"), ("correction_kind", "process")):
                ingested.insert_message_facet(MessageFacet(
                    unit_type=LabelUnit.EXCHANGE, session_key=sk,
                    message_key=ingested.message_key_for(sk, f"{sid[0]}-u2"),
                    facet_id=qid, labeler_kind=LabelerKind.MODEL, labeler="jev",
                    labeler_version="jev-1.13.0", value_text=value))
        run_couch(ingested, include_filesystem=False)
        assert self._findings(ingested, "labeled_correction_recurring") == []

    def test_one_session_is_not_a_pattern(self, ingested, tmp_path, questions_file):
        rows = [r for r in _correction_labels() if r["native_session_id"] == SESSION_A]
        ingest_labels(ingested, path=_write_jsonl(tmp_path / "l.jsonl", rows),
                      questions=questions_file)
        run_couch(ingested, include_filesystem=False)
        assert self._findings(ingested, "labeled_correction_recurring") == []

    def test_human_labels_count_without_probability(self, ingested, tmp_path, questions_file):
        ingest_labels(ingested, path=_write_jsonl(
            tmp_path / "l.jsonl", _correction_labels(kind="human", labeler="owner")),
            questions=questions_file)
        run_couch(ingested, include_filesystem=False)
        (f,) = self._findings(ingested, "labeled_correction_recurring")
        assert "labeled by owner (human)" in f.summary

    def test_rule_violations_exclude_none(self, ingested, tmp_path, questions_file):
        rows = [_label(sid, "rule_violated", "ask-before-commit") for sid in (SESSION_A, SESSION_B)]
        rows += [_label(sid, "rule_violated", "none", labeler="claude", version="c-1")
                 for sid in (SESSION_A, SESSION_B)]
        ingest_labels(ingested, path=_write_jsonl(tmp_path / "l.jsonl", rows),
                      questions=questions_file)
        run_couch(ingested, include_filesystem=False)
        (f,) = self._findings(ingested, "labeled_rule_violation_recurring")
        assert f.summary.startswith("ask-before-commit:")


class TestForkedSessions:
    """A resumed or forked session copies earlier entries -- same uuid, text
    and timestamp -- into a new file under its own sessionId. One reply is
    then two fact_message rows in two sessions, and must still count once."""

    FORK = "ffffffff-0000-0000-0000-00000000000f"

    @pytest.fixture
    def with_fork(self, tmp_path, store):
        proj = tmp_path / "projects" / PROJECT_DIR
        proj.mkdir(parents=True)
        (proj / f"{SESSION_A}.jsonl").write_text("\n".join(_session_lines(SESSION_A, "2026-06-01")) + "\n")
        (proj / f"{SESSION_B}.jsonl").write_text("\n".join(_session_lines(SESSION_B, "2026-06-02")) + "\n")
        copied = [json.dumps({**json.loads(line), "sessionId": self.FORK})
                  for line in _session_lines(SESSION_A, "2026-06-01")]
        (proj / f"{self.FORK}.jsonl").write_text("\n".join(copied) + "\n")
        ingest_transcripts(store, root=tmp_path / "projects")
        return store

    def _labels_on_both_copies(self):
        rows = _correction_labels()  # sessions A and B
        rows += [r | {"native_session_id": self.FORK} for r in rows
                 if r["native_session_id"] == SESSION_A]
        return rows

    def test_copy_is_one_reply_in_one_conversation(self, with_fork, tmp_path, questions_file):
        rows = [r for r in self._labels_on_both_copies() if r["native_session_id"] != SESSION_B]
        ingest_labels(with_fork, path=_write_jsonl(tmp_path / "l.jsonl", rows),
                      questions=questions_file)
        assert with_fork.count_rows("fact_message_facets") == 4  # both copies labeled
        run_couch(with_fork, include_filesystem=False)
        assert self._findings(with_fork) == []

    def test_copies_do_not_inflate_counts(self, with_fork, tmp_path, questions_file):
        ingest_labels(with_fork, path=_write_jsonl(tmp_path / "l.jsonl", self._labels_on_both_copies()),
                      questions=questions_file)
        run_couch(with_fork, include_filesystem=False)
        (f,) = self._findings(with_fork)
        assert f.occurrence_count == 2
        # Counted as two conversations; evidence names every session that
        # holds a labeled reply, the resumed copy included.
        assert len(f.evidence_session_keys) == 3
        assert f.summary.startswith("process: 2 corrective repl(ies) across 2 session(s)")

    def test_evidence_names_the_session_holding_the_reply(self, with_fork, tmp_path, questions_file):
        """A reply typed only in the resumed file is evidenced by that file,
        not by the original it continues."""
        fork_key = with_fork.session_key_for(RecordSource.TRANSCRIPT_INGEST, self.FORK)
        rows = [r | {"native_session_id": self.FORK} for r in _correction_labels()
                if r["native_session_id"] == SESSION_A]
        rows += [r for r in _correction_labels() if r["native_session_id"] == SESSION_B]
        ingest_labels(with_fork, path=_write_jsonl(tmp_path / "l.jsonl", rows),
                      questions=questions_file)
        run_couch(with_fork, include_filesystem=False)
        (f,) = self._findings(with_fork)
        assert fork_key in f.evidence_session_keys

    @staticmethod
    def _findings(store):
        return store.list_findings(finding_type="labeled_correction_recurring")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_ingest_labels(tmp_path):
    from freud_schema.cli import main

    db = str(tmp_path / "w.duckdb")
    proj = tmp_path / "projects" / PROJECT_DIR
    proj.mkdir(parents=True)
    (proj / f"{SESSION_A}.jsonl").write_text("\n".join(_session_lines(SESSION_A, "2026-06-01")) + "\n")
    main(["--db", db, "ingest", "transcripts", "--root", str(tmp_path / "projects")])
    questions = _write_jsonl(tmp_path / "questions.jsonl", QUESTIONS)
    labels = _write_jsonl(tmp_path / "labels.jsonl", [
        _label(SESSION_A, "user_response", "correct"),
        _label(SESSION_A, "user_response", "correct", user="no-such-uuid"),
    ])
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        main(["--db", db, "ingest", "labels", "--file", labels, "--questions", questions])
    finally:
        sys.stdout = old
    out = buf.getvalue()
    assert "rows written:              1" in out
    assert "rejected, unknown_message: 1" in out
