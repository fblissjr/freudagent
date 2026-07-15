#!/usr/bin/env python3
"""Deterministic synthetic-corpus generator for data/synthetic/.

Generates the structured and volume portions of the PUBLIC synthetic
corpus: SaaS exports (project management, support tickets, CRM),
relational database extracts, human-feedback datasets, unstructured
streams (chat, logs), and generic event streams shaped for
`freud-schema ingest events`. Hand-authored documents (knowledge-base
pages, runbooks, meeting notes, emails, call transcripts) live alongside
the generated files and are NOT touched by this script; the manifest
step records whatever is present.

Everything is fictional: Acme Analytics (a made-up B2B usage-analytics
SaaS), its fictional employees, and fictional customers. All domains use
the reserved `.example` TLD.

Determinism: a fixed seed and fixed base dates -- no wall-clock reads --
so re-running the script reproduces the corpus byte-for-byte. Anchor
entities (the 2026-03-11 ingestion incident, key tickets/issues) are
pinned explicitly so documents can reference stable IDs.

Usage:
    uv run python scripts/generate_synthetic_data.py [--out DIR]
"""

from __future__ import annotations

import argparse
import csv
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import orjson

SEED = 20260311
CORPUS_START = datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc)
CORPUS_END = datetime(2026, 6, 30, 18, 0, tzinfo=timezone.utc)
INCIDENT_START = datetime(2026, 3, 11, 14, 2, tzinfo=timezone.utc)
INCIDENT_END = datetime(2026, 3, 11, 15, 47, tzinfo=timezone.utc)

COMPANY_DOMAIN = "acme-analytics.example"

# ---------------------------------------------------------------------------
# Fixed reference data (all fictional)
# ---------------------------------------------------------------------------

EMPLOYEES = [
    ("Priya Raghavan", "priya.raghavan", "Engineering Manager", "platform"),
    ("Marcus Webb", "marcus.webb", "Senior Backend Engineer", "platform"),
    ("Elena Sokolova", "elena.sokolova", "Data Engineer", "pipeline"),
    ("Dana Kim", "dana.kim", "Frontend Engineer", "platform"),
    ("Tom Alvarez", "tom.alvarez", "Site Reliability Engineer", "infra"),
    ("Yuki Tanaka", "yuki.tanaka", "Support Lead", "support"),
    ("Sam Osei", "sam.osei", "Support Engineer", "support"),
    ("Ingrid Bauer", "ingrid.bauer", "Product Manager", "product"),
    ("Carlos Mendes", "carlos.mendes", "Customer Success Manager", "success"),
    ("Aisha Diallo", "aisha.diallo", "Account Executive", "sales"),
    ("Noah Lindqvist", "noah.lindqvist", "Data Engineer", "pipeline"),
    ("Fatima al-Rashid", "fatima.alrashid", "QA Engineer", "platform"),
]

ENGINEERS = ["priya.raghavan", "marcus.webb", "elena.sokolova", "dana.kim",
             "tom.alvarez", "noah.lindqvist", "fatima.alrashid"]
SUPPORT_AGENTS = ["yuki.tanaka", "sam.osei"]

# (name, industry, segment, plan)
CUSTOMERS = [
    ("Bluewater Logistics", "logistics", "enterprise", "enterprise"),
    ("Kestrel Health", "healthcare", "enterprise", "enterprise"),
    ("Orchard Retail Group", "retail", "mid-market", "scale"),
    ("Nimbus Media", "media", "mid-market", "scale"),
    ("Ferrostar Manufacturing", "manufacturing", "enterprise", "scale"),
    ("Pinewood Insurance", "insurance", "mid-market", "scale"),
    ("Cobalt Games", "gaming", "smb", "growth"),
    ("Harborview Hospitality", "hospitality", "mid-market", "growth"),
    ("Quill & Sable Publishing", "media", "smb", "growth"),
    ("Redwood Robotics", "manufacturing", "smb", "growth"),
    ("Atlas Freight", "logistics", "mid-market", "scale"),
    ("Meridian Energy", "energy", "enterprise", "enterprise"),
    ("Sable Financial", "financial-services", "enterprise", "enterprise"),
    ("Larkspur Biotech", "biotech", "smb", "growth"),
    ("Copperline Telecom", "telecom", "enterprise", "scale"),
    ("Juniper Foods", "food-beverage", "mid-market", "growth"),
    ("Vantage Legal", "legal", "smb", "starter"),
    ("Brightwater Utilities", "energy", "mid-market", "scale"),
    ("Stonebridge Construction", "construction", "smb", "starter"),
    ("Halcyon Travel", "travel", "smb", "growth"),
    ("Verdant Agritech", "agriculture", "smb", "starter"),
    ("Northgate Security", "security", "mid-market", "growth"),
    ("Lumen Cinemas", "entertainment", "smb", "starter"),
    ("Cascadia Outfitters", "retail", "smb", "growth"),
    ("Ironwood Furniture", "manufacturing", "smb", "starter"),
]

PLAN_MRR = {"starter": 299, "growth": 1200, "scale": 4500, "enterprise": 12500}

CONTACT_FIRST = ["Jordan", "Riley", "Mei", "Omar", "Lucia", "Henrik", "Amara",
                 "Devon", "Sofia", "Ravi", "Nadia", "Felix", "Grace", "Ibrahim",
                 "Wren", "Paulo", "Anouk", "Kenji", "Tessa", "Malik"]
CONTACT_LAST = ["Whitfield", "Okafor", "Lindgren", "Castellanos", "Brennan",
                "Duval", "Marchetti", "Nakagawa", "Petrov", "Ashworth",
                "Kavanagh", "Suarez", "Holloway", "Njoku", "Fairbanks",
                "Delacroix", "Moreno", "Iversen", "Beaumont", "Trask"]


def slugify(name: str) -> str:
    out = []
    for ch in name.lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in " &":
            out.append("-")
    slug = "".join(out)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def jdump(obj) -> bytes:
    return orjson.dumps(obj, option=orjson.OPT_INDENT_2) + b"\n"


def jsonl(rows) -> bytes:
    return b"".join(orjson.dumps(r) + b"\n" for r in rows)


def rand_dt(rng: random.Random, start: datetime, end: datetime) -> datetime:
    span = int((end - start).total_seconds())
    return start + timedelta(seconds=rng.randrange(span))


def business_hours(dt: datetime) -> datetime:
    """Clamp a timestamp to 08:00-19:00 UTC so activity looks human."""
    if dt.hour < 8:
        return dt.replace(hour=8 + dt.hour % 4)
    if dt.hour >= 19:
        return dt.replace(hour=9 + dt.hour % 8)
    return dt


# ---------------------------------------------------------------------------
# CRM (SaaS export)
# ---------------------------------------------------------------------------


def build_accounts(rng: random.Random) -> list[dict]:
    accounts = []
    owners = ["aisha.diallo", "carlos.mendes"]
    for i, (name, industry, segment, plan) in enumerate(CUSTOMERS):
        signup = rand_dt(rng, datetime(2023, 2, 1, tzinfo=timezone.utc),
                         datetime(2025, 12, 15, tzinfo=timezone.utc))
        domain = f"{slugify(name)}.example"
        contacts = []
        for _ in range(rng.choice([1, 1, 2])):
            first = rng.choice(CONTACT_FIRST)
            last = rng.choice(CONTACT_LAST)
            contacts.append({
                "name": f"{first} {last}",
                "email": f"{first.lower()}.{last.lower()}@{domain}",
            })
        accounts.append({
            "account_id": f"ACCT-{1001 + i}",
            "name": name,
            "industry": industry,
            "segment": segment,
            "plan": plan,
            "arr_usd": PLAN_MRR[plan] * 12,
            "owner": f"{rng.choice(owners)}@{COMPANY_DOMAIN}",
            "domain": domain,
            "signup_date": signup.strftime("%Y-%m-%d"),
            "contacts": contacts,
        })
    return accounts


def write_crm(out: Path, rng: random.Random, accounts: list[dict]) -> None:
    crm = out / "saas" / "crm"
    crm.mkdir(parents=True, exist_ok=True)

    with open(crm / "accounts.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["account_id", "account_name", "industry", "segment",
                    "plan", "arr_usd", "owner_email", "primary_contact",
                    "primary_contact_email", "signup_date"])
        for a in accounts:
            w.writerow([a["account_id"], a["name"], a["industry"],
                        a["segment"], a["plan"], a["arr_usd"], a["owner"],
                        a["contacts"][0]["name"], a["contacts"][0]["email"],
                        a["signup_date"]])

    stages = ["prospecting", "qualification", "proposal", "negotiation",
              "closed_won", "closed_lost"]
    products = ["dashboards-addon", "metering-api", "premium-support",
                "seat-expansion", "annual-renewal"]
    with open(crm / "opportunities.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["opportunity_id", "account_id", "product", "stage",
                    "amount_usd", "created_date", "close_date", "owner_email"])
        for i in range(40):
            a = rng.choice(accounts)
            created = rand_dt(rng, CORPUS_START, CORPUS_END - timedelta(days=30))
            close = created + timedelta(days=rng.randrange(20, 120))
            stage = rng.choices(stages, weights=[3, 3, 3, 2, 3, 2])[0]
            amount = rng.choice([5000, 8000, 12000, 15000, 24000, 30000, 54000])
            w.writerow([f"OPP-{2001 + i}", a["account_id"],
                        rng.choice(products), stage, amount,
                        created.strftime("%Y-%m-%d"),
                        close.strftime("%Y-%m-%d"), a["owner"]])


# ---------------------------------------------------------------------------
# Relational extract (OLTP-style CSVs + DDL)
# ---------------------------------------------------------------------------

SCHEMA_SQL = """\
-- Source schema for the relational extract in this folder.
-- Fictional OLTP database `acmedb` behind Acme Analytics' billing service.
-- The CSVs are straight SELECT * exports of these tables.

CREATE TABLE customers (
    customer_id   INTEGER PRIMARY KEY,
    account_id    VARCHAR(16) NOT NULL,        -- CRM foreign identity (ACCT-*)
    company_name  VARCHAR(120) NOT NULL,
    billing_email VARCHAR(200) NOT NULL,
    country       CHAR(2) NOT NULL,
    created_at    TIMESTAMP NOT NULL
);

CREATE TABLE subscriptions (
    subscription_id INTEGER PRIMARY KEY,
    customer_id     INTEGER NOT NULL REFERENCES customers(customer_id),
    plan            VARCHAR(20) NOT NULL,      -- starter|growth|scale|enterprise
    mrr_usd         DECIMAL(10,2) NOT NULL,
    seats           INTEGER NOT NULL,
    started_at      DATE NOT NULL,
    canceled_at     DATE,                      -- NULL = active
    billing_cycle   VARCHAR(10) NOT NULL       -- monthly|annual
);

CREATE TABLE invoices (
    invoice_id      VARCHAR(20) PRIMARY KEY,   -- INV-YYYYMM-NNNN
    subscription_id INTEGER NOT NULL REFERENCES subscriptions(subscription_id),
    period_start    DATE NOT NULL,
    period_end      DATE NOT NULL,
    amount_usd      DECIMAL(10,2) NOT NULL,
    status          VARCHAR(12) NOT NULL,      -- paid|open|past_due|void
    issued_at       DATE NOT NULL,
    paid_at         DATE
);

CREATE TABLE usage_daily (
    customer_id   INTEGER NOT NULL REFERENCES customers(customer_id),
    usage_date    DATE NOT NULL,
    api_calls     BIGINT NOT NULL,
    events_ingested BIGINT NOT NULL,
    dashboards_viewed INTEGER NOT NULL,
    PRIMARY KEY (customer_id, usage_date)
);
"""

COUNTRIES = ["US", "US", "US", "CA", "GB", "DE", "NL", "AU", "SE", "JP"]


def write_relational(out: Path, rng: random.Random, accounts: list[dict]) -> None:
    rel = out / "relational"
    rel.mkdir(parents=True, exist_ok=True)
    (rel / "schema.sql").write_text(SCHEMA_SQL, encoding="utf-8")

    with open(rel / "customers.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["customer_id", "account_id", "company_name",
                    "billing_email", "country", "created_at"])
        for i, a in enumerate(accounts):
            w.writerow([i + 1, a["account_id"], a["name"],
                        f"billing@{a['domain']}", rng.choice(COUNTRIES),
                        a["signup_date"] + " 00:00:00"])

    subs = []
    with open(rel / "subscriptions.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["subscription_id", "customer_id", "plan", "mrr_usd",
                    "seats", "started_at", "canceled_at", "billing_cycle"])
        sub_id = 5001
        for i, a in enumerate(accounts):
            plan = a["plan"]
            seats = {"starter": 5, "growth": 20, "scale": 75,
                     "enterprise": 250}[plan] + rng.randrange(0, 10)
            cycle = "annual" if plan in ("scale", "enterprise") else \
                rng.choice(["monthly", "annual"])
            # A couple of customers downgraded: closed row + current row.
            if a["name"] in ("Cobalt Games", "Halcyon Travel"):
                w.writerow([sub_id, i + 1, "scale", PLAN_MRR["scale"], 60,
                            a["signup_date"], "2026-02-28", cycle])
                sub_id += 1
                started = "2026-03-01"
            else:
                started = a["signup_date"]
            w.writerow([sub_id, i + 1, plan, PLAN_MRR[plan], seats,
                        started, "", cycle])
            subs.append({"subscription_id": sub_id, "customer_id": i + 1,
                         "mrr": PLAN_MRR[plan]})
            sub_id += 1

    with open(rel / "invoices.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["invoice_id", "subscription_id", "period_start",
                    "period_end", "amount_usd", "status", "issued_at",
                    "paid_at"])
        n = 1
        for month in range(1, 7):
            period_start = datetime(2026, month, 1)
            period_end = (datetime(2026, month + 1, 1) - timedelta(days=1))
            for s in subs:
                issued = period_start + timedelta(days=1)
                # Sable Financial disputes its March invoice (anchor:
                # referenced by support ticket SUP-1063).
                if s["customer_id"] == 13 and month == 3:
                    status, paid = "past_due", ""
                elif month == 6:
                    status = rng.choices(["paid", "open"], weights=[3, 2])[0]
                    paid = (issued + timedelta(days=rng.randrange(1, 20))
                            ).strftime("%Y-%m-%d") if status == "paid" else ""
                else:
                    status = "paid"
                    paid = (issued + timedelta(days=rng.randrange(1, 20))
                            ).strftime("%Y-%m-%d")
                w.writerow([f"INV-2026{month:02d}-{n:04d}",
                            s["subscription_id"],
                            period_start.strftime("%Y-%m-%d"),
                            period_end.strftime("%Y-%m-%d"),
                            s["mrr"], status,
                            issued.strftime("%Y-%m-%d"), paid])
                n += 1

    with open(rel / "usage_daily.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["customer_id", "usage_date", "api_calls",
                    "events_ingested", "dashboards_viewed"])
        base_calls = {"starter": 2_000, "growth": 15_000, "scale": 90_000,
                      "enterprise": 400_000}
        start = datetime(2026, 2, 1)
        for day in range(90):
            date = start + timedelta(days=day)
            weekend = date.weekday() >= 5
            for i, a in enumerate(accounts):
                base = base_calls[a["plan"]]
                factor = rng.uniform(0.7, 1.3) * (0.35 if weekend else 1.0)
                calls = int(base * factor)
                ingested = int(calls * rng.uniform(6, 14))
                # Incident day: ingestion drops sharply mid-day (the lag),
                # then the backlog drains the following day.
                if date.date() == INCIDENT_START.date():
                    ingested = int(ingested * 0.45)
                elif date.date() == (INCIDENT_START + timedelta(days=1)).date():
                    ingested = int(ingested * 1.6)
                w.writerow([i + 1, date.strftime("%Y-%m-%d"), calls,
                            ingested, rng.randrange(3, 220)])


