"""Guards on the CROSS-GRANULARITY "join challenge" datasets
(data/synthetic/*/*_weekly.csv, headcount_monthly.csv, kpi_quarterly.csv,
ar_aging_2026-06-30.csv). Every one of these files is DERIVED from the
fine-grained corpus, so their eval value is that the grain conversions, key
derivations, and entity-resolution mappings hold exactly. Each test recomputes
the ground truth from the source files and asserts an exact match. Mirrors the
style of test_synthetic_internal.py: module fixtures, csv/orjson parsing,
shared constants. The normalization helper below doubles as the reference
implementation for the AR-aging entity resolution.
"""

import csv
import re
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import orjson
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS = REPO_ROOT / "data" / "synthetic"
INTERNAL = CORPUS / "internal"

_LEGAL_TOKENS = {"inc", "llc", "ltd", "co", "corp"}


def _csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _jsonl(path: Path) -> list[dict]:
    return [orjson.loads(line) for line in path.read_bytes().splitlines()
            if line.strip()]


def _d(s: str) -> date:
    return date.fromisoformat(s[:10])


def _mondays() -> list[date]:
    weeks, d = [], date(2026, 1, 5)
    while d <= date(2026, 6, 29):
        weeks.append(d)
        d += timedelta(days=7)
    return weeks


def normalize(name: str) -> str:
    """Reference normalization for AR-aging entity resolution: lowercase;
    &->and; strip punctuation; drop trailing legal tokens; collapse whitespace.
    """
    s = name.lower().replace("&", "and")
    s = re.sub(r"[^\w\s]", " ", s)
    tokens = s.split()
    while tokens and tokens[-1] in _LEGAL_TOKENS:
        tokens.pop()
    return " ".join(tokens)


@pytest.fixture(scope="module")
def tickets() -> list[dict]:
    return _jsonl(CORPUS / "saas" / "tickets" / "support_tickets.jsonl")


@pytest.fixture(scope="module")
def employees() -> list[dict]:
    return _csv(INTERNAL / "hris" / "employees.csv")


@pytest.fixture(scope="module")
def accounts() -> list[dict]:
    return _csv(CORPUS / "saas" / "crm" / "accounts.csv")


# ---------------------------------------------------------------------------
# (a) weekly ticket metrics recompute exactly from support_tickets.jsonl
# ---------------------------------------------------------------------------

def test_ticket_metrics_weekly(tickets):
    rows = _csv(CORPUS / "saas" / "tickets" / "ticket_metrics_weekly.csv")
    weeks = _mondays()
    assert [r["week_start"] for r in rows] == [w.isoformat() for w in weeks]

    by_week = {r["week_start"]: r for r in rows}
    for wk in weeks:
        wk_end = wk + timedelta(days=7)
        opened = [t for t in tickets if wk <= _d(t["created_at"]) < wk_end]
        resolved = [t for t in tickets
                    if t["status"] in ("solved", "closed")
                    and wk <= _d(t["updated_at"]) < wk_end]
        urgent_high = [t for t in opened
                       if t["priority"] in ("urgent", "high")]
        distinct = {t["account_id"] for t in opened}
        r = by_week[wk.isoformat()]
        assert int(r["tickets_opened"]) == len(opened), wk
        assert int(r["tickets_resolved"]) == len(resolved), wk
        assert int(r["urgent_or_high_opened"]) == len(urgent_high), wk
        assert int(r["distinct_accounts_opened"]) == len(distinct), wk


# ---------------------------------------------------------------------------
# (b) monthly headcount recomputes exactly from employees.csv
# ---------------------------------------------------------------------------

def _active_at(e, ref: date) -> bool:
    if _d(e["hire_date"]) > ref:
        return False
    t = e["termination_date"]
    if t and _d(t) <= ref:
        return False
    return True


def test_headcount_monthly(employees):
    rows = _csv(INTERNAL / "hris" / "headcount_monthly.csv")
    expected = []
    depts = sorted({e["department"] for e in employees})
    for month in range(1, 7):
        mstr = f"2026-{month:02d}"
        mstart = date(2026, month, 1)
        mend = date(2026, month + 1, 1) - timedelta(days=1)
        for dept in depts:
            de = [e for e in employees if e["department"] == dept]
            hc = sum(1 for e in de if _active_at(e, mend))
            if hc == 0:
                continue
            hires = sum(1 for e in de if mstart <= _d(e["hire_date"]) <= mend)
            terms = sum(1 for e in de if e["termination_date"]
                        and mstart <= _d(e["termination_date"]) <= mend)
            expected.append((mstr, dept, hc, hires, terms))

    got = [(r["month"], r["department"], int(r["headcount_end_of_month"]),
            int(r["hires_in_month"]), int(r["terminations_in_month"]))
           for r in rows]
    assert got == expected


# ---------------------------------------------------------------------------
# (c) quarterly KPIs recompute from GL / subscriptions / CSAT / employees
# ---------------------------------------------------------------------------

QUARTERS = {
    "2026-Q1": (date(2026, 3, 31), ("2026-01", "2026-02", "2026-03")),
    "2026-Q2": (date(2026, 6, 30), ("2026-04", "2026-05", "2026-06")),
}


@pytest.fixture(scope="module")
def kpi() -> dict:
    by = defaultdict(dict)
    for r in _csv(INTERNAL / "reporting" / "kpi_quarterly.csv"):
        by[r["quarter"]][r["metric"]] = r
    return by


def test_kpi_subscription_revenue_matches_gl(kpi):
    gl_4000 = {r["month"]: float(r["amount_usd"])
               for r in _csv(INTERNAL / "finance" / "gl_monthly.csv")
               if r["account_code"] == "4000"}
    for qtr, (_, months) in QUARTERS.items():
        expected = round(sum(gl_4000[m] for m in months), 2)
        assert float(kpi[qtr]["subscription_revenue_usd"]["value"]) == \
            pytest.approx(expected), qtr


