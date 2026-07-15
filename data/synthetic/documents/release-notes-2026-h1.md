# Acme Analytics — Release Notes (H1 2026)

Product updates for Acme Analytics, the usage-analytics platform. Newest month
first. Entries reference internal tracker keys (ACME-* / DATA-*) for
cross-linking with engineering records; these keys are internal and are shown
for traceability only.

---

## June 2026

- **Parquet export compression options.** Scheduled and on-demand parquet
  exports now let you choose the compression codec (snappy or zstd) per report.
  Zstd trims delivered file size on large datasets at a small CPU cost; snappy
  remains the default for fastest downstream reads.

- **Per-key last-used timestamps in the admin panel.** The API keys view now
  shows the last time each key was used against a metering endpoint, making it
  easier to spot stale keys before rotating them.

- **Usage explorer polish.** Column ordering in the explorer now persists with
  your saved views, and CSV exports carry the same column order you see on
  screen.

## May 2026

- **Scheduled report exports are now generally available (May 18).** After the
  private beta, scheduled exports are open to all scale and enterprise plans.
  Define daily, weekly, or monthly recurrence rules in your chosen timezone,
  export to CSV or parquet, and receive each delivery through a 24-hour signed
  URL. Every delivery emits one `export.completed` audit event so you can
  reconcile what was sent and when. Tracked under the ACME-180 initiative.

- **Delivery reliability.** Signed-URL delivery now retries transient failures
  before marking a run failed, and failed runs surface a clear reason in the
  exports history.

## April 2026

- **Dashboard staleness banner (ACME-247).** Dashboards now show an explicit
  banner when the aggregates behind them are lagging more than 10 minutes. The
  banner reads the freshness watermark (`X-Acme-Freshness`) so you always know
  whether a number reflects recent events or is catching up. This closes a gap
  from the March incident, where stale aggregates were served without any
  visible signal.

- **Freshness watermark on the API.** The `/v1/usage` responses now include the
  `X-Acme-Freshness` header, giving API consumers the same staleness signal the
  dashboards use.

## March 2026

- **Consumer performance fix — batch decompression moved off the partition
  lock (DATA-88).** The event consumer previously decompressed batched payloads
  while holding the Kafka partition lock, which let large batches starve
  partitions under load. Decompression now runs in a bounded worker pool, with
  offsets committed only after the downstream write completes. In load testing
  at 3x normal volume, p99 commit latency dropped from 2.1s to 140ms. Shipped
  in consumer build 2026.3.9.

- **March 11 service incident (INC-2026-0311).** On March 11 (14:02–15:47 UTC),
  a consumer build regression held the partition lock during payload
  decompression, starving several usage-events partitions. Consumer lag peaked
  around 41 minutes, dashboards served stale aggregates without a staleness
  signal, and up to 18% of `/v1/usage` requests returned 502 as upstream
  latency exceeded the gateway timeout. We restored service by rolling back the
  consumer build; lag returned to zero by 15:47 UTC. A postmortem summary has
  been published to customers. The root-cause fix shipped in DATA-88, and the
  staleness banner (ACME-247) was added so silent staleness can't recur.
  Replayed backlog events are tagged `replay=true` and excluded from billing so
  the recovery did not affect billable counts.

- **Backfill tooling (DATA-80).** You can now replay events from object storage
  by date range, making it straightforward to recover from gaps or re-run
  historical ingestion windows.

- **Rate-limit headers on metering endpoints (ACME-143).** All public metering
  endpoints now return standard rate-limit headers, so clients can back off
  gracefully instead of guessing at limits.

- **Timezone selector fix (ACME-114).** Fixed a bug where the timezone selector
  reset to UTC after you saved dashboard preferences. Your chosen timezone now
  persists correctly.

## February 2026

- **Scheduled report exports — private beta (Feb 9).** Scheduled exports opened
  in private beta for scale and enterprise plans. Beta participants can define
  recurrence rules and receive CSV or parquet deliveries via signed URL. Part
  of the ACME-180 initiative.

- **Ingest-time deduplication (DATA-83).** The ingestion pipeline now
  deduplicates events at ingest time on `(source_id, idempotency_key)`,
  preventing accidental double-counting from client retries.

## January 2026

- **CSV export in the usage explorer (ACME-163).** You can now export the
  current usage explorer view to CSV directly from the toolbar, matching the
  filters and columns on screen.

- **Explorer filter refinements.** Minor improvements to filter chips and empty
  states in the usage explorer for clearer feedback when a query returns no
  rows.

---

_Questions about any release? Contact your account team. Batch API remains
limited to 1,000 events per request._