# ---------------------------------------------------------------------------
# Project management (issue-tracker export)
# ---------------------------------------------------------------------------

ISSUE_TOPICS = [
    # (project, type, summary, labels, area)
    ("ACME", "bug", "Dashboard tiles render blank when a saved filter references a deleted metric", ["dashboards", "regression"], "dashboards"),
    ("ACME", "bug", "Metering API returns 500 on batch sizes above 1000 events", ["metering-api"], "api"),
    ("ACME", "story", "Add CSV export to the usage explorer", ["exports"], "exports"),
    ("ACME", "story", "Scheduled report exports: recurrence rules UI", ["exports", "epic:ACME-180"], "exports"),
    ("ACME", "story", "Scheduled report exports: delivery via signed URL", ["exports", "epic:ACME-180"], "exports"),
    ("ACME", "bug", "SAML assertion with multi-value groups attribute fails to map roles", ["auth", "sso"], "auth"),
    ("ACME", "task", "Rotate API gateway TLS certificates", ["infra"], "infra"),
    ("ACME", "bug", "Timezone selector resets to UTC after saving dashboard preferences", ["dashboards"], "dashboards"),
    ("ACME", "story", "Rate-limit headers on all public metering endpoints", ["metering-api"], "api"),
    ("ACME", "bug", "Invoice PDF omits usage overage line items for annual plans", ["billing"], "billing"),
    ("ACME", "task", "Upgrade dashboard charting library to v9", ["dashboards", "tech-debt"], "dashboards"),
    ("ACME", "story", "Allow read-only dashboard sharing links with expiry", ["dashboards", "sharing"], "dashboards"),
    ("ACME", "bug", "Webhook retries duplicate report.generated events after gateway timeout", ["webhooks"], "api"),
    ("ACME", "task", "Add alerting runbook links to on-call pager payloads", ["infra", "oncall"], "infra"),
    ("ACME", "bug", "Usage explorer date picker off-by-one across DST boundary", ["dashboards"], "dashboards"),
    ("ACME", "story", "Self-serve plan upgrade flow for growth tier", ["billing", "growth"], "billing"),
    ("DATA", "story", "Partition usage events topic by customer for consumer parallelism", ["kafka", "ingestion"], "ingestion"),
    ("DATA", "bug", "Late-arriving events older than 48h dropped without dead-letter record", ["ingestion"], "ingestion"),
    ("DATA", "task", "Backfill tooling: replay events from object storage by date range", ["ingestion", "tooling"], "ingestion"),
    ("DATA", "story", "Deduplicate events on (source_id, idempotency_key) at ingest", ["ingestion"], "ingestion"),
    ("DATA", "bug", "Aggregation job double-counts events replayed during compaction", ["aggregation"], "aggregation"),
    ("DATA", "task", "Consumer lag dashboards per topic partition", ["kafka", "observability"], "observability"),
    ("DATA", "story", "Schema registry: reject producer schema changes without version bump", ["ingestion", "governance"], "ingestion"),
    ("DATA", "bug", "Hourly rollup misses events landing in the final 5 minutes of the hour", ["aggregation"], "aggregation"),
]

COMMENT_TEMPLATES = [
    "Reproduced on staging with the {area} fixture set. Stack trace attached to the run log.",
    "This is blocking {customer} -- support thread linked. Raising priority.",
    "Root cause is in the {area} path: we assume the payload is already normalized, and it is not when the batch API is used.",
    "PR is up, waiting on review from the {area} owners.",
    "Deployed to staging. Please verify against the acceptance criteria before we promote.",
    "Verified on staging -- metrics look flat after the fix, closing once it ships.",
    "Downgrading to P3: only reproduces with the legacy exporter, which is on a deprecation path.",
    "Splitting the schema-registry portion into its own ticket, this one now covers ingestion only.",
    "Customer confirmed the workaround holds. Fix still needed for GA.",
    "Adding a regression test that pins the old behavior so this cannot silently return.",
]

# Pinned anchor issues: documents/tickets/chat reference these keys.
ANCHOR_ISSUES = [
    {
        "key": "ACME-180", "issue_type": "epic",
        "summary": "Scheduled report exports (Q1-Q2 initiative)",
        "description": "Customers on scale and enterprise plans want recurring usage reports delivered without logging in. Covers recurrence rules, rendering, delivery via signed URL, and audit events.",
        "status": "in_progress", "priority": "P2",
        "assignee": "ingrid.bauer", "reporter": "ingrid.bauer",
        "labels": ["exports", "initiative"], "sprint": None,
        "story_points": None,
        "created": "2026-01-12T10:04:00Z", "updated": "2026-06-18T15:22:00Z",
        "resolved": None, "comments": [],
    },
    {
        "key": "ACME-231", "issue_type": "bug",
        "summary": "Metering API 5xx spike and stale dashboards during 2026-03-11 ingestion incident",
        "description": "During INC-2026-0311 the usage consumer group fell 40+ minutes behind, dashboards served stale aggregates, and the metering API returned 502s at the gateway once upstream latency breached the timeout. Tracking the customer-facing symptoms; root cause work is DATA-88.",
        "status": "done", "priority": "P1",
        "assignee": "tom.alvarez", "reporter": "yuki.tanaka",
        "labels": ["incident", "metering-api", "dashboards"],
        "sprint": "SPR-2026-06", "story_points": 3,
        "created": "2026-03-11T14:31:00Z", "updated": "2026-03-13T11:05:00Z",
        "resolved": "2026-03-13T11:05:00Z",
        "comments": [
            {"author": "tom.alvarez", "created": "2026-03-11T14:48:00Z",
             "body": "Gateway 502 rate at 18% for /v1/usage. Consumer lag on usage-events partitions 3, 7, 11 climbing ~90s/min. Declared SEV2, incident channel open."},
            {"author": "elena.sokolova", "created": "2026-03-11T15:20:00Z",
             "body": "Lag traced to the 08:40 deploy of consumer build 2026.3.4: the new batch decompression path holds the partition lock while decompressing. Rolling back."},
            {"author": "tom.alvarez", "created": "2026-03-11T15:52:00Z",
             "body": "Rollback complete 15:41, lag drained by 15:47. Keeping this open for the postmortem and the follow-up fix (DATA-88)."},
            {"author": "priya.raghavan", "created": "2026-03-13T11:05:00Z",
             "body": "Postmortem published (see 2026-03-12 notes). Closing; remediation tracked on DATA-88 and ACME-247."},
        ],
    },
    {
        "key": "DATA-88", "issue_type": "story",
        "summary": "Move batch decompression off the consumer partition lock",
        "description": "Root-cause fix from INC-2026-0311: decompression of batched event payloads must not run under the partition lock. Decompress in a bounded worker pool, commit offsets only after downstream write.",
        "status": "done", "priority": "P1",
        "assignee": "elena.sokolova", "reporter": "priya.raghavan",
        "labels": ["ingestion", "kafka", "incident-followup"],
        "sprint": "SPR-2026-06", "story_points": 5,
        "created": "2026-03-12T09:15:00Z", "updated": "2026-03-24T16:40:00Z",
        "resolved": "2026-03-24T16:40:00Z",
        "comments": [
            {"author": "elena.sokolova", "created": "2026-03-18T13:02:00Z",
             "body": "Worker pool sized at 4x partitions with a 64MB in-flight cap. Load test shows p99 commit latency down from 2.1s to 140ms at 3x normal volume."},
            {"author": "noah.lindqvist", "created": "2026-03-24T16:40:00Z",
             "body": "Shipped in consumer build 2026.3.9. Lag alarms quiet for 72h under production load. Done."},
        ],
    },
    {
        "key": "ACME-247", "issue_type": "task",
        "summary": "Serve dashboards with an explicit staleness banner when aggregates lag > 10 min",
        "description": "Incident follow-up: during ingestion lag, dashboards silently served stale data. Surface a banner with the freshness watermark instead of pretending the data is current.",
        "status": "done", "priority": "P2",
        "assignee": "dana.kim", "reporter": "ingrid.bauer",
        "labels": ["dashboards", "incident-followup"],
        "sprint": "SPR-2026-07", "story_points": 3,
        "created": "2026-03-13T10:20:00Z", "updated": "2026-04-02T12:10:00Z",
        "resolved": "2026-04-02T12:10:00Z",
        "comments": [
            {"author": "dana.kim", "created": "2026-03-30T11:00:00Z",
             "body": "Banner reads from the freshness watermark endpoint added in DATA-88. Copy reviewed by support so it matches KB troubleshooting language."},
        ],
    },
]


def write_project_mgmt(out: Path, rng: random.Random) -> list[dict]:
    pm = out / "saas" / "project_mgmt"
    pm.mkdir(parents=True, exist_ok=True)

    sprints = []
    sprint_start = datetime(2026, 1, 5, tzinfo=timezone.utc)
    for i in range(12):
        start = sprint_start + timedelta(days=14 * i)
        end = start + timedelta(days=13)
        sprints.append({
            "sprint_id": f"SPR-2026-{i + 1:02d}",
            "name": f"2026 Sprint {i + 1}",
            "start_date": start.strftime("%Y-%m-%d"),
            "end_date": end.strftime("%Y-%m-%d"),
            "state": "closed" if end < CORPUS_END - timedelta(days=14) else (
                "active" if start <= CORPUS_END - timedelta(days=14) else "future"),
            "goal": rng.choice([
                "Ingestion reliability and consumer observability",
                "Scheduled exports milestone",
                "Dashboard performance and sharing",
                "Billing accuracy and invoicing polish",
                "Auth hardening and SSO edge cases",
                "Incident follow-ups and tech debt",
            ]),
        })
    (pm / "sprints.json").write_bytes(jdump(sprints))

    statuses = ["backlog", "todo", "in_progress", "in_review", "done", "done",
                "done"]
    counters = {"ACME": 100, "DATA": 40}
    anchor_keys = {a["key"] for a in ANCHOR_ISSUES}
    issues: list[dict] = []

    for proj, itype, summary, labels, area in ISSUE_TOPICS * 3:
        counters[proj] += rng.randrange(1, 4)
        key = f"{proj}-{counters[proj]}"
        if key in anchor_keys:
            counters[proj] += 1
            key = f"{proj}-{counters[proj]}"
        created = business_hours(rand_dt(rng, CORPUS_START,
                                         CORPUS_END - timedelta(days=7)))
        status = rng.choice(statuses)
        sprint = rng.choice(sprints[:-2])["sprint_id"] if status != "backlog" else None
        resolved = None
        updated = created + timedelta(days=rng.randrange(1, 21),
                                      hours=rng.randrange(0, 9))
        if status == "done":
            resolved = updated
        n_comments = rng.randrange(0, 4)
        comments = []
        ctime = created
        for _ in range(n_comments):
            ctime = ctime + timedelta(days=rng.randrange(1, 5),
                                      hours=rng.randrange(1, 8))
            tmpl = rng.choice(COMMENT_TEMPLATES)
            comments.append({
                "author": rng.choice(ENGINEERS),
                "created": iso(min(ctime, CORPUS_END)),
                "body": tmpl.format(area=area,
                                    customer=rng.choice(CUSTOMERS)[0]),
            })
        issues.append({
            "key": key,
            "issue_type": itype,
            "summary": summary if summary not in {i["summary"] for i in issues}
            else f"{summary} ({area}, follow-up)",
            "description": f"Filed against the {area} component. {summary}.",
            "status": status,
            "priority": rng.choices(["P1", "P2", "P3", "P4"],
                                    weights=[1, 3, 4, 2])[0],
            "assignee": rng.choice(ENGINEERS) if status != "backlog" else None,
            "reporter": rng.choice(ENGINEERS + ["ingrid.bauer", "yuki.tanaka"]),
            "labels": labels,
            "sprint": sprint,
            "story_points": rng.choice([1, 2, 3, 5, 8]) if itype != "bug" else None,
            "created": iso(created),
            "updated": iso(min(updated, CORPUS_END)),
            "resolved": iso(min(resolved, CORPUS_END)) if resolved else None,
            "comments": comments,
        })

    issues.extend(ANCHOR_ISSUES)
    issues.sort(key=lambda i: i["created"])
    (pm / "issues.json").write_bytes(jdump({
        "export_kind": "issue_tracker_export",
        "generated_by": "scripts/generate_synthetic_data.py",
        "projects": [
            {"key": "ACME", "name": "Acme Platform"},
            {"key": "DATA", "name": "Data Pipeline"},
        ],
        "issues": issues,
    }))
    return issues


# ---------------------------------------------------------------------------
# Support tickets (helpdesk export)
# ---------------------------------------------------------------------------

TICKET_TOPICS = [
    ("Dashboard shows no data for yesterday", "dashboards",
     "Our exec dashboard is empty for yesterday's numbers. API ingest looks fine on our side."),
    ("Metering API returning 429 more often since last week", "api",
     "We have not changed our call volume but are seeing sustained 429s during our morning batch."),
    ("How do we add SSO group-based role mapping?", "auth",
     "We want our identity provider groups to map onto viewer/editor roles automatically."),
    ("Invoice does not match the usage we see in the explorer", "billing",
     "The overage line on our latest invoice is higher than the usage explorer total for the same period."),
    ("CSV export truncates at 10,000 rows", "exports",
     "Exports from the usage explorer cut off at exactly 10k rows with no warning."),
    ("Webhook deliveries arriving twice", "api",
     "Our endpoint receives duplicate report.generated events a few seconds apart."),
    ("Need to rotate our API keys", "security",
     "Security policy requires quarterly key rotation. What is the recommended zero-downtime procedure?"),
    ("Sharing link expired for board deck", "dashboards",
     "The read-only link we shared with our leadership expired mid-meeting. Can expiry be extended?"),
    ("Data retention question for compliance review", "compliance",
     "Our auditors need written confirmation of how long raw events are retained."),
    ("Onboarding new team members", "account",
     "We need 15 more seats and a bulk invite option."),
]