def test_kpi_arr_and_active_customers(kpi):
    subs = _csv(CORPUS / "relational" / "subscriptions.csv")
    for qtr, (qend, _) in QUARTERS.items():
        active = [s for s in subs if _d(s["started_at"]) <= qend
                  and (not s["canceled_at"] or _d(s["canceled_at"]) > qend)]
        arr = sum(float(s["mrr_usd"]) for s in active) * 12.0
        customers = len({s["customer_id"] for s in active})
        assert float(kpi[qtr]["arr_run_rate_usd"]["value"]) == \
            pytest.approx(arr), qtr
        assert int(kpi[qtr]["active_customers"]["value"]) == customers, qtr


def test_kpi_headcount_end(kpi, employees):
    for qtr, (qend, _) in QUARTERS.items():
        expected = sum(1 for e in employees if _active_at(e, qend))
        assert int(kpi[qtr]["headcount_end"]["value"]) == expected, qtr


def test_kpi_avg_csat(kpi):
    csat = _csv(CORPUS / "feedback" / "csat_survey.csv")
    for qtr, (_, months) in QUARTERS.items():
        scores = [int(r["score"]) for r in csat
                  if r["submitted_at"][:7] in months]
        expected = round(sum(scores) / len(scores), 2)
        assert float(kpi[qtr]["avg_csat"]["value"]) == pytest.approx(expected), \
            qtr


def test_kpi_uptime_pinned(kpi):
    assert float(kpi["2026-Q1"]["uptime_pct"]["value"]) == 99.71
    assert float(kpi["2026-Q2"]["uptime_pct"]["value"]) == 99.93
    assert "INC-2026-0311" in kpi["2026-Q1"]["uptime_pct"]["notes"]


# ---------------------------------------------------------------------------
# (d) weekly web sessions: derived domains, tidewater ramp, noise floor
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def web_sessions() -> list[dict]:
    return _csv(CORPUS / "saas" / "marketing" / "web_sessions_weekly.csv")


def test_web_sessions_cover_account_domains(web_sessions, accounts):
    account_domains = {a["primary_contact_email"].split("@")[1]
                       for a in accounts}
    present = {r["company_domain"] for r in web_sessions}
    assert account_domains <= present


def test_web_sessions_tidewater_ramp(web_sessions):
    tw = [r for r in web_sessions
          if r["company_domain"] == "tidewater-marine.example"]
    assert tw, "tidewater rows missing"
    assert all(_d(r["week_start"]) >= date(2026, 4, 6) for r in tw)
    assert any(_d(r["week_start"]) >= date(2026, 4, 6) for r in tw)
    # No tidewater traffic before the pipeline enters the CRM story.
    assert not any(r["company_domain"] == "tidewater-marine.example"
                   and _d(r["week_start"]) < date(2026, 4, 6)
                   for r in web_sessions)


def test_web_sessions_noise_domains(web_sessions, accounts):
    account_domains = {a["primary_contact_email"].split("@")[1]
                       for a in accounts}
    present = {r["company_domain"] for r in web_sessions}
    noise = present - account_domains
    assert len(noise) >= 10


# ---------------------------------------------------------------------------
# (e) AR aging: entity-resolution bijection + bucket ground truth
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def ar_rows() -> list[dict]:
    return _csv(INTERNAL / "finance" / "ar_aging_2026-06-30.csv")


def _unpaid_by_customer() -> dict:
    cust_name = {r["customer_id"]: r["company_name"]
                 for r in _csv(CORPUS / "relational" / "customers.csv")}
    sub_customer = {r["subscription_id"]: r["customer_id"]
                    for r in _csv(CORPUS / "relational" / "subscriptions.csv")}
    totals = defaultdict(float)
    for r in _csv(CORPUS / "relational" / "invoices.csv"):
        if r["status"] not in ("open", "past_due"):
            continue
        name = cust_name[sub_customer[r["subscription_id"]]]
        totals[name] += float(r["amount_usd"])
    return totals


def test_ar_aging_bijection_and_totals(ar_rows, accounts):
    unpaid = _unpaid_by_customer()
    account_names = {a["account_name"] for a in accounts}
    unpaid_accounts = {n for n in unpaid if n in account_names}

    # Each messy customer_name normalizes onto exactly one unpaid account, and
    # the mapping is a bijection covering every unpaid account.
    norm_to_account = {normalize(n): n for n in unpaid_accounts}
    assert len(norm_to_account) == len(unpaid_accounts)   # accounts distinct

    resolved = {}
    for r in ar_rows:
        key = normalize(r["customer_name"])
        assert key in norm_to_account, r["customer_name"]
        resolved[key] = norm_to_account[key]
    assert len(resolved) == len(ar_rows)                  # messy names distinct
    assert set(resolved) == set(norm_to_account)          # onto (bijection)

    for r in ar_rows:
        account = norm_to_account[normalize(r["customer_name"])]
        buckets = [float(r["days_1_30_usd"]), float(r["days_31_60_usd"]),
                   float(r["days_61_90_usd"]), float(r["days_90_plus_usd"])]
        assert float(r["current_usd"]) == 0.0
        assert float(r["total_usd"]) == pytest.approx(sum(buckets)
                                                      + float(r["current_usd"]))
        assert float(r["total_usd"]) == pytest.approx(unpaid[account])


def test_ar_aging_sable_ninety_plus(ar_rows):
    sable = [r for r in ar_rows
             if normalize(r["customer_name"]) == "sable financial"]
    assert sable, "Sable Financial row missing"
    assert float(sable[0]["days_90_plus_usd"]) >= 12500
