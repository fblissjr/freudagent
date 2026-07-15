# Change management policy

- **Owner:** Johan Brandt (VP Engineering), with Diego Fuentes (Head of IT)
- **Audience:** everyone who deploys to production systems or changes corporate IT
- **Last updated:** 2026-03-20 (revised after INC-2026-0311)

## Scope

This policy covers all changes to **production systems** (the usage-analytics
platform, its data pipelines, customer-facing services) and to **corporate
IT** (identity, networking, endpoint fleet, SaaS configuration). A "change"
is any modification to a running system: deploys, config edits, infra
changes, access-model changes, and dependency upgrades. Documentation-only
edits are out of scope.

## Change classes

Every change is one of three classes. Pick the lowest class that honestly
fits; misclassifying to skip review is a policy violation.

| Class | Definition | Approval path |
|-------|------------|---------------|
| **Standard** | Low-risk, routine, from the pre-approved change catalog (e.g. cataloged config toggles, routine cert rotation). | Pre-approved. No CAB. Log a CHG record. |
| **Normal** | Anything not in the catalog and not an emergency. Default class for feature deploys and infra changes. | **CAB review, Wednesdays 15:00 UTC.** |
| **Emergency** | Restores or protects service during active or imminent incident; cannot wait for CAB. | **One authorized approver** now, plus **mandatory retroactive review within 48 hours.** |

The pre-approved standard catalog is maintained jointly by Engineering and
IT and reviewed each quarter. Adding a change type to the catalog is itself
a normal change.

## CHG records and rollback

**Every change gets a CHG record** (format `CHG-2026-0023`) created **before
approval**, and no change is approved without a written **rollback plan** in
that record. The rollback plan must be specific: what you revert, how, who
runs it, and how you confirm recovery. "Roll forward with a fix" is not a
rollback plan.

CAB meets **Wednesdays at 15:00 UTC**. Normal changes are submitted with
their CHG record by end of day Tuesday so reviewers have time. The CAB is
chaired by IT with an Engineering representative; it reviews risk, blast
radius, rollback plan, and timing against freeze windows.

## Freeze windows

- **Finance systems freeze:** the last two business days of each month, no
  changes to Quillbrook Ledger, Lanternfell Expense, or their integrations,
  to protect the close.
- **Incident-time freeze:** while any SEV1 or SEV2 incident is open, only
  emergency changes that address the incident are permitted. Everything else
  waits.
- Additional freezes (e.g. around major customer events) are announced by
  Engineering leadership.

## March 2026 revision -- the INC-2026-0311 case

This section was added on 2026-03-20 after our most instructive failure.

**What happened.** Change **CHG-2026-0023** rolled out usage-consumer build
`2026.3.4` on 2026-03-11. It passed CAB review and deployed clean at 08:40
UTC with no immediate errors. At roughly **14:02 UTC** it caused production
incident **INC-2026-0311** (ingestion lag, stale customer dashboards). The
emergency rollback **CHG-2026-0024** ran 15:12--15:41 UTC and resolved the
incident. A change that reviewed clean and deployed clean still took six
hours to reveal its damage.

**Lessons, now institutionalized:**

1. **Prefer rollback to hotfix.** When a deploy is in the suspect window,
   roll it back first and prove innocence later. Rollback resolved in 29
   minutes what a hotfix path would have stretched into hours.
2. **Emergency changes get retroactive review within 48 hours.** CHG-2026-0024
   was reviewed after the fact on schedule; this is now the rule for every
   emergency change, not a courtesy.
3. **Canary traffic must reflect the production batch-size distribution.**
   CHG-2026-0023's canary used uniform small batches and never exercised the
   large-batch path that failed in production. Canaries that do not mirror
   real batch-size distribution do not count as canaries.

## Metrics

Reviewed monthly by Engineering and IT leadership:

- **Change failure rate** -- share of changes causing an incident or
  requiring rollback.
- **Emergency-change count** -- a rising count signals gaps in the normal
  pipeline or the standard catalog.

Trends feed the quarterly catalog review and future revisions of this policy.
