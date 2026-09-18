"""Guards on the synthetic agent sessions (data/synthetic/agent_sessions/)
and their planted answer key (data/synthetic/eval/exchange_labels.jsonl).

The key is what a labeler gets scored against before any real session
text is used, so a wrong key row silently mis-scores every labeler. These
tests re-derive what each key row claims from the transcripts and the
rule history on disk, rather than trusting the generator that wrote both:

- every key row names a typed reply, never a filter trap (tool results,
  meta entries, command output, hook reminders, compact summaries,
  interruption markers, subagent transcripts), and the assistant entry it
  names is the last one before that reply
- every trap kind is present, so a reply filter is actually exercised
- rule_violated values and option hashes match the rule set in force on
  the session's date, rebuilt from eval/exchange_rules_history.jsonl
- the key ingests with nothing rejected, and the label detectors fire on it
- the ingest refuses a label on every user entry that is not a unit, on
  its own, so a labeler's filter bug cannot put findings on a trap
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import orjson
import pytest

from freud_schema.couch import run_couch
from freud_schema.ingest import ingest_labels, ingest_transcripts, options_hash

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS = REPO_ROOT / "data" / "synthetic"
SESSIONS = CORPUS / "agent_sessions"
KEY = CORPUS / "eval" / "exchange_labels.jsonl"
QUESTIONS = CORPUS / "eval" / "exchange_questions.jsonl"

_TRAP_PREFIXES = ("<command-", "<local-command", "<system-reminder>",
                  "[Request interrupted")


def _jsonl(path: Path) -> list[dict]:
    return [orjson.loads(line) for line in path.read_bytes().splitlines() if line.strip()]


@pytest.fixture(scope="module")
def key() -> list[dict]:
    return _jsonl(KEY)


@pytest.fixture(scope="module")
def transcripts() -> dict[str, dict]:
    """native_session_id -> {project_dir, day, entries} for root sessions."""
    out = {}
    for proj in sorted(p for p in SESSIONS.iterdir() if p.is_dir()):
        for f in sorted(proj.glob("*.jsonl")):
            entries = _jsonl(f)
            out[f.stem] = {"project_dir": proj.name,
                           "day": entries[0]["timestamp"][:10],
                           "entries": entries}
    return out


def _is_typed_reply(entry: dict) -> bool:
    if entry["type"] != "user" or entry.get("isMeta") or entry.get("isCompactSummary"):
        return False
    content = entry["message"]["content"]
    return isinstance(content, str) and not content.startswith(_TRAP_PREFIXES)


def test_key_rows_name_typed_replies_and_the_turn_before(key, transcripts):
    for row in key:
        entries = transcripts[row["native_session_id"]]["entries"]
        idx = {e["uuid"]: i for i, e in enumerate(entries)}
        reply_i = idx[row["user_entry_uuid"]]
        assert _is_typed_reply(entries[reply_i]), row
        last_assistant = max(i for i, e in enumerate(entries[:reply_i])
                             if e["type"] == "assistant")
        assert entries[last_assistant]["uuid"] == row["assistant_entry_uuid"], row


def test_every_trap_kind_is_present(transcripts):
    seen = set()
    for t in transcripts.values():
        for e in t["entries"]:
            if e["type"] != "user":
                continue
            content = e["message"]["content"]
            if e.get("isMeta"):
                seen.add("meta")
            elif e.get("isCompactSummary"):
                seen.add("compact")
            elif isinstance(content, list):
                seen.add("tool_result")
            elif content.startswith("<command-"):
                seen.add("command")
            elif content.startswith("<system-reminder>"):
                seen.add("reminder")
            elif content.startswith("[Request interrupted"):
                seen.add("interrupt")
    assert seen == {"meta", "compact", "tool_result", "command", "reminder", "interrupt"}
    assert list(SESSIONS.glob("*/*/subagents/agent-*.jsonl")), "no subagent transcripts"


def test_correction_kind_only_on_corrections(key):
    response = {(r["native_session_id"], r["user_entry_uuid"]): r["value"]
                for r in key if r["question_id"] == "user_response"}
    for r in key:
        if r["question_id"] == "correction_kind":
            assert response[(r["native_session_id"], r["user_entry_uuid"])] == "correct"


def test_rule_violated_matches_rules_in_force(key, transcripts):
    history = _jsonl(CORPUS / "eval" / "exchange_rules_history.jsonl")
    for r in (r for r in key if r["question_id"] == "rule_violated"):
        t = transcripts[r["native_session_id"]]
        in_force = sorted(
            (h["rule_id"], h["statement"]) for h in history
            if h["project_dir"] == t["project_dir"]
            and h["effective_from"] <= t["day"]
            and (h["effective_to"] is None or t["day"] < h["effective_to"]))
        pairs = [list(p) for p in in_force] + [["none", "the reply points at no listed rule"]]
        assert r["value"] in {p[0] for p in pairs}, r
        assert r["options_hash"] == options_hash(pairs), r


def test_a_correction_before_its_rule_exists_is_keyed_none(key, transcripts):
    """The same unasked-push reply appears before and after ask-before-push
    took effect; only the later one may point at the rule."""
    reply = "Don't push. I didn't ask you to push anything."
    by_uuid = {e["uuid"]: e for t in transcripts.values() for e in t["entries"]}
    values = sorted(r["value"] for r in key
                    if r["question_id"] == "rule_violated"
                    and by_uuid[r["user_entry_uuid"]]["message"]["content"] == reply)
    assert values == ["ask-before-push", "none"]


def test_static_option_hashes_match_the_questions_file(key):
    questions = {q["question_id"]: q for q in _jsonl(QUESTIONS)}
    for qid in ("user_response", "correction_kind"):
        expected = options_hash(questions[qid]["options"])
        assert {r["options_hash"] for r in key if r["question_id"] == qid} == {expected}


def test_ingest_refuses_labels_on_every_non_unit_entry(store, key, tmp_path):
    """The ingest enforces the typed-reply rule on its own, so a labeler
    bug cannot land labels on a trap. Point an exchange label at every user
    entry the key does not name -- trap entries, opening prompts and all
    subagent entries -- and expect every one refused, none unknown."""
    ingest_transcripts(store, root=SESSIONS)
    units = {(r["native_session_id"], r["user_entry_uuid"]) for r in key}
    rows = []
    for f in sorted(SESSIONS.glob("*/*.jsonl")) + sorted(SESSIONS.glob("*/*/subagents/*.jsonl")):
        native = (f.stem if f.parent.name != "subagents"
                  else f"{f.parent.parent.name}/{f.stem}")
        last_assistant = None
        for e in _jsonl(f):
            if e["type"] == "assistant":
                last_assistant = e["uuid"]
            elif e["type"] == "user" and (native, e["uuid"]) not in units:
                rows.append({
                    "unit_type": "exchange", "native_session_id": native,
                    "user_entry_uuid": e["uuid"],
                    "assistant_entry_uuid": last_assistant,
                    "question_id": "user_response", "question_version": "v1",
                    "labeler_kind": "key", "labeler": "synthetic",
                    "value": "correct"})
    labels = tmp_path / "non_unit_labels.jsonl"
    labels.write_bytes(b"".join(orjson.dumps(r) + b"\n" for r in rows))
    stats = ingest_labels(store, path=labels, questions=QUESTIONS)
    assert stats["rows_written"] == 0
    assert sum(stats["rejected"].values()) == len(rows)
    assert "unknown_message" not in stats["rejected"]
    assert set(stats["rejected"]) == {
        "no_text", "meta_entry", "compact_summary", "subagent_message",
        "injected_text", "no_assistant_turn"}


def test_key_ingests_and_detectors_fire(store):
    ingest_transcripts(store, root=SESSIONS)
    rows = _jsonl(KEY)
    stats = ingest_labels(store, path=KEY, questions=QUESTIONS)
    assert stats["rejected"] == {}
    assert stats["rows_written"] == len(rows)
    run_couch(store, include_filesystem=False)
    counts = defaultdict(int)
    for f in store.list_findings():
        counts[f.finding_type] += 1
    assert counts["labeled_correction_recurring"] > 0
    assert counts["labeled_rule_violation_recurring"] > 0