AGENT_REPLIES = [
    "Thanks for the report -- I can reproduce this on our side and have opened an internal issue ({issue}). I will keep this ticket updated.",
    "This is expected behavior on the {plan} plan; the limit is documented in our knowledge base. Upgrading to the next tier raises it.",
    "Could you send the request ID from the response headers? That lets us trace the exact call in our gateway logs.",
    "We shipped a fix this morning. Could you confirm on your side and we will close this out?",
    "I have escalated this to our engineering team with the diagnostics you provided.",
]

ANCHOR_TICKETS = [
    {
        "ticket_id": "SUP-1042",
        "subject": "Dashboards stale and usage API 502s (urgent - exec review today)",
        "status": "solved", "priority": "urgent", "channel": "email",
        "account_id": "ACCT-1001",  # Bluewater Logistics
        "requester": "jordan.whitfield@bluewater-logistics.example",
        "assignee": "yuki.tanaka",
        "tags": ["incident", "dashboards", "metering-api"],
        "linked_issue": "ACME-231",
        "created_at": "2026-03-11T14:19:00Z",
        "updated_at": "2026-03-12T09:30:00Z",
        "satisfaction_score": 4,
        "messages": [
            {"at": "2026-03-11T14:19:00Z", "from": "jordan.whitfield@bluewater-logistics.example",
             "kind": "public",
             "body": "Our ops dashboards have not updated since about 14:00 UTC and our own service is getting 502s from the usage API. We present these numbers to our exec team at 17:00 today. Please advise urgently."},
            {"at": "2026-03-11T14:33:00Z", "from": "yuki.tanaka", "kind": "public",
             "body": "We have a confirmed incident affecting event ingestion and the usage API and are actively working on it. Your data is safe -- events are queued, not lost -- and dashboards will backfill automatically once ingestion recovers. Status updates every 30 minutes on this ticket."},
            {"at": "2026-03-11T14:35:00Z", "from": "yuki.tanaka", "kind": "internal_note",
             "body": "Linked to ACME-231 / INC-2026-0311. Enterprise account, exec review at 17:00 UTC -- flagging to Carlos for proactive outreach."},
            {"at": "2026-03-11T15:55:00Z", "from": "yuki.tanaka", "kind": "public",
             "body": "The incident is resolved as of 15:47 UTC. Ingestion has caught up and dashboards are current. The 502s stopped once upstream latency recovered. A postmortem summary will be shared with your CSM."},
            {"at": "2026-03-12T09:30:00Z", "from": "jordan.whitfield@bluewater-logistics.example",
             "kind": "public",
             "body": "Confirmed everything is current this morning. The 30-minute updates were appreciated. Closing."},
        ],
    },
    {
        "ticket_id": "SUP-1057",
        "subject": "SAML login fails for users in more than 20 groups",
        "status": "open", "priority": "high", "channel": "web",
        "account_id": "ACCT-1002",  # Kestrel Health
        "requester": "mei.nakagawa@kestrel-health.example",
        "assignee": "sam.osei",
        "tags": ["sso", "auth", "enterprise"],
        "linked_issue": None,
        "created_at": "2026-04-07T10:12:00Z",
        "updated_at": "2026-04-09T16:44:00Z",
        "satisfaction_score": None,
        "messages": [
            {"at": "2026-04-07T10:12:00Z", "from": "mei.nakagawa@kestrel-health.example",
             "kind": "public",
             "body": "Clinicians who belong to more than ~20 directory groups get a generic 'assertion invalid' error at login. Users with fewer groups sign in fine. We cannot reduce group membership for compliance reasons."},
            {"at": "2026-04-07T11:05:00Z", "from": "sam.osei", "kind": "public",
             "body": "Thanks -- that points at how we parse the groups attribute in the SAML assertion. Could you send a redacted assertion XML for one affected user? Please remove any patient-adjacent identifiers first."},
            {"at": "2026-04-09T16:44:00Z", "from": "sam.osei", "kind": "internal_note",
             "body": "Assertion received. Multi-value groups attribute is chunked across two AttributeValue elements above ~20 groups and our mapper only reads the first. Matches open engineering bug on the auth component -- escalating."},
        ],
    },
    {
        "ticket_id": "SUP-1063",
        "subject": "Disputing March invoice INV-202603-0063 - overage charged during your outage",
        "status": "pending", "priority": "high", "channel": "email",
        "account_id": "ACCT-1013",  # Sable Financial
        "requester": "henrik.petrov@sable-financial.example",
        "assignee": "yuki.tanaka",
        "tags": ["billing", "invoice-dispute", "incident"],
        "linked_issue": "ACME-231",
        "created_at": "2026-04-03T09:41:00Z",
        "updated_at": "2026-04-10T14:02:00Z",
        "satisfaction_score": None,
        "messages": [
            {"at": "2026-04-03T09:41:00Z", "from": "henrik.petrov@sable-financial.example",
             "kind": "public",
             "body": "Our March invoice includes an ingestion overage we believe was caused by the March 11 incident: your pipeline replayed our events the next day and double-window counting pushed us over our committed volume. We are withholding payment on INV-202603-0063 pending review."},
            {"at": "2026-04-03T13:20:00Z", "from": "yuki.tanaka", "kind": "public",
             "body": "Understood, and thank you for the specific invoice reference. I have asked our billing engineering team to recompute March usage for your account excluding the incident replay window. We will not apply late fees while this is under review."},
            {"at": "2026-04-10T14:02:00Z", "from": "yuki.tanaka", "kind": "internal_note",
             "body": "Recompute confirms ~6% inflation from the replay on 03-12. Credit memo drafted, waiting on finance approval. Keep status pending."},
        ],
    },
]


def write_support(out: Path, rng: random.Random, accounts: list[dict],
                  issues: list[dict]) -> list[dict]:
    sup = out / "saas" / "tickets"
    sup.mkdir(parents=True, exist_ok=True)
    issue_keys = [i["key"] for i in issues]

    tickets: list[dict] = []
    tid = 1001
    anchor_ids = {t["ticket_id"] for t in ANCHOR_TICKETS}
    for n in range(57):
        while f"SUP-{tid}" in anchor_ids:
            tid += 1
        a = rng.choice(accounts)
        subject, area, opening = rng.choice(TICKET_TOPICS)
        created = business_hours(rand_dt(rng, CORPUS_START,
                                         CORPUS_END - timedelta(days=3)))
        status = rng.choices(["solved", "closed", "open", "pending"],
                             weights=[4, 3, 2, 2])[0]
        agent = rng.choice(SUPPORT_AGENTS)
        contact = rng.choice(a["contacts"])
        msgs = [{"at": iso(created), "from": contact["email"],
                 "kind": "public", "body": opening}]
        t = created
        linked = None
        for _ in range(rng.randrange(1, 4)):
            t = t + timedelta(hours=rng.randrange(1, 30))
            reply = rng.choice(AGENT_REPLIES)
            if "{issue}" in reply:
                linked = rng.choice(issue_keys)
            msgs.append({"at": iso(min(t, CORPUS_END)), "from": agent,
                         "kind": rng.choices(["public", "internal_note"],
                                             weights=[4, 1])[0],
                         "body": reply.format(issue=linked or "",
                                              plan=a["plan"])})
        tickets.append({
            "ticket_id": f"SUP-{tid}",
            "subject": subject,
            "status": status,
            "priority": rng.choices(["low", "normal", "high", "urgent"],
                                    weights=[2, 5, 2, 1])[0],
            "channel": rng.choice(["email", "web", "chat"]),
            "account_id": a["account_id"],
            "requester": contact["email"],
            "assignee": agent,
            "tags": [area],
            "linked_issue": linked,
            "created_at": iso(created),
            "updated_at": msgs[-1]["at"],
            "satisfaction_score": rng.choice([None, None, 3, 4, 4, 5, 5, 2])
            if status in ("solved", "closed") else None,
            "messages": msgs,
        })
        tid += rng.randrange(1, 3)

    tickets.extend(ANCHOR_TICKETS)
    tickets.sort(key=lambda t: t["created_at"])
    with open(sup / "support_tickets.jsonl", "wb") as f:
        f.write(jsonl(tickets))
    return tickets


# ---------------------------------------------------------------------------
# Human feedback
# ---------------------------------------------------------------------------

NPS_VERBATIMS = [
    (9, "The usage explorer paid for itself in a quarter. Exports could be faster."),
    (10, "Rock solid since we onboarded. The March incident was handled with honest comms."),
    (8, "Great product, but SSO setup took three support tickets longer than it should."),
    (7, "Dashboards are excellent. Billing transparency on overages needs work."),
    (6, "Does what it says, but the API rate limits feel arbitrary on the growth plan."),
    (4, "We hit the CSV export cap constantly and only found the limit in a forum answer."),
    (3, "Two invoice disputes in six months. The product is fine; billing is not."),
    (9, "Support actually reads the diagnostics you send. Rare."),
    (5, "Fine for basics. Alerting is too coarse to page on."),
    (10, "The staleness banner after the incident was exactly the right fix -- trust restored."),
    (2, "Login broke for our largest team for two days. Deal-breaker territory."),
    (8, "Metering API is well designed. Docs lag behind the actual behavior sometimes."),
]

# Simulated human corrections on agent extractions over THIS corpus --
# shaped for the flywheel's typed-correction taxonomy (CorrectionType).
ANNOTATION_CORRECTIONS = [
    {
        "correction_id": "CORR-0001",
        "source_path": "documents/product-spec-usage-metering.md",
        "task_type": "extraction",
        "correction_type": "wrong_value",
        "field": "batch_max_events",
        "extracted": {"batch_max_events": 500},
        "corrected": {"batch_max_events": 1000},
        "note": "Agent took the value from the deprecated v0 limits table instead of the current limits section.",
        "annotator": "ingrid.bauer",
        "created_at": "2026-05-04T10:12:00Z",
    },
    {
        "correction_id": "CORR-0002",
        "source_path": "saas/knowledge_base/pages/billing-and-invoicing-faq.md",
        "task_type": "extraction",
        "correction_type": "missing_field",
        "field": "overage_grace_percent",
        "extracted": {},
        "corrected": {"overage_grace_percent": 5},
        "note": "The 5% overage grace threshold is stated in the FAQ but the extraction schema never asks for it.",
        "annotator": "carlos.mendes",
        "created_at": "2026-05-04T10:31:00Z",
    },
    {
        "correction_id": "CORR-0003",
        "source_path": "relational/schema.sql",
        "task_type": "schema_mapping",
        "correction_type": "field_mapping",
        "field": "customers.account_id",
        "extracted": {"maps_to": "dim_customer.customer_key"},
        "corrected": {"maps_to": "crm accounts.account_id (ACCT-*)"},
        "note": "account_id is the CRM identity, not a warehouse surrogate key. The comment in the DDL says so.",
        "annotator": "elena.sokolova",
        "created_at": "2026-05-06T14:02:00Z",
    },
    {
        "correction_id": "CORR-0004",
        "source_path": "saas/tickets/support_tickets.jsonl",
        "task_type": "classification",
        "correction_type": "false_positive",
        "field": "churn_risk",
        "extracted": {"ticket_id": "SUP-1042", "churn_risk": "high"},
        "corrected": {"ticket_id": "SUP-1042", "churn_risk": "low"},
        "note": "Urgent tone during an incident is not churn signal; the customer closed the ticket satisfied (CSAT 4).",
        "annotator": "yuki.tanaka",
        "created_at": "2026-05-11T09:45:00Z",
    },
    {
        "correction_id": "CORR-0005",
        "source_path": "documents/policy-data-retention.txt",
        "task_type": "extraction",
        "correction_type": "wrong_value",
        "field": "raw_event_retention_days",
        "extracted": {"raw_event_retention_days": 90},
        "corrected": {"raw_event_retention_days": 395},
        "note": "90 days is the hot-storage tier only; the policy total including cold storage is 395 days.",
        "annotator": "ingrid.bauer",
        "created_at": "2026-05-11T11:20:00Z",
    },
    {
        "correction_id": "CORR-0006",
        "source_path": "saas/project_mgmt/issues.json",
        "task_type": "summarization",
        "correction_type": "wrong_value",
        "field": "incident_root_cause",
        "extracted": {"incident": "INC-2026-0311", "root_cause": "gateway TLS certificate rotation"},
        "corrected": {"incident": "INC-2026-0311", "root_cause": "consumer build 2026.3.4 held the partition lock during batch decompression"},
        "note": "Agent latched onto the unrelated cert-rotation task in the same sprint. ACME-231 comments state the actual cause.",
        "annotator": "priya.raghavan",
        "created_at": "2026-05-15T16:08:00Z",
    },
    {
        "correction_id": "CORR-0007",
        "source_path": "unstructured/call-transcripts/2026-04-16-bluewater-qbr.txt",
        "task_type": "extraction",
        "correction_type": "missing_field",
        "field": "renewal_risk_flags",
        "extracted": {"renewal_risk_flags": []},
        "corrected": {"renewal_risk_flags": ["single-region deployment concern raised by customer ops lead"]},
        "note": "The concern is voiced verbatim in the transcript but phrased as a question, so the extractor missed it.",
        "annotator": "carlos.mendes",
        "created_at": "2026-05-18T13:37:00Z",
    },
    {
        "correction_id": "CORR-0008",
        "source_path": "saas/crm/opportunities.csv",
        "task_type": "classification",
        "correction_type": "false_positive",
        "field": "expansion_signal",
        "extracted": {"signal": "seat-expansion opportunity implies product-led growth"},
        "corrected": {"signal": "none"},
        "note": "Seat expansion rows in the CRM are sales-created placeholders, not observed product signals.",
        "annotator": "aisha.diallo",
        "created_at": "2026-05-22T10:55:00Z",
    },
]


def write_feedback(out: Path, rng: random.Random, tickets: list[dict],
                   accounts: list[dict]) -> None:
    fb = out / "feedback"
    fb.mkdir(parents=True, exist_ok=True)

    closed = [t for t in tickets if t["status"] in ("solved", "closed")]
    with open(fb / "csat_survey.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["response_id", "ticket_id", "account_id", "score",
                    "comment", "submitted_at"])
        comments = {
            5: ["Fast and clear.", "Solved on the first reply.",
                "Excellent follow-through."],
            4: ["Good outcome, slightly slow.", "Helpful once escalated.",
                "Clear updates throughout."],
            3: ["Resolved, but I had to explain twice.",
                "Okay. Docs should have covered this."],
            2: ["Took too long for something this basic.",
                "Felt like a scripted runaround."],
            1: ["Issue closed without actually being fixed."],
        }
        n = 1
        for t in closed:
            if rng.random() < 0.4:
                continue
            score = t["satisfaction_score"] or rng.choices(
                [5, 4, 3, 2, 1], weights=[5, 4, 2, 1, 1])[0]
            submitted = datetime.fromisoformat(
                t["updated_at"].replace("Z", "+00:00")) + timedelta(
                hours=rng.randrange(2, 48))
            w.writerow([f"CSAT-{n:04d}", t["ticket_id"], t["account_id"],
                        score, rng.choice(comments[score]),
                        iso(min(submitted, CORPUS_END))])
            n += 1

    rows = []
    for i, (score, verbatim) in enumerate(NPS_VERBATIMS * 3):
        a = rng.choice(accounts)
        jitter = max(0, min(10, score + rng.choice([-1, 0, 0, 0, 1])))
        rows.append({
            "response_id": f"NPS-{3001 + i}",
            "account_id": a["account_id"],
            "segment": a["segment"],
            "respondent_role": rng.choice(
                ["admin", "analyst", "engineer", "executive", "ops"]),
            "score": jitter,
            "verbatim": verbatim,
            "survey_wave": rng.choice(["2026-Q1", "2026-Q2"]),
            "submitted_at": iso(business_hours(
                rand_dt(rng, CORPUS_START + timedelta(days=45), CORPUS_END))),
        })
    rows.sort(key=lambda r: r["submitted_at"])
    (fb / "nps_comments.jsonl").write_bytes(jsonl(rows))

    (fb / "annotation_corrections.jsonl").write_bytes(
        jsonl(ANNOTATION_CORRECTIONS))


