---
page_id: KB-114
space: support
title: Troubleshooting data delays in dashboards
author: yuki.tanaka
created: 2026-01-20
last_updated: 2026-04-02
version: 5
labels: [dashboards, ingestion, troubleshooting]
---

# Troubleshooting data delays in dashboards

Use this page when a customer reports that dashboards are "missing" recent
data. In almost every case the data is delayed, not lost: ingestion is
at-least-once and events are durably queued before aggregation.

## Triage checklist

1. **Check the freshness watermark.** Every dashboard shows a staleness
   banner when aggregates lag more than 10 minutes. If the banner is up,
   this is a known-delay state, not data loss.
2. **Check the status page.** An active ingestion incident explains delays
   across all customers.
3. **Ask for a request ID.** If the customer's own sends are failing
   (`4xx`/`5xx` from `/v1/usage`), the `X-Request-Id` response header lets
   engineering trace the call in the gateway logs.
4. **Confirm the timezone.** "Yesterday looks empty" is frequently a
   dashboard timezone preference issue, not a data issue.

## What to tell customers during an ingestion delay

- Events are queued, not lost; dashboards backfill automatically once
  ingestion catches up.
- Do NOT advise re-sending events "to be safe" -- replays inflate usage
  and can produce billing overages that then need manual correction (this
  is what happened with the March 2026 replay-window disputes).

## Escalation

Open an internal issue on the DATA project with: account ID, affected
time range, one example request ID, and the freshness watermark value.
Link the support ticket so the fix lands back on the customer thread.
