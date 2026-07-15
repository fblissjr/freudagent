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
from datetime import datetime, timedelta, timezone
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