# ---------------------------------------------------------------------------
# Unstructured: chat + logs
# ---------------------------------------------------------------------------

INCIDENT_CHAT = [
    ("2026-03-11T14:07:00Z", "tom.alvarez",
     "seeing elevated 502s on /v1/usage at the gateway, ~6% and climbing"),
    ("2026-03-11T14:09:00Z", "marcus.webb",
     "upstream latency p99 just went from 300ms to 9s. not the gateway's fault"),
    ("2026-03-11T14:12:00Z", "elena.sokolova",
     "consumer lag on usage-events is growing on partitions 3, 7, 11. started ~14:02"),
    ("2026-03-11T14:15:00Z", "tom.alvarez",
     "declaring SEV2, opening INC-2026-0311. I'm IC"),
    ("2026-03-11T14:22:00Z", "yuki.tanaka",
     "first customer reports coming in -- stale dashboards. Bluewater has an exec review at 17:00, ticket SUP-1042"),
    ("2026-03-11T14:31:00Z", "tom.alvarez",
     "tracking customer-facing symptoms in ACME-231. status page updated"),
    ("2026-03-11T14:44:00Z", "elena.sokolova",
     "correlation: lag started 3h22m after the 08:40 consumer deploy hit 100%. suspicious but not conclusive"),
    ("2026-03-11T15:05:00Z", "elena.sokolova",
     "found it. build 2026.3.4 decompresses batches while holding the partition lock. big batches = lock held for seconds"),
    ("2026-03-11T15:11:00Z", "priya.raghavan",
     "rollback to 2026.3.3, don't hotfix under incident. agreed?"),
    ("2026-03-11T15:12:00Z", "elena.sokolova", "agreed, rolling back now"),
    ("2026-03-11T15:41:00Z", "elena.sokolova",
     "rollback complete, lag draining fast"),
    ("2026-03-11T15:47:00Z", "tom.alvarez",
     "lag at zero, 502s gone. calling it resolved 15:47. postmortem tomorrow 10:00, notes to follow"),
    ("2026-03-11T15:50:00Z", "yuki.tanaka",
     "updating SUP-1042 and the other tickets now. nice work everyone"),
    ("2026-03-12T09:58:00Z", "priya.raghavan",
     "postmortem in 2 min. pre-read: ACME-231 timeline plus the consumer deploy diff"),
]

ROUTINE_CHAT = [
    "standup thread: yesterday {y}, today {t}, no blockers",
    "deploying {svc} build {build} to staging",
    "staging deploy of {svc} verified, promoting to prod",
    "heads up: {svc} error budget at {pct}% for the month",
    "review requested on the {topic} PR, small one",
    "anyone else seeing flaky {topic} tests on CI? rerun passed, filing if it repeats",
    "reminder: dependency upgrade window is Thursday",
    "merged the {topic} change, watch the dashboards for the next hour",
    "on-call handoff complete, quiet week: two pages, both auto-resolved",
    "sprint planning moved to 13:00 tomorrow, same room",
]

CHAT_TOPICS = ["exports", "ingestion", "dashboards", "auth", "billing",
               "webhooks", "aggregation"]
CHAT_SERVICES = ["usage-consumer", "metering-api", "dashboard-web",
                 "billing-worker", "export-renderer"]


def write_chat(out: Path, rng: random.Random) -> None:
    chat_dir = out / "unstructured" / "chat"
    chat_dir.mkdir(parents=True, exist_ok=True)

    messages = []
    for ts, user, text in INCIDENT_CHAT:
        messages.append({"ts": ts, "channel": "eng-observability",
                         "user": user, "text": text})
    day = CORPUS_START
    build = 2026_301
    while day < CORPUS_END:
        if day.weekday() < 5:
            for _ in range(rng.randrange(1, 4)):
                tmpl = rng.choice(ROUTINE_CHAT)
                build += rng.randrange(1, 3)
                text = tmpl.format(
                    y=rng.choice(["ingest fixes", "export polish",
                                  "review backlog", "lag dashboards"]),
                    t=rng.choice(["more of the same", "the sprint goal",
                                  "pairing on the consumer", "test cleanup"]),
                    svc=rng.choice(CHAT_SERVICES),
                    build=f"2026.{build % 100}.{build % 7}",
                    pct=rng.randrange(55, 99),
                    topic=rng.choice(CHAT_TOPICS),
                )
                at = day.replace(hour=rng.randrange(9, 18),
                                 minute=rng.randrange(60))
                messages.append({"ts": iso(at), "channel": "eng-observability",
                                 "user": rng.choice(ENGINEERS), "text": text})
        day += timedelta(days=1)
    messages.sort(key=lambda m: m["ts"])
    (chat_dir / "eng-observability.jsonl").write_bytes(jsonl(messages))


LOG_PATHS = ["/v1/usage", "/v1/usage/batch", "/v1/reports", "/v1/dashboards",
             "/v1/auth/token", "/v1/exports"]


def write_logs(out: Path, rng: random.Random) -> None:
    log_dir = out / "unstructured" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    lines = []
    t = datetime(2026, 3, 11, 13, 30, tzinfo=timezone.utc)
    end = datetime(2026, 3, 11, 16, 30, tzinfo=timezone.utc)
    req = 88000
    while t < end:
        t += timedelta(seconds=rng.randrange(5, 25))
        req += rng.randrange(3, 40)
        path = rng.choice(LOG_PATHS)
        in_incident = INCIDENT_START <= t <= INCIDENT_END
        usage_path = path.startswith("/v1/usage")
        if in_incident and usage_path and rng.random() < 0.35:
            status, latency, level = 502, rng.randrange(9000, 15001), "ERROR"
        elif in_incident and usage_path and rng.random() < 0.5:
            status, latency, level = 200, rng.randrange(2500, 9000), "WARN"
        else:
            status = rng.choices([200, 200, 200, 200, 201, 400, 401, 404],
                                 weights=[20, 20, 20, 20, 3, 2, 1, 1])[0]
            latency = rng.randrange(40, 900)
            level = "INFO" if status < 400 else "WARN"
        line = (f"{iso(t)} {level} api-gateway req_id=r-{req:07d} "
                f"method={'POST' if 'batch' in path or 'token' in path else 'GET'} "
                f"path={path} status={status} latency_ms={latency} "
                f"upstream=metering-api")
        if status == 502:
            line += " error=upstream_timeout"
        lines.append(line)
        if in_incident and rng.random() < 0.08:
            lines.append(
                f"{iso(t)} WARN usage-consumer group=usage-aggregators "
                f"partition={rng.choice([3, 7, 11])} "
                f"lag_events={rng.randrange(120000, 900000)} "
                f"lag_seconds={rng.randrange(300, 2400)} msg=consumer_lag_high")
    (log_dir / "api-gateway-2026-03-11.log").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Event streams (shaped for `freud-schema ingest events` / JsonlEventAdapter)
# ---------------------------------------------------------------------------


def write_events(out: Path, rng: random.Random, accounts: list[dict]) -> None:
    ev = out / "events"
    ev.mkdir(parents=True, exist_ok=True)

    # Product webhook stream: one JSON object per line, fields chosen to
    # match JsonlEventAdapter ({id, type, timestamp, actor, payload, text}).
    rows = []
    n = 1
    day = CORPUS_START
    while day < CORPUS_END:
        for _ in range(rng.randrange(2, 6)):
            a = rng.choice(accounts)
            etype = rng.choices(
                ["report.generated", "export.completed", "alert.triggered",
                 "api_key.rotated", "dashboard.shared", "ingest.backpressure"],
                weights=[5, 3, 2, 1, 2, 1])[0]
            at = day.replace(hour=rng.randrange(0, 24),
                             minute=rng.randrange(60))
            payload = {"account_id": a["account_id"], "plan": a["plan"]}
            if etype == "report.generated":
                payload["report"] = rng.choice(
                    ["weekly-usage", "monthly-billing", "exec-summary"])
                text = f"Generated {payload['report']} report for {a['account_id']}"
            elif etype == "export.completed":
                payload["rows"] = rng.randrange(200, 250000)
                payload["format"] = rng.choice(["csv", "parquet"])
                text = f"Export of {payload['rows']} rows completed for {a['account_id']}"
            elif etype == "alert.triggered":
                payload["metric"] = rng.choice(
                    ["api_calls", "events_ingested", "error_rate"])
                payload["threshold"] = rng.choice([0.8, 0.9, 0.95])
                text = f"Alert on {payload['metric']} breached threshold {payload['threshold']} for {a['account_id']}"
            elif etype == "ingest.backpressure":
                payload["lag_seconds"] = rng.randrange(60, 900)
                text = f"Backpressure: ingestion lag {payload['lag_seconds']}s for {a['account_id']}"
            else:
                text = f"{etype} for {a['account_id']}"
            rows.append({"id": f"whk-{n:06d}", "type": etype,
                         "timestamp": iso(at), "actor": "system",
                         "payload": payload, "text": text})
            n += 1
        day += timedelta(days=1)
    # Incident burst: backpressure + alert storm during the outage window.
    t = INCIDENT_START
    while t < INCIDENT_END:
        a = rng.choice(accounts)
        rows.append({"id": f"whk-{n:06d}", "type": "ingest.backpressure",
                     "timestamp": iso(t), "actor": "system",
                     "payload": {"account_id": a["account_id"],
                                 "lag_seconds": rng.randrange(600, 2400)},
                     "text": f"Backpressure: ingestion lag "
                             f"{rng.randrange(600, 2400)}s for {a['account_id']}"})
        n += 1
        t += timedelta(minutes=rng.randrange(2, 7))
    rows.sort(key=lambda r: r["timestamp"])
    (ev / "product_webhooks.jsonl").write_bytes(jsonl(rows))

    # Admin audit stream (same adapter shape, human actors).
    audit = []
    n = 1
    day = CORPUS_START
    admin_types = ["user.login", "user.invited", "role.changed",
                   "sso.config.updated", "api_key.created", "plan.changed",
                   "export.downloaded"]
    while day < CORPUS_END:
        for _ in range(rng.randrange(1, 4)):
            a = rng.choice(accounts)
            actor = rng.choice(a["contacts"])["email"]
            etype = rng.choices(admin_types, weights=[6, 2, 1, 1, 1, 1, 3])[0]
            at = business_hours(day.replace(hour=rng.randrange(0, 24),
                                            minute=rng.randrange(60)))
            payload = {"account_id": a["account_id"],
                       "ip": f"203.0.113.{rng.randrange(1, 255)}"}
            if etype == "role.changed":
                payload["role"] = rng.choice(["viewer", "editor", "admin"])
            audit.append({"id": f"aud-{n:06d}", "type": etype,
                          "timestamp": iso(at), "actor": actor,
                          "payload": payload,
                          "text": f"{etype} by {actor} on {a['account_id']}"})
            n += 1
        day += timedelta(days=1)
    audit.sort(key=lambda r: r["timestamp"])
    (ev / "admin_audit.jsonl").write_bytes(jsonl(audit))


# ---------------------------------------------------------------------------
# Internal enterprise applications (HRIS / ITSM / finance / IAM / security /
# recruiting) for the same fictional company. A FRESH, independently seeded
# RNG is used here so these draws never perturb the public-corpus outputs
# above -- everything under write_internal() is additive.
# ---------------------------------------------------------------------------

INTERNAL_SEED = 20260312
WINDOW_START = date(2026, 1, 5)
WINDOW_END = date(2026, 6, 30)

# (employee_id, full_name, title, department, team, manager, hire_date,
#  status, termination_date) -- exact HRIS anchors.
_PINNED_EMPLOYEES = [
    ("EMP-1001", "Renata Voss", "CEO", "Executive", "executive", "", "2022-03-01", "active", ""),
    ("EMP-1002", "Grace Adeyemi", "CFO", "Finance", "finance", "EMP-1001", "2022-09-12", "active", ""),
    ("EMP-1003", "Johan Brandt", "VP Engineering", "Engineering", "engineering", "EMP-1001", "2022-06-06", "active", ""),
    ("EMP-1004", "Maya Kaplan", "VP People", "People", "people", "EMP-1001", "2023-01-16", "active", ""),
    ("EMP-1005", "Diego Fuentes", "Head of IT", "IT", "it", "EMP-1002", "2022-11-07", "active", ""),
    ("EMP-1006", "Sylvia Ngata", "General Counsel", "Legal & Compliance", "legal", "EMP-1001", "2023-05-22", "active", ""),
    ("EMP-1007", "Ravi Chandran", "Security Engineer", "Security", "security", "EMP-1005", "2024-02-05", "active", ""),
    ("EMP-1008", "Nora Vasquez", "VP Customer Experience", "Customer Experience", "customer-experience", "EMP-1001", "2023-03-13", "active", ""),
    ("EMP-1009", "Theo Marchand", "VP Sales", "Sales", "sales", "EMP-1001", "2023-08-28", "active", ""),
    ("EMP-1010", "Priya Raghavan", "Engineering Manager", "Engineering", "platform", "EMP-1003", "2023-04-03", "active", ""),
    ("EMP-1011", "Marcus Webb", "Senior Backend Engineer", "Engineering", "platform", "EMP-1010", "2023-10-09", "active", ""),
    ("EMP-1012", "Elena Sokolova", "Data Engineer", "Engineering", "pipeline", "EMP-1010", "2024-01-15", "active", ""),
    ("EMP-1013", "Dana Kim", "Frontend Engineer", "Engineering", "platform", "EMP-1010", "2024-05-20", "active", ""),
    ("EMP-1014", "Tom Alvarez", "Site Reliability Engineer", "Engineering", "infra", "EMP-1010", "2023-07-17", "active", ""),
    ("EMP-1015", "Yuki Tanaka", "Support Lead", "Customer Experience", "support", "EMP-1008", "2023-09-04", "active", ""),
    ("EMP-1016", "Sam Osei", "Support Engineer", "Customer Experience", "support", "EMP-1015", "2024-08-12", "active", ""),
    ("EMP-1017", "Ingrid Bauer", "Product Manager", "Product", "product", "EMP-1001", "2023-11-27", "active", ""),
    ("EMP-1018", "Carlos Mendes", "Customer Success Manager", "Customer Experience", "success", "EMP-1008", "2024-03-04", "active", ""),
    ("EMP-1019", "Aisha Diallo", "Account Executive", "Sales", "sales", "EMP-1009", "2024-06-10", "active", ""),
    ("EMP-1020", "Noah Lindqvist", "Data Engineer", "Engineering", "pipeline", "EMP-1010", "2024-09-23", "active", ""),
    ("EMP-1021", "Fatima al-Rashid", "QA Engineer", "Engineering", "platform", "EMP-1010", "2025-01-06", "active", ""),
    ("EMP-1030", "Omar Haddad", "IT Support Specialist", "IT", "it", "EMP-1005", "2024-04-08", "active", ""),
    ("EMP-1031", "Lena Fischer", "IT Systems Engineer", "IT", "it", "EMP-1005", "2023-12-11", "active", ""),
    ("EMP-1042", "Derek Mun", "Sales Development Representative", "Sales", "sales", "EMP-1009", "2025-08-04", "terminated", "2026-03-31"),
    ("EMP-1107", "Talia Reyes", "Data Engineer", "Engineering", "pipeline", "EMP-1010", "2026-05-11", "active", ""),
]

