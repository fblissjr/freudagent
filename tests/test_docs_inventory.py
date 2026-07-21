"""Agent-facing reference docs must match the code they describe.

`docs/` describes what should be true -- it is a design, and the status section
says what is built. `skill/` and `.claude/` are a different contract: an agent
loads them and acts on them without checking, so they describe what IS true.
There is no aspirational mode available in this half of the repo.

Everything here guards one failure: a fact stated in both code and a doc, then
updated only in the code. That is not hypothetical. The v0.23 MD5 -> sha256/32
migration left `skill/reference/trace-capture.md` computing keys with `md5()`,
so an agent following it wrote rows keyed against nothing the store computes --
silently, with no error at write time. And that was a KNOWN failure mode:
`docs/implementation-plan.md` named this exact drift on 2026-07-09 ("the couch
skill's key recipe still saying md5"), fixed one file, and missed the other.
The careful manual sweep has already been tried and it does not hold.

So these assertions are deliberately mechanical. They do not check that prose is
good, only that no identifier the code defines has gone missing from the doc an
agent reads to find it, and that no doc names something the code does not have.
"""

from __future__ import annotations

import enum
import re
import subprocess
from pathlib import Path

import pytest

from freud_schema import tables
from freud_schema.db import ALL_TABLES, ALL_VIEWS

REPO_ROOT = Path(__file__).resolve().parent.parent

SCHEMA_DOC = REPO_ROOT / "skill" / "reference" / "schema.md"
DB_QUERY_DOC = REPO_ROOT / ".claude" / "skills" / "db-query.md"

# Both files are inventories an agent consults to find out what exists.
INVENTORY_DOCS = (SCHEMA_DOC, DB_QUERY_DOC)


def _read(path: Path) -> str:
    assert path.exists(), f"{path.relative_to(REPO_ROOT)} is missing"
    return path.read_text(encoding="utf-8")


def _enum_classes() -> list[type[enum.Enum]]:
    """Every enum in tables.py -- the single source of truth for vocabularies."""
    return [
        obj
        for obj in vars(tables).values()
        if isinstance(obj, type) and issubclass(obj, enum.Enum) and obj is not enum.Enum
    ]


@pytest.mark.parametrize("doc", INVENTORY_DOCS, ids=lambda p: p.name)
def test_every_view_is_documented(doc: Path) -> None:
    """A view missing from the docs is tooling an agent cannot find.

    The four couch views went undocumented in schema.md for four releases. An
    agent asked to find retry loops read the reference, saw no view for it, and
    would either hand-roll the aggregation against fact_tool_use -- diverging
    from the thresholds in couch.py -- or report the data was not there.
    """
    text = _read(doc)
    missing = sorted(v for v in ALL_VIEWS if v not in text)
    assert not missing, (
        f"{doc.relative_to(REPO_ROOT)} does not mention {len(missing)} view(s) "
        f"that exist in ALL_VIEWS: {missing}. Add them, or an agent reading this "
        f"file cannot discover them."
    )


@pytest.mark.parametrize("doc", INVENTORY_DOCS, ids=lambda p: p.name)
def test_no_view_is_invented(doc: Path) -> None:
    """The reverse drift: a doc promising a view that was renamed or dropped."""
    named = set(re.findall(r"\bv_[a-z0-9_]+\b", _read(doc)))
    unknown = sorted(named - set(ALL_VIEWS))
    assert not unknown, (
        f"{doc.relative_to(REPO_ROOT)} names view(s) that do not exist in "
        f"ALL_VIEWS: {unknown}. An agent will write a query against them and it "
        f"will fail at runtime."
    )


def test_every_table_is_documented() -> None:
    """schema.md is the table reference; a table absent from it is invisible."""
    text = _read(SCHEMA_DOC)
    missing = sorted(t for t in ALL_TABLES if t not in text)
    assert not missing, (
        f"skill/reference/schema.md does not mention {len(missing)} table(s) "
        f"registered in ALL_TABLES: {missing}."
    )


