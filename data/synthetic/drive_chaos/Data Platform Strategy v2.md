Rev — ingrid.bauer — 2026-03-05

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
- Dashboards and the newly-shipped scheduled exports read from that store.
- The March incident (INC-2026-0311) exposed how a single bad config push can
  degrade the whole ingestion path.

## The Core Question

How much resilience and scale should we build into the platform in 2026, and how
fast?

## Recommendation

We should build an in-house multi-region active-active pipeline now. A single
region is a structural risk we can no longer accept as we sign larger accounts,
and DR alone means accepting hours of degradation during a regional failure.
Active-active gives us continuous availability and positions us for the scale our
enterprise pipeline implies. We should commit to this in 2026 and start the build
this quarter. The March incident makes the case concrete rather than theoretical.

## Rationale

- Enterprise buyers increasingly ask about regional failover in security reviews.
- The March incident showed our blast radius is region-wide today.
- Building it in-house keeps the platform under our control and avoids vendor
  lock-in on a core capability.
- Doing it now, while the platform is smaller, is cheaper than retrofitting later.

## Risks and Trade-offs

- Active-active is a significant engineering investment and adds operational
  complexity.
- We would be building resilience ahead of hard customer commitments.
- It competes for the same engineers doing export and analytics work.

## Proposed Next Steps

1. Scope the active-active build and size the team.
2. Bring a plan and timeline to the next architecture review.
3. Sequence it against the export and analytics roadmap.
