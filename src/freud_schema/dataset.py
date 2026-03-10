"""Load and query the Freud Schema dataset."""

from __future__ import annotations

from pathlib import Path

from freud_schema.models import FreudEntry

_DATA_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "freud_schema.jsonl"


def load_entries(path: Path | None = None) -> list[FreudEntry]:
    """Load all FreudEntry records from the JSONL data file."""
    p = path or _DATA_FILE
    entries: list[FreudEntry] = []
    with open(p) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(FreudEntry.model_validate_json(line))
    return entries


def filter_by_topic(entries: list[FreudEntry], topic: str) -> list[FreudEntry]:
    """Return entries whose core_topic contains the given substring (case-insensitive)."""
    topic_lower = topic.lower()
    return [e for e in entries if topic_lower in e.core_topic.lower()]


def filter_by_book(entries: list[FreudEntry], book: str) -> list[FreudEntry]:
    """Return entries whose book_title contains the given substring (case-insensitive)."""
    book_lower = book.lower()
    return [e for e in entries if book_lower in e.book_title.lower()]


def search_terminology(entries: list[FreudEntry], term: str) -> list[FreudEntry]:
    """Return entries that reference the given term in key_terminology."""
    term_lower = term.lower()
    return [
        e for e in entries
        if any(term_lower in t.lower() for t in e.key_terminology)
    ]


def search_text(entries: list[FreudEntry], query: str) -> list[FreudEntry]:
    """Full-text search across major_finding, crucial_quote, and source_context."""
    q = query.lower()
    return [
        e for e in entries
        if q in e.major_finding.lower()
        or q in e.crucial_quote.lower()
        or q in e.source_context.lower()
    ]


def list_topics(entries: list[FreudEntry]) -> list[str]:
    """Return a sorted list of unique core topics."""
    return sorted({e.core_topic for e in entries})


def list_books(entries: list[FreudEntry]) -> list[str]:
    """Return a sorted list of unique book titles."""
    return sorted({e.book_title for e in entries})


def to_jsonl(entries: list[FreudEntry]) -> str:
    """Serialize entries back to JSONL format."""
    return "\n".join(e.model_dump_json() for e in entries) + "\n"
