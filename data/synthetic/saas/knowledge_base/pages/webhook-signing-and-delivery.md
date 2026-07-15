---
page_id: KB-152
space: product-docs
title: Webhook signing and delivery
author: marcus.webb
created: 2026-02-03
last_updated: 2026-05-27
version: 3
labels: [webhooks, developers, security]
---

# Webhook signing and delivery

Acme Analytics delivers product events to your registered HTTPS endpoints as
signed JSON webhooks. This page covers signature verification, the delivery and
retry model, and the event catalog.

## Signature verification

Every webhook request carries two headers:

- `X-Acme-Timestamp` -- Unix timestamp when the request was signed.
- `X-Acme-Signature` -- HMAC-SHA256 of `timestamp + "." + body`, hex-encoded,
  computed with your per-endpoint signing secret.

The signing secret is shown **once** when the endpoint is created. Store it
securely; if lost, roll the endpoint to generate a new one.

Reject any request whose `X-Acme-Timestamp` differs from your server clock by
more than **5 minutes** -- this blocks replay of captured payloads.

```python
import hmac, hashlib, time

def verify(secret, headers, raw_body):
    ts = int(headers["X-Acme-Timestamp"])
    if abs(time.time() - ts) > 300:          # 5-minute skew window
        return False
    signed = f"{ts}.{raw_body}".encode()
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, headers["X-Acme-Signature"])
```

Always compare with a constant-time function and verify against the raw request
body before JSON parsing.

## Delivery and deduplication

Delivery is **at-least-once**. The same event may arrive more than once, so
consumers MUST deduplicate on the event `id` field. Treat a repeat `id` as a
no-op.

Return any 2xx status to acknowledge. Respond quickly (under a few seconds) and
process asynchronously if the work is slow.

## Retry schedule

On any non-2xx response or timeout, delivery is retried on this schedule:

| Attempt | Delay after previous |
|--------:|----------------------|
| 1 | 1 minute |
| 2 | 5 minutes |
| 3 | 30 minutes |
| 4 | 2 hours |
| 5 | 6 hours |
| 6+ | hourly, up to 24 hours total |

After 24 hours of failures the endpoint is **auto-paused** and the account
admin is emailed. Resume it from the webhooks settings panel once the receiver
is healthy.

## Event types

| Event type | Fires when |
|------------|-----------|
| `report.generated` | A report finishes rendering |
| `export.completed` | A scheduled or manual export is delivered |
| `alert.triggered` | A usage alert crosses its threshold |
| `api_key.rotated` | An API key is revoked during rotation |
| `dashboard.shared` | A dashboard is shared with another user |
| `ingest.backpressure` | The ingest pipeline signals sustained backpressure |

All event bodies share a common envelope with `id`, `type`, `created`, and a
`data` object specific to the event type.
