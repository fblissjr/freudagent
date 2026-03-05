"""Command-line interface for querying the Freud Schema dataset and generating agent prompts."""

from __future__ import annotations

import argparse
import json
import sys

from freud_schema.archetypes import (
    ARCHETYPES,
    get_archetype,
    get_by_category,
    list_archetype_names,
    search_archetypes,
)
from freud_schema.dataset import (
    filter_by_book,
    filter_by_topic,
    list_books,
    list_topics,
    load_entries,
    search_terminology,
    search_text,
)
from freud_schema.harness import PRESETS, compose_preset, compose_system_prompt
from freud_schema.models import ArchetypeCategory, FreudEntry


def _print_entry(entry: FreudEntry, verbose: bool = False) -> None:
    print(f"  Book:    {entry.book_title}")
    print(f"  Chapter: {entry.chapter_section}")
    print(f"  Topic:   {entry.core_topic}")
    print(f"  Finding: {entry.major_finding}")
    print(f"  Quote:   \"{entry.crucial_quote}\"")
    if verbose:
        print(f"  Terms:   {', '.join(entry.key_terminology)}")
        print(f"  Context: {entry.source_context}")
        print(f"  Translation: {entry.translation_notes}")
    print()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="freud-schema",
        description="Query the Freud Schema dataset and generate agent prompts",
    )
    sub = parser.add_subparsers(dest="command")

    # --- Data commands ---
    sub.add_parser("list-topics", help="List all core topics")
    sub.add_parser("list-books", help="List all book titles")

    p_topic = sub.add_parser("topic", help="Filter entries by core topic")
    p_topic.add_argument("query", help="Substring to match in core_topic")
    p_topic.add_argument("-v", "--verbose", action="store_true")

    p_book = sub.add_parser("book", help="Filter entries by book title")
    p_book.add_argument("query", help="Substring to match in book_title")
    p_book.add_argument("-v", "--verbose", action="store_true")

    p_term = sub.add_parser("term", help="Search key terminology")
    p_term.add_argument("query", help="Term to search for")
    p_term.add_argument("-v", "--verbose", action="store_true")

    p_search = sub.add_parser("search", help="Full-text search across findings, quotes, and source context")
    p_search.add_argument("query", help="Text to search for")
    p_search.add_argument("-v", "--verbose", action="store_true")

    p_show = sub.add_parser("show", help="Show all entries")
    p_show.add_argument("-v", "--verbose", action="store_true")

    sub.add_parser("export", help="Export all entries as JSON array")

    # --- Archetype commands ---
    sub.add_parser("list-archetypes", help="List all agentic archetypes")

    p_archetype = sub.add_parser("archetype", help="Show details of a specific archetype")
    p_archetype.add_argument("name", help="Archetype name (e.g. structural-triad)")

    p_arch_search = sub.add_parser("search-archetypes", help="Search archetypes by keyword")
    p_arch_search.add_argument("query", help="Keyword to search for")

    # --- Harness commands ---
    sub.add_parser("list-presets", help="List available prompt presets")

    p_prompt = sub.add_parser("prompt", help="Generate a system prompt from archetypes")
    p_prompt.add_argument(
        "archetypes", nargs="*",
        help="Archetype names to include (or use --preset)",
    )
    p_prompt.add_argument("--preset", help="Use a named preset instead")
    p_prompt.add_argument("--task", default="", help="Task context to include")

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        sys.exit(1)

    # --- Data commands ---
    if args.command in ("list-topics", "list-books", "topic", "book", "term",
                        "search", "show", "export"):
        entries = load_entries()

        if args.command == "list-topics":
            for t in list_topics(entries):
                print(f"  - {t}")
        elif args.command == "list-books":
            for b in list_books(entries):
                print(f"  - {b}")
        elif args.command == "topic":
            results = filter_by_topic(entries, args.query)
            print(f"Found {len(results)} entries for topic '{args.query}':\n")
            for e in results:
                _print_entry(e, args.verbose)
        elif args.command == "book":
            results = filter_by_book(entries, args.query)
            print(f"Found {len(results)} entries for book '{args.query}':\n")
            for e in results:
                _print_entry(e, args.verbose)
        elif args.command == "term":
            results = search_terminology(entries, args.query)
            print(f"Found {len(results)} entries for term '{args.query}':\n")
            for e in results:
                _print_entry(e, args.verbose)
        elif args.command == "search":
            results = search_text(entries, args.query)
            print(f"Found {len(results)} entries matching '{args.query}':\n")
            for e in results:
                _print_entry(e, args.verbose)
        elif args.command == "show":
            print(f"All {len(entries)} entries:\n")
            for e in entries:
                _print_entry(e, args.verbose)
        elif args.command == "export":
            data = [e.model_dump() for e in entries]
            print(json.dumps(data, indent=2, ensure_ascii=False))

    # --- Archetype commands ---
    elif args.command == "list-archetypes":
        for a in ARCHETYPES:
            print(f"  {a.name:25s} [{a.category.value}]  {a.freudian_concept}")

    elif args.command == "archetype":
        a = get_archetype(args.name)
        if a is None:
            print(f"Unknown archetype: {args.name}", file=sys.stderr)
            sys.exit(1)
        print(f"  Name:      {a.name}")
        print(f"  Concept:   {a.freudian_concept}")
        print(f"  Category:  {a.category.value}")
        print(f"  Pattern:   {a.sdk_pattern}")
        print(f"  Description: {a.description}")
        if a.prompt_fragment:
            print(f"\n  Prompt fragment:\n    {a.prompt_fragment}")

    elif args.command == "search-archetypes":
        results = search_archetypes(args.query)
        if not results:
            print(f"No archetypes matching '{args.query}'")
        else:
            print(f"Found {len(results)} archetypes matching '{args.query}':\n")
            for a in results:
                print(f"  {a.name:25s} {a.freudian_concept}")

    # --- Harness commands ---
    elif args.command == "list-presets":
        for name, arch_names in sorted(PRESETS.items()):
            print(f"  {name}:")
            for an in arch_names:
                print(f"    - {an}")
            print()

    elif args.command == "prompt":
        if args.preset:
            prompt = compose_preset(args.preset, task_context=args.task)
        elif args.archetypes:
            prompt = compose_system_prompt(args.archetypes, task_context=args.task)
        else:
            print("Provide archetype names or --preset", file=sys.stderr)
            sys.exit(1)
        print(prompt)


if __name__ == "__main__":
    main()
