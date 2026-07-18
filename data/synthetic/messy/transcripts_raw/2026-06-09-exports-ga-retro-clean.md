# Scheduled Exports GA - Retrospective

**Date:** 2026-06-09
**Meeting:** Retro on the Scheduled Report Exports GA (shipped 2026-05-18)
**Attendees:** ingrid.bauer (PM), marcus.webb (Eng), dana.kim (Eng)

## Summary

The team reviewed the scheduled exports release three weeks post-GA. The rollout
was considered smooth: a private beta with eight accounts (including bluewater-logistics)
preceded the 2026-05-18 GA. A CSV truncation bug was caught during beta and never
reached GA. The staleness banner was called out as the standout feature of the release,
credited with a large drop in a whole category of support tickets. The main open issue
is that Parquet exports are written uncompressed, producing very large files for big
accounts.

## Discussion

**ingrid.bauer:** Opened the retro, framing it around the 2026-05-18 GA and the goal of
landing on action items. Noted the rollout was smooth, with a private beta of eight
accounts before GA.

**marcus.webb:** Flagged a beta-only bug: the CSV export truncated at ~10,000 rows for
high-event accounts due to a pagination defect. It never shipped to GA, but was risky
because a customer trusting a truncated export would silently miss data.

**dana.kim:** Confirmed the pagination bug and credited carlos.mendes with catching it
during the bluewater-logistics beta (he noticed the exported row count didn't match the
dashboard). Praised the staleness banner as the best thing shipped in the release: it
warns when exported data is more than an hour old by stamping the snapshot generation
time, heading off confusion when downloaded numbers don't match live figures. Noted
yuki.tanaka's support team reported a large drop in that ticket category.

**ingrid.bauer:** Attributed the staleness banner to a combination of a support request
and product spec.

**marcus.webb:** Raised the main "didn't go well" item: Parquet exports are written
completely uncompressed, making files huge (multiple gigabytes for a single monthly
export at large accounts) and slow to download. Parquet supports built-in compression
(Snappy or zstd); it simply is not enabled. Expected to be mostly a config change.

**dana.kim:** Noted the export docs still say "beta" in a couple of places.

## Action Items

- **marcus.webb** - Enable Parquet compression (evaluate Snappy vs zstd) and file the change.
- **marcus.webb** - Add a regression test for the pagination/row-count truncation bug (folded into the Parquet work).
- **dana.kim** - Clean up leftover "beta" labels in the export documentation.
