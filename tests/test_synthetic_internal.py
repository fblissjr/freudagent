"""Guards on the INTERNAL-enterprise synthetic corpus (data/synthetic/internal/
plus the two internal event streams). These files back the HRIS / ITSM /
finance / IAM / security scenarios, and their value for eval is the derived
figures and cross-source references holding exactly. Mirrors the style of
test_synthetic_data.py: module fixtures, csv/orjson parsing, shared constants.
"""

import csv
from collections import defaultdict
from pathlib import Path

import orjson
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS = REPO_ROOT / "data" / "synthetic"
INTERNAL = CORPUS / "internal"
MONTHS = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]


def _csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _jsonl(path: Path) -> list[dict]:
    return [orjson.loads(line) for line in path.read_bytes().splitlines()
            if line.strip()]


@pytest.fixture(scope="module")
def employees() -> list[dict]:
    return _csv(INTERNAL / "hris" / "employees.csv")


@pytest.fixture(scope="module")
def gl() -> list[dict]:
    return _csv(INTERNAL / "finance" / "gl_monthly.csv")


@pytest.fixture(scope="module")
def gl_by_month(gl) -> dict:
    by = defaultdict(dict)
    for r in gl:
        by[r["month"]][r["account_code"]] = float(r["amount_usd"])
    return by


# ---------------------------------------------------------------------------
# (a) GL 4000 == invoice sums per period_start month
# ---------------------------------------------------------------------------

def test_gl_subscription_revenue_matches_invoices(gl_by_month):
    inv_by_month = defaultdict(float)
    for r in _csv(CORPUS / "relational" / "invoices.csv"):
        inv_by_month[r["period_start"][:7]] += float(r["amount_usd"])
    for m in MONTHS:
        assert gl_by_month[m]["4000"] == pytest.approx(
            round(inv_by_month[m], 2)), m


# ---------------------------------------------------------------------------
# (b) GL 6300 == expense_report sums per expense_date month
# ---------------------------------------------------------------------------

def test_gl_travel_matches_expenses(gl_by_month):
    exp_by_month = defaultdict(float)
    for r in _csv(INTERNAL / "finance" / "expense_reports.csv"):
        exp_by_month[r["expense_date"][:7]] += float(r["amount_usd"])
    for m in MONTHS:
        assert gl_by_month[m]["6300"] == pytest.approx(
            round(exp_by_month[m], 2)), m


# ---------------------------------------------------------------------------
# (c) GL 6100 == 22% of 6000 per month
# ---------------------------------------------------------------------------

def test_gl_payroll_taxes_are_22pct_of_salaries(gl_by_month):
    for m in MONTHS:
        assert gl_by_month[m]["6100"] == pytest.approx(
            round(gl_by_month[m]["6000"] * 0.22, 2)), m


# ---------------------------------------------------------------------------
# (d) pinned employees present with exact id / email / status
# ---------------------------------------------------------------------------

def test_pinned_employees(employees):
    by_id = {e["employee_id"]: e for e in employees}
    dom = "acme-analytics.example"

    assert by_id["EMP-1001"]["full_name"] == "Renata Voss"
    assert by_id["EMP-1001"]["email"] == f"renata.voss@{dom}"
    assert by_id["EMP-1001"]["title"] == "CEO"
    assert by_id["EMP-1001"]["base_salary_usd"] == "320000"

    assert by_id["EMP-1010"]["full_name"] == "Priya Raghavan"
    assert by_id["EMP-1010"]["email"] == f"priya.raghavan@{dom}"

    assert by_id["EMP-1042"]["status"] == "terminated"
    assert by_id["EMP-1042"]["termination_date"] == "2026-03-31"

    assert by_id["EMP-1107"]["hire_date"] == "2026-05-11"
    assert by_id["EMP-1107"]["status"] == "active"

    assert len(by_id) == len(employees)                       # unique ids
    assert len({e["email"] for e in employees}) == len(employees)  # unique emails


