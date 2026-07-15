---
page_id: KB-140
space: product-docs
title: Dashboard sharing and permissions
author: dana.kim
created: 2026-02-14
last_updated: 2026-06-09
version: 3
labels: [dashboards, sharing, permissions]
---

# Dashboard sharing and permissions

## Roles

- **viewer** -- see dashboards shared with them; no editing, no exports
  above 1,000 rows.
- **editor** -- create and edit dashboards, run exports up to the plan cap.
- **admin** -- everything, plus member management, API keys, SSO, billing.

## Read-only sharing links

Editors can create read-only links to a dashboard with an expiry of 1, 7,
or 30 days. Links snapshot permissions at creation time; rotating the link
invalidates the old URL immediately. Extending an expired link is not
possible -- create a new link (this is deliberate: expired links are a
security boundary, not a soft timeout).

## Export caps

CSV exports from the usage explorer are capped at **10,000 rows** in the
browser. Larger exports should use scheduled report exports (scale and
enterprise plans) or the Metering API's paginated read endpoints. The
in-browser cap exists because larger exports were the top cause of
browser-tab crashes in 2025 support volume.
