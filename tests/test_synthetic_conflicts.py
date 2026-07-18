"""Guards on the AUTHORITY / STALENESS / CONFLICT eval set (data/synthetic/).

This is the machine-readable ground truth a structuring agent uses to resolve
competing "facts" by source authority, recency, and system-of-record rules --
not naive latest-wins. Three artifacts carry the load: the conflict answer key
(eval/conflicts.jsonl), the system-of-record registry, and the source-authority
scoring model. These tests pin their shape and the invariants the eval depends on.

Note: we deliberately do NOT assert that competing_sources paths exist on disk.
Some referenced files (time/*, decks/*) are produced by other generators in
parallel; the main session validates on-disk existence at integration time. Here
we only assert each path is a well-formed relative path under data/synthetic/.
"""

import csv
from pathlib import Path

import orjson
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS = REPO_ROOT / "data" / "synthetic"

RESOLUTION_RULES = {
    "recency_supersession",
    "process_status",
    "document_type_authority",
    "system_of_record",
    "org_authority",
}

CONFLICT_KEYS = {
    "conflict_id",
    "question",
    "fact_type",
    "competing_sources",
    "correct_value",
    "winning_source_path",
    "resolution_rule",
    "rationale",
}

SOURCE_KEYS = {"path", "stated_value", "as_of", "authored_by", "source_type"}


def _is_wellformed_corpus_path(path: str) -> bool:
    """A relative POSIX path that stays under data/synthetic/ (no leading slash,
    no drive, no parent escapes). Existence is NOT checked (see module docstring)."""
    if not isinstance(path, str) or not path:
        return False
    p = Path(path)
    return not p.is_absolute() and ".." not in p.parts and "\\" not in path


@pytest.fixture(scope="module")
def conflicts() -> list[dict]:
    path = CORPUS / "eval" / "conflicts.jsonl"
    return [orjson.loads(line) for line in path.read_bytes().splitlines()
            if line.strip()]


@pytest.fixture(scope="module")
def decisions() -> list[dict]:
    path = CORPUS / "governance" / "decision_log.jsonl"
    return [orjson.loads(line) for line in path.read_bytes().splitlines()
            if line.strip()]


def test_conflicts_is_valid_jsonl(conflicts):
    assert len(conflicts) >= 7
    ids = [c["conflict_id"] for c in conflicts]
    assert len(ids) == len(set(ids))


def test_conflict_records_have_required_keys(conflicts):
    for c in conflicts:
        assert CONFLICT_KEYS <= set(c.keys()), c.get("conflict_id")
        assert c["correct_value"] not in (None, ""), c["conflict_id"]
        assert isinstance(c["competing_sources"], list) and c["competing_sources"]
        for src in c["competing_sources"]:
            assert SOURCE_KEYS <= set(src.keys()), c["conflict_id"]


def test_resolution_rules_are_allowed(conflicts):
    for c in conflicts:
        assert c["resolution_rule"] in RESOLUTION_RULES, c["conflict_id"]


def test_winning_source_is_a_competing_source(conflicts):
    for c in conflicts:
        paths = {src["path"] for src in c["competing_sources"]}
        assert c["winning_source_path"] in paths, c["conflict_id"]


def test_competing_source_paths_are_wellformed(conflicts):
    # Existence is not asserted here -- other generators create some paths in
    # parallel; only shape is checked (see module docstring).
    for c in conflicts:
        for src in c["competing_sources"]:
            assert _is_wellformed_corpus_path(src["path"]), \
                (c["conflict_id"], src["path"])


def test_system_of_record_registry_columns():
    path = CORPUS / "governance" / "system_of_record.csv"
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        expected = {"domain", "fact_type", "system_of_record",
                    "source_path_glob", "authority_note"}
        assert set(reader.fieldnames or []) == expected
        rows = list(reader)
    assert len(rows) >= 8
    # CRM (pipeline) must be distinguished from Finance (recognized revenue).
    by_sor = {r["fact_type"]: r["system_of_record"] for r in rows}
    assert by_sor["recognized_revenue_arr"] == "Finance GL"
    assert by_sor["pipeline_stage_owner"] == "CRM"


def test_source_authority_scoring_model():
    path = CORPUS / "governance" / "source_authority.csv"
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        expected = {"source_type", "base_authority", "half_life_days",
                    "decay_class", "note"}
        assert set(reader.fieldnames or []) == expected
        rows = list(reader)
    assert len(rows) >= 10
    auth = {}
    for r in rows:
        val = float(r["base_authority"])
        assert 0.0 <= val <= 1.0, r["source_type"]
        assert float(r["half_life_days"]) > 0, r["source_type"]
        auth[r["source_type"]] = val
    # External/news are the least authoritative; decisions/approved-policy the most.
    assert auth["external_analyst"] <= 0.2
    assert auth["news"] <= 0.2
    assert auth["decision_log"] >= 0.85
    assert auth["approved_policy"] >= 0.85
    # The intended ordering the eval scores against.
    assert auth["external_analyst"] < auth["proposal"] < auth["knowledge_base"]
    assert auth["knowledge_base"] < auth["hris"]
    assert auth["hris"] <= auth["decision_log"]


def test_decision_log_has_one_reversal_and_the_multiregion_deferral(decisions):
    reversed_ = [d for d in decisions if d["status"] == "reversed"]
    assert len(reversed_) == 1, [d["decision_id"] for d in reversed_]

    deferrals = [d for d in decisions
                 if d["status"] == "decided"
                 and "defer" in d["decision"].lower()
                 and "active-active" in d["decision"].lower()]
    assert deferrals, "expected the multi-region deferral decided record"


def test_every_competing_source_path_exists(conflicts):
    """Integration guard: every path a conflict cites must resolve on disk.
    (The authoring agent could not check this -- some paths are produced by
    sibling generators -- so it is asserted here once the corpus is whole.)"""
    for c in conflicts:
        for src in c["competing_sources"]:
            assert (CORPUS / src["path"]).is_file(), (c["conflict_id"], src["path"])
