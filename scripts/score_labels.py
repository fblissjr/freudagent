#!/usr/bin/env python3
"""Score message labelers against a reference: the synthetic answer key or a
person's labels.

Two modes:

- Throwaway (default). Ingests the synthetic agent sessions, their answer key
  and the given label files into a temporary database through the real
  ingest, scores them, and deletes the database. The warehouse is never
  touched, and a label file that breaks the label contract shows up here as
  counted rejections.
- Warehouse (--db PATH). Scores the labels already in a warehouse, e.g. a
  model's labels against the owner's (--reference human:owner). Nothing is
  ingested.

Prints, per labeler and question:
- accuracy against the reference with a 95% Wilson interval, beside the
  majority-class baseline on the same replies
- for labelers that report probabilities: calibration (stated confidence
  against how often each bucket agreed with the reference, with intervals)
  and routing (the share auto-applied at a threshold, and its accuracy)
- for score questions: which level was taken for which

Each labeler's latest label per reply counts, the same rule the detectors
use. correction_kind is scored only where the reference answered it, which
for the synthetic key means replies it keys as corrections.

Usage (from the repo root):
    uv run python scripts/score_labels.py LABELS.jsonl[:QUESTIONS.jsonl] ...
    uv run python scripts/score_labels.py --db data/freudagent.duckdb --reference human:owner
"""

from __future__ import annotations

import argparse
import math
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from freud_schema.db import connect
from freud_schema.ingest import ingest_labels, ingest_transcripts
from freud_schema.store import ExperimentStore
from freud_schema.tables import FacetOutputType, LabelerKind

REPO_ROOT = Path(__file__).resolve().parent.parent
SYNTHETIC = REPO_ROOT / "data" / "synthetic"
DEFAULT_SESSIONS = SYNTHETIC / "agent_sessions"
DEFAULT_KEY = SYNTHETIC / "eval" / "exchange_labels.jsonl"
DEFAULT_QUESTIONS = SYNTHETIC / "eval" / "exchange_questions.jsonl"

QUESTION_ORDER = ["user_response", "correction_kind", "rule_violated", "frustration"]
THRESHOLDS = (0.6, 0.7, 0.8, 0.9)


