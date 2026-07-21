# freudagent

<p align="center">
  <a href="assets/theman-medium.png">
    <img src="assets/theman-medium.png" alt="freud agent logo" width="320">
  </a>
</p>

Agent instructions go stale. Someone writes a good CLAUDE.md, it's accurate for
a quarter, then the business changes and nobody updates it.

This is a design for making the system keep them current from evidence about
what actually happened, with a person approving every change. It runs inside
your harness rather than wrapping it: the harness orchestrates, this handles the
data.

Mostly a joke repo. But the thesis is serious.

Last updated: 2026-07-21

<img src="docs/assets/flywheel-tldr.svg" alt="An animated loop of six stages: ingest, analyze, propose, approve, compile, verify. A pulse travels the loop and each stage is explained in turn. Approve is marked as done by a person." width="100%">

## Start here

- [How this works](docs/how-it-works.md) — the short version, about five
  minutes, no jargon
- [The data flywheel](docs/data-flywheel.md) — the full design, in detail. The
  source of truth for everything else here
- [How data flywheels fail](docs/flywheel-failure-modes.md) — twenty ways this
  goes wrong and how to catch each one

## Setup

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
