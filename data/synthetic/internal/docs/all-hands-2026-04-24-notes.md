# All-hands notes -- 2026-04-24

- **Date:** 2026-04-24
- **Host:** renata.voss
- **Notes:** People team (maya.kaplan's org)
- **Format:** company-wide, ~45 min + Q&A

## Q1 business recap (Renata)

- Solid quarter overall: pipeline is healthy and up quarter over quarter,
  new-logo velocity on track.
- Honest note: two SMB accounts contracted effective 2026-03-01, combined
  **-$79.2k ARR**. Both were scale-tier accounts that had over-bought and
  never grew into their usage.
- What we're changing: **quarterly utilization reviews for scale-tier
  accounts**, so CS opens right-sizing conversations on our terms instead of
  reacting to a renewal. Carlos's team owns the cadence.
- Framing from Renata: right-sizing an under-used account is not a loss of
  trust, it's how we keep the ones we want. We do not defend MRR the usage
  can't support.

## March incident retro (Johan)

- Plain-language recap of **INC-2026-0311** for the whole company: on
  2026-03-11 a routine deploy of our ingestion consumer slowed event
  processing under large batches, dashboards showed stale numbers, and the
  usage API returned intermittent 502s for about an hour and three-quarters.
  We rolled the deploy back. **No data was lost** -- queued events were fully
  processed.
- What's shipped since: a **dashboard staleness banner** (live 2026-04-02) so
  customers see when data is behind instead of finding out the hard way, and
  the **consumer fix in production** (2026-03-24).
- Thank-yous to Support for the 30-minute-cadence customer comms during the
  incident -- Yuki's team kept enterprise accounts calm and that showed up in
  the CSAT.

## Product (Ingrid)

- **Scheduled report exports go GA on 2026-05-18.** Private beta has been
  running since February; design partners are happy. GA covers recurrence
  rules, CSV/parquet output, and signed-URL delivery.
- Post-GA roadmap teaser: direct-to-bucket delivery is next on the list, order
  set by customer feedback.

## SOC 2 kickoff (Sylvia / Diego)

- We've kicked off a **SOC 2 Type II** engagement with **Ashgrove Audit &
  Assurance**. Fieldwork runs over the next couple of months.
- What this means for you: **expect evidence requests, and say yes quickly.**
  If an auditor or a control owner asks for a screenshot, a ticket, or a
  policy acknowledgment, treat it as top of your list. Fast turnaround is the
  whole game.

## People (Maya)

- **Q2 hiring plan** approved: a focused set of reqs across engineering, CS,
  and sales, including a **pipeline data-engineer req** on Johan's side.
  Referrals welcome -- Harrowgate Hire has the open list.
- **Benefits reminder:** mid-year enrollment questions go to People; nothing
  changes this quarter, but check your elections.
- **Badge etiquette:** no tailgating. Everyone badges in individually at
  Doorstile readers, including at the server-room door. Hold the door for a
  colleague and you've just created an access-review headache.

## Q&A

1. **"After the March incident -- are we multi-region yet?"** (engineer)
   Johan, honestly: no, we run a **single region** today. We ran a **DR test
   this morning** and restore times met target. **Active-active is on the
   roadmap, not a promise** -- it's a large investment and we'd rather ship it
   right than announce a date we might miss. The staleness banner and the
   consumer fix address the failure mode we actually hit in March.

2. **"When does the exports GA marketing go out?"** (CS)
   Ingrid: sales enablement lands the week before 2026-05-18; customer-facing
   announcement on GA day.

3. **"Do we get audit questions directly or through our managers?"** (support)
   Sylvia: through your control owner or manager, usually. If Ashgrove reaches
   you directly, loop in Diego and answer factually -- don't guess, point them
   to the system of record.

## Close

Renata: strong Q1 execution, one honest churn lesson banked, a clean incident
story, a GA date, and an audit that -- so far -- is showing our records hold
up. Back to it.
