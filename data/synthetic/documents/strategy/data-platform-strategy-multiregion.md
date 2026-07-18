# Strategy proposal: active-active multi-region ingestion for 2026

> **Status: PROPOSAL FOR DISCUSSION — not an approved decision.** This is an
> IC-authored argument intended to open a design review. It has not been
> ratified by engineering leadership. See the decision log for the authoritative
> outcome (governance/decision_log.jsonl).

- **Authors:** elena.sokolova (Data Engineer), with niko.xu (Staff Engineer) — 2026-02-20
- **Audience:** VP Engineering, platform + pipeline teams
- **Type:** technical proposal / RFC

## The ask

We should commit, in 2026, to building **active-active multi-region ingestion**
for the usage-metering pipeline: two regions accepting writes concurrently, with
cross-region replication of the raw-event and aggregate stores. Today we run a
single active region with cold standby. We are arguing that standby is no longer
good enough for where the business is going.

## Why now — INC-2026-0311 as motivation

On 2026-03-11 [sic — drafted after the design review that anticipated it], the
ingestion pipeline showed how a single active region concentrates risk: a single
consumer build (`2026.3.4`) took the whole ingest path into lag, and customer
dashboards went stale for hours. The rollback was clean, but for the duration
there was no second region absorbing writes. A regional outage — not just a bad
deploy — would have been strictly worse: total ingest loss until manual failover.

We concede up front that INC-2026-0311 was a deploy regression, not a regional
failure. But it exposed the same structural gap: we have no live second region.
The next incident may not be so kind about geography.

## Goals

- **RPO ≤ 5 seconds** for accepted events (today: bounded only by backup cadence,
  effectively minutes).
- **RTO ≤ 60 seconds** for a full regional loss (today: 20–40 minutes of manual
  failover, tested quarterly).
- **Zero-downtime deploys** by draining one region at a time behind the load
  balancer instead of canarying against the only active region.

## Design sketch

1. **Dual write path.** Both regions run the full ingest → validate → dedup →
   aggregate chain. A global load balancer routes by client geography with
   health-based failover.
2. **Conflict-free aggregates.** Usage counters are additive; we partition
   aggregate ownership by `tenant_id` hash so each region owns disjoint keys and
   cross-region merge is a sum, not a conflict. Dedup keys are already globally
   unique (event UUID), so double-delivery is idempotent.
3. **Replication.** Async cross-region replication of the raw-event log with a
   bounded replication-lag alarm. On failover, the surviving region replays any
   unreplicated tail from the shared durable queue.
4. **Backpressure.** Per-region rate limits stay as they are; the 1,000-events
   per-batch limit is unchanged by this work.

## Cost

Rough order-of-magnitude: a second always-on region roughly **doubles ingest
compute and storage** for the pipeline tier, plus cross-region egress for
replication. We estimate a **30–45% increase** in total platform infrastructure
spend (the pipeline is not our only cost line). This is the crux of the tradeoff
and the reason this is a proposal, not a foregone conclusion.

## Why we think it is worth it

- Enterprise prospects in regulated segments increasingly ask for a multi-region
  availability story in security review. We are answering "single region, tested
  DR" today, and losing time explaining it.
- The failover we run quarterly is a **procedure**, not a **property**. Procedures
  rot; properties hold. Active-active makes availability a property.
- The incremental engineering cost falls the longer we wait: retrofitting
  active-active onto a larger data footprint is harder every quarter.

## What we are NOT claiming

- We are not claiming this is free, or that INC-2026-0311 would have been
  prevented by it (it would not — see above).
- We are not claiming leadership has approved it. **This document advocates a
  direction; it does not set one.** The call belongs to VP Engineering and the
  CEO, and the decision of record lives in the decision log.

## Recommendation

Fund a one-quarter design spike, then commit to active-active build-out in H2
2026. We (the authors) will own the spike.

*— elena.sokolova, niko.xu*
