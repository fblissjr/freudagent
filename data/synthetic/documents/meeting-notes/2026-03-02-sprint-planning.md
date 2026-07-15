# Sprint planning notes -- 2026 Sprint 5 (2026-03-02)

- **Facilitator:** priya.raghavan. **Notes:** dana.kim
- **Attendees:** platform + pipeline teams, ingrid.bauer

## Sprint goal

Scheduled exports milestone: recurrence rules UI and signed-URL delivery
behind the beta flag, end to end for one design-partner account.

## Committed

- Scheduled report exports: recurrence rules UI (ACME-180 child) -- dana.kim
- Scheduled report exports: delivery via signed URL (ACME-180 child) --
  marcus.webb
- Consumer lag dashboards per topic partition -- noah.lindqvist
- Rotate API gateway TLS certificates (ops window Thursday) -- tom.alvarez

## Discussed, not committed

- Batch-consumer performance work: elena.sokolova flagged that the new
  decompression path in the consumer build going out next week "changes
  where the CPU burns" and asked for a load-test slot; deferred to next
  sprint pending the observability dashboards. (In hindsight: see
  INC-2026-0311 postmortem.)
- Self-serve plan upgrades: needs billing review first, ingrid to scope.

## Risks

- Cert rotation and the consumer rollout land the same week; agreed to
  separate them by at least one day so alert noise stays attributable.
