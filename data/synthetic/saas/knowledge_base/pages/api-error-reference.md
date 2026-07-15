---
page_id: KB-145
space: product-docs
title: API error reference
author: marcus.webb
created: 2026-01-15
last_updated: 2026-06-12
version: 4
labels: [metering-api, developers, troubleshooting]
---

# API error reference

Every Acme Analytics API endpoint under `/v1` returns a structured error body
on failure. This page documents the status codes callers should handle and how
to escalate to support with the right identifiers.

## Error body shape

All error responses share the same JSON envelope:

```json
{
  "error": {
    "code": "batch_too_large",
    "message": "Batch exceeds the 1,000 event limit.",
    "request_id": "req_9f3a2c7b1e"
  }
}
```

- `error.code` -- stable machine-readable string; safe to branch on.
- `error.message` -- human-readable explanation; may change wording over time.
- `error.request_id` -- unique per request; matches the `X-Request-Id`
  response header. Support asks for `request_id` when you escalate, so log it.

## Status codes

| Status | Meaning | Common causes |
|-------:|---------|---------------|
| 400 | Validation error | Malformed JSON, missing required field, event payload over 32 KB |
| 401 | Authentication failed | Missing, malformed, or revoked API key |
| 403 | Not permitted | Feature not on your plan, or role lacks permission (viewer/editor/admin) |
| 404 | Not found | Unknown resource path or deleted object |
| 413 | Payload too large | Batch over 1,000 events, event over 32 KB, or request body over 4 MB |
| 429 | Rate limited | Per-minute request limit exceeded |
| 5xx | Server error | Upstream or internal fault; 502 surfaces an upstream dependency issue |

### 400 -- validation

Returned when the request body fails schema validation. Example:

```json
{
  "error": {
    "code": "missing_field",
    "message": "Field 'source_id' is required.",
    "request_id": "req_1a2b3c4d5e"
  }
}
```

### 401 -- authentication

The API key is absent, malformed, or has been revoked. Rotate the key from the
admin panel and redeploy callers. See the key management guide.

### 403 -- plan or role restriction

The key is valid but the account plan or the caller's role does not grant the
requested operation. SSO and group-based role mapping, for example, are gated
by plan tier.

### 413 -- payload too large

Three distinct limits map to 413:

- Batch requests to `POST /v1/usage/batch` may carry at most **1,000 events**
  (the v0 limit of 500 was sunset 2025-12-31).
- A single event payload may not exceed **32 KB**.
- The total batch request body may not exceed **4 MB**.

Split oversized batches client-side before retrying.

### 429 -- rate limit

Every response carries the current rate-limit state:

| Header | Meaning |
|--------|---------|
| `X-RateLimit-Limit` | Requests allowed in the current window |
| `X-RateLimit-Remaining` | Requests remaining in the current window |
| `X-RateLimit-Reset` | Unix timestamp when the window resets |

Per-plan limits:

| Plan | Requests/min | Burst |
|------|-------------:|------:|
| starter | 60 | 120 |
| growth | 300 | 600 |
| scale | 1,200 | 2,400 |
| enterprise | custom | custom |

Back off until `X-RateLimit-Reset`, and move high-volume single-event traffic
to `POST /v1/usage/batch`.

### 5xx -- server errors

Transient. A `502` indicates an upstream dependency issue rather than a problem
with your request. Retry with exponential backoff, and check the status page at
status.acme-analytics.example before opening a ticket. If failures persist,
escalate to support@acme-analytics.example with the `request_id`.
