---
page_id: KB-101
space: product-docs
title: Metering API overview
author: ingrid.bauer
created: 2025-11-03
last_updated: 2026-04-21
version: 7
labels: [metering-api, developers]
---

# Metering API overview

The Metering API is how customer systems send usage events to Acme Analytics
and read aggregated usage back. All endpoints live under `/v1` and
authenticate with an API key sent as a bearer token.

## Sending events

- `POST /v1/usage` -- single event. Use for low-volume, latency-sensitive
  paths.
- `POST /v1/usage/batch` -- up to **1,000 events per request** (the v0 limit
  of 500 is retired; v0 was sunset 2025-12-31). Requests above the limit are
  rejected with `413`.
- Events carry an `idempotency_key`; retries with the same key are
  deduplicated at ingest.

## Reading usage

- `GET /v1/usage` -- aggregated usage by day, metric, and dimension filters.
- Aggregates are eventually consistent. The freshness watermark is exposed on
  every response (`X-Acme-Freshness`); dashboards show a staleness banner
  when the watermark lags more than 10 minutes (added after INC-2026-0311,
  see ACME-247).

## Rate limits

| Plan | Requests/min | Burst |
|------|-------------:|------:|
| starter | 60 | 120 |
| growth | 300 | 600 |
| scale | 1,200 | 2,400 |
| enterprise | custom | custom |

Every response includes `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and
`X-RateLimit-Reset`. Sustained `429`s usually mean a batch job should move
to `POST /v1/usage/batch` rather than the single-event endpoint.

## Webhooks

Product events (`report.generated`, `export.completed`, `alert.triggered`,
and others) are delivered as JSON webhooks. Delivery is at-least-once:
consumers MUST deduplicate on the event `id`. See the request signing
appendix in the developer portal for verification.
