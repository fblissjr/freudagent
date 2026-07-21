# How data flywheels fail

Last updated: 2026-07-21

A data flywheel that is running but not compounding is worse than no flywheel,
because it looks like progress. This lists the ways that happens, how to spot
each one, and what to do.

It is a companion to [the data flywheel](data-flywheel.md), which explains how
the loop is meant to work. Read that first if you have not.

Nothing here is specific to this repo. Any system that improves itself from its
own usage data can fail in these ways, whether the knowledge is prompts, rules,
retrieval indexes or model weights. Where this repo has a defence, or lacks one,
the entry says so.

## The short version

If you only read one thing: the loop dies from lack of signal far more often
than from bad mechanics. Five failures cause most of it.

| Failure | What you see | First thing to check |
|---|---|---|
| Nobody corrects anything | detectors fire, no corrections arrive | count of human corrections per week |
| Signal from one corner | one domain improves, others quietly rot | corrections grouped by domain, user, task type |
| Synthetic feedback from a biased seed | volume rises, quality does not | how the seed examples were sampled |
| Knowledge goes stale | answers were right last year | age of each knowledge unit, source hashes |
| Approval becomes a rubber stamp | everything gets approved | rejection rate |

## Signal starvation

### Nobody ever corrects anything

What it looks like: detectors keep producing findings about mechanical things —
retries, errors, permission denials — and no proposals ever come from quality
problems, because nobody is telling the system when an answer was wrong.

Why it happens: reviewing output is work with no immediate reward. It is the
first thing dropped when people are busy. The loop keeps running, so nothing
looks broken.

The consequence is specific and easy to miss: the system optimizes what it can
measure without help. Retry loops shrink, error rates fall, and answer quality
does not move, because nothing in the pipeline knows what a good answer is.

How to catch it: count corrections per week alongside sessions per week. If
sessions climb and corrections stay flat, the loop is running on mechanical
signal alone.

What to do: make review a step in the work rather than a separate chore, and
route a sample of output through validation even when nobody complains. Cold
start playbooks that require validating everything exist for this reason.

### You only ever hear about failures

What it looks like: people record a correction when output is wrong and record
nothing when it is right. Feedback volume looks healthy.

Why it happens: correcting an error has an obvious payoff. Confirming a success
feels like paperwork.

Why it matters: you can measure whether known problems shrank, but not whether
anything that used to work has broken. A change that fixes the reported problem
and quietly breaks three unreported things scores as a win. A two-sided
verification gate needs examples of correct output to test against, and this
failure mode starves exactly that half.

How to catch it: look at the ratio of validations to rejections. If almost every
recorded judgement is negative, you have no positive baseline.

What to do: make confirming an answer as cheap as correcting one — ideally one
keystroke — and treat validated-correct output as a first-class record rather
than an absence of complaint.

### Success starves the loop

What it looks like: the system improves, corrections become rare because there
is less to correct, and improvement flattens. Then the world changes and nobody
notices, because the signal that would have caught it dried up.

Why it happens: the flywheel's fuel is errors. Removing errors removes fuel.

This is the counterintuitive one. Early on, abundant signal makes progress feel
easy, and teams conclude the loop works. The hard part starts when it is working
well, and there is a real risk of concluding the loop is finished rather than
starved.

How to catch it: watch correction volume per hundred sessions over time. A
decline is ambiguous — it means either genuine improvement or attention moving
elsewhere, and those need distinguishing.

What to do: keep a standing sample of output under review regardless of
complaint volume, and lean harder on staleness detection as correction volume
falls. Maintenance signal has to replace error signal over time.

## Biased signal

Sampling bias is more dangerous than low volume, because volume problems are
visible and bias is not. A biased loop produces confident, well-evidenced,
systematically wrong improvements.

### Feedback comes from one corner

What it looks like: most corrections come from one domain, one team, one
customer, or one kind of task. Improvements are real for that slice and quietly
regress everything else.

Why it matters more than it seems: the held-out set used to verify improvements
is usually drawn from the same pool as the feedback. If both are skewed the same
way, verification confirms the bias instead of catching it. The gate reports
success precisely when it should be failing.

How to catch it: group corrections by domain, task type, reviewer and time. Do
the same for whatever your verification set is drawn from. Compare the two
distributions against the distribution of actual usage.

What to do: sample the verification set by usage rather than by convenience, and
track per-slice quality rather than one pooled number. A single aggregate metric
is exactly the thing that hides this.

### One reviewer becomes the policy

What it looks like: a single person approves everything, and their preferences
compound into rules. Nothing is wrong with any individual decision. The result
is a knowledge base encoding one person's taste as fact.

Why it happens: approval is the human atom, and it is usually one human.

How to catch it: this one is nearly invisible from inside, because there is no
disagreement signal to measure. The honest check is structural: count distinct
approvers. If it is one, you have this problem by construction, whether or not
it has bitten yet.

What to do: get a second reviewer on anything that changes behaviour broadly, and
record the reasoning on rejections rather than only on approvals. Rejections with
reasons are the only trace of what the policy is not.

