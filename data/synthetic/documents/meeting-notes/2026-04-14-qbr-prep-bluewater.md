# QBR prep -- Bluewater Logistics (ACCT-1001), call on 2026-04-16

- **Prepared by:** carlos.mendes, with aisha.diallo
- **Customer attendees expected:** Jordan Whitfield (ops lead, primary
  contact), plus their data engineering manager

## Account snapshot

- Enterprise plan, $150k ARR, renewal 2026-Q4.
- Usage trending at 88-94% of committed volume -- healthy, no overage
  exposure, no headroom pressure yet.
- Support: 4 tickets this quarter; SUP-1042 (incident, closed CSAT 4) is
  the one to address head-on, not avoid.

## Narrative for the incident section

Own it: timeline, root cause (consumer deploy), what shipped since --
staleness banner (ACME-247) and the consumer fix (DATA-88, in prod since
2026-03-24, lag alarms quiet). The 30-minute update cadence was noticed;
reinforce it's policy, not luck.

## Expansion hypothesis

Their `export.completed` volume doubled since January and they're pulling
daily parquet exports into their own lakehouse -- the metering-api addon
with paginated reads is the honest fit. Do NOT pitch the seat-expansion
placeholder in the CRM; there's no product signal behind it.

## Open questions to expect

- Multi-region: their ops team asked twice on support whether we run
  active-active. We are single-region with cross-region DR today; do not
  oversell. If they push, the roadmap conversation goes through ingrid.
- SSO group mapping limits (their IT follows the Kestrel thread on the
  community forum, apparently).
