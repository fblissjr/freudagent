# Synthetic corpus (public)

A fully synthetic, git-tracked corpus for developing and evaluating the
FreudAgent flywheel end to end: source registration, extraction, validation,
typed corrections, couch detectors, event ingestion, and the eventual human
surfaces over post-agent-processed data.

**Everything here is fictional.** The company (Acme Analytics, a made-up B2B
usage-analytics SaaS), its employees, its customers, and every email address
and domain (all on the reserved `.example` TLD) are invented. No real
transcript, personal, or machine-specific content appears in this folder --
that data stays in the gitignored private paths (`data/*.duckdb`,
`data/papers/`).

> **Contributing:** this directory is **public-by-construction** -- the
> manifest inventories whatever lands here and it is all committed. Never drop
> real exports, logs, or personal data under `data/synthetic/`; keep emails on
> `.example`, IPs in the RFC 5737 doc ranges, and no home paths or secrets. Two
> guards in `tests/test_synthetic_data.py` enforce this (every manifest path is
> tracked; no corpus file carries private data) -- if one trips, fix the file
> or the `.gitignore` rule, don't just `git add`.

## Layout

```
MANIFEST.json               machine-readable inventory (path, format, source
                            system, byte size, record count per file)
saas/
  project_mgmt/             issue-tracker export: issues.json (76 issues with
                            comments), sprints.json (12 sprints)
  tickets/                  helpdesk export: support_tickets.jsonl (60 tickets
                            with threaded public replies + internal notes)
  crm/                      CRM export: accounts.csv, opportunities.csv
  knowledge_base/pages/     10 wiki-style pages (markdown + YAML frontmatter)
  status_page/              status-page SaaS export: incident_history.json
  marketing/                web analytics keyed by visitor company domain
api_specs/                  OpenAPI 3.1 spec for the fictional metering API
internal/                   the company's OWN enterprise systems:
  hris/                     employees.csv (124, incl. every named person),
                            pto_requests.csv, headcount_monthly.csv
  itsm/                     it_tickets.jsonl, assets.csv, changes.csv (incl.
                            the failed change behind INC-2026-0311)
  finance/                  vendors, purchase_orders, expense_reports,
                            gl_monthly.csv (revenue ties to invoices.csv,
                            T&E ties to expenses), ar_aging_2026-06-30.csv
  iam/                      app_catalog.csv, access_review_2026q2.csv
  security/                 phishing_sim_results.csv
  reporting/                kpi_quarterly.csv (executive scorecard)
  docs/                     corporate docs: SOC 2 readiness memo, expense /
                            change-management / acceptable-use policies,
                            laptop provisioning runbook, all-hands notes,
                            onboarding checklist
relational/                 OLTP extract of the fictional `acmedb` billing
                            database: schema.sql (DDL) + customers,
                            subscriptions, invoices, usage_daily CSVs
documents/                  internal docs: product spec, incident runbook,
                            CS onboarding guide, retention policy, release
                            notes, DATA-88 design doc, order-form/MSA
                            template, meeting notes (incl. the 2026-03-12
                            postmortem and the Q1 churn review)
feedback/                   human feedback: csat_survey.csv, nps_comments.jsonl,
                            annotation_corrections.jsonl (typed corrections on
                            simulated agent extractions over this corpus,
                            using the CorrectionType taxonomy)
unstructured/
  chat/                     team chat export (JSONL, Slack-like shape)
  logs/                     api-gateway log covering the incident window
  email/                    .eml messages (RFC 822-ish): incident status,
                            invoice dispute, beta announcement, downgrade
                            confirmation, sales proposal
  call-transcripts/         plain-text call transcripts: QBR, SSO support
                            call, downgrade call, sales discovery
events/                     generic JSONL event streams shaped for
                            `freud-schema ingest events` (JsonlEventAdapter:
                            {id, type, timestamp, actor, payload, text}):
                            product webhooks, admin audit, badge access,
                            security alerts
```

## The connective tissue

The corpus is one coherent scenario (2026-01-05 through 2026-06-30), so
cross-source reasoning has ground truth to be evaluated against:

- **The 2026-03-11 ingestion incident** (INC-2026-0311, 14:02-15:47 UTC)
  appears in the gateway log, the `ingest.backpressure` webhook burst, the
  `#eng-observability` chat thread, issues ACME-231 / DATA-88 / ACME-247,
  support tickets SUP-1042 and SUP-1063, the `usage_daily` dip-and-replay,
  invoice INV-202603-0063 (`past_due`, disputed), the postmortem meeting
  notes, an incident-status email, and NPS verbatims.
