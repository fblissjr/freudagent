---
page_id: KB-158
space: product-docs
title: Scheduled report exports guide
author: ingrid.bauer
created: 2026-05-18
last_updated: 2026-06-24
version: 2
labels: [exports, reporting, how-to]
---

# Scheduled report exports guide

Scheduled report exports let you generate usage reports on a recurring schedule
and have them delivered automatically. This feature reached general
availability on **2026-05-18** after a private beta that opened 2026-02-09. A
warm thank-you to the design partners who ran early schedules with us and
shaped the recurrence and delivery model.

## Availability

Scheduled exports are available on the **scale** and **enterprise** plans.
Accounts on starter or growth see the feature as an upgrade prompt.

## Creating a schedule

1. Open a saved report and choose **Schedule export**.
2. Pick a recurrence rule (see below).
3. Choose an output format.
4. Add one or more delivery recipients.
5. Save. The first run fires on the next matching slot.

## Recurrence rules

Schedules are timezone-aware; the timezone you select determines when each run
fires and how day and month boundaries are interpreted.

| Recurrence | Behavior |
|------------|----------|
| Daily | Runs once per day at the chosen local time |
| Weekly | Runs on the chosen weekday(s) at the chosen local time |
| Monthly | Runs on the chosen day-of-month at the chosen local time |

## Output formats

- **CSV** -- portable, spreadsheet-friendly.
- **parquet** -- columnar, efficient for large result sets and downstream
  analytics pipelines.

## Delivery

Each run produces a file delivered via a **time-limited signed URL that is
valid for 24 hours**. Download or copy the file to durable storage within that
window; expired URLs cannot be reissued for the same run, but the next
scheduled run produces a fresh delivery.

One `export.completed` webhook fires per delivery, giving you a machine-readable
audit trail of every export. Deduplicate on the event `id` as with all
webhooks.

## Row limits

The in-browser CSV export cap of 10,000 rows does **not** apply to scheduled
exports. Scheduled exports write to a file, so full result sets are delivered
regardless of row count.

## FAQ

**Can I deliver exports directly to my cloud storage bucket?**
Not yet. Direct-to-bucket delivery is on the roadmap. Today, exports are
delivered exclusively through the 24-hour signed URL; automate retrieval by
subscribing to the `export.completed` webhook and fetching the file from your
own job.

**What timezone do runs use?**
Whatever you select on the schedule. Daylight-saving transitions are handled by
the timezone database, so local run times stay stable across the change.

**Can I schedule the same report in more than one format?**
Yes -- create one schedule per format, or use separate schedules with different
recurrence rules as needed.
