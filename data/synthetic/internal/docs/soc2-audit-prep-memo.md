# SOC 2 Type II readiness -- fieldwork complete

- **To:** Executive team (Renata Voss, Grace Adeyemi, Johan Brandt, Maya
  Kaplan, Nora Vasquez, Theo Marchand)
- **From:** Sylvia Ngata (General Counsel) & Diego Fuentes (Head of IT)
- **Date:** 2026-06-16
- **Re:** SOC 2 Type II readiness -- fieldwork complete, findings & remediation

## Engagement summary

Our SOC 2 Type II engagement is with **Ashgrove Audit & Assurance**. Kickoff
was announced in April; fieldwork ran April through May and is now complete.
The observation window is H1 2026 (2026-01-01 through 2026-06-30), so a
handful of controls are still accumulating evidence through month-end. We
expect Ashgrove's report in Q3.

This memo covers what tested well, the three findings raised during
fieldwork, and where we need leadership to act. Nothing here is a surprise
to the control owners -- we walked each item with Ashgrove as it came up.

## What tested well

- **Change management.** Our strongest evidence, ironically, is a failure.
  The March incident chain is complete end to end: change record
  **CHG-2026-0023** (the consumer rollout that regressed),
  **INC-2026-0311** (the incident it caused, 2026-03-11), and
  **CHG-2026-0024** (the emergency rollback) all tie together with
  timestamps, approvals, and a published postmortem. Ashgrove specifically
  called out that even our worst day this half has a clean audit trail --
  that is exactly what a change-management control is supposed to
  demonstrate.
- **Incident response and postmortems.** INC-2026-0311 was declared,
  triaged, rolled back, and post-mortemed within 24 hours, with the
  postmortem published 2026-03-12 and follow-ups tracked to close (dashboard
  staleness banner shipped 2026-04-02; the consumer fix reached production
  2026-03-24). The blameless format and the follow-up register both mapped
  cleanly to the criteria.
- **Data-retention policy v3.2 adherence.** Sampled retention jobs matched
  the stated schedule; no over-retention observed in the sample. Policy
  version, effective date, and enforcement all lined up.

## Findings & remediation

Three findings. All were disclosed to us and discussed as they arose; none
was a control we claimed and failed to operate.

1. **Offboarding SaaS deprovisioning gap.** When sales rep Derek Mun
   (EMP-1042) left on 2026-03-31, offboarding ticket **IT-2231** covered his
   laptop, badge, and directory account, but his **Saltmarsh CRM**
   entitlement stayed active until the Q2 access review caught and revoked it
   in early June. Root cause: the provisioning runbook had no explicit
   per-app SaaS deprovisioning step.
   - **Remediation:** runbook revised **2026-06-12** to require per-app SaaS
     deprovisioning on every departure, plus quarterly user-access reviews as
     a backstop. Owner: **Diego Fuentes**. **Status: closed.**

2. **February phishing click rate (14%).** The 2026-02-12 simulation showed
   a ~14% click rate against a ~22% report rate -- higher clicks than we want.
   - **Remediation:** an awareness push following the real invoice-themed
     phishing wave on **2026-05-20**, then a June simulation
     (2026-06-16) that improved to a ~6% click rate and a ~41% report rate.
     Owner: **Ravi Chandran**. **Status: closed.**

3. **Server-room badge-access list had no documented review cadence.** The
   physical-access list was accurate when sampled, but there was no recurring,
   evidenced review of who holds server-room access.
   - **Remediation:** fold a server-room badge-access review into the same
     quarterly cadence as the user-access reviews, with sign-off recorded in
     Torchstone Desk. Owner: **Diego Fuentes**. **Status: in progress** --
     first documented review scheduled alongside the Q3 access review.

## Open asks of leadership

- **Department leaders:** keep treating access-review requests as a standing
  quarterly obligation, not a one-time audit chore. The Q2 review (reviewers =
  department leaders) is what caught finding #1.
- **Renata / Grace:** budget confirmation for the Ashgrove fieldwork months
  is done ($25k/mo across April and May); no further spend is expected before
  the Q3 report.
- **All execs:** when Ashgrove sends evidence requests during the report
  phase, say yes quickly. Turnaround is the single biggest lever on the Q3
  timeline.

## Next steps timeline

- **Now -- 2026-06-30:** observation window closes; remaining H1 evidence
  finishes accumulating.
- **By 2026-06-30:** first documented server-room badge-access review
  (closes finding #3).
- **Q3:** Ashgrove delivers the Type II report; Sylvia and Diego debrief the
  executive team.

Questions to Sylvia Ngata or Diego Fuentes.
