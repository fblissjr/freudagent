"""Guards on the citation-graph builder (scripts/build_citation_graph.py).

The builder scans the whole committed corpus -- generated and hand-authored
files alike -- and extracts mentions of corpus identifiers into an edge list.
Its eval value is that the closed-set references it discovers actually resolve:
every account/employee cited in STRUCTURED data is a real row. Free text may
cite planned/external/illustrative ids (the spec's own carve-out) -- e.g. a
runbook that shows a ticket-title format with a hypothetical future hire -- so
the strict closed-set guarantee is scoped to non-prose sources, and any
unresolved id is asserted to live only in hand-authored prose. The incident-web
spot checks pin the anchor edges the README promises.
"""

import csv
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS = REPO_ROOT / "data" / "synthetic"
BUILDER = REPO_ROOT / "scripts" / "build_citation_graph.py"

# Hand-authored free text may carry illustrative/placeholder ids; structured
# extracts (CSV/JSONL/JSON/SQL/XML) are the closed-set producers that must join.
_PROSE_SUFFIXES = (".md", ".txt", ".html", ".eml")


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_citation_graph", BUILDER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def edges() -> list[dict]:
    return _load_builder().build(CORPUS)


def _is_prose(from_path: str) -> bool:
    return from_path.endswith(_PROSE_SUFFIXES)


def test_builder_produces_edges(edges):
    assert edges, "no citation edges produced"
    # Every edge is well-formed and globally sorted by (from_path, to_id).
    keys = [(e["from_path"], e["to_id"]) for e in edges]
    assert keys == sorted(keys)
    for e in edges:
        assert e["from_path"].startswith("data/synthetic/")
        assert e["mention_count"] >= 1


def test_account_edges_resolve(edges):
    """Every ACCT-#### cited in structured data resolves to a real account,
    and any unresolved account citation lives only in prose."""
    account_ids = {r["account_id"]
                   for r in _csv(CORPUS / "saas" / "crm" / "accounts.csv")}
    account_edges = [e for e in edges if e["id_type"] == "account"]
    assert account_edges, "no account citations found"

    structured = {e["to_id"] for e in account_edges if not _is_prose(e["from_path"])}
    assert structured, "no structured account citations"
    assert structured <= account_ids, structured - account_ids

    unresolved = {e["to_id"] for e in account_edges} - account_ids
    for e in account_edges:
        if e["to_id"] in unresolved:
            assert _is_prose(e["from_path"]), (e["to_id"], e["from_path"])


def test_employee_edges_resolve(edges):
    """Every EMP-#### cited in structured data resolves to a real employee,
    and any unresolved employee citation lives only in prose (e.g. a runbook's
    hypothetical onboarding example)."""
    employee_ids = {r["employee_id"]
                    for r in _csv(CORPUS / "internal" / "hris" / "employees.csv")}
    emp_edges = [e for e in edges if e["id_type"] == "employee"]
    assert emp_edges, "no employee citations found"

    structured = {e["to_id"] for e in emp_edges if not _is_prose(e["from_path"])}
    assert structured, "no structured employee citations"
    assert structured <= employee_ids, structured - employee_ids

    unresolved = {e["to_id"] for e in emp_edges} - employee_ids
    for e in emp_edges:
        if e["to_id"] in unresolved:
            assert _is_prose(e["from_path"]), (e["to_id"], e["from_path"])


def test_incident_web_anchor_edges(edges):
    """The 2026-03-11 incident web is cited somewhere in the corpus."""
    cited = {e["to_id"] for e in edges}
    for anchor in ("ACME-231", "SUP-1042", "INV-202603-0063", "CHG-2026-0023"):
        assert anchor in cited, anchor
