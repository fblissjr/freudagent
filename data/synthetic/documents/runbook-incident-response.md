# Runbook: incident response

- **Owner:** tom.alvarez (SRE)
- **Audience:** anyone on the engineering on-call rotation
- **Last updated:** 2026-03-20 (post INC-2026-0311 review)

## Severities

| Sev | Definition | Example |
|-----|------------|---------|
| SEV1 | Data loss, security breach, or full outage | events acknowledged but not durably written |
| SEV2 | Major degradation, customer-visible, no data loss | ingestion lag with stale dashboards (INC-2026-0311) |
| SEV3 | Partial/limited impact, workaround exists | one export format failing |

## Declare

1. Say it out loud in `#eng-observability`: "declaring SEVn, opening
   INC-YYYY-MMDD". Numbering is date-based; suffix `-b` if there are two in
   a day.
2. The declarer is Incident Commander (IC) until handed off. IC coordinates
   and communicates; IC does not debug.
3. Update the status page within 15 minutes of declaration.

## During

- IC posts a status line to the incident channel every 30 minutes minimum
  -- same cadence support promises customers on urgent tickets.
- Support (yuki.tanaka's team) owns customer threads; engineering never
  replies on tickets directly during an incident.
- Track customer-facing symptoms in one issue (like ACME-231); keep
  root-cause work in separate issues so the symptom ticket can close when
  impact ends.
- **Prefer rollback to hotfix.** If a deploy is in the suspect window,
  roll it back first and prove innocence later. (Reaffirmed in the
  2026-03-12 postmortem: the rollback resolved in 30 minutes what a hotfix
  path would have stretched to hours.)

## Resolve

Impact ended = incident resolved, even if the root-cause fix isn't shipped.
Record the resolution timestamp from telemetry, not memory (INC-2026-0311
resolved 15:47 UTC when consumer lag hit zero).

## After

- Postmortem within 2 business days, blameless, IC drafts.
- Follow-ups get issues with the `incident-followup` label and an owner
  before the postmortem doc is considered done.
- Billing checks for replay-window inflation on any incident that replayed
  events (see the March 2026 invoice disputes for why this is not optional).