### The easy cases get reviewed and the hard ones do not

What it looks like: reviewers work through the queue, and the queue drains from
the bottom. Ambiguous, long or unfamiliar cases are skipped and eventually
scroll away.

Why it matters: the system learns most from the cases nearest its competence
boundary. Reviewing only the easy ones teaches it what it already knew, while
the hard cases — the ones that would move quality — never enter the loop.

How to catch it: compare the characteristics of reviewed items against
unreviewed ones. Length, domain, confidence, time in queue. If reviewed items
are systematically shorter or more routine, you have it.

What to do: order the queue by value rather than by arrival, and track queue
age. An item that has waited a long time is usually one people are avoiding, and
that is a signal in itself.

### Synthetic feedback amplifies a biased seed

This is the most dangerous entry on the page, because it looks like the
solution to every problem above.

What it looks like: human feedback is scarce, so you bootstrap. A model
generates feedback, or judges output, or synthesizes training examples, using a
sample of human-reviewed cases as its seed. Volume increases enormously.
Coverage appears to be solved.

What actually happens: whatever bias was in the seed is now applied at scale and
with consistency no human would achieve. If the seed over-represented one
domain, the synthetic feedback confidently covers everything in that domain's
idiom. If the human reviewers shared a blind spot, the judge inherits it and
never disagrees with itself. The bias stops being noisy and becomes systematic,
which makes it much harder to detect — noise averages out, systematic error
compounds.

Two further traps sit inside this one. A model judging output produced by a
model of the same family tends to agree with it, so the judge is not independent
of the thing it judges. And once synthetic feedback outnumbers human feedback,
the human signal is statistically drowned even though it is still being
collected, so the check you think you have is not doing any work.

How to catch it: audit the seed before trusting anything downstream. What
sampled it, and against what distribution? Then hold out a genuinely human-only
slice that no synthetic process touched, and measure against that separately.
If synthetic and human evaluation ever disagree, believe the human set and go
find out why.

What to do: treat synthetic feedback as amplification, not as substitute. Keep
it clearly labelled in storage so it can be excluded from any measurement that
matters, and keep a fixed ratio of genuinely human judgements rather than
letting synthetic volume float free. Diversity in the seed matters more than
size of the seed.

## Self-reference

### The evaluation set becomes synthetic

What it looks like: validated output is used as ground truth for verifying
future versions. Over time, most validated output was itself produced by an
earlier version of the system.

Why it matters: the loop stops being anchored to anything external. Each version
is verified against the previous version's habits, so drift in a consistent
direction is never detected — it is the standard being measured against.

How to catch it: track the provenance of everything in your verification set.
What fraction traces to a human judgement that was not itself assisted by the
system?

What to do: keep a fixed reference set that is human-authored and never
regenerated, and re-check against it periodically even though it ages.

### Rubber-stamped validation becomes ground truth

What it looks like: output is marked correct quickly and without close reading.
That output then enters the verification set. Now an error is encoded as the
standard, and a future version that fixes the error fails the gate.

This is the nastiest inversion in the whole design: the verification mechanism
actively blocks a genuine improvement, with a green check mark.

How to catch it: sample your verification set and re-review it properly. Time
spent per validation is a crude but useful proxy — validations that took two
seconds deserve suspicion.

What to do: distinguish "checked carefully" from "not obviously wrong" at
record time, and only promote the former into verification data.

## Decay

### Knowledge goes stale and nothing notices

What it looks like: rules and skills that were right when written, and are now
wrong, because the source document changed, the API changed, or the policy
changed. Nothing in the loop is watching for this, because the loop is oriented
toward errors in new output rather than rot in old knowledge.

How to catch it: record a content hash for every registered source and re-check
it on a schedule. Track the age of every knowledge unit and the date of the
evidence behind it.

What to do: treat staleness as a detector that produces findings like any other,
so an outdated skill becomes a proposal through the normal path. In this repo
that is the `stale_source` detector, and its blind spot is worth stating: it
only covers sources that were registered with a baseline hash. Knowledge that
came from a conversation, or from a source nobody registered, has nothing to
compare against and will not be caught.

### The knowledge base only ever grows

What it looks like: every finding adds a rule. Nothing ever removes one. After a
year there are hundreds, the always-loaded context is enormous, and the
instructions have become a document nobody reads — which is the exact failure
the whole design was meant to avoid.

Why it happens: adding a rule has a clear justification and an obvious author.
Removing one requires arguing that something is no longer needed, which is
harder and thankless.

How to catch it: count active rules over time and measure the size of the
always-loaded context. Both should be roughly flat, not monotonically rising.

What to do: give knowledge units an expiry or a review date, and make retirement
a first-class proposal type rather than an afterthought. Scope-limited loading
helps with the symptom, but the underlying problem is that nothing prunes.

### Rules start contradicting each other

What it looks like: two rules added months apart, for good reasons, that give
opposing instructions in some situation nobody considered. The agent follows one
of them, unpredictably.

Why it happens: each rule is reviewed on its own merits against the evidence
that motivated it. Nothing reviews it against everything already in force.