# ---------------------------------------------------------------------------
# (e) referential integrity
# ---------------------------------------------------------------------------

def test_referential_integrity(employees):
    emp_ids = {e["employee_id"] for e in employees}
    app_ids = {a["app_id"] for a in _csv(INTERNAL / "iam" / "app_catalog.csv")}

    for r in _csv(INTERNAL / "iam" / "access_review_2026q2.csv"):
        assert r["employee_id"] in emp_ids, r["review_id"]
        assert r["app_id"] in app_ids, r["review_id"]

    for a in _csv(INTERNAL / "itsm" / "assets.csv"):
        if a["assigned_to_employee_id"]:
            assert a["assigned_to_employee_id"] in emp_ids, a["asset_id"]

    for t in _jsonl(INTERNAL / "itsm" / "it_tickets.jsonl"):
        assert t["requester_employee_id"] in emp_ids, t["ticket_id"]


# ---------------------------------------------------------------------------
# (f) anchors
# ---------------------------------------------------------------------------

def test_asset_and_onboarding_anchors():
    assets = {a["asset_id"]: a for a in _csv(INTERNAL / "itsm" / "assets.csv")}
    assert assets["AST-1289"]["assigned_to_employee_id"] == "EMP-1107"
    assert assets["AST-1289"]["purchase_order_id"] == "PO-2026-041"
    assert assets["AST-1077"]["assigned_to_employee_id"] == ""
    assert assets["AST-1077"]["status"] == "stock"

    tickets = {t["ticket_id"]: t
               for t in _jsonl(INTERNAL / "itsm" / "it_tickets.jsonl")}
    assert tickets["IT-2231"]["category"] == "offboarding"
    assert tickets["IT-2412"]["category"] == "onboarding"
    assert tickets["IT-2412"]["linked_asset"] == "AST-1289"


def test_change_anchors():
    changes = {c["change_id"]: c
               for c in _csv(INTERNAL / "itsm" / "changes.csv")}
    assert changes["CHG-2026-0023"]["status"] == "failed"
    assert changes["CHG-2026-0023"]["linked_incident"] == "INC-2026-0311"
    assert changes["CHG-2026-0024"]["change_type"] == "emergency"
    assert changes["CHG-2026-0024"]["status"] == "success"


def test_access_review_terminated_anchor():
    rows = _csv(INTERNAL / "iam" / "access_review_2026q2.csv")
    derek = [r for r in rows
             if r["employee_id"] == "EMP-1042" and r["app_id"] == "APP-05"]
    assert derek, "Derek/Saltmarsh CRM revoke row missing"
    assert derek[0]["app_name"] == "Saltmarsh CRM"
    assert derek[0]["decision"] == "revoke"
    assert derek[0]["employee_status"] == "terminated"
    # Derek plus exactly two more terminated-with-leftover-access rows.
    assert sum(1 for r in rows if r["employee_status"] == "terminated") == 3


# ---------------------------------------------------------------------------
# (g) badge stream
# ---------------------------------------------------------------------------

def test_badge_server_room_restricted():
    dom = "acme-analytics.example"
    allowed = {f"tom.alvarez@{dom}", f"lena.fischer@{dom}", f"diego.fuentes@{dom}"}
    events = _jsonl(CORPUS / "events" / "badge_access.jsonl")
    server_actors = {e["actor"] for e in events
                     if e["payload"]["door"] == "server-room"}
    assert server_actors
    assert server_actors <= allowed

    # EMP-1042 (terminated before the badge window) has no events.
    assert not any(e["payload"]["employee_id"] == "EMP-1042" for e in events)


# ---------------------------------------------------------------------------
# (h) security stream
# ---------------------------------------------------------------------------

def test_security_phishing_wave():
    events = _jsonl(CORPUS / "events" / "security_alerts.jsonl")
    reported = [e for e in events
                if e["type"] == "phishing.reported"
                and e["timestamp"].startswith("2026-05-20")]
    actors = {e["actor"] for e in reported}
    assert len(actors) >= 8
