# Postmortem: INC-2026-0311 -- ingestion lag and metering API 5xx

- **Date of incident:** 2026-03-11, 14:02-15:47 UTC (SEV2)
- **Postmortem held:** 2026-03-12, 10:00 UTC (blameless)
- **IC:** tom.alvarez. **Scribe:** fatima.alrashid
- **Attendees:** priya.raghavan, marcus.webb, elena.sokolova, dana.kim,
  tom.alvarez, yuki.tanaka, ingrid.bauer, noah.lindqvist, fatima.alrashid

## Impact

- Usage-event consumer lag peaked at ~41 minutes on partitions 3, 7, 11.
- Dashboards served stale aggregates with no indication of staleness.
- Metering API returned 502 at the gateway (peak 18% of `/v1/usage`
  requests) once upstream latency breached the gateway timeout.
- 9 support tickets, 2 enterprise escalations (SUP-1042 Bluewater with an
  exec review that afternoon; one Meridian thread resolved same-day).
- Next-day backlog replay inflated 03-12 ingestion counts; one billing
  dispute followed (SUP-1063, INV-202603-0063) -- handled per the billing
  FAQ recompute remedy.

## Timeline (UTC)

- 08:40 -- consumer build 2026.3.4 reaches 100% of the fleet.
- 14:02 -- lag begins climbing on high-volume partitions.
- 14:07 -- gateway 502 alerts fire; 14:15 SEV2 declared, INC opened.
- 15:05 -- root cause identified: 2026.3.4 decompresses batched payloads
  while holding the partition lock; large batches hold the lock for
  seconds, starving the partition.
- 15:12 -- decision: roll back to 2026.3.3 rather than hotfix.
- 15:41 -- rollback complete; 15:47 lag at zero, 502s stopped. Resolved.

## Why it took 3 hours to surface

The defect only bites when batch size × compression ratio crosses the
lock-hold threshold; morning traffic is dominated by large nightly batch
senders in EU/US-overlap hours. The canary fleet saw only small batches.

## What went well

- Rollback-first decision (runbook) cut resolution time decisively.
- Support cadence: 30-minute updates on urgent tickets, customers stayed
  calm; Bluewater closed at CSAT 4.

## What went poorly

- Dashboards had no staleness signal -- customers discovered the problem
  before we told them.
- Canary batch profile is unrepresentative of peak batch sizes.
- Replay tagging didn't exist, so the backlog drain polluted billable
  counts.

## Follow-ups (all `incident-followup`)

| Issue | Action | Owner |
|-------|--------|-------|
| DATA-88 | Move batch decompression off the partition lock; commit offsets after downstream write | elena.sokolova |
| ACME-247 | Dashboard staleness banner from the freshness watermark | dana.kim |
| DATA-91* | Canary traffic replay with production batch-size distribution | noah.lindqvist |
| BILL* | Tag replayed events `replay=true`, exclude from billable series | marcus.webb |

*Filed after the meeting; keys assigned in the tracker.
