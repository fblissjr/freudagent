# freudagent
README Last updated: 2026-07-21

<p align="center">
  <a href="assets/theman-medium.png">
    <img src="assets/theman-medium.png" alt="freud agent logo" width="320">
  </a>
</p>

*Mostly a joke repo. The design underneath is not.*

Most sets of agent instructions go stale. Someone writes a really good
CLAUDE.md, it's accurate for a quarter, then the business changes and nobody
updates it. Exactly what happens to every data catalog anyone has ever bought.

This is a design for making the system keep them current, from evidence about
what actually happened, with a person approving every change. It runs inside
your agent harness — Claude Code, the Agent SDK — rather than wrapping it: the
harness orchestrates, this handles the data.

It's a design, not a finished product. [The data
flywheel](docs/data-flywheel.md) is the full version of everything below, and a
section near its end says which parts run today. "What isn't built yet" at the
bottom of this page is the short answer.

<img src="docs/assets/flywheel-tldr.svg" alt="An animated loop of six stages: ingest, analyze, propose, approve, compile, verify. A pulse travels the loop and each stage is explained in turn. Approve is marked as done by a person." width="100%">

Record what happened, find what repeats, propose a change, have a person approve
it, compile it into what the agent loads, and check it helped. Each of those is
below.

## What sits between your data and the agent

A layer of governed data. Not a prompt and not a config file — this design calls
it the grounding layer, because nothing else named it, and it has three faces.

<img src="docs/assets/grounding-layer.svg" alt="Raw material feeds a governed layer with constraints on both sides: left-hand constraints saying what the agent may and must do, grounding data in the middle, and right-hand constraints defining what good means. The agent reads from that layer and its results feed back in." width="100%">

Constraints on one side, saying what the agent may and must do. Checked
knowledge in the middle, with the evidence behind it and where it came from.
Constraints on the other side too, saying what good means and whether it was
achieved. That second set is the one most people never build, and skipping it is
why a lot of these systems never visibly improve — you can give an agent
excellent instructions and still have no way to tell whether it succeeded.

The unit inside all this is a skill. Not a single instruction — a hierarchy of
rules, code and references, of uneven depth. At the top, guidance about how this
kind of work breaks down. At the bottom, what a particular database field
actually means to your business, which of three date columns anyone means by
"closed", what your team counts as an active customer. That bottom layer is the
least glamorous part and the most reliably useful, because in real organizations
these systems fail on not knowing which column was meant, not on reasoning.

The agent doesn't get all of this at once. It gets the small part that always
applies, plus whatever matches the work in hand, and it opens the rest by name
when it needs it. The same holds one level down, for any subagent it spawns, and
for their subagents. Loading everything would make answers worse, not just more
expensive — a context window is attention rather than storage.

## Where the knowledge lives

A skill should live in two places at once. The artifact goes in git, where it's
diffable and it's the form the agent reads best. The metadata goes in a table:
version, identifier, which run created it, what changed and why. That split
isn't built here yet — the table still holds the skill's text along with its
metadata, and nothing compiles a skill out to a file.

That second half isn't bookkeeping. It's what lets you ask whether a skill's
evolution moved outcomes up or down, and what a change three months ago did to
results since. You can't ask that of a git history.

Whether any particular thing belongs in files, in a table, or in both is a real
question with real tradeoffs, and it depends on what the thing is. What isn't
negotiable is that wherever it lives, it's versioned and never edited in place.
Changes append. The previous version and the difference between them survive,
and every version ties back to the run that produced it and the evidence that
justified it.

## What actually happens

Six steps, looping.

The system records what it does — outputs, messages, tool calls, and the
reasoning behind them, kept as it arrives rather than summarized. Turning that
reasoning into a typed trail (this was a decision point, that was a dead end) is
a separate step and isn't built. Capture comes first because it's the part you
can't go back for: transcripts rotate, and a note saying reasoning existed
isn't reasoning.

Something scans that record for things that repeat. A field corrected the same
way twelve times. A source document that changed since anyone read it. A step
that keeps failing for one customer segment.