def wilson(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion. Honest at small n, where
    the normal approximation claims certainty the data does not have."""
    if n == 0:
        return 0.0, 1.0
    p = hits / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def _order(facet_id: str) -> tuple[int, str]:
    return (QUESTION_ORDER.index(facet_id) if facet_id in QUESTION_ORDER else 99, facet_id)


def accuracy(pairs: list[dict]) -> list[dict]:
    """Per labeler and question: n, hits, accuracy, its interval, and the
    majority-class baseline computed on the same replies."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for p in pairs:
        groups[(p["labeler_kind"], p["labeler"], p["facet_id"])].append(p)
    out = []
    for (kind, labeler, facet), rows in groups.items():
        n = len(rows)
        hits = sum(1 for r in rows if r["hit"])
        lo, hi = wilson(hits, n)
        majority = Counter(r["reference_value"] for r in rows).most_common(1)[0][1] / n
        out.append({"labeler_kind": kind, "labeler": labeler, "facet_id": facet,
                    "n": n, "hits": hits, "accuracy": hits / n, "low": lo, "high": hi,
                    "majority": majority})
    return sorted(out, key=lambda r: (r["labeler_kind"], r["labeler"], _order(r["facet_id"])))


def calibration(pairs: list[dict], width: float = 0.1) -> list[dict]:
    """Per labeler, question and probability bucket: n, mean stated
    probability, observed agreement and its interval. Only labels that
    carry a probability take part."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for p in pairs:
        if p["probability"] is None:
            continue
        bucket = min(math.floor(p["probability"] / width) * width, 1 - width)
        groups[(p["labeler"], p["facet_id"], round(bucket, 6))].append(p)
    out = []
    for (labeler, facet, bucket), rows in groups.items():
        n = len(rows)
        hits = sum(1 for r in rows if r["hit"])
        lo, hi = wilson(hits, n)
        out.append({"labeler": labeler, "facet_id": facet, "bucket": bucket, "n": n,
                    "stated": sum(r["probability"] for r in rows) / n,
                    "observed": hits / n, "low": lo, "high": hi})
    return sorted(out, key=lambda r: (r["labeler"], _order(r["facet_id"]), r["bucket"]))


def routing(pairs: list[dict], thresholds=THRESHOLDS) -> list[dict]:
    """Per labeler, question and threshold: the share of replies at or above
    the threshold (applied automatically) and the accuracy of that share."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for p in pairs:
        if p["probability"] is not None:
            groups[(p["labeler"], p["facet_id"])].append(p)
    out = []
    for (labeler, facet), rows in groups.items():
        for t in thresholds:
            auto = [r for r in rows if r["probability"] >= t]
            hits = sum(1 for r in auto if r["hit"])
            out.append({"labeler": labeler, "facet_id": facet, "threshold": t,
                        "share": len(auto) / len(rows),
                        "accuracy": hits / len(auto) if auto else None,
                        "n": len(auto)})
    return sorted(out, key=lambda r: (r["labeler"], _order(r["facet_id"]), r["threshold"]))


def confusion(pairs: list[dict], facet_id: str) -> dict[tuple[str, str], Counter]:
    """(labeler_kind, labeler) -> Counter of (reference value, labeler value)."""
    out: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for p in pairs:
        if p["facet_id"] == facet_id:
            out[(p["labeler_kind"], p["labeler"])][(p["reference_value"], p["value"])] += 1
    return out


def _pct(x: float | None) -> str:
    return "-" if x is None else f"{x:.1%}"


def _level(v: str) -> str:
    """Score levels arrive as numeric text ("1.0"); show whole levels bare."""
    return v[:-2] if v.endswith(".0") else v


def report(store: ExperimentStore, reference_kind: LabelerKind,
           reference_labeler: str | None, out=sys.stdout) -> None:
    pairs = store.query_label_pairs(reference_kind, reference_labeler)
    ref = reference_kind.value + (f":{reference_labeler}" if reference_labeler else "")
    if not pairs:
        print(f"No labels overlap the reference ({ref}).", file=out)
        return

    print(f"\nAccuracy against {ref} (95% interval; majority class on the same replies)",
          file=out)
    print(f"{'labeler':<20}{'question':<17}{'n':>4}{'accuracy':>10}{'interval':>17}"
          f"{'majority':>10}", file=out)
    for r in accuracy(pairs):
        who = f"{r['labeler_kind']}:{r['labeler']}"
        interval = f"{r['low']:.0%}-{r['high']:.0%}"
        print(f"{who:<20}{r['facet_id']:<17}{r['n']:>4}{_pct(r['accuracy']):>10}"
              f"{interval:>17}{_pct(r['majority']):>10}", file=out)

    cal = calibration(pairs)
    if cal:
        print("\nCalibration: stated confidence against observed agreement", file=out)
        print(f"{'labeler':<14}{'question':<17}{'bucket':>8}{'n':>5}{'stated':>9}"
              f"{'observed':>10}{'interval':>13}", file=out)
        for r in cal:
            interval = f"{r['low']:.0%}-{r['high']:.0%}"
            print(f"{r['labeler']:<14}{r['facet_id']:<17}{r['bucket']:>7.1f}+{r['n']:>5}"
                  f"{_pct(r['stated']):>9}{_pct(r['observed']):>10}{interval:>13}", file=out)
        print("\nRouting: apply automatically at probability >= threshold", file=out)
        print(f"{'labeler':<14}{'question':<17}{'threshold':>10}{'auto share':>12}"
              f"{'n':>5}{'accuracy':>10}", file=out)
        for r in routing(pairs):
            print(f"{r['labeler']:<14}{r['facet_id']:<17}{r['threshold']:>10.2f}"
                  f"{_pct(r['share']):>12}{r['n']:>5}{_pct(r['accuracy']):>10}", file=out)

    score_questions = sorted(
        {p["facet_id"] for p in pairs}
        - {ft.facet_id for ft in store.list_facet_types()
           if ft.output_type != FacetOutputType.NUMERIC})
    for facet in score_questions:
        print(f"\n{facet}: reference level -> labeler level (counts)", file=out)
        for (kind, labeler), counts in sorted(confusion(pairs, facet).items()):
            cells = ", ".join(f"{_level(a)}->{_level(b)}: {n}"
                              for (a, b), n in sorted(counts.items()))
            print(f"  {kind}:{labeler}  {cells}", file=out)


def _parse_reference(raw: str) -> tuple[LabelerKind, str | None]:
    kind, _, labeler = raw.partition(":")
    return LabelerKind(kind), (labeler or None)


def main(argv: list[str] | None = None, out=sys.stdout) -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("labels", nargs="*",
                        help="label files to ingest, each optionally LABELS:QUESTIONS")
    parser.add_argument("--reference", default="key", type=_parse_reference,
                        help="key (default), or human:<labeler> to score against a person")
    parser.add_argument("--db", default=None,
                        help="score an existing warehouse instead; nothing is ingested")
    parser.add_argument("--sessions", default=str(DEFAULT_SESSIONS),
                        help="transcript root for throwaway mode (default: synthetic sessions)")
    parser.add_argument("--key", default=str(DEFAULT_KEY),
                        help="answer-key file for throwaway mode ('' to skip)")
    parser.add_argument("--key-questions", default=str(DEFAULT_QUESTIONS))
    args = parser.parse_args(argv)
    reference_kind, reference_labeler = args.reference

    if args.db:
        if args.labels:
            parser.error("--db scores what the warehouse holds; ingest files with "
                         "`freud-schema ingest labels` first")
        with ExperimentStore(connect(args.db)) as store:
            report(store, reference_kind, reference_labeler, out)
        return

    with tempfile.TemporaryDirectory() as tmp, \
            ExperimentStore(connect(str(Path(tmp) / "score.duckdb"))) as store:
        ingest_transcripts(store, root=args.sessions)
        sources = ([f"{args.key}:{args.key_questions}"] if args.key else []) + args.labels
        for spec in sources:
            path, _, questions = spec.partition(":")
            stats = ingest_labels(store, path=path, questions=questions or None)
            rejected = ", ".join(f"{k} {v}" for k, v in stats["rejected"].items()) or "none"
            print(f"{Path(path).name}: {stats['rows_read']} read, "
                  f"{stats['rows_written']} written, rejected: {rejected}", file=out)
        report(store, reference_kind, reference_labeler, out)


if __name__ == "__main__":
    main()
