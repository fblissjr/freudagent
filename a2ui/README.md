# a2ui — deprecated

Last updated: 2026-07-21

**This subproject is deprecated and unmaintained. Do not build on it.**

It is a visual-surface experiment: an MCP server plus a Lit client that rendered
A2UI surfaces over the warehouse. It has its own `pyproject.toml` and virtualenv
and is not part of this repo's package or test suite.

## Why it is deprecated

It was written against the pre-v0.17 schema and never migrated. `server.py` and
`queries.py` still assume integer ids and pre-v0.17 column names, both of which
stopped existing when the warehouse moved to SCD-2 dimensions and sha256/32
surrogate keys. Nothing in `tests/` exercises it, so nothing caught the drift.

Migrating it was on the backlog for a while. It is being retired instead,
because the direction it explored has a better answer: the review surface should
be the harness itself, not a separate application. An agent pulls a sample,
presents each item beside its source, captures the judgment, and writes it back
labeled — one more thing built from the same data rather than another web app to
keep in sync with the schema.

## What is kept, and why

The code stays in the tree rather than being deleted. It is the only worked
example of rendering warehouse rows into a visual surface, and `prompt.py` plus
`prompt_addendum.md` record how the surface was described to a model. If the
review-sampler work wants any of that, it is easier to read here than to
reconstruct from git history.

It carries no guarantee of running. Expect it not to.

## If you are reviving this

Do not migrate it in place. The schema moved twice underneath it. Read
`skill/reference/schema.md` for the current model and treat this as a reference
for the rendering approach only.