A pattern with enough behind it becomes a written proposal: change this rule,
add this instruction, retire this one. It links to the exact records that
justify it, so you can check the claim instead of trusting the summary.

A person reads it and says yes or no.

If yes, it becomes a new version and gets compiled into the files the agent
loads. The old version isn't overwritten, it's closed with a date.

Then you check whether it actually helped, against work you'd already judged
correct.

## What decides whether it works

The six steps are the easy half. They're the visible engineering. Build only
those and the system runs without improving.

What decides it is the quality of the signal going in, and there are two ways
that goes wrong.

**Nobody can give you useful feedback on a whole outcome.** Ask "was that good?"
and you learn it was bad and nothing else. No idea where it broke or why.

So the work gets broken down, and you ask people to judge at whatever level they
can actually answer confidently — then roll those judgments up to whatever level
the business cares about. The recording goes all the way to the bottom
regardless, because you can't aggregate detail you didn't keep. Only the asking
is tuned.

That breakdown isn't something someone authors up front. The agent does it while
it works, leaning on its skills and context to navigate, the same way a person
would. A trivial request doesn't break down at all — there's nothing to break
down, and forcing structure onto it would be invention. Recording the breakdown
as it happens is what gives you the why rather than just the what: which path it
chose, what it considered and discarded, where it changed its mind. The raw
material for that is captured here; structuring it into judgeable units isn't
built yet.

**Getting a model to generate feedback is the obvious fix and the fastest way to
break it.** Human review doesn't scale, so you seed a model with human-reviewed
examples and let it label the rest. This works, but only if the seed covers a
wide range.

If your human feedback is all from one corner, the model has two options on
everything else. Fall back on what it knows from pretraining, which isn't your
company's judgment and can't be audited. Or stretch the feedback it does have
onto material it was never about. Both produce labels that are confident,
consistent, and wrong.

Neither looks like a problem. Volume goes up, coverage looks solved, and the
errors are systematic rather than random — so they pile up instead of canceling
out.

The fix is boring and structural. Records are never edited; feedback is a
separate record pointing at the original, carrying what produced it. That means
two people can disagree about the same output without overwriting each other,
and you can pull the model-generated judgments out of any measurement that
matters. Keep a slice only people have judged, and measure against that
separately. When they disagree, believe the people.

And collect the seed deliberately. Left alone, review concentrates on whatever
is quickest to check, which is exactly the material the system already handles
fine. Something has to actively pick what a person gets shown, spread across
domains, customers and difficulty. The harness itself can be that interface —
pull the sample, show each item next to its source, capture the judgment, write
it back labeled. The review tool becomes one more thing built from the same
data rather than another application to maintain.

## Why a person approves

An agent that can write its own instructions can write instructions that load
into its own next session.

<img src="docs/assets/human-gate.svg" alt="An agent drafts a proposal, a person approves it, and it becomes a new version compiled into a file. A second path where the agent switches on a rule for itself is blocked." width="100%">

The fully automated version of this loop exists in the published research, and
it's reported to fail the way you'd expect — systems that learn to game their
own scoring, and edits to shared pieces that break things far from where the
edit happened. Those results come from papers we could only read as abstracts,
so treat them as the authors' claims rather than as settled.

So the gate goes in the tools, not in a policy document. The tools an agent can
call only ever produce drafts. Drafts don't compile, so they never load. The
approval step asks the person running the session.

That holds for tools that go through the gate. Anything else with write access —
a command line, a database client, a permission list that quietly grew — is a
separate problem.

The automation here is aimed at reducing how much a person has to look at. Never
at reducing how carefully they look. Those are different goals and only one of
them is safe.

## When the agent doesn't follow the guidance

If you record what the agent was told to do and what it actually did, the gap
between them is information — and it can indict either side.

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

## Is this different from writing better prompts?

The question assumes someone sits down and writes the instructions. Mostly, in
this design, nobody does.

