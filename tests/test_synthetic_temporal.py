"""Guards on the TIME/STALENESS corpus (data/synthetic/time/).

These files carry structured ground truth for temporal reasoning: as-of org
snapshots derived from HRIS, product-roadmap evolution across three dates,
knowledge-base revision history (the deprecated batch-limit staleness trap),
and a policy supersession chain (draft vs approved). Each test recomputes or
pins the property the corpus advertises. Mirrors the style of the other
corpus tests: REPO_ROOT/CORPUS constants, csv/orjson parsing.
"""

import csv
from datetime import date
from pathlib import Path

import orjson
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS = REPO_ROOT / "data" / "synthetic"
TIME = CORPUS / "time"


def _csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _jsonl(path: Path) -> list[dict]:
    return [orjson.loads(line) for line in path.read_bytes().splitlines()
            if line.strip()]


def _d(s: str) -> date:
    return date.fromisoformat(s[:10])


def _active_at(e: dict, ref: date) -> bool:
    if _d(e["hire_date"]) > ref:
        return False
    t = e["termination_date"]
    if t and _d(t) <= ref:
        return False
    return True


@pytest.fixture(scope="module")
def employees() -> list[dict]:
    return _csv(CORPUS / "internal" / "hris" / "employees.csv")


# ---------------------------------------------------------------------------
# Org-chart snapshots
# ---------------------------------------------------------------------------

_SNAPSHOT_DATES = ["2026-02-01", "2026-04-15", "2026-06-30"]


def _snapshot(asof: str) -> list[dict]:
    return _csv(TIME / "snapshots" / f"org_chart_{asof}.csv")


def test_org_snapshots_active_membership(employees):
    """Every snapshot is exactly the set of employees active as of its date,
    and every listed employee_id resolves to the HRIS roster."""
    by_id = {e["employee_id"]: e for e in employees}
    for asof in _SNAPSHOT_DATES:
        ref = _d(asof)
        rows = _snapshot(asof)
        present_ids = {r["employee_id"] for r in rows}
        expected = {e["employee_id"] for e in employees if _active_at(e, ref)}
        assert present_ids == expected, asof
        for r in rows:
            assert r["employee_id"] in by_id, r["employee_id"]
            assert r["status_as_of"] == "active"
        # Sorted by employee_id (numeric part).
        nums = [int(r["employee_id"].split("-")[1]) for r in rows]
        assert nums == sorted(nums), asof


def test_org_snapshot_derek_absent_after_termination():
    """EMP-1042 (terminated 2026-03-31): present 02-01, gone thereafter."""
    ids_0201 = {r["employee_id"] for r in _snapshot("2026-02-01")}
    ids_0415 = {r["employee_id"] for r in _snapshot("2026-04-15")}
    ids_0630 = {r["employee_id"] for r in _snapshot("2026-06-30")}
    assert "EMP-1042" in ids_0201
    assert "EMP-1042" not in ids_0415
    assert "EMP-1042" not in ids_0630


def test_org_snapshot_talia_present_after_hire():
    """EMP-1107 (hired 2026-05-11): absent early, present on 06-30."""
    ids_0201 = {r["employee_id"] for r in _snapshot("2026-02-01")}
    ids_0415 = {r["employee_id"] for r in _snapshot("2026-04-15")}
    ids_0630 = {r["employee_id"] for r in _snapshot("2026-06-30")}
    assert "EMP-1107" not in ids_0201
    assert "EMP-1107" not in ids_0415
    assert "EMP-1107" in ids_0630


# ---------------------------------------------------------------------------
# Roadmap evolution
# ---------------------------------------------------------------------------

def _roadmap(asof: str) -> list[dict]:
    return _jsonl(TIME / "snapshots" / f"roadmap_{asof}.jsonl")


def _find(items: list[dict], title: str) -> dict:
    for it in items:
        if it["title"] == title:
            return it
    raise AssertionError(f"roadmap item not found: {title!r}")


def test_roadmap_multi_region_never_committed():
    """Multi-region active-active is proposed/under_evaluation in every
    snapshot -- never shipped or committed."""
    for asof in ["2026-01-15", "2026-04-15", "2026-06-30"]:
        item = _find(_roadmap(asof), "Multi-region active-active")
        assert item is not None, asof
        assert item["status"] not in ("shipped", "committed"), (asof, item["status"])


def test_roadmap_exports_shipped_only_at_end():
    """Scheduled report exports ships only in the 06-30 snapshot."""
    assert _find(_roadmap("2026-01-15"),
                 "Scheduled report exports")["status"] != "shipped"
    assert _find(_roadmap("2026-04-15"),
                 "Scheduled report exports")["status"] != "shipped"
    assert _find(_roadmap("2026-06-30"),
                 "Scheduled report exports")["status"] == "shipped"


# ---------------------------------------------------------------------------
# Page revision history
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def page_history() -> list[dict]:
    return _jsonl(TIME / "page_history.jsonl")


def test_page_history_single_current_per_page(page_history):
    by_page: dict[str, list[dict]] = {}
    for r in page_history:
        by_page.setdefault(r["page_id"], []).append(r)
    assert by_page, "no page history"
    for page_id, revs in by_page.items():
        current = [r for r in revs if r["is_current"]]
        assert len(current) == 1, page_id


def test_metering_batch_limit_staleness_anchor(page_history):
    """metering-api-overview history proves 500 was once documented and was
    later raised to 1000 -- the deprecated-limit staleness ground truth."""
    revs = [r for r in page_history if r["page_id"] == "KB-101"]
    assert revs, "metering-api-overview history missing"

    was_500 = [r for r in revs if "500" in r["change_summary"]
               and "1000" not in r["change_summary"]]
    raised = [r for r in revs if "500 -> 1000" in r["change_summary"]]
    assert was_500, "no revision documenting the 500-event limit"
    assert raised, "no revision raising 500 -> 1000"
    assert min(r["edited_at"] for r in raised) > \
        min(r["edited_at"] for r in was_500)


# ---------------------------------------------------------------------------
# Policy supersession chain
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def policies() -> list[dict]:
    return _jsonl(TIME / "policy_versions.jsonl")


def test_policy_retention_one_approved_current(policies):
    retention = [p for p in policies if p["policy_id"] == "POL-DATA-RETENTION"]
    approved = [p for p in retention if p["status"] == "approved"]
    assert len(approved) == 1, "expected exactly one approved retention row"
    current = approved[0]
    assert current["version"] == "3.2"
    assert (CORPUS / current["path"]).is_file(), current["path"]


def test_policy_retention_has_abandoned_draft(policies):
    retention = [p for p in policies if p["policy_id"] == "POL-DATA-RETENTION"]
    drafts = [p for p in retention if p["status"] == "draft"]
    assert drafts, "expected a draft retention row that never became approved"
    # A draft never carries an approved counterpart at the same version.
    approved_versions = {p["version"] for p in retention
                         if p["status"] == "approved"}
    assert all(p["version"] not in approved_versions for p in drafts)