- **Shared identities**: CRM `account_id` (ACCT-*) joins accounts.csv,
  customers.csv, support tickets, feedback, and both event streams; issue
  keys (ACME-*/DATA-*) join issues, tickets (`linked_issue`), chat, and docs.
- **Planted extraction traps**: the product spec keeps a deprecated v0
  limits table, and the retention policy splits retention across hot and
  cold tiers -- `feedback/annotation_corrections.jsonl` records the human
  corrections an agent that falls for them should receive.
- **Secondary arcs**: the Cobalt Games / Halcyon Travel contractions
  (subscriptions.csv closed rows -> downgrade call, confirmation email,
  churn-review notes), the Tidewater Marine sales pipeline (discovery
  transcript -> proposal email -> rising web traffic; deliberately absent
  from the CRM, which only holds signed accounts), and the MSA section 6.3
  dispute terms that the Sable Financial email and ticket SUP-1063 invoke.
- **The compliance arc (internal/)**: sales rep terminated 2026-03-31
  (EMP-1042 in hris/employees.csv) -> offboarding ticket IT-2231 misses
  SaaS deprovisioning -> Q2 access review revokes the leftover Saltmarsh
  CRM entitlement -> laptop-provisioning runbook revised 2026-06-12 ->
  finding #1 in the SOC 2 readiness memo. The March incident also has an
  internal spine: change record CHG-2026-0023 (failed) -> emergency
  rollback CHG-2026-0024 -> the change-management policy's 2026-03
  revision.
- **Financial reconciliation ties**: gl_monthly.csv account 4000 equals
  invoices.csv summed per month; account 6300 equals expense_reports.csv
  per month; 6100 is exactly 22% of 6000; kpi_quarterly.csv rolls the same
  numbers up to quarters.

## Granularity & join challenges

Deliberate grain mismatches and imperfect keys, each with exact ground
truth (guarded by `tests/test_synthetic_granularity.py`) so agent code for
cross-grain joins and key derivation can be evaluated:

| File | Grain | Joins to | What an agent must do |
|------|-------|----------|-----------------------|
| saas/tickets/ticket_metrics_weekly.csv | weekly | support_tickets.jsonl (event) | roll tickets up to ISO weeks; reconcile counts |
| internal/hris/headcount_monthly.csv | monthly | employees.csv (entity) | effective-dated (SCD-style) point-in-time counting over hire/termination dates |
| internal/reporting/kpi_quarterly.csv | quarterly | gl_monthly, subscriptions, csat_survey, employees | multi-source quarter rollups; ARR derived as quarter-end MRR x 12 |
| saas/marketing/web_sessions_weekly.csv | weekly, keyed by company domain | accounts.csv | derive each account's domain from contact emails (no shared ID exists); tolerate noise domains that match nothing |
| internal/finance/ar_aging_2026-06-30.csv | as-of snapshot, keyed by messy names | invoices/subscriptions/customers | entity resolution (case, punctuation, legal suffixes, &/and) plus multi-hop key bridging and date-bucket math |
| events/badge_access.jsonl vs hris/pto_requests.csv | timestamp vs date-range | -- | interval overlap joins |
| usage_daily.csv vs invoices.csv vs gl_monthly.csv | daily vs monthly | -- | grain conversion with billing-window semantics |

## Messy / real-world formats (`messy/`, `drive_chaos/`)

Most enterprise data is not clean CSV and markdown. `messy/` holds inputs a
structuring agent must actually normalize -- several paired with clean ground
truth so structuring is a scored task, not a vibe:

