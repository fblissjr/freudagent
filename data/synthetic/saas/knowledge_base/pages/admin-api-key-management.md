---
page_id: KB-170
space: support
title: Admin API key management
author: yuki.tanaka
created: 2026-04-10
last_updated: 2026-06-18
version: 2
labels: [security, admin, api-keys]
---

# Admin API key management

API key management is restricted to the **admin** role. Editors and viewers
cannot create, scope, or revoke keys. This page covers key scoping and the
zero-downtime quarterly rotation procedure support recommends.

## Key basics

- Keys are shown **once**, at creation. Copy the key immediately and store it in
  a secrets manager -- Acme Analytics cannot display it again.
- Each key is authenticated as a bearer token on `/v1` requests.
- The admin panel shows a per-key **last-used timestamp** so you can confirm
  which keys are still receiving traffic.

## Scoping

Assign each key the narrowest scope its caller needs:

| Scope | Grants |
|-------|--------|
| read-only | `GET /v1/usage` and other read endpoints |
| ingest+read | Read endpoints plus `POST /v1/usage` and `POST /v1/usage/batch` |

Give reporting and dashboard integrations a read-only key; reserve ingest+read
for systems that actually send events.

## Zero-downtime rotation

Rotate keys on a quarterly cadence. The procedure below rotates without
dropping a single request:

1. **Create a second key** with the same scope as the one you are replacing.
   Both keys are now valid simultaneously.
2. **Deploy the new key** to all callers (secrets manager, CI, environment
   config). Roll it out everywhere the old key is used.
3. **Verify traffic has moved** using the per-key last-used timestamp in the
   admin panel. The new key's timestamp should advance while the old key's goes
   idle. Wait until the old key shows no recent use.
4. **Revoke the old key.** On revocation, an `api_key.rotated` webhook fires so
   downstream systems can record the change.

Because both keys are valid through steps 1--3, no caller is ever left without a
working credential.

## Security rules

- **Never embed keys client-side.** Keys in browser code, mobile bundles, or
  public repos are compromised the moment they ship. Keep keys server-side.
- Prefer short-scoped keys per integration over one shared key, so a single
  leak has a contained blast radius and a revocation does not break unrelated
  callers.
- A revoked key returns `401` immediately; make sure no caller depends on it
  before completing step 4.
- Subscribe to the `api_key.rotated` webhook to audit every rotation centrally.

For help mid-rotation, contact support@acme-analytics.example with the affected
key's identifier (never the key value itself).