Skills come out of the loop: what the agent actually did, the patterns detected
across those runs, and people's judgments on real work. A person approves
changes and corrects output. They rarely author a skill, and after the first
turn they mostly shouldn't — writing one by hand means guessing at what the
evidence would have told you, and the guess is what goes stale.

That changes three things.

It accumulates. Every change is a version with evidence attached, so the
knowledge base gets better over time instead of drifting. You can ask why a rule
exists and get an answer.

Maintenance has an owner. Human upkeep of written knowledge fails structurally
rather than through carelessness, in every organization that has tried it — so
the system does it, and people govern what changes rather than doing the
writing.

You can tell whether it's working. Correction rates per version, whether a
pattern actually shrank after you targeted it, how often proposals get rejected.
If nobody ever rejects a proposal, the gate isn't doing anything and you now
know that.

## Starting from nothing

On day one none of this exists — no runs to learn from, no evidence, no history.
This is the cold start problem and every deployment has it.

So the first turn is deliberately manual. Register your sources. Hand-write the
first rules and skills. Run the agent over them. Then put every single output in
front of a person, because nothing the system produced is trustworthy yet and
the first turn's job is to build a reference set rather than to save anyone
time.

That turn is the expensive one and it doesn't repeat. The mistake to avoid is
treating what comes out of it as truth just because the system produced it.

## What isn't built yet

The mechanical half of this exists and the signal half mostly doesn't.
Verification doesn't exist, so no change has ever been checked against work
already judged correct before shipping. Reasoning is captured now, but nothing
yet turns it into the structured trail the rest of the argument leans on. The
per-stage table in [the data flywheel](docs/data-flywheel.md) is the detailed
version.

There's also a real chance a chunk of this gets absorbed by better models.
Models improve by learning from inputs, outputs and the paths between them, not
from being told rules — which means the recorded data may end up mattering more
than the written guidance. If that's right, generic guidance gets absorbed and
what survives is what pretraining can't teach: your definitions, your policies,
your business rules.

That's a prediction you can check rather than a worry. Over time the surviving
instructions should look less like technique and more like your business. If
they don't, you're writing down things the model would have done anyway.

## Setup

A Python package with a command line interface and a DuckDB warehouse.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh

git clone https://github.com/fblissjr/freudagent.git
cd freudagent
uv sync --extra dev
```

## Try it

- [Cold start](docs/tutorial-cold-start.md) — day one, from an empty database to
  the first turn of the loop
- [Extraction](docs/tutorial-arxiv-extraction.md) — the full pipeline against a
  real document, with the reasoning behind each step
- [The feedback loop](docs/tutorial-flywheel.md) — review output, record
  corrections, then the governed path: detectors, proposal, approval, compile
- [RLM provider](docs/tutorial-rlm-provider.md) — wrapping a model in a Python
  loop for large inputs

## Reference

- [The data flywheel](docs/data-flywheel.md) — the full design, in detail. The
  source of truth for everything on this page
- [How data flywheels fail](docs/flywheel-failure-modes.md) — the ways this goes
  wrong, what each looks like, and how to catch it
- [CLI and commands](skill/skill.md)
- [Schema](skill/reference/schema.md) — every table, column and enum
- [Archetypes and presets](skill/reference/archetypes.md)
- [Progressive disclosure](skill/reference/retrieval-thesis.md) — why skills are
  something you look up rather than switch on
- [Roadmap](ROADMAP.md) — what scales, what breaks, in what order
- [Implementation plan](docs/implementation-plan.md) — milestones and definitions
  of done
- [Research review](docs/research-agent-data-representation.md) — the literature
  and production practice this design was checked against

Repository layout and conventions are in [CLAUDE.md](CLAUDE.md).

## Development

```bash
uv sync --extra dev
uv run pytest tests/
```

Requires Python 3.10+. Core dependencies are pydantic, duckdb and orjson.
Optional extras: `anthropic` for the Claude API, `local` for OpenAI-compatible
endpoints, `mcp` for the store-ops server.

## License

MIT
