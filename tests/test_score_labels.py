"""scripts/score_labels.py and ExperimentStore.query_label_pairs.

The scorer turns labels into the numbers that decide whether a model's
confidence can route work, so its arithmetic is pinned against labels whose
right answers are known by construction: a model labeler built from the
synthetic answer key, wrong on a chosen few replies at a chosen probability.
"""

from __future__ import annotations

import importlib.util
import io
from pathlib import Path

import orjson
import pytest

from freud_schema.db import connect
from freud_schema.ingest import ingest_labels, ingest_transcripts
from freud_schema.store import ExperimentStore
from freud_schema.tables import LabelerKind

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "score_labels.py"
KEY = REPO_ROOT / "data" / "synthetic" / "eval" / "exchange_labels.jsonl"
QUESTIONS = REPO_ROOT / "data" / "synthetic" / "eval" / "exchange_questions.jsonl"
SESSIONS = REPO_ROOT / "data" / "synthetic" / "agent_sessions"
WRONG = 5  # user_response rows the simulated model gets wrong, at p=0.55
FRUSTRATION_WRONG = 3


def _load_script():
    spec = importlib.util.spec_from_file_location("score_labels", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def scorer():
    return _load_script()


def _key_rows() -> list[dict]:
    return [orjson.loads(line) for line in KEY.read_bytes().splitlines() if line.strip()]


def _model_rows() -> list[dict]:
    """A model labeler derived from the key: user_response right except the
    first WRONG replies (p=0.55 when wrong, 0.95 when right); frustration
    off by one level on the first FRUSTRATION_WRONG replies."""
    out = []
    ur = sorted((r for r in _key_rows() if r["question_id"] == "user_response"),
                key=lambda r: r["user_entry_uuid"])
    for i, r in enumerate(ur):
        wrong = i < WRONG
        value = ("approve" if r["value"] != "approve" else "other") if wrong else r["value"]
        out.append({**r, "labeler_kind": "model", "labeler": "sim",
                    "labeler_version": "sim-1", "value": value,
                    "probability": 0.55 if wrong else 0.95,
                    "input_content_hash": "0" * 64,
                    "labeled_at": "2026-09-18T20:00:00Z"})
    fr = sorted((r for r in _key_rows() if r["question_id"] == "frustration"),
                key=lambda r: r["user_entry_uuid"])
    for i, r in enumerate(fr):
        value = (r["value"] + 1) % 3 if i < FRUSTRATION_WRONG else r["value"]
        out.append({**r, "labeler_kind": "model", "labeler": "sim",
                    "labeler_version": "sim-1", "value": value, "probability": 0.9,
                    "input_content_hash": "0" * 64,
                    "labeled_at": "2026-09-18T20:00:00Z"})
    return out


def _write(path: Path, rows: list[dict]) -> Path:
    path.write_bytes(b"".join(orjson.dumps(r) + b"\n" for r in rows))
    return path


@pytest.fixture
def scored(store, tmp_path):
    ingest_transcripts(store, root=SESSIONS)
    ingest_labels(store, path=KEY, questions=QUESTIONS)
    ingest_labels(store, path=_write(tmp_path / "sim.jsonl", _model_rows()))
    return store


class TestWilson:
    def test_empty_is_uninformative(self, scorer):
        assert scorer.wilson(0, 0) == (0.0, 1.0)

    def test_perfect_small_sample_is_not_certain(self, scorer):
        lo, hi = scorer.wilson(10, 10)
        assert hi == 1.0 and 0.72 < lo < 0.73

    def test_half_is_symmetric(self, scorer):
        lo, hi = scorer.wilson(5, 10)
        assert abs((0.5 - lo) - (hi - 0.5)) < 1e-9


class TestScores:
    def _pairs(self, store, labeler="sim"):
        return [p for p in store.query_label_pairs(LabelerKind.KEY)
                if p["labeler"] == labeler]

    def test_accuracy_and_majority_on_the_same_replies(self, scorer, scored):
        rows = {r["facet_id"]: r for r in scorer.accuracy(self._pairs(scored))}
        ur = rows["user_response"]
        assert (ur["n"], ur["hits"]) == (56, 56 - WRONG)
        key_ur = [r["value"] for r in _key_rows() if r["question_id"] == "user_response"]
        top = max(key_ur.count(v) for v in set(key_ur))
        assert ur["majority"] == pytest.approx(top / len(key_ur))
        assert ur["low"] < ur["accuracy"] < ur["high"]
        fr = rows["frustration"]
        assert (fr["n"], fr["hits"]) == (56, 56 - FRUSTRATION_WRONG)

    def test_calibration_buckets(self, scorer, scored):
        cal = {(r["facet_id"], r["bucket"]): r
               for r in scorer.calibration(self._pairs(scored))}
        high, low = cal[("user_response", 0.9)], cal[("user_response", 0.5)]
        assert (high["n"], high["observed"]) == (56 - WRONG, 1.0)
        assert (low["n"], low["observed"]) == (WRONG, 0.0)
        assert high["stated"] == pytest.approx(0.95)

    def test_routing(self, scorer, scored):
        r = {(x["facet_id"], x["threshold"]): x for x in scorer.routing(self._pairs(scored))}
        at_09 = r[("user_response", 0.9)]
        assert at_09["share"] == pytest.approx((56 - WRONG) / 56)
        assert at_09["accuracy"] == 1.0
        assert r[("user_response", 0.6)]["n"] == 56 - WRONG

    def test_confusion_for_a_score_question(self, scorer, scored):
        (counts,) = scorer.confusion(self._pairs(scored), "frustration").values()
        assert sum(counts.values()) == 56
        off = sum(n for (a, b), n in counts.items() if a != b)
        assert off == FRUSTRATION_WRONG


class TestReference:
    def _human(self, tmp_path, labeler: str, n: int) -> Path:
        rows = [r for r in _key_rows() if r["question_id"] == "user_response"][:n]
        return _write(tmp_path / f"{labeler}.jsonl",
                      [{**r, "labeler_kind": "human", "labeler": labeler,
                        "labeler_version": None} for r in rows])

    def test_score_against_a_person(self, scored, tmp_path):
        ingest_labels(scored, path=self._human(tmp_path, "owner", 10))
        pairs = scored.query_label_pairs(LabelerKind.HUMAN, "owner")
        sim = [p for p in pairs if p["labeler"] == "sim"]
        assert len(sim) == 10
        assert not any(p["labeler"] == "owner" for p in pairs)

    def test_ambiguous_reference_is_refused(self, scored, tmp_path):
        ingest_labels(scored, path=self._human(tmp_path, "owner", 5))
        ingest_labels(scored, path=self._human(tmp_path, "reviewer", 5))
        with pytest.raises(ValueError, match="name the reference labeler"):
            scored.query_label_pairs(LabelerKind.HUMAN)


class TestScript:
    def test_throwaway_mode(self, scorer, tmp_path):
        labels = _write(tmp_path / "sim.jsonl", _model_rows())
        out = io.StringIO()
        scorer.main([str(labels)], out=out)
        text = out.getvalue()
        assert "sim.jsonl: 112 read, 112 written, rejected: none" in text
        assert "Accuracy against key" in text
        assert "model:sim" in text and "Calibration" in text and "Routing" in text
        assert "frustration: reference level -> labeler level" in text

    def test_warehouse_mode_reads_what_is_there(self, scorer, tmp_path):
        db = str(tmp_path / "w.duckdb")
        with ExperimentStore(connect(db)) as store:
            ingest_transcripts(store, root=SESSIONS)
            ingest_labels(store, path=KEY, questions=QUESTIONS)
            ingest_labels(store, path=_write(tmp_path / "sim.jsonl", _model_rows()))
        out = io.StringIO()
        scorer.main(["--db", db], out=out)
        assert "model:sim" in out.getvalue()

    def test_warehouse_mode_refuses_label_files(self, scorer, tmp_path):
        with pytest.raises(SystemExit):
            scorer.main(["--db", str(tmp_path / "w.duckdb"), "x.jsonl"])
