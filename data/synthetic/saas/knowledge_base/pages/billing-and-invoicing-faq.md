---
page_id: KB-133
space: support
title: Billing and invoicing FAQ
author: carlos.mendes
created: 2026-01-08
last_updated: 2026-05-02
version: 6
labels: [billing, invoicing, plans]
---

# Billing and invoicing FAQ

## What are the plans and prices?

| Plan | Monthly price | Included events/mo | API rate limit |
|------|--------------:|-------------------:|---------------:|
| starter | $299 | 1M | 60 req/min |
| growth | $1,200 | 10M | 300 req/min |
| scale | $4,500 | 75M | 1,200 req/min |
| enterprise | $12,500+ | custom | custom |

Annual billing is available on all plans and required on scale and
enterprise.

## How are overages charged?

Usage above the included event volume is billed per additional million
events at the rate on your order form. There is a **5% grace threshold**:
months where you exceed the included volume by 5% or less are not charged
an overage line at all.

## An invoice doesn't match what the usage explorer shows

The invoice counts *billable* ingested events for the calendar month in
UTC; the usage explorer defaults to your dashboard timezone and includes
rejected/deduplicated events in its "received" series. Compare against the
"billable" series with the timezone set to UTC first.

If the gap persists, open a support ticket with the invoice ID (`INV-*`).
Billing can recompute a month excluding incident replay windows -- this is
the standard remedy when a pipeline replay (ours, not yours) inflates a
month, as with the March 2026 incident.

## When are invoices issued and due?

Invoices are issued on the 2nd of each month for the prior month, due
net-30. Unpaid invoices move to `past_due`; no late fees accrue while a
dispute is under active review.