| Path | Format / mess | Structuring task |
|------|---------------|------------------|
| messy/spreadsheets/*.csv | human exports: title/blank/prepared-by rows above the header, embedded subtotal/total rows, EU locale (`;` delim, comma decimals, DD.MM.YYYY), footnotes | find the real header, drop non-data rows, parse locale; grand total is pinned in the folder README |
| messy/ocr/*.txt + *.ground-truth.json | OCR of a scanned invoice (l↔1, O↔0, hyphen breaks, column bleed) + the clean extraction | read past OCR noise to reproduce the ground-truth JSON (total $9,450) |
| messy/xml/*.xml | JUnit CI report; EDI-style logistics ASN | flatten nested/namespaced XML to tables |
| messy/calendar/*.ics | VCALENDAR export with RRULE recurrence | parse VEVENTs; cross-format join to the meeting notes (corroborates INC-2026-0311) |
| messy/db_dumps/*.sql | mysqldump-style INSERTs with escaped quotes, NULLs, multi-row values | parse INSERTs back to rows |
| messy/api_responses/*.json | paginated JSON:API envelope (data/meta/links) across 3 pages | de-envelope and concatenate; follow `links.next` to null |
| messy/logs/*.log | one file mixing RFC5424 syslog, CEF, and key=value | normalize three formats into unified events |
| messy/html/*.html | intranet page and newsletter email (nav/table-layout/tracking-pixel chrome) | strip chrome, extract the article/announcements |
| messy/transcripts_raw/*-raw.txt + *-clean.md | raw ASR (bad diarization, fillers, [inaudible]) + clean attributed version | diarization cleanup, speaker attribution, action-item extraction |
| messy/mbox/*.mbox | 5-message thread: top-posting, growing quote trails, a forwarded block | reconstruct reply structure |
| messy/decks/*.outline.txt | slide-deck outline with `Notes:` speaker-note blocks | separate public bullets from private asides |
| drive_chaos/ | five near-duplicate versioned drafts of one strategy doc + a temp/lock artifact | cluster into one identity, pick the canonical version, discard detritus (ground truth named in its README) |

## Authority, staleness & conflict (`time/`, `governance/`, `external/`, `eval/`)

The corpus is not internally consistent -- because the real world isn't. The
same fact is asserted with different values by sources of different authority,
age, and process status, and a structuring agent must resolve them by *rule*,
not naive latest-wins. The ground truth for that lives here:

- **`time/`** makes staleness derivable rather than asserted: `page_history.jsonl`
  (KB revisions -- including the revision where the batch limit was *correctly*
  500, before the 500->1000 change), `snapshots/` (org chart and roadmap at
  three dates, capturing a termination and a hire), and `policy_versions.jsonl`
  (a draft-vs-approved-vs-superseded retention chain).
- **`governance/system_of_record.csv`** declares the canonical source per fact
  domain (titles->HRIS, recognized revenue->GL, pipeline->CRM, entitlements->IAM,
  uptime->status page, decisions->the decision log). **`source_authority.csv`**
  is the scoring model in structured form: per source-type `base_authority` and
  `half_life_days` (status-page truth decays in days; approved policy in a year;
  external analyst notes start near-zero). **`decision_log.jsonl`** is DACI-style
  decisions of record, including one *reversed* decision.
- **`external/`** is deliberately low-authority and partly *wrong*: an analyst
  note that misstates the batch limit, claims multi-region shipped, and inflates
  a job title -- the unvalidated outside view every real corpus carries.
- **`eval/conflicts.jsonl`** is the answer key: each record lists the competing
  sources (path, value, as-of, author, type), the correct value, the winning
  source, and the **resolution rule** -- one of `recency_supersession`,
  `process_status`, `document_type_authority`, `system_of_record`,
  `org_authority`. It encodes the load-bearing distinction: org authority
  settles *decisions* (the CEO's deferral beats an IC's active-active proposal),
  but **system-of-record settles facts** (the CEO's deck does *not* beat the
  general ledger on revenue). **`eval/citation_edges.csv`** is the cross-reference
  graph -- every corpus ID mention as a `(from_path, to_id)` edge, the substrate
  for PageRank-style source-centrality scoring -- built by
  `scripts/build_citation_graph.py`.

Guarded by `tests/test_synthetic_temporal.py`, `test_synthetic_conflicts.py`,
and `test_citation_graph.py`.

## Regeneration

Structured/volume files are generated deterministically (fixed seed, fixed
dates -- byte-identical on re-run):

```bash
uv run python scripts/generate_synthetic_data.py     # generated volumes + time/ + MANIFEST.json
uv run python scripts/build_citation_graph.py         # derives eval/citation_edges.csv from the whole corpus
```

Run the citation-graph builder *after* the generator (and after any
hand-authored edits): it scans the entire corpus on disk, so it is a
separate step, not part of `generate()` -- the determinism test regenerates
into a temp dir that has only the generated files, where a disk-scanning
citation step could not be reproducible. Re-run it whenever corpus content
changes; then re-run the generator once more so `MANIFEST.json` re-inventories
the refreshed `citation_edges.csv`.

Hand-authored files (`documents/`, `saas/knowledge_base/`, `unstructured/`,
`messy/`, `drive_chaos/`, `governance/`, `external/`, `eval/conflicts.jsonl`,
this README) are not touched by the generator; it re-inventories everything
present into `MANIFEST.json`. If you change generated volumes or anchors, keep
the cross-references above true -- the `tests/test_synthetic_*.py` suite checks
the load-bearing ones.