@pytest.mark.parametrize("doc", INVENTORY_DOCS, ids=lambda p: p.name)
def test_every_record_source_is_documented(doc: Path) -> None:
    """An incomplete record_source list produces silently wrong answers.

    This is the worst shape of drift here, because nothing raises. `event_ingest`
    was missing from both files while being the value every row from
    `ingest events` carries. An agent writing a lineage filter from the
    documented list excludes the entire generic event grain and returns a
    confident, complete-looking, wrong result.
    """
    values = [m.value for m in tables.RecordSource]
    text = _read(doc)

    # Checking "appears anywhere in the file" is too weak: a doc can list every
    # value in one table and still carry a truncated list somewhere else, which
    # is exactly how event_ingest went missing from the lineage envelope while
    # being present in the enum table two hundred lines away. Check each passage
    # that enumerates the vocabulary, not the file as a whole.
    # Flatten first: these lists are prose and wrap across lines, so a per-line
    # scan silently passes a truncated list that happens to break mid-sentence.
    flat = " ".join(text.split())
    enumerating = [
        window
        for m in re.finditer(r"record_source", flat)
        if sum(v in (window := flat[m.start() : m.start() + 260]) for v in values) >= 2
    ]
    assert enumerating, (
        f"{doc.relative_to(REPO_ROOT)} no longer enumerates record_source values "
        f"anywhere. If that list moved, point this test at its new home."
    )

    for line in enumerating:
        missing = sorted(v for v in values if v not in line)
        assert not missing, (
            f"{doc.relative_to(REPO_ROOT)} enumerates record_source values but "
            f"omits {missing}:\n  {line.strip()}\n"
            f"A filter built from this list silently drops those rows -- nothing "
            f"raises, the answer just comes back wrong and complete-looking."
        )


def test_every_enum_value_is_documented() -> None:
    """Enum members back CHECK constraints; an undocumented one looks invalid.

    CLAUDE.md states schema.md's Enum Values table must list every column with a
    CHECK constraint. This asserts the values themselves are present, which is
    the part an agent needs in order to write a valid row or a correct filter.
    """
    text = _read(SCHEMA_DOC)
    missing: dict[str, list[str]] = {}
    for cls in _enum_classes():
        absent = sorted(m.value for m in cls if m.value not in text)
        if absent:
            missing[cls.__name__] = absent
    assert not missing, (
        f"skill/reference/schema.md omits enum value(s) defined in tables.py: "
        f"{missing}. An agent cannot tell a valid value from an invalid one."
    )


def test_claude_md_map_names_every_directory_and_root_doc() -> None:
    """CLAUDE.md's repo map must be exhaustive where absence misleads.

    A map is selective by design -- naming all 21 test files would be noise, not
    accuracy. But that only works if the reader can tell selection from
    completeness. `.claude/agents/` was missing while `.claude/rules/` was
    listed, so the map implied the directory did not exist, and the delegation
    rule that routes work to those agents had no visible target.

    So the rule is: exhaustive at the level where absence is a wrong signal
    (directories, root documents), selective below it. This asserts the first
    half only. The second half is a judgment call and should not be frozen into
    an assertion.

    Config files (.gitignore, uv.lock, pyproject.toml) are deliberately exempt:
    they are conventional, and nobody concludes anything from their absence.
    """
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout.splitlines()

    directories = sorted({p.split("/")[0] + "/" for p in tracked if "/" in p})
    claude_subdirs = sorted({
        "/".join(p.split("/")[:2]) + "/"
        for p in tracked
        if p.startswith(".claude/") and p.count("/") > 1
    })
    root_docs = sorted(
        p for p in tracked
        if "/" not in p and p.endswith(".md") and p != "CLAUDE.md"
    )

    text = _read(REPO_ROOT / "CLAUDE.md")
    required = directories + claude_subdirs + root_docs
    missing = [
        name for name in required
        if name.rstrip("/").split("/")[-1] not in text
    ]
    assert not missing, (
        f"CLAUDE.md's repo map does not name {missing}. A reader takes absence "
        f"from the map as absence from the repo -- add an entry, or the next "
        f"person concludes it does not exist."
    )


def test_registry_dimensions_are_all_named_together() -> None:
    """The registry dims are a stated pattern; a partial list is a wrong rule.

    An agent reasoning about which dimensions are append-only registries versus
    SCD-2 needs the complete set. `dim_event_type` was documented in its own
    section but missing from the list that states the pattern, which yields a
    wrong general rule rather than a lookup failure.
    """
    registry_dims = [
        "dim_tenant",
        "dim_project",
        "dim_facet_type",
        "dim_finding_type",
        "dim_event_type",
    ]
    for name in registry_dims:
        assert name in ALL_TABLES, (
            f"{name} is no longer in ALL_TABLES -- update this test's expected "
            f"registry set, it is now out of date with the schema."
        )

    text = _read(SCHEMA_DOC)
    # Find the passage that enumerates registry dimensions and check it is whole.
    for match in re.finditer(r"[Rr]egistry dimensions?[^\n]*\n?[^\n]*", text):
        passage = match.group(0)
        if sum(d in passage for d in registry_dims) < 2:
            continue  # not the enumerating passage
        missing = [d for d in registry_dims if d not in passage]
        assert not missing, (
            f"schema.md's registry-dimension list omits {missing}. A partial "
            f"list here becomes a wrong rule about which dims are SCD-2."
        )