_DEPT_LEADER = {
    "Executive": "EMP-1001", "Finance": "EMP-1002", "Engineering": "EMP-1003",
    "People": "EMP-1004", "IT": "EMP-1005", "Legal & Compliance": "EMP-1006",
    "Security": "EMP-1007", "Customer Experience": "EMP-1008", "Sales": "EMP-1009",
    "Product": "EMP-1017",
}

# Department head-count targets for the generated remainder (~99 people).
_DEPT_COUNTS = [
    ("Engineering", 35), ("Sales", 15), ("Customer Experience", 15),
    ("Product", 6), ("Marketing", 8), ("Finance", 6), ("People", 5),
    ("IT", 4), ("Legal & Compliance", 2), ("Security", 3),
]

# (title, salary_band) pools per department for generated ICs.
_TITLES = {
    "Engineering": [("Backend Engineer", "B3"), ("Frontend Engineer", "B3"),
                    ("Data Engineer", "B3"), ("Senior Backend Engineer", "B4"),
                    ("Senior Frontend Engineer", "B4"), ("Site Reliability Engineer", "B3"),
                    ("QA Engineer", "B2"), ("Staff Engineer", "B4"),
                    ("Machine Learning Engineer", "B4"), ("Platform Engineer", "B3")],
    "Sales": [("Account Executive", "B3"), ("Sales Development Representative", "B2"),
              ("Senior Account Executive", "B4"), ("Sales Engineer", "B3")],
    "Customer Experience": [("Support Engineer", "B2"), ("Customer Success Manager", "B3"),
                            ("Senior Support Engineer", "B3"), ("Onboarding Specialist", "B2")],
    "Product": [("Product Manager", "B4"), ("Senior Product Manager", "B4"),
                ("Product Designer", "B3"), ("UX Researcher", "B3")],
    "Marketing": [("Marketing Manager", "B3"), ("Content Strategist", "B2"),
                  ("Demand Generation Specialist", "B3"),
                  ("Product Marketing Manager", "B4"), ("Marketing Coordinator", "B1")],
    "Finance": [("Financial Analyst", "B3"), ("Accountant", "B2"),
                ("Senior Financial Analyst", "B4"), ("Accounts Payable Specialist", "B1")],
    "People": [("Recruiter", "B2"), ("People Operations Specialist", "B2"),
               ("HR Business Partner", "B3"), ("Talent Acquisition Lead", "B3")],
    "IT": [("IT Support Specialist", "B2"), ("IT Systems Engineer", "B3"),
           ("IT Administrator", "B2")],
    "Legal & Compliance": [("Compliance Analyst", "B3"), ("Corporate Counsel", "B4")],
    "Security": [("Security Analyst", "B3"), ("Security Engineer", "B3"),
                 ("Security Operations Analyst", "B3")],
}

_FIRST_NAMES = [
    "Aaron", "Bianca", "Cedric", "Dahlia", "Emilio", "Farah", "Gustavo", "Hana",
    "Idris", "Juno", "Kai", "Liora", "Mateo", "Nadine", "Oscar", "Petra",
    "Quentin", "Rosa", "Selim", "Tara", "Ulric", "Vera", "Wesley", "Ximena",
    "Yara", "Zane", "Anika", "Bruno", "Celeste", "Darius", "Esme", "Felipe",
    "Greta", "Hugo", "Imani", "Jasper", "Kira", "Lorenzo", "Mira", "Niko",
    "Ophelia", "Pablo", "Rania", "Sven", "Thea", "Uma", "Viktor", "Wanda",
    "Yusuf", "Zoe",
]
_LAST_NAMES = [
    "Abara", "Bellini", "Cho", "Dvorak", "Engberg", "Falk", "Gutierrez",
    "Halloran", "Ibsen", "Jansen", "Kovac", "Larsen", "Mistry", "Novak",
    "Oyelaran", "Pereira", "Quist", "Rasmussen", "Sato", "Thorne", "Ustinov",
    "Varga", "Wilder", "Xu", "Yamada", "Zielinski", "Ashby", "Bourne",
    "Castellano", "Derevko", "Eberhardt", "Finlay", "Grimaldi", "Haas",
    "Ishikawa", "Jovergaard", "Lindholm", "Moreau", "Nunez", "Ortega",
    "Pryce", "Rourke", "Sandoval", "Tremblay", "Ueno", "Vasilenko",
    "Whitlock", "Yoon", "Zabel",
]

_BAND_RANGE = {"B1": (60000, 82000), "B2": (78000, 112000), "B3": (105000, 150000),
               "B4": (150000, 205000), "B5": (190000, 285000)}


def _d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _localpart(full_name: str) -> str:
    parts = full_name.split()
    first = parts[0].lower()
    last = "".join(c for c in "".join(parts[1:]).lower() if c.isalnum())
    return f"{first}.{last}"


def _band_for_title(title: str) -> str:
    t = title.lower()
    if "ceo" in t:
        return "B5"
    if t == "cfo" or "vp " in t or "general counsel" in t or "head of" in t or "chief" in t:
        return "B5"
    if "senior" in t or "director" in t or "principal" in t or "staff" in t:
        return "B4"
    if "success manager" in t:
        return "B3"
    if "manager" in t or "lead" in t:
        return "B4"
    if ("support" in t or "representative" in t or t.startswith("qa")
            or "specialist" in t or "coordinator" in t or "associate" in t):
        return "B2"
    return "B3"


def _salary(rng: random.Random, band: str, title: str) -> int:
    if "ceo" in title.lower():
        return 320000
    lo, hi = _BAND_RANGE[band]
    return int(round(rng.uniform(lo, hi) / 1000.0)) * 1000


def _team_for(rng: random.Random, dept: str) -> str:
    if dept == "Engineering":
        return rng.choice(["platform", "pipeline", "infra"])
    if dept == "Customer Experience":
        return rng.choice(["support", "success"])
    return {"Sales": "sales", "Product": "product", "Marketing": "marketing",
            "Finance": "finance", "People": "people", "IT": "it",
            "Legal & Compliance": "legal", "Security": "security"}[dept]


def _build_internal_employees(rng: random.Random) -> list[dict]:
    employees: list[dict] = []
    used_ids: set[int] = set()
    used_lp: set[str] = set()

    for (eid, name, title, dept, team, mgr, hire, status, term) in _PINNED_EMPLOYEES:
        used_ids.add(int(eid.split("-")[1]))
        lp = _localpart(name)
        used_lp.add(lp)
        band = _band_for_title(title)
        sal = _salary(rng, band, title)
        loc = rng.choices(["Harbor City HQ", "Remote"], weights=[3, 2])[0]
        employees.append({
            "employee_id": eid, "full_name": name,
            "email": f"{lp}@{COMPANY_DOMAIN}", "department": dept, "team": team,
            "title": title, "manager_employee_id": mgr, "location": loc,
            "hire_date": hire, "employment_type": "full_time", "status": status,
            "termination_date": term, "salary_band": band,
            "base_salary_usd": sal, "pinned": True,
        })

    gen_depts: list[str] = []
    for dept, count in _DEPT_COUNTS:
        gen_depts.extend([dept] * count)
    pool_ids = [n for n in range(1022, 1141) if n not in used_ids]
    gen_ids = sorted(rng.sample(pool_ids, len(gen_depts)))

    generated: list[dict] = []
    for gid, dept in zip(gen_ids, gen_depts):
        title, band = rng.choice(_TITLES[dept])
        while True:
            lp = f"{rng.choice(_FIRST_NAMES).lower()}.{rng.choice(_LAST_NAMES).lower()}"
            if lp not in used_lp:
                break
        used_lp.add(lp)
        first, last = (p.capitalize() for p in lp.split("."))
        name = f"{first} {last}"
        if dept == "Engineering":
            mgr = rng.choice(["EMP-1010", "EMP-1003"])
        elif dept == "Marketing":
            mgr = "EMP-1001"          # provisional; a marketing head is set below
        else:
            mgr = _DEPT_LEADER[dept]
        hire = rand_dt(rng, datetime(2022, 3, 1, tzinfo=timezone.utc),
                       datetime(2026, 4, 30, tzinfo=timezone.utc)).date()
        rec = {
            "employee_id": f"EMP-{gid}", "full_name": name,
            "email": f"{lp}@{COMPANY_DOMAIN}", "department": dept,
            "team": _team_for(rng, dept), "title": title,
            "manager_employee_id": mgr, "location": rng.choices(
                ["Harbor City HQ", "Remote"], weights=[3, 2])[0],
            "hire_date": hire.isoformat(), "employment_type": "full_time",
            "status": "active", "termination_date": "", "salary_band": band,
            "base_salary_usd": _salary(rng, band, title), "pinned": False,
        }
        generated.append(rec)
        employees.append(rec)

    # Promote the lowest-id Marketing hire to department head (Marketing has no
    # pinned leader) and reparent the rest of Marketing under them.
    mkt = sorted([e for e in generated if e["department"] == "Marketing"],
                 key=lambda e: e["employee_id"])
    lead = mkt[0]
    lead.update({"title": "Head of Marketing", "team": "marketing",
                 "manager_employee_id": "EMP-1001", "salary_band": "B5",
                 "base_salary_usd": _salary(rng, "B5", "Head of Marketing")})
    for e in mkt[1:]:
        e["manager_employee_id"] = lead["employee_id"]

    # 5 additional terminations among generated ICs hired early enough that a
    # 2025-06..2026-05 termination sits after their hire. Exclude the head.
    elig = [e for e in generated
            if e is not lead and _d(e["hire_date"]) <= _d("2025-03-01")]
    for e in rng.sample(elig, 5):
        hire = _d(e["hire_date"])
        lo = max(_d("2025-06-01"), hire + timedelta(days=150))
        hi = _d("2026-05-25")
        term = lo + timedelta(days=rng.randrange((hi - lo).days))
        e["status"] = "terminated"
        e["termination_date"] = term.isoformat()

    employees.sort(key=lambda e: int(e["employee_id"].split("-")[1]))
    return employees


def _leader_email_map(employees: list[dict]) -> dict:
    by_id = {e["employee_id"]: e for e in employees}
    m = {dept: by_id[eid]["email"] for dept, eid in _DEPT_LEADER.items()}
    head = next(e for e in employees if e["title"] == "Head of Marketing")
    m["Marketing"] = head["email"]
    return m


def _write_hris(out: Path, employees: list[dict]) -> None:
    d = out / "internal" / "hris"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "employees.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["employee_id", "full_name", "email", "department", "team",
                    "title", "manager_employee_id", "location", "hire_date",
                    "employment_type", "status", "termination_date",
                    "salary_band", "base_salary_usd"])
        for e in employees:
            w.writerow([e["employee_id"], e["full_name"], e["email"],
                        e["department"], e["team"], e["title"],
                        e["manager_employee_id"], e["location"], e["hire_date"],
                        e["employment_type"], e["status"],
                        e["termination_date"], e["salary_band"],
                        e["base_salary_usd"]])


def _write_pto(out: Path, rng: random.Random, employees: list[dict]) -> None:
    d = out / "internal" / "hris"
    eligible = [e for e in employees
                if e["status"] == "active" and _d(e["hire_date"]) <= _d("2026-06-01")]
    days_by_type = {"vacation": (1, 10), "sick": (1, 3),
                    "parental": (5, 15), "bereavement": (2, 4)}
    with open(d / "pto_requests.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["request_id", "employee_id", "type", "start_date",
                    "end_date", "days", "status", "submitted_at"])
        for i in range(150):
            e = rng.choice(eligible)
            typ = rng.choices(["vacation", "sick", "parental", "bereavement"],
                              weights=[6, 3, 1, 1])[0]
            lo_d, hi_d = days_by_type[typ]
            days = rng.randint(lo_d, hi_d)
            lo = max(WINDOW_START, _d(e["hire_date"]) + timedelta(days=7))
            hi = date(2026, 5, 20)
            sub = lo + timedelta(days=rng.randrange((hi - lo).days))
            start = sub + timedelta(days=rng.randint(3, 30))
            end = start + timedelta(days=max(0, days - 1))
            submitted = business_hours(datetime(sub.year, sub.month, sub.day,
                                                rng.randrange(8, 18),
                                                rng.randrange(60), tzinfo=timezone.utc))
            w.writerow([f"PTO-{i + 1:04d}", e["employee_id"], typ,
                        start.isoformat(), end.isoformat(), days,
                        rng.choices(["approved", "pending", "denied"],
                                    weights=[8, 1, 1])[0], iso(submitted)])


