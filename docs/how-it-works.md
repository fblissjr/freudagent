# How this works

Last updated: 2026-07-21

Every set of agent instructions goes stale. Someone writes a really good
CLAUDE.md, it's accurate for a quarter, then the business changes and nobody
updates it. Exactly what happens to every data catalog anyone has ever bought.

This is a design for making the system keep its own instructions current, from
evidence about what actually happened, with a person approving every change.

That's the whole idea. The rest of this page is how.

<img src="assets/flywheel-tldr.svg" alt="An animated loop of six stages: ingest, analyze, propose, approve, compile, verify. A pulse travels the loop and each stage is explained in turn. Approve is marked as done by a person." width="100%">

## The move

Don't keep the agent's instructions in a file someone edits. Keep them in a
database as versioned rows, and build the files from the rows.

The agent still reads files — that's what agents are good at. But those files
are build output, the way a binary is build output. Changing what the agent does
means changing a row.

That sounds like a small distinction. It isn't, because a row comes with things
a file doesn't:

- who changed it and when
- what it said before, and the difference
- which evidence justified the change
- which runs used which version, so you can ask whether it helped

You can't get any of that from a file someone edited last March.

## What actually happens

Six steps, looping.

The system records everything it does — not just outputs, but the reasoning:
what it tried, what it discarded, where it changed approach.

Something scans that record for things that repeat. A field corrected the same
way twelve times. A source document that changed since anyone read it. A step
that keeps failing for one customer segment.

A pattern with enough behind it becomes a written proposal: change this rule,
add this instruction, retire this one. It links to the exact records that
justify it, so you can check the claim instead of trusting the summary.

A person reads it and says yes or no.

If yes, it becomes a new version and gets compiled into the files the agent
loads. The old version doesn't get overwritten, it gets closed with a date.

Then you check whether it actually helped, against work you'd already judged
correct.

## The part everyone gets wrong

The six steps are the easy half. They're the visible engineering. Most teams
build them, and most of those systems still don't improve.

What decides it is the quality of the signal going in, and there are two ways
that goes wrong.

**Nobody can give you useful feedback on a whole outcome.** If you ask "was that
good?", you learn it was bad and nothing else. No idea where it broke or why.

So the work gets broken down as far as it goes, and you ask people to judge at
whatever level they can actually answer confidently — then roll those judgements
up to whatever level the business cares about. The recording goes all the way to
the bottom regardless, because you can't aggregate detail you didn't keep. Only
the asking is tuned.

**Getting a model to generate feedback is the obvious fix and the fastest way to
break it.** Human review doesn't scale, so you seed a model with human-reviewed
examples and let it label the rest. This works, but only if the seed covers a
wide range.

If your human feedback is all from one corner, the model has two options on
everything else. Fall back on what it knows from pretraining, which isn't your
company's judgement and can't be audited. Or stretch the feedback it does have
onto material it was never about. Both produce labels that are confident,
consistent, and wrong.

Neither looks like a problem. Volume goes up, coverage looks solved, and the
errors are systematic rather than random — so they pile up instead of cancelling
out.

The fix is boring and structural. Label every piece of feedback with what
produced it, so you can pull the model-generated ones out of any measurement
that matters. Keep a slice only people have judged, and measure against that
separately. When they disagree, believe the people.

And collect the seed deliberately. Left alone, review concentrates on whatever
is quickest to check, which is exactly the stuff the system already handles
fine. Something has to actively pick what a person gets shown.

## Why a person has to approve

<img src="assets/human-gate.svg" alt="An agent drafts a proposal, a person approves it, and it becomes a new version compiled into a file. A second path where the agent switches on a rule for itself is blocked." width="100%">

An agent that can write its own instructions can write instructions that load
into its own next session. The fully automated version of this loop exists in
the published research, and it fails the way you'd expect — systems that learn
to game their own scoring, and edits to shared pieces that break things far away
from where the edit happened.

So the gate goes in the tools, not in a policy document. The tools an agent can
call only ever produce drafts. Drafts don't compile, so they never load. The
approval step asks the person running the session.

Worth being honest about the limit: that holds for tools that go through the
gate. Anything else with write access — a command line, a database client, a
permission list that quietly grew — is a separate problem.

The automation here is aimed at reducing how much a person has to look at. Never
at reducing how carefully they look. Those are different goals and only one of
them is safe.

## The thing that surprised us

If you record what the agent was told to do and what it actually did, the gap
between them is information — and it runs both ways.

The agent departs from the guidance and does worse: the guidance was right.

The agent departs from the guidance and gets there faster with the same result:
the guidance was wrong, and the agent found out.

That second one flips what the loop is for. It's not just people writing rules
and the system catching the agent breaking them. It's also the system catching
the rules being wrong.

It only works if you can measure the outcome, though. Otherwise you can't tell a
real shortcut from a corner cut, and you'll promote the corner cut, because in
the short run they look the same. Worse: some steps exist to prevent something
rare, and skipping those looks better every single time until the rare thing
happens.

## Is this actually different from writing better prompts?

Fair question. Three things make it different.

It accumulates. Every change is a version with evidence attached, so the
knowledge base gets better over time instead of drifting. You can ask why a rule
exists and get an answer.

It's maintained by the system, not by you. That's the entire point. Human
maintenance of knowledge fails structurally, in every organisation that's tried
it, and betting against that pattern hasn't worked for anyone yet.

You can tell whether it's working. Correction rates per version, whether a
pattern actually shrank after you targeted it, how often proposals get rejected.
If nobody ever rejects a proposal, the gate isn't doing anything and you now
know that.

## What we can't tell you yet

The honest version: the mechanical half of this is built and the signal half
mostly isn't. Verification doesn't exist. The loop has run end to end once.

There's also a real chance a chunk of this gets absorbed by better models.
Models improve by learning from inputs, outputs and the paths between them, not
from being told rules — which means the recorded data may end up mattering more
than the written guidance. If that's right, generic guidance gets absorbed and
what survives is what pretraining can't teach: your definitions, your policies,
your business rules.

That's a prediction you can check rather than a worry. Over time the surviving
instructions should look less like technique and more like your business. If
they don't, you're writing down things the model would have done anyway.

## Go deeper

- [The data flywheel](data-flywheel.md) — the full design, in detail. This page
  is the short version of that one.
- [How data flywheels fail](flywheel-failure-modes.md) — twenty ways this goes
  wrong, what each looks like, and how to catch it
- [Cold-start tutorial](tutorial-cold-start.md) — day one, from an empty
  database to the first turn
- [Feedback tutorial](tutorial-flywheel.md) — the loop as actual commands
