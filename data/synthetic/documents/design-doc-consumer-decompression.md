# Design: Move batch decompression off the consumer partition lock

- **Tracker:** DATA-88
- **Author:** elena.sokolova@acme-analytics.example
- **Reviewers:** marcus.webb@acme-analytics.example, noah.lindqvist@acme-analytics.example, priya.raghavan@acme-analytics.example
- **Status:** implemented
- **Date:** 2026-03-16

## Context

On 2026-03-11 (14:02–15:47 UTC) we ran incident INC-2026-0311 (SEV2). Consumer
build 2026.3.4, deployed at 08:40 UTC that morning, changed how the usage-events
consumer handled batched payloads: it decompressed each batch **while holding the
Kafka partition lock**. Under normal batch sizes this went unnoticed; under large
batches, decompression held the lock for seconds at a time, and the effect
compounded on the hot partitions. Partitions 3, 7, and 11 of the usage-events
topic were starved as lock hold times stacked up; consumer lag peaked at roughly
41 minutes. Because dashboards read aggregates without any staleness signal at
the time, they served stale numbers silently, and once upstream latency breached
the API gateway timeout the gateway returned 502 on up to 18% of `/v1/usage`
requests. We resolved it by rolling back to build 2026.3.3 (rollback complete
15:41 UTC; lag back to zero at 15:47 UTC). The next-day backlog replay inflated
billable counts, mitigated by tagging replayed events `replay=true` and excluding
them from billing. This doc addresses the root cause: **decompression must not
run under the partition lock.**

## Problem statement

The consumer runs CPU-bound decompression inside the critical section that guards
partition progress, so lock hold time scales with batch size — effectively
customer-controlled. We need decompression cost decoupled from lock hold time so a
large batch cannot starve a partition.

## Goals

- Decompression never runs while the partition lock is held; lock hold time is
  bounded and independent of batch payload size.
- No event loss and no double-commit under load or worker saturation.
- In-partition ordering guarantees preserved.
- Verifiable improvement at 3x normal volume before fleet rollout.

## Non-goals

- Changing the wire format or compression codec of batched payloads.
- Changing the billing replay/`replay=true` handling (owned separately).
- Reworking the API gateway timeout, or cross-partition ordering (never
  guaranteed) — both out of scope.

## Option A — Hotfix in place (rejected)

Keep decompression on the consumer thread but cap batch size and add a fast-path
that yields the lock between chunks. Rejected because:

- Capping batch size pushes the problem onto producers and reduces throughput
  for legitimate large uploads; it treats a symptom, not the cause.
- Yielding the lock mid-decompression reintroduces the ordering hazards we get
  for free by holding it, without removing CPU work from the critical section.
- It leaves lock hold time correlated with payload size — the exact property
  that caused the incident, so any future codec or batch-shape change reopens
  the same failure.

## Option B — Bounded worker pool (chosen)

Move decompression to a bounded worker pool that runs outside the partition
lock. The critical section becomes: read the batch reference, hand it to a
worker, and — only after that batch's downstream write completes — commit the
offset. Design parameters:

| Parameter               | Value                                   |
| ----------------------- | --------------------------------------- |
| Worker pool size        | 4x the partition count                  |
| In-flight payload cap   | 64 MB across all workers                |
| Offset commit point     | after the downstream write succeeds     |
| Commit ordering         | strictly in offset order per partition  |

Rationale: 4x partitions gives enough concurrency to keep partitions moving
while bounding in-flight work. The 64 MB cap is the backpressure knob — once
in-flight bytes hit it, the consumer stops handing out new work rather than
growing memory unbounded. Committing offsets **only after the downstream write**
guarantees at-least-once delivery; with ingest-time dedup on `(source_id,
idempotency_key)` (DATA-83), effective processing is idempotent.

## Failure modes considered

- **Worker-pool exhaustion / in-flight cap reached.** Result is *backpressure,
  not data loss*: the consumer pauses fetching for the affected partitions until
  in-flight bytes drop below the cap. Lag may rise briefly, but nothing is
  dropped and no offset is committed ahead of its write.
- **Poison batch (undecompressable / malformed).** Routed to a dead-letter
  destination with a reason code rather than blocking the partition; the offset
  advances past it so one bad payload cannot stall a partition. Dead-lettered
  batches are counted and alertable.
- **Ordering within a partition.** Preserved. Workers may finish out of order,
  but offsets commit strictly in offset order per partition, so the committed
  position never skips ahead of an incomplete earlier batch.

## Load-test results

Replayed against a synthetic stream at 3x normal volume:

| Metric             | Before (build 2026.3.4) | After |
| ------------------ | ----------------------- | ----- |
| p99 commit latency | 2.1s                    | 140ms |

Lock hold time became flat with respect to batch size — the design target. No
dropped events and no duplicate downstream writes were seen across the run.

## Rollout plan

1. **Canary.** Deploy to a single canary consumer, fed a replay of the production
   batch-size distribution from 2026-03-11 — the incident's own batch profile — so
   we exercise the exact large-batch shapes that triggered the starvation. Watch
   lock hold time, p99 commit latency, in-flight bytes, and dead-letter counts.
2. **Fleet-wide.** On clean canary results, roll out to the full consumer fleet
   as build **2026.3.9**.
3. **Guardrails.** Alert on in-flight bytes sitting at the cap and on any nonzero
   dead-letter rate; keep the ability to roll back as we did during the incident.

## Follow-ups

- Add a dashboard staleness signal so stale aggregates can never again be served
  silently (tracked as ACME-247).
- Tune the 64 MB in-flight cap per hardware profile once we have fleet data, and
  revisit worker-pool sizing if partition count changes materially.