def _build_assets(rng: random.Random, employees: list[dict]) -> list[dict]:
    active = [e for e in employees if e["status"] == "active"]
    active_others = [e for e in active if e["employee_id"] != "EMP-1107"]
    laptop_models = ["Corvid Book 14", "Corvid Book 16"]

    assets: list[dict] = []

    def add(aid, atype, model, assigned, po, purchased, status):
        assets.append({
            "asset_id": f"AST-{aid}", "asset_type": atype, "model": model,
            "serial_number": f"SN-{rng.getrandbits(32):08x}",
            "assigned_to_employee_id": assigned, "purchase_order_id": po,
            "purchased_date": purchased.isoformat(), "status": status,
            "warranty_end": (purchased + timedelta(days=1095)).isoformat(),
        })

    n_stock = 19
    pool = [x for x in range(1001, 1301) if x not in (1077, 1289)]
    ids = sorted(rng.sample(pool, len(active_others) + n_stock))
    laptop_ids = ids[:len(active_others)]
    stock_ids = ids[len(active_others):]

    for aid, e in zip(laptop_ids, active_others):
        hire = _d(e["hire_date"])
        purchased = max(_d("2022-03-01"), hire + timedelta(days=rng.randint(0, 4)))
        add(aid, "laptop", rng.choice(laptop_models), e["employee_id"], "",
            purchased, "in_use")

    for aid in stock_ids:
        atype = rng.choices(["laptop", "monitor", "phone", "dock"],
                            weights=[4, 3, 2, 2])[0]
        model = {"laptop": rng.choice(laptop_models), "monitor": "Vistapane 27",
                 "phone": "Slatestone S3", "dock": "Corvid Dock D2"}[atype]
        purchased = rand_dt(rng, datetime(2022, 6, 1, tzinfo=timezone.utc),
                            datetime(2026, 5, 1, tzinfo=timezone.utc)).date()
        add(aid, atype, model, "", "",
            purchased, rng.choices(["stock", "retired"], weights=[3, 2])[0])

    # Anchors.
    add(1289, "laptop", "Corvid Book 14", "EMP-1107", "PO-2026-041",
        _d("2026-05-04"), "in_use")
    add(1077, "laptop", "Corvid Book 14", "", "", _d("2025-08-01"), "stock")

    assets.sort(key=lambda a: int(a["asset_id"].split("-")[1]))
    return assets


def _write_assets(out: Path, assets: list[dict]) -> None:
    d = out / "internal" / "itsm"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "assets.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["asset_id", "asset_type", "model", "serial_number",
                    "assigned_to_employee_id", "purchase_order_id",
                    "purchased_date", "status", "warranty_end"])
        for a in assets:
            w.writerow([a["asset_id"], a["asset_type"], a["model"],
                        a["serial_number"], a["assigned_to_employee_id"],
                        a["purchase_order_id"], a["purchased_date"],
                        a["status"], a["warranty_end"]])


_CHANGE_TITLES = [
    "Deploy {svc} build {build} to production",
    "OS patching batch - engineering laptops",
    "DNS record update for {sub}.acme-analytics.example",
    "Firewall rule update for {svc}",
    "SSO configuration update - {app}",
    "Database index maintenance",
    "TLS certificate renewal - {sub}",
    "Rotate service account credentials",
    "Kubernetes node pool upgrade",
    "Enable rate limiting on {svc}",
]
_CHANGE_IMPLEMENTERS = ["tom.alvarez", "elena.sokolova", "marcus.webb",
                        "noah.lindqvist", "dana.kim", "lena.fischer", "omar.haddad"]
_CHANGE_APPROVERS = ["priya.raghavan", "diego.fuentes", "johan.brandt"]


def _build_changes(rng: random.Random) -> list[dict]:
    def em(local):
        return f"{local}@{COMPANY_DOMAIN}"

    pinned = [
        {"change_id": "CHG-2026-0018", "title": "API gateway TLS certificate rotation",
         "change_type": "standard", "risk": "low", "requested_by": em("tom.alvarez"),
         "implemented_by": em("tom.alvarez"), "approved_by": em("priya.raghavan"),
         "scheduled_start": "2026-03-05T09:00:00Z", "actual_start": "2026-03-05T09:00:00Z",
         "actual_end": "2026-03-05T09:35:00Z", "status": "success",
         "linked_incident": "", "notes": "Certificate rotated on the API gateway; no downtime.",
         "_date": "2026-03-05", "_anchor": True},
        {"change_id": "CHG-2026-0023", "title": "usage-consumer build 2026.3.4 production rollout",
         "change_type": "normal", "risk": "medium", "requested_by": em("elena.sokolova"),
         "implemented_by": em("elena.sokolova"), "approved_by": em("priya.raghavan"),
         "scheduled_start": "2026-03-11T08:00:00Z", "actual_start": "2026-03-11T08:12:00Z",
         "actual_end": "2026-03-11T08:40:00Z", "status": "failed",
         "linked_incident": "INC-2026-0311",
         "notes": "Rollout completed clean; regression under large batched payloads surfaced at traffic peak ~14:02 and was traced to this build. See INC-2026-0311.",
         "_date": "2026-03-11", "_anchor": True},
        {"change_id": "CHG-2026-0024", "title": "EMERGENCY: roll back usage-consumer to build 2026.3.3",
         "change_type": "emergency", "risk": "high", "requested_by": em("elena.sokolova"),
         "implemented_by": em("elena.sokolova"), "approved_by": em("priya.raghavan"),
         "scheduled_start": "2026-03-11T15:12:00Z", "actual_start": "2026-03-11T15:12:00Z",
         "actual_end": "2026-03-11T15:41:00Z", "status": "success",
         "linked_incident": "INC-2026-0311",
         "notes": "Rollback resolved consumer lag; incident resolved 15:47Z. Retrospective review completed 2026-03-12.",
         "_date": "2026-03-11", "_anchor": True},
        {"change_id": "CHG-2026-0031", "title": "usage-consumer build 2026.3.9 rollout (DATA-88 fix)",
         "change_type": "normal", "risk": "medium", "requested_by": em("elena.sokolova"),
         "implemented_by": em("elena.sokolova"), "approved_by": em("priya.raghavan"),
         "scheduled_start": "2026-03-24T08:00:00Z", "actual_start": "2026-03-24T08:05:00Z",
         "actual_end": "2026-03-24T08:33:00Z", "status": "success",
         "linked_incident": "", "notes": "Root-cause fix shipped; consumer lag alarms quiet post-deploy.",
         "_date": "2026-03-24", "_anchor": True},
    ]

    app_names = [a[1] for a in _APPS]
    generated = []
    for _ in range(30):
        cd = rand_dt(rng, datetime(2026, 1, 5, tzinfo=timezone.utc),
                     datetime(2026, 6, 27, tzinfo=timezone.utc))
        start = business_hours(cd).replace(second=0, microsecond=0)
        dur = timedelta(minutes=rng.randrange(15, 90))
        status = rng.choices(["success", "failed"], weights=[9, 1])[0]
        title = rng.choice(_CHANGE_TITLES).format(
            svc=rng.choice(CHAT_SERVICES),
            build=f"2026.{rng.randrange(1, 7)}.{rng.randrange(1, 9)}",
            sub=rng.choice(["api", "app", "dashboards", "auth", "cdn"]),
            app=rng.choice(app_names))
        generated.append({
            "change_id": None, "title": title,
            "change_type": rng.choices(["standard", "normal", "emergency"],
                                       weights=[5, 4, 1])[0],
            "risk": rng.choices(["low", "medium", "high"], weights=[5, 3, 1])[0],
            "requested_by": em(rng.choice(_CHANGE_IMPLEMENTERS)),
            "implemented_by": em(rng.choice(_CHANGE_IMPLEMENTERS)),
            "approved_by": em(rng.choice(_CHANGE_APPROVERS)),
            "scheduled_start": iso(start), "actual_start": iso(start),
            "actual_end": iso(start + dur), "status": status,
            "linked_incident": "",
            "notes": "Routine change completed within the maintenance window."
            if status == "success" else "Change backed out after validation failure.",
            "_date": start.date().isoformat(), "_anchor": False,
        })

    changes = pinned + generated
    changes.sort(key=lambda c: (c["_date"], c.get("_anchor", False)))
    next_num = 1
    for c in changes:
        if c["_anchor"]:
            next_num = max(next_num, int(c["change_id"].split("-")[-1]) + 1)
        else:
            c["change_id"] = f"CHG-2026-{next_num:04d}"
            next_num += 1
    return changes


def _write_changes(out: Path, changes: list[dict]) -> None:
    d = out / "internal" / "itsm"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "changes.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["change_id", "title", "change_type", "risk", "requested_by",
                    "implemented_by", "approved_by", "scheduled_start",
                    "actual_start", "actual_end", "status", "linked_incident",
                    "notes"])
        for c in sorted(changes, key=lambda c: c["change_id"]):
            w.writerow([c["change_id"], c["title"], c["change_type"], c["risk"],
                        c["requested_by"], c["implemented_by"], c["approved_by"],
                        c["scheduled_start"], c["actual_start"], c["actual_end"],
                        c["status"], c["linked_incident"], c["notes"]])


_TICKET_TMPL = [
    ("access", "Request access to {app}"),
    ("access", "Cannot log into {app} after password change"),
    ("access", "Shared drive permission request"),
    ("access", "Password reset request"),
    ("access", "MFA device lost, need re-enrollment"),
    ("software", "Software install request: {app}"),
    ("software", "Application crashing on launch: {app}"),
    ("hardware", "Laptop battery draining quickly"),
    ("hardware", "Slow laptop performance"),
    ("hardware", "New monitor request"),
    ("hardware", "Docking station not detecting external display"),
    ("hardware", "Replacement charger needed"),
    ("network", "VPN won't connect from home"),
    ("network", "Wi-Fi drops on the 3rd floor"),
    ("network", "Guest wifi access for visitor"),
    ("onboarding", "New hire setup checklist"),
    ("offboarding", "Departing contractor access removal"),
    ("security", "Reported suspicious email"),
]
_TICKET_RES = [
    "Resolved remotely; user confirmed working.",
    "Access granted per manager approval.",
    "Hardware replaced from stock.",
    "Reset completed; user notified.",
    "Reinstalled application; issue cleared.",
    "Network configuration corrected.",
    "Walked user through setup; closed.",
]


def _build_it_tickets(rng: random.Random, employees: list[dict],
                      assets: list[dict], changes: list[dict]) -> list[dict]:
    active = [e for e in employees if e["status"] == "active"]
    gen_active = [e for e in active if not e["pinned"]]
    asset_ids = [a["asset_id"] for a in assets]
    change_ids = [c["change_id"] for c in changes]
    app_names = [a[1] for a in _APPS]

    g1, g2 = rng.sample(gen_active, 2)
    anchors = [
        {"ticket_id": "IT-2231", "opened_at": "2026-03-30T09:15:00Z",
         "closed_at": "2026-04-01T16:20:00Z", "status": "closed", "priority": "normal",
         "category": "offboarding", "requester_employee_id": "EMP-1009",
         "requester_email": f"theo.marchand@{COMPANY_DOMAIN}", "assignee": "omar.haddad",
         "summary": "Offboarding: Derek Mun (EMP-1042) - last day 2026-03-31",
         "resolution_note": "Laptop AST-1077 returned and wiped; badge deactivated; directory account disabled.",
         "linked_asset": "AST-1077", "linked_change": None, "_anchor": True},
        {"ticket_id": "IT-2412", "opened_at": "2026-05-06T10:05:00Z",
         "closed_at": "2026-05-12T11:30:00Z", "status": "closed", "priority": "normal",
         "category": "onboarding", "requester_employee_id": "EMP-1010",
         "requester_email": f"priya.raghavan@{COMPANY_DOMAIN}", "assignee": "lena.fischer",
         "summary": "Onboarding: Talia Reyes (EMP-1107) - start 2026-05-11",
         "resolution_note": "Laptop AST-1289 issued; accounts provisioned (email, SSO, Stoneferry CI); badge issued.",
         "linked_asset": "AST-1289", "linked_change": None, "_anchor": True},
        {"ticket_id": "IT-2467", "opened_at": "2026-05-20T09:42:00Z",
         "closed_at": "2026-05-20T10:30:00Z", "status": "closed", "priority": "high",
         "category": "security", "requester_employee_id": g1["employee_id"],
         "requester_email": g1["email"], "assignee": "omar.haddad",
         "summary": "Reported suspicious email",
         "resolution_note": "Confirmed phishing; sender domain blocked; forwarded to security.",
         "linked_asset": None, "linked_change": None, "_anchor": True},
        {"ticket_id": "IT-2468", "opened_at": "2026-05-20T11:18:00Z",
         "closed_at": "2026-05-20T12:05:00Z", "status": "closed", "priority": "high",
         "category": "security", "requester_employee_id": g2["employee_id"],
         "requester_email": g2["email"], "assignee": "omar.haddad",
         "summary": "Reported suspicious email",
         "resolution_note": "Confirmed phishing; sender domain blocked; forwarded to security.",
         "linked_asset": None, "linked_change": None, "_anchor": True},
    ]

    generated = []
    for _ in range(80):
        cat, tmpl = rng.choice(_TICKET_TMPL)
        e = rng.choice(active)
        opened = business_hours(rand_dt(rng, datetime(2026, 1, 5, tzinfo=timezone.utc),
                                        datetime(2026, 6, 28, tzinfo=timezone.utc)))
        status = rng.choices(["closed", "open", "in_progress"], weights=[7, 2, 1])[0]
        if status == "closed":
            closed = iso(opened + timedelta(hours=rng.randrange(1, 120)))
            res = rng.choice(_TICKET_RES)
        else:
            closed, res = None, None
        generated.append({
            "ticket_id": None, "opened_at": iso(opened), "closed_at": closed,
            "status": status,
            "priority": rng.choices(["low", "normal", "high"], weights=[3, 5, 2])[0],
            "category": cat, "requester_employee_id": e["employee_id"],
            "requester_email": e["email"],
            "assignee": rng.choice(["omar.haddad", "lena.fischer"]),
            "summary": tmpl.format(app=rng.choice(app_names)),
            "resolution_note": res,
            "linked_asset": rng.choice(asset_ids)
            if cat == "hardware" and rng.random() < 0.4 else None,
            "linked_change": rng.choice(change_ids) if rng.random() < 0.08 else None,
            "_anchor": False,
        })

    tickets = anchors + generated
    tickets.sort(key=lambda t: (t["opened_at"], t.get("_anchor", False)))
    next_num = 2001
    for t in tickets:
        if t["_anchor"]:
            next_num = max(next_num, int(t["ticket_id"].split("-")[1]) + 1)
        else:
            t["ticket_id"] = f"IT-{next_num}"
            next_num += 1
    return tickets


def _write_it_tickets(out: Path, tickets: list[dict]) -> None:
    d = out / "internal" / "itsm"
    d.mkdir(parents=True, exist_ok=True)
    keys = ["ticket_id", "opened_at", "closed_at", "status", "priority",
            "category", "requester_employee_id", "requester_email", "assignee",
            "summary", "resolution_note", "linked_asset", "linked_change"]
    rows = [{k: t.get(k) for k in keys} for t in tickets]
    (d / "it_tickets.jsonl").write_bytes(jsonl(rows))


_VENDORS = [
    ("Nimbostrat Cloud", "cloud infrastructure"),
    ("Fernwake Software", "HRIS"),
    ("Torchstone Systems", "ITSM"),
    ("Quillbrook Financial Software", "ERP"),
    ("Lanternfell Inc", "expense management"),
    ("Saltmarsh Software", "CRM"),
    ("Harrowgate Talent Systems", "ATS"),
    ("Nightledger Security", "SIEM"),
    ("Doorstile Access Systems", "badge/physical access"),
    ("Corvid Hardware Supply", "IT hardware"),
    ("Harbor City Properties", "facilities/rent"),
    ("Ironquay Office Services", "office services"),
    ("Bluecrest Insurance Brokers", "insurance"),
    ("Ashgrove Audit & Assurance", "audit"),
    ("Glimmerfen Communications", "comms tools"),
    ("Stoneferry DevTools", "CI/CD"),
    ("Bramblehold Networks", "VPN/network"),
    ("Wrenfield Travel", "travel agency"),
]


