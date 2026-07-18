Final — ingrid.bauer — 2026-03-20 (incorporates exec steer)

# Data Platform Strategy (One-Pager)

## Context

Acme Analytics ingests usage events from customer applications, processes them
through our ingestion tier, and serves dashboards and scheduled exports. As we
move upmarket into larger enterprise accounts, the reliability and scale
expectations on the data platform are rising. This one-pager sets our direction
for the next 12 months.

## Current State

- Single-region deployment with a tested disaster-recovery (DR) plan.
- Ingestion tier processes events into our analytical store.
- Dashboards and the scheduled exports (GA 2026-05-18) read from that store.
- The March incident (INC-2026-0311) exposed how a single bad config push can
  degrade the whole ingestion path.

## The Core Question

How much resilience and scale should we build into the platform in 2026, and how
fast?

## Recommendation

We should evaluate a multi-region active-active pipeline, but single-region plus
tested DR is adequate for 2026. A single region is a real consideration as we sign
larger accounts, but the March incident was a config-safety failure, not a
regional-failover failure, and it is already addressed by the staged rollout gate
and canary check we shipped. Active-active is a significant investment we should
scope rather than commit to this year, and revisit once enterprise demand or a
signed commitment justifies the build. Per exec steer: do not commit to
active-active on a date.

## Rationale

- Enterprise buyers increasingly ask about regional failover in security reviews.
- The March incident's root cause is config safety, now mitigated - not a lack of
  active-active.
- Building it in-house keeps the platform under our control, but that argument
  holds whether we build now or later.

## Risks and Trade-offs

- Active-active is a significant engineering investment and adds operational
  complexity.
- Choosing evaluation-over-build means we carry the single-region risk through 2026.
- It competes for the same engineers doing export and analytics work.

## Proposed Next Steps

1. Produce an active-active evaluation and rough sizing (design only, no build).
2. Keep single-region + DR as the committed posture for 2026.
3. Revisit the build decision if enterprise demand or a signed commitment emerges.
