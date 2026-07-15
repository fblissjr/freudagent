---
page_id: KB-163
space: product-docs
title: Usage alerting guide
author: dana.kim
created: 2026-03-25
last_updated: 2026-06-05
version: 3
labels: [alerting, monitoring, how-to]
---

# Usage alerting guide

Usage alerts notify you before consumption or errors reach a level you care
about. This guide covers the available metrics, threshold configuration,
delivery channels, and one important caveat about freshness.

## Metrics

| Metric | Measures | Threshold basis |
|--------|----------|-----------------|
| `api_calls` | Request volume against your plan's rate limits | Fraction of plan volume |
| `events_ingested` | Events accepted through the Metering API | Fraction of plan volume |
| `error_rate` | Share of requests returning 4xx/5xx | Absolute value |

## Thresholds

For volume metrics (`api_calls`, `events_ingested`), thresholds are configured
as a fraction of your plan's included volume:

| Threshold | Fires at |
|----------:|----------|
| 0.8 | 80% of plan volume |
| 0.9 | 90% of plan volume |
| 0.95 | 95% of plan volume |

For `error_rate`, set an absolute threshold (for example, 0.02 for a 2% error
rate) rather than a fraction of plan volume.

**Recommendation:** alert at **0.8**. The 5% overage grace threshold means you
have limited headroom above 100%, so an 80% alert gives you time to react --
throttle a noisy job, upgrade a plan, or investigate -- before overage
charges begin.

## Delivery

Triggered alerts are delivered two ways:

- **`alert.triggered` webhook** -- machine-readable, for routing into your own
  on-call or automation. Deduplicate on the event `id`.
- **Email** -- to the alert's configured recipients.

Configure recipients per alert so the right team is notified.

## Freshness caveat

Alerts evaluate against the **freshness watermark**, the same watermark exposed
on read responses via `X-Acme-Freshness`. During ingestion delays the watermark
lags real time, and alerts lag with it -- an alert may fire later than the
underlying usage actually crossed the threshold.

When the watermark lags more than 10 minutes, dashboards display a staleness
banner. If you see the banner, treat alert timing as approximate until ingest
catches up. See the metering API overview for how freshness is surfaced.

## Tips

- Layer 0.8 / 0.9 / 0.95 alerts on the same metric to escalate as usage climbs.
- Route `alert.triggered` webhooks to a dedupe-aware consumer so a redelivered
  event does not page twice.
- Pair volume alerts with an `error_rate` alert to catch integration problems
  that inflate call counts.