How to catch it: this is hard to detect mechanically and is one of the better
uses of a model in the loop — periodically ask one to look for conflicting
guidance across the active set. Rising rule count with no retirements makes it
near certain.

What to do: check new proposals against the current active set at approval time,
not just against their own evidence. Consolidation passes that reconcile the
whole corpus catch what per-change review structurally cannot.

### The evidence is pruned and the rule survives

What it looks like: a rule with a provenance trail pointing at findings and
sessions that no longer exist, because retention policy deleted the telemetry
they lived in. The rule is still enforced. Why it exists is now unknowable.

Why it matters: the ability to answer "why does this say what it says" is the
main thing provenance buys, and retention silently removes it while leaving the
citation in place, so the trail looks intact until someone follows it.

How to catch it: periodically resolve provenance references and check they still
point at rows that exist.

What to do: when a proposal is approved, copy the evidence it depends on into
knowledge-side storage rather than referencing telemetry that is on a deletion
clock. Knowledge and telemetry need different retention, and this is the concrete
reason why.

## Gate failures

### Approval becomes a rubber stamp

What it looks like: proposals arrive faster than anyone can genuinely review
them, and the rejection rate approaches zero. The gate still exists in the
diagram.

How to catch it: rejection rate is the single most useful number here. A rate
near zero almost never means every proposal was good.

What to do: reduce volume rather than speed up review — deduplicate recurring
findings into single cases, batch related proposals, and put risk-scoring in
front of the queue so attention goes where it matters. Making review survivable
is the legitimate goal; making it faster per item mostly means making it
shallower.

### The gate gets so slow that people route around it

The opposite failure, and just as fatal. Proposals queue for weeks, so people
start editing the compiled files by hand. Now the files and the database
disagree, provenance is fiction, and the next compile silently reverts
everyone's work.

How to catch it: check for drift between compiled artifacts and what the
database says they should contain. Any difference means someone bypassed the
loop.

What to do: run that drift check automatically rather than trusting the
convention, and treat a growing proposal queue as an incident rather than a
backlog.

## Measurement failures

### You measure too early

Declaring victory on an underpowered sample. This repo did exactly this on its
first rule: identical-retry sessions went from 1.5 percent before to zero out of
sixty-four after. Directionally encouraging, statistically meaningless.

What to do: denominate verification windows in sessions rather than days, and
work out the sample size needed to detect the effect before running the test
rather than after.

### The metric improves and the problem does not

The classic form: a rule tells the agent not to retry identical calls, retry
findings drop to zero, and the underlying task still fails — the agent now gives
up instead of looping. The detector measured the symptom, and the symptom is
gone.

How to catch it: pair every detector with an outcome measure that is harder to
game. Alongside retry counts, track whether tasks completed.

What to do: when a finding disappears after a change, check that something good
replaced it rather than assuming.

### You cannot tell the change from everything else

The pattern shrank after the rule shipped. It also shrank because the underlying
model was upgraded that week and the workload shifted. With one timeline and no
control, attribution is guesswork.

What to do: keep prior versions serving a slice where the stakes allow it, since
versioned knowledge makes that a query rather than an architecture change. Where
that is not possible, record the confounders — model version, workload mix —
alongside the measurement, so at least the ambiguity is visible later.

## What this repo defends against today

Honest accounting, matching the status markers in
[the data flywheel](data-flywheel.md).

| Failure | Defence today |
|---|---|
| Nobody corrects anything | none automated; the cold-start playbook requires validating everything early |
| Only hearing about failures | partial: validation is recorded separately from rejection |
| Success starves the loop | none; correction volume per hundred sessions is queryable but nothing watches it |
| Signal from one corner | none; corrections can be grouped by domain manually |
| One reviewer becomes policy | none; single-operator by design so far |
| Easy cases reviewed, hard skipped | none; queue ordering by risk is planned (M12) |
| Synthetic feedback amplifies bias | none; the concern is documented, the controls are not built |
| Evaluation set becomes synthetic | none; the verification gate itself is not built (M13) |
| Rubber-stamped validation | none |
| Knowledge goes stale | partial: `stale_source` covers registered sources with a baseline hash |
| Knowledge only grows | partial: scoped compilation planned (M10); nothing prunes |
| Rules contradict each other | none; consolidation passes planned (M15) |
| Evidence pruned, rule survives | none; already observed after a schema reset |
| Approval becomes a rubber stamp | partial: rejection rate is queryable; nothing alerts |
| Gate too slow, people route around | planned: `compile --check` drift detection (M10) |
| Measuring too early | learned the hard way; session-denominated windows planned (M13) |
| Metric improves, problem does not | none |
| Cannot separate change from confounders | none; versioned knowledge makes A/B possible later |

The pattern in that table is worth stating plainly rather than leaving implicit.
The mechanical half of the loop is built and the signal-quality half is mostly
not. That is the normal order in which these systems get built, and it is also
the reason so many of them plateau: the mechanics are the visible engineering
problem, and the signal is what actually determines whether anything compounds.
