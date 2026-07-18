#!/usr/bin/env python3
"""Citation-graph builder for the public synthetic corpus (data/synthetic/).

Scans every text file in the committed corpus -- including the hand-authored
documents that the deterministic generator never touches -- and extracts
mentions of corpus identifiers (issues, tickets, invoices, changes, incidents,
employees, accounts, POs, assets). The result is an edge list mapping each
source file to the IDs it cites, emitted to data/synthetic/eval/citation_edges.csv.

This lives OUTSIDE generate() on purpose: it must read files that are authored
by hand and cross-reference generated IDs, so it cannot run inside the tmp-dir
determinism path. It is deterministic (no wall-clock, no rng): the same corpus
always yields the same edges in the same order.

Usage:
    uv run python scripts/build_citation_graph.py [--corpus DIR]
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

# id_type -> compiled word-boundary pattern. id_types are disjoint by prefix,
# so a given to_id resolves to exactly one type.
_ID_PATTERNS = {
    "issue": re.compile(r"\b(?:ACME|DATA)-\d+\b"),
    "ticket": re.compile(r"\bSUP-\d+\b"),
    "it_ticket": re.compile(r"\bIT-\d+\b"),
    "invoice": re.compile(r"\bINV-\d{6}-\d{4}\b"),
    "change": re.compile(r"\bCHG-\d{4}-\d{4}\b"),
    "incident": re.compile(r"\bINC-\d{4}-\d{4}\b"),
    "employee": re.compile(r"\bEMP-\d+\b"),
    "account": re.compile(r"\bACCT-\d+\b"),
    "purchase_order": re.compile(r"\bPO-\d{4}-\d+\b"),
    "asset": re.compile(r"\bAST-\d+\b"),
}

_SCAN_SUFFIXES = {".md", ".txt", ".json", ".jsonl", ".csv", ".sql", ".xml",
                  ".ics", ".html", ".eml", ".log"}

# Never scan the manifest or the graph's own output.
_EXCLUDE_RELPOSIX = {"MANIFEST.json", "eval/citation_edges.csv"}


def build(corpus_dir: Path) -> list[dict]:
    """Return the citation edge list: one dict per (from_path, to_id) with a
    mention_count. from_path is repo-relative posix (e.g. data/synthetic/...).
    Ordering is deterministic: sorted by from_path, then to_id."""
    corpus_dir = corpus_dir.resolve()
    repo_root = corpus_dir.parents[1]

    edges: list[dict] = []
    for path in sorted(corpus_dir.rglob("*")):
        if not path.is_file() or path.suffix not in _SCAN_SUFFIXES:
            continue
        rel = path.relative_to(corpus_dir).as_posix()
        if rel in _EXCLUDE_RELPOSIX:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        from_path = path.relative_to(repo_root).as_posix()

        # (to_id, id_type) -> count within this file.
        counts: dict[tuple[str, str], int] = {}
        for id_type, pattern in _ID_PATTERNS.items():
            for match in pattern.findall(text):
                counts[(match, id_type)] = counts.get((match, id_type), 0) + 1

        for (to_id, id_type), count in counts.items():
            edges.append({
                "from_path": from_path,
                "to_id": to_id,
                "id_type": id_type,
                "mention_count": count,
            })

    edges.sort(key=lambda e: (e["from_path"], e["to_id"]))
    return edges


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus", type=Path,
        default=repo_root / "data" / "synthetic",
        help="corpus directory to scan (default: data/synthetic)")
    args = parser.parse_args()

    edges = build(args.corpus)
    out = args.corpus / "eval" / "citation_edges.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["from_path", "to_id", "id_type", "mention_count"])
        for e in edges:
            w.writerow([e["from_path"], e["to_id"], e["id_type"],
                        e["mention_count"]])
    print(f"wrote {len(edges)} citation edges to "
          f"{out.relative_to(repo_root).as_posix()}")


if __name__ == "__main__":
    main()