def _write_vendors(out: Path, rng: random.Random) -> list[dict]:
    d = out / "internal" / "finance"
    d.mkdir(parents=True, exist_ok=True)
    vendors = []
    with open(d / "vendors.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["vendor_id", "vendor_name", "category", "payment_terms", "active"])
        for i, (name, cat) in enumerate(_VENDORS):
            vid = f"VEN-{i + 1:03d}"
            terms = rng.choices(["net-30", "net-45", "due-on-receipt"],
                                weights=[6, 3, 1])[0]
            active = "true" if rng.random() < 0.9 else "false"
            w.writerow([vid, name, cat, terms, active])
            vendors.append({"vendor_id": vid, "vendor_name": name, "category": cat})
    return vendors


_APPS = [
    ("APP-01", "Fernwake People", "HRIS", "People"),
    ("APP-02", "Torchstone Desk", "ITSM", "IT"),
    ("APP-03", "Quillbrook Ledger", "finance", "Finance"),
    ("APP-04", "Lanternfell Expense", "expense", "Finance"),
    ("APP-05", "Saltmarsh CRM", "CRM", "Sales"),
    ("APP-06", "Harrowgate Hire", "ATS", "People"),
    ("APP-07", "Nightledger SIEM", "security", "Security"),
    ("APP-08", "Doorstile Badge Admin", "physical access", "IT"),
    ("APP-09", "Bellwether Wiki", "knowledge", "IT"),
    ("APP-10", "Glimmerfen Chat", "communications", "IT"),
    ("APP-11", "Stoneferry CI", "developer tools", "Engineering"),
    ("APP-12", "Bramblehold VPN", "network", "IT"),
    ("APP-13", "Acme Analytics Prod Admin", "internal product admin", "Engineering"),
    ("APP-14", "Marrowgate Vault", "secrets management", "Security"),
]
# Per-app plausible seat-count ranges.
_APP_USERS = {
    "APP-01": (110, 123), "APP-02": (110, 123), "APP-03": (6, 12),
    "APP-04": (100, 120), "APP-05": (28, 42), "APP-06": (4, 8),
    "APP-07": (3, 6), "APP-08": (4, 8), "APP-09": (108, 123),
    "APP-10": (110, 123), "APP-11": (40, 55), "APP-12": (100, 120),
    "APP-13": (18, 30), "APP-14": (14, 24),
}


def _write_app_catalog(out: Path, rng: random.Random) -> None:
    d = out / "internal" / "iam"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "app_catalog.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["app_id", "app_name", "category", "owner_department",
                    "sso_enforced", "user_count"])
        for aid, name, cat, owner in _APPS:
            lo, hi = _APP_USERS[aid]
            sso = "false" if aid == "APP-13" else "true"
            w.writerow([aid, name, cat, owner, sso, rng.randint(lo, hi)])


def _write_purchase_orders(out: Path, rng: random.Random,
                           vendors: list[dict]) -> None:
    d = out / "internal" / "finance"
    it_cats = {"IT hardware", "ITSM", "VPN/network", "CI/CD", "badge/physical access",
               "cloud infrastructure", "SIEM"}
    people_cats = {"ATS", "HRIS"}
    amount_by_cat = {
        "cloud infrastructure": (40000, 90000), "HRIS": (8000, 30000),
        "ITSM": (6000, 24000), "ERP": (10000, 40000), "expense management": (5000, 18000),
        "CRM": (12000, 45000), "ATS": (6000, 22000), "SIEM": (15000, 50000),
        "badge/physical access": (4000, 20000), "IT hardware": (2000, 15000),
        "facilities/rent": (30000, 70000), "office services": (3000, 15000),
        "insurance": (8000, 40000), "audit": (20000, 60000), "comms tools": (5000, 20000),
        "CI/CD": (6000, 30000), "VPN/network": (5000, 22000), "travel agency": (2000, 20000),
    }
    requesters = ["lena.fischer", "omar.haddad", "diego.fuentes", "grace.adeyemi",
                  "maya.kaplan", "ingrid.bauer", "theo.marchand"]

    rows = []
    for _ in range(40):
        v = rng.choice(vendors)
        cat = v["category"]
        if cat in it_cats:
            approver = "diego.fuentes"
        elif cat in people_cats:
            approver = "maya.kaplan"
        else:
            approver = "grace.adeyemi"
        lo, hi = amount_by_cat[cat]
        amount = round(rng.uniform(lo, hi), 2)
        created = rand_dt(rng, datetime(2026, 1, 6, tzinfo=timezone.utc),
                          datetime(2026, 6, 25, tzinfo=timezone.utc)).date()
        rows.append({
            "vendor_id": v["vendor_id"],
            "description": f"{rng.choice(['Annual subscription', 'Renewal', 'Services engagement', 'Quarterly true-up'])} - {v['vendor_name']}",
            "amount_usd": f"{amount:.2f}",
            "requested_by": f"{rng.choice(requesters)}@{COMPANY_DOMAIN}",
            "approved_by": f"{approver}@{COMPANY_DOMAIN}",
            "created_date": created.isoformat(),
            "status": rng.choices(["open", "received", "paid"], weights=[2, 4, 4])[0],
        })
    rows.sort(key=lambda r: r["created_date"])
    for i, r in enumerate(rows):
        r["po_id"] = f"PO-2026-{i + 1:03d}"

    anchor = {
        "po_id": "PO-2026-041",
        "vendor_id": next(v["vendor_id"] for v in vendors
                          if v["vendor_name"] == "Corvid Hardware Supply"),
        "description": "Laptop refresh + new-hire batch (5x Corvid Book 14)",
        "amount_usd": "9450.00", "requested_by": f"lena.fischer@{COMPANY_DOMAIN}",
        "approved_by": f"diego.fuentes@{COMPANY_DOMAIN}",
        "created_date": "2026-04-28", "status": "received",
    }
    rows.append(anchor)

    with open(d / "purchase_orders.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["po_id", "vendor_id", "description", "amount_usd",
                    "requested_by", "approved_by", "created_date", "status"])
        for r in rows:
            w.writerow([r["po_id"], r["vendor_id"], r["description"],
                        r["amount_usd"], r["requested_by"], r["approved_by"],
                        r["created_date"], r["status"]])


_EXP_MERCHANTS = {
    "travel_air": ["Wrenfield Travel"],
    "lodging": ["Cloudside Suites", "Harborview Inn", "Grandview Hotel"],
    "meals": ["Harborview Bistro", "Corner Deli", "Riverside Grill"],
    "ground_transport": ["Transit Metro", "City Cabs", "Rideline"],
    "software": ["Stoneferry DevTools", "Glimmerfen Communications", "Cloudside Tools"],
    "other": ["Sundry Supplies", "Quayside Print", "Harbor Stationers"],
}
_EXP_AMOUNT = {
    "travel_air": (180, 650), "lodging": (120, 420), "meals": (15, 120),
    "ground_transport": (12, 90), "software": (20, 400), "other": (10, 200),
}


def _build_expenses(rng: random.Random, employees: list[dict]) -> list[dict]:
    active = [e for e in employees if e["status"] == "active"]
    weight = {"Sales": 3, "Customer Experience": 3, "Executive": 3,
              "Product": 2, "Marketing": 2}
    weighted = [e for e in active for _ in range(weight.get(e["department"], 1))]
    by_id = {e["employee_id"]: e for e in employees}

    rows = []
    for _ in range(116):
        e = rng.choice(weighted)
        cat = rng.choices(list(_EXP_AMOUNT), weights=[2, 2, 3, 2, 2, 2])[0]
        lo, hi = _EXP_AMOUNT[cat]
        hire = _d(e["hire_date"])
        lo_day = max(WINDOW_START, hire)
        hi_day = WINDOW_END - timedelta(days=5)
        if lo_day >= hi_day:
            lo_day = WINDOW_START
        exp_date = lo_day + timedelta(days=rng.randrange((hi_day - lo_day).days))
        submitted = min(WINDOW_END, exp_date + timedelta(days=rng.randint(1, 9)))
        rows.append({
            "employee_id": e["employee_id"], "employee_email": e["email"],
            "category": cat, "merchant": rng.choice(_EXP_MERCHANTS[cat]),
            "amount": round(rng.uniform(lo, hi), 2),
            "expense_date": exp_date.isoformat(),
            "submitted_at": iso(business_hours(datetime(
                submitted.year, submitted.month, submitted.day,
                rng.randrange(8, 18), rng.randrange(60), tzinfo=timezone.utc))),
            "status": rng.choices(["reimbursed", "approved", "pending"],
                                  weights=[6, 3, 1])[0],
            "trip_tag": "",
        })

    aisha = by_id["EMP-1019"]
    trip = "tidewater-onsite-2026-05"
    for cat, amt, dt, merch in [
            ("travel_air", 412.00, "2026-05-26", "Wrenfield Travel"),
            ("meals", 86.40, "2026-05-27", "Harborview Bistro"),
            ("lodging", 378.00, "2026-05-28", "Cloudside Suites"),
            ("ground_transport", 54.25, "2026-05-28", "Transit Metro")]:
        rows.append({
            "employee_id": "EMP-1019", "employee_email": aisha["email"],
            "category": cat, "merchant": merch, "amount": amt,
            "expense_date": dt, "submitted_at": "2026-05-29T10:15:00Z",
            "status": "reimbursed", "trip_tag": trip,
        })

    rows.sort(key=lambda r: (r["expense_date"], r["employee_id"]))
    for i, r in enumerate(rows):
        r["report_id"] = f"EXP-{i + 1:04d}"
    return rows


def _write_expenses(out: Path, expenses: list[dict]) -> None:
    d = out / "internal" / "finance"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "expense_reports.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["report_id", "employee_id", "employee_email", "category",
                    "merchant", "amount_usd", "expense_date", "submitted_at",
                    "status", "trip_tag"])
        for r in expenses:
            w.writerow([r["report_id"], r["employee_id"], r["employee_email"],
                        r["category"], r["merchant"], f"{r['amount']:.2f}",
                        r["expense_date"], r["submitted_at"], r["status"],
                        r["trip_tag"]])


def _write_gl(out: Path, rng: random.Random, employees: list[dict],
              expenses: list[dict]) -> None:
    d = out / "internal" / "finance"
    d.mkdir(parents=True, exist_ok=True)

    # 4000 subscription revenue is the sum of invoice amounts by period_start
    # month -- read straight from the relational extract written earlier.
    inv_by_month: dict[str, float] = {}
    with open(out / "relational" / "invoices.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            m = r["period_start"][:7]
            inv_by_month[m] = inv_by_month.get(m, 0.0) + float(r["amount_usd"])

    exp_by_month: dict[str, float] = {}
    for x in expenses:
        m = x["expense_date"][:7]
        exp_by_month[m] = exp_by_month.get(m, 0.0) + x["amount"]

    with open(d / "gl_monthly.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["month", "account_code", "account_name", "account_type",
                    "amount_usd", "notes"])
        for month in range(1, 7):
            mstr = f"2026-{month:02d}"
            mstart = date(2026, month, 1)
            mend = date(2026, month + 1, 1) - timedelta(days=1)

            def active_in_month(e):
                if _d(e["hire_date"]) > mend:
                    return False
                t = e["termination_date"]
                if t and _d(t) < mstart:
                    return False
                return True

            salaries = round(sum(e["base_salary_usd"] / 12.0
                                 for e in employees if active_in_month(e)), 2)
            prof_extra = 25000.0 if month in (4, 5) else 0.0
            prof_note = "SOC 2 Type II fieldwork - Ashgrove Audit & Assurance" \
                if month in (4, 5) else ""
            recruiting = round(rng.uniform(15000, 22000) if month in (3, 4, 5)
                               else rng.uniform(8000, 15000), 2)
            accounts = [
                ("4000", "Subscription revenue", "revenue",
                 round(inv_by_month.get(mstr, 0.0), 2), ""),
                ("5000", "Cloud infrastructure", "expense",
                 round(rng.uniform(185000, 215000), 2), "Nimbostrat Cloud"),
                ("5100", "Third-party software", "expense",
                 round(rng.uniform(40000, 50000), 2), ""),
                ("6000", "Salaries & wages", "expense", salaries, ""),
                ("6100", "Payroll taxes & benefits", "expense",
                 round(salaries * 0.22, 2), ""),
                ("6200", "Contractors", "expense", round(rng.uniform(18000, 42000), 2), ""),
                ("6300", "Travel & entertainment", "expense",
                 round(exp_by_month.get(mstr, 0.0), 2), ""),
                ("6400", "Rent & facilities", "expense", 62000.00, "Harbor City Properties"),
                ("6500", "Marketing programs", "expense", round(rng.uniform(25000, 60000), 2), ""),
                ("6600", "Recruiting", "expense", recruiting, ""),
                ("6700", "Insurance", "expense", 9800.00, "Bluecrest Insurance Brokers"),
                ("6800", "Office & equipment", "expense", round(rng.uniform(5000, 18000), 2), ""),
                ("7100", "Professional services", "expense",
                 round(rng.uniform(6000, 12000) + prof_extra, 2), prof_note),
                ("7200", "Depreciation", "expense", 14500.00, ""),
            ]
            for code, name, atype, amount, notes in accounts:
                w.writerow([mstr, code, name, atype, f"{amount:.2f}", notes])


