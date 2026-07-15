# Product spec: usage metering pipeline

- **Owner:** ingrid.bauer
- **Engineering leads:** priya.raghavan (platform), elena.sokolova (pipeline)
- **Status:** shipped (v1); this document is maintained as the reference spec
- **Last updated:** 2026-04-28

## Summary

The metering pipeline turns raw customer events into billable, queryable
usage: ingest → validate → deduplicate → aggregate → serve. Correctness
requirements are asymmetric: undercounting is a refund, overcounting is a
trust incident. When in doubt the pipeline must undercount and reconcile.

## Ingest

Events arrive via `POST /v1/usage` (single) and `POST /v1/usage/batch`.
Producers set an `idempotency_key`; ingest deduplicates on
`(source_id, idempotency_key)` within a 48-hour window. Events older than
48 hours are routed to a dead-letter store with a reason code, never
silently dropped.

### Current limits (v1)

| Limit | Value |
|-------|------:|
| Max events per batch request | **1,000** |
| Max event payload size | 32 KB |
| Max batch request size | 4 MB |
| Dedup window | 48 h |

### Deprecated limits (v0 -- sunset 2025-12-31, kept for historical reference)

| Limit | Value |
|-------|------:|
| Max events per batch request | 500 |
| Max event payload size | 16 KB |

## Aggregation

Events are aggregated into hourly and daily rollups per customer, metric,
and dimension set. Rollups are recomputed when late events land inside the
48-hour window; after the window closes, corrections require an explicit
backfill job with an audit record.

**Billing counts only the `billable` series** -- deduplicated, validated
events within the customer's calendar month (UTC). Replayed events from
pipeline-internal recovery (e.g., incident replays) are tagged
`replay=true` and excluded from the billable series. This tag was added
after the March 2026 incident, where replayed events inflated overages and
produced invoice disputes.

## Serving

Aggregates are served through `GET /v1/usage` and the dashboards. Both
expose the freshness watermark; dashboards render a staleness banner when
the watermark lags more than 10 minutes (ACME-247). The API never blocks
on freshness -- consumers decide what staleness they tolerate.

## Non-goals

- Sub-minute aggregation latency. The SLO is p95 freshness under 5 minutes;
  real-time streams are a separate (unscheduled) initiative.
- Customer-defined metrics DSL. Dimensions are declared at the schema
  registry, not free-form per event.