def _write_access_review(out: Path, rng: random.Random, employees: list[dict],
                         leader_email: dict) -> None:
    d = out / "internal" / "iam"
    d.mkdir(parents=True, exist_ok=True)
    app_name = {a[0]: a[1] for a in _APPS}
    active = [e for e in employees if e["status"] == "active"]

    def dept_apps(dept):
        base = [("APP-10", "member"), ("APP-09", "member"),
                ("APP-04", "member"), ("APP-02", "member")]
        extra = {
            "People": [("APP-01", "admin"), ("APP-06", "editor")],
            "Finance": [("APP-03", "editor"), ("APP-04", "admin")],
            "Sales": [("APP-05", "editor")],
            "Customer Experience": [("APP-05", "member")],
            "Security": [("APP-07", "admin"), ("APP-14", "admin")],
            "IT": [("APP-02", "admin"), ("APP-08", "admin"), ("APP-12", "admin")],
            "Engineering": [("APP-11", "editor"), ("APP-13", "editor"),
                            ("APP-14", "member")],
            "Executive": [("APP-01", "viewer"), ("APP-03", "viewer")],
        }.get(dept, [])
        return base + extra

    candidates = []
    for e in active:
        for aid, ent in dept_apps(e["department"]):
            candidates.append((e, aid, ent))
    rng.shuffle(candidates)

    rows = []
    for e, aid, ent in candidates[:147]:
        revoke = rng.random() < 0.05
        rows.append({
            "employee_id": e["employee_id"], "employee_email": e["email"],
            "employee_status": "active", "app_id": aid, "app_name": app_name[aid],
            "entitlement": ent,
            "reviewer_email": leader_email.get(e["department"], leader_email["Executive"]),
            "decision": "revoke" if revoke else "approve",
            "reviewed_at": f"2026-06-{rng.randint(2, 13):02d}",
            "note": "Role change - entitlement no longer required." if revoke else "",
        })

    # Terminated-with-leftover-access rows: the Derek anchor plus exactly two
    # more generated terminations, each carrying one un-deprovisioned entitlement.
    by_id = {e["employee_id"]: e for e in employees}
    derek = by_id["EMP-1042"]
    rows.append({
        "employee_id": "EMP-1042", "employee_email": derek["email"],
        "employee_status": "terminated", "app_id": "APP-05",
        "app_name": "Saltmarsh CRM", "entitlement": "member",
        "reviewer_email": f"theo.marchand@{COMPANY_DOMAIN}", "decision": "revoke",
        "reviewed_at": "2026-06-09",
        "note": "Terminated 2026-03-31; access not removed at offboarding (IT-2231). Deprovisioned during review.",
    })
    gen_term = sorted([e for e in employees
                       if e["status"] == "terminated" and e["employee_id"] != "EMP-1042"],
                      key=lambda e: e["employee_id"])[:2]
    for e in gen_term:
        dept = e["department"]
        aid = {"Sales": "APP-05", "Engineering": "APP-11",
               "Finance": "APP-03"}.get(dept, "APP-04")
        rows.append({
            "employee_id": e["employee_id"], "employee_email": e["email"],
            "employee_status": "terminated", "app_id": aid,
            "app_name": app_name[aid], "entitlement": "member",
            "reviewer_email": leader_email.get(dept, leader_email["Executive"]),
            "decision": "revoke", "reviewed_at": f"2026-06-{rng.randint(2, 13):02d}",
            "note": "Access not removed at offboarding; deprovisioned during review.",
        })

    with open(d / "access_review_2026q2.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["review_id", "employee_id", "employee_email", "employee_status",
                    "app_id", "app_name", "entitlement", "reviewer_email",
                    "decision", "reviewed_at", "note"])
        for i, r in enumerate(rows):
            w.writerow([f"REV-{i + 1:04d}", r["employee_id"], r["employee_email"],
                        r["employee_status"], r["app_id"], r["app_name"],
                        r["entitlement"], r["reviewer_email"], r["decision"],
                        r["reviewed_at"], r["note"]])


def _write_phishing_sim(out: Path, rng: random.Random,
                        employees: list[dict]) -> None:
    d = out / "internal" / "security"
    d.mkdir(parents=True, exist_ok=True)

    def active_on(e, ref: date) -> bool:
        if _d(e["hire_date"]) > ref:
            return False
        t = e["termination_date"]
        if t and _d(t) < ref:
            return False
        return True

    campaigns = [
        ("PHSIM-2026-02", _d("2026-02-12"), "2026-02-12T14:00:00Z", 0.14, 0.22),
        ("PHSIM-2026-06", _d("2026-06-16"), "2026-06-16T14:00:00Z", 0.06, 0.41),
    ]
    with open(d / "phishing_sim_results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["campaign_id", "sent_at", "employee_id", "email", "action",
                    "time_to_action_minutes"])
        for cid, ref, sent_at, click_rate, report_rate in campaigns:
            for e in employees:
                if not active_on(e, ref):
                    continue
                roll = rng.random()
                if roll < click_rate:
                    action, tta = "clicked", rng.randint(1, 30)
                elif roll < click_rate + report_rate:
                    action, tta = "reported", rng.randint(2, 120)
                else:
                    action, tta = "ignored", ""
                w.writerow([cid, sent_at, e["employee_id"], e["email"], action, tta])


def _write_badge_access(out: Path, rng: random.Random,
                        employees: list[dict]) -> None:
    ev = out / "events"
    ev.mkdir(parents=True, exist_ok=True)
    hq_active = [e for e in employees
                 if e["status"] == "active" and e["location"] == "Harbor City HQ"]
    server_room = {"tom.alvarez", "lena.fischer", "diego.fuentes"}
    by_local = {e["email"].split("@")[0]: e for e in employees}
    specials = [by_local[lp] for lp in ["tom.alvarez", "lena.fischer", "diego.fuentes"]
                if lp in by_local]
    others = [e for e in hq_active if e not in specials]
    regulars = specials + rng.sample(others, min(27, len(others)))

    rows = []
    n = 1
    day = date(2026, 4, 1)
    end = date(2026, 6, 30)
    while day <= end:
        if day.weekday() < 5:
            k = rng.randint(6, 8)
            for e in rng.sample(regulars, k):
                lp = e["email"].split("@")[0]
                if lp in server_room:
                    door = rng.choice(["server-room", "main-lobby", "eng-floor-3"])
                elif e["department"] == "Engineering":
                    door = rng.choice(["eng-floor-3", "main-lobby"])
                else:
                    door = "main-lobby"
                entry = datetime(day.year, day.month, day.day,
                                 rng.randrange(7, 10), rng.randrange(60), tzinfo=timezone.utc)
                exit_ = datetime(day.year, day.month, day.day,
                                 rng.randrange(16, 19), rng.randrange(60), tzinfo=timezone.utc)
                for etype, at in [("badge.entry", entry), ("badge.exit", exit_)]:
                    rows.append({
                        "id": f"bdg-{n:06d}", "type": etype, "timestamp": iso(at),
                        "actor": e["email"],
                        "payload": {"employee_id": e["employee_id"], "door": door},
                        "text": f"{etype} {door} by {e['email']}",
                    })
                    n += 1
        day += timedelta(days=1)
    rows.sort(key=lambda r: r["timestamp"])
    for i, r in enumerate(rows):
        r["id"] = f"bdg-{i + 1:06d}"
    (ev / "badge_access.jsonl").write_bytes(jsonl(rows))


def _write_security_alerts(out: Path, rng: random.Random,
                           employees: list[dict]) -> None:
    ev = out / "events"
    ev.mkdir(parents=True, exist_ok=True)
    active = [e for e in employees if e["status"] == "active"]

    def src_ip():
        return f"{rng.choice(['203.0.113', '198.51.100'])}.{rng.randint(1, 254)}"

    rows = []
    for _ in range(240):
        at = rand_dt(rng, datetime(2026, 1, 5, tzinfo=timezone.utc),
                     datetime(2026, 6, 30, tzinfo=timezone.utc))
        etype = rng.choices(
            ["auth.bruteforce_detected", "malware.blocked", "dlp.policy_flagged",
             "phishing.reported", "login.impossible_travel"],
            weights=[3, 3, 2, 3, 1])[0]
        if etype == "auth.bruteforce_detected":
            target = rng.choice(active)["email"]
            payload = {"source_ip": src_ip(), "target_user": target,
                       "attempts": rng.randint(20, 400), "verdict": "blocked"}
            text = f"auth.bruteforce_detected against {target} from {payload['source_ip']} (blocked)"
            actor = "system"
        elif etype == "malware.blocked":
            payload = {"source_ip": src_ip(), "endpoint": f"WS-{rng.randrange(100, 999)}",
                       "signature": f"Gen.Trojan.{rng.randrange(1000, 9999)}", "verdict": "quarantined"}
            text = f"malware.blocked on {payload['endpoint']} (quarantined)"
            actor = "system"
        elif etype == "dlp.policy_flagged":
            user = rng.choice(active)["email"]
            payload = {"user": user, "policy": rng.choice(
                ["pii-egress", "source-code-share", "financials-external"]),
                "verdict": "flagged"}
            text = f"dlp.policy_flagged for {user} on policy {payload['policy']}"
            actor = "system"
        elif etype == "phishing.reported":
            e = rng.choice(active)
            actor = e["email"]
            payload = {"sender_domain": rng.choice(
                ["invoices-billing.example", "secure-login-check.example",
                 "hr-benefits-update.example"]),
                "reported_via": "mail client button", "verdict": "under_review"}
            text = f"phishing.reported by {actor} ({payload['sender_domain']})"
        else:
            user = rng.choice(active)["email"]
            payload = {"user": user, "source_ip": src_ip(),
                       "prior_location": rng.choice(["Harbor City", "Remote-EU"]),
                       "current_location": rng.choice(["Remote-APAC", "Remote-SA"]),
                       "verdict": "challenge"}
            text = f"login.impossible_travel for {user} (challenge)"
            actor = "system"
        rows.append({"id": None, "type": etype, "timestamp": iso(at),
                     "actor": actor, "payload": payload, "text": text})

    # Anchor: an invoice-themed phishing wave reported the morning of 2026-05-20.
    for e in rng.sample(active, 9):
        at = datetime(2026, 5, 20, rng.randrange(9, 13), rng.randrange(60),
                      tzinfo=timezone.utc)
        rows.append({
            "id": None, "type": "phishing.reported", "timestamp": iso(at),
            "actor": e["email"],
            "payload": {"campaign_note": "invoice-themed lure",
                        "reported_via": "mail client button"},
            "text": f"phishing.reported by {e['email']} (invoice-themed lure)",
        })

    rows.sort(key=lambda r: r["timestamp"])
    for i, r in enumerate(rows):
        r["id"] = f"sec-{i + 1:05d}"
    (ev / "security_alerts.jsonl").write_bytes(jsonl(rows))


def write_internal(out: Path) -> None:
    """Generate the INTERNAL-ENTERPRISE application corpus (HRIS / ITSM /
    finance / IAM / security). Uses its own independently seeded RNG so it
    never perturbs the public-corpus byte stream produced above."""
    rng = random.Random(INTERNAL_SEED)
    employees = _build_internal_employees(rng)
    leader_email = _leader_email_map(employees)

    _write_hris(out, employees)
    _write_pto(out, rng, employees)

    assets = _build_assets(rng, employees)
    _write_assets(out, assets)
    changes = _build_changes(rng)
    _write_changes(out, changes)
    tickets = _build_it_tickets(rng, employees, assets, changes)
    _write_it_tickets(out, tickets)

    vendors = _write_vendors(out, rng)
    _write_app_catalog(out, rng)
    _write_purchase_orders(out, rng, vendors)
    expenses = _build_expenses(rng, employees)
    _write_expenses(out, expenses)
    _write_gl(out, rng, employees, expenses)

    _write_access_review(out, rng, employees, leader_email)
    _write_phishing_sim(out, rng, employees)

    _write_badge_access(out, rng, employees)
    _write_security_alerts(out, rng, employees)


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

FORMAT_BY_SUFFIX = {".json": "json", ".jsonl": "jsonl", ".csv": "csv",
                    ".md": "markdown", ".sql": "sql", ".txt": "text",
                    ".log": "log", ".eml": "email"}

SOURCE_SYSTEM_BY_DIR = {
    "README.md": "corpus metadata",
    "saas/project_mgmt": "issue tracker (project-management SaaS export)",
    "saas/tickets": "helpdesk (support-ticket SaaS export)",
    "saas/knowledge_base": "knowledge-management SaaS (wiki export)",
    "saas/crm": "CRM SaaS export",
    "saas/status_page": "status-page SaaS export",
    "api_specs": "API specifications (OpenAPI)",
    "relational": "relational OLTP database extract (acmedb)",
    "documents": "internal documents",
    "feedback": "human feedback",
    "unstructured/chat": "team chat export",
    "unstructured/logs": "application logs",
    "unstructured/email": "email archive",
    "unstructured/call-transcripts": "call transcripts",
    "internal/docs": "internal documents (corporate)",
    "internal/hris": "HRIS export",
    "internal/itsm": "IT service management export",
    "internal/finance": "ERP / finance extracts",
    "internal/iam": "identity & access management export",
    "internal/security": "security operations data",
    "internal/recruiting": "applicant-tracking export",
    "events": "generic event streams (freud-schema ingest events)",
}


def count_records(path: Path) -> int | None:
    suffix = path.suffix
    if suffix == ".jsonl":
        return sum(1 for line in path.read_bytes().splitlines() if line.strip())
    if suffix == ".csv":
        with open(path, encoding="utf-8") as f:
            return max(0, sum(1 for _ in csv.reader(f)) - 1)
    if suffix == ".json":
        data = orjson.loads(path.read_bytes())
        if isinstance(data, list):
            return len(data)
        if isinstance(data, dict):
            for v in data.values():
                if isinstance(v, list) and len(v) > 3:
                    return len(v)
    return None


def write_manifest(out: Path) -> dict:
    files = []
    for path in sorted(out.rglob("*")):
        if not path.is_file() or path.name == "MANIFEST.json":
            continue
        rel = path.relative_to(out).as_posix()
        source_system = "unclassified"
        for prefix, label in SOURCE_SYSTEM_BY_DIR.items():
            if rel.startswith(prefix):
                source_system = label
                break
        files.append({
            "path": rel,
            "format": FORMAT_BY_SUFFIX.get(path.suffix, path.suffix.lstrip(".")),
            "source_system": source_system,
            "bytes": path.stat().st_size,
            "records": count_records(path),
        })
    manifest = {
        "corpus": "acme-analytics-synthetic",
        "version": 1,
        "description": (
            "Fully synthetic public corpus for developing and evaluating the "
            "FreudAgent flywheel. Fictional company (Acme Analytics), "
            "fictional people, fictional customers; all domains use the "
            "reserved .example TLD. Structured files are generated "
            "deterministically by scripts/generate_synthetic_data.py; "
            "documents are hand-authored and cross-reference generated IDs."),
        "generator": "scripts/generate_synthetic_data.py",
        "seed": SEED,
        "time_range": [iso(CORPUS_START), iso(CORPUS_END)],
        "files": files,
    }
    (out / "MANIFEST.json").write_bytes(jdump(manifest))
    return manifest


# ---------------------------------------------------------------------------


def generate(out: Path) -> dict:
    rng = random.Random(SEED)
    accounts = build_accounts(rng)
    write_crm(out, rng, accounts)
    write_relational(out, rng, accounts)
    issues = write_project_mgmt(out, rng)
    tickets = write_support(out, rng, accounts, issues)
    write_feedback(out, rng, tickets, accounts)
    write_chat(out, rng)
    write_logs(out, rng)
    write_events(out, rng, accounts)
    write_internal(out)
    return write_manifest(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", type=Path,
        default=Path(__file__).resolve().parent.parent / "data" / "synthetic",
        help="output directory (default: data/synthetic)")
    args = parser.parse_args()
    manifest = generate(args.out)
    total = sum(f["bytes"] for f in manifest["files"])
    print(f"wrote {len(manifest['files'])} files, {total / 1024:.0f} KiB, "
          f"under {args.out}")


if __name__ == "__main__":
    main()
