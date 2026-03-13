"""Command-line interface for querying the Freud Schema dataset and managing the experiment harness."""

from __future__ import annotations

import argparse
import sys

import orjson

from freud_schema.archetypes import (
    ARCHETYPES,
    get_archetype,
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
from freud_schema.models import FreudEntry
from freud_schema.tables import (
    CorrectionType,
    RuleScope,
    SessionStatus,
    SkillStatus,
    ValidationStatus,
)


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


def _print_json(data: dict | str, indent: str = "  ") -> None:
    """Pretty-print JSON data (dict or string) with a fixed indent prefix."""
    if isinstance(data, str):
        try:
            data = orjson.loads(data)
        except Exception:
            for line in data.split("\n"):
                print(f"{indent}{line}")
            return
    text = orjson.dumps(data, option=orjson.OPT_INDENT_2).decode()
    for line in text.split("\n"):
        print(f"{indent}{line}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="freud-schema",
        description="Experiment harness for data-driven agent orchestration",
    )
    parser.add_argument("--db", default=None, help="Path to DuckDB file (default: data/freudagent.duckdb)")
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

    # --- Experiment harness commands ---
    sub.add_parser("db", help="Database operations").add_argument(
        "action", choices=["init", "reset", "status", "ddl"],
        help="init: create tables, reset: drop and recreate, status: show counts, ddl: print SQL",
    )

    p_skill = sub.add_parser("skill", help="Manage skills")
    p_skill_sub = p_skill.add_subparsers(dest="skill_action")
    p_skill_add = p_skill_sub.add_parser("add", help="Add a skill")
    p_skill_add.add_argument("--domain", required=True)
    p_skill_add.add_argument("--task-type", required=True)
    p_skill_add.add_argument("--content", help="Skill content (or use --file)")
    p_skill_add.add_argument("--file", help="Read skill content from file")
    p_skill_add.add_argument("--status", default="draft", choices=[e.value for e in SkillStatus])
    p_skill_sub.add_parser("list", help="List all skills")

    p_source = sub.add_parser("source", help="Manage sources")
    p_source_sub = p_source.add_subparsers(dest="source_action")
    p_source_add = p_source_sub.add_parser("add", help="Register a source")
    p_source_add.add_argument("--path", required=True, help="File path")
    p_source_add.add_argument("--media-type", required=True, help="MIME type")
    p_source_sub.add_parser("list", help="List all sources")

    p_rule = sub.add_parser("rule", help="Manage rules")
    p_rule_sub = p_rule.add_subparsers(dest="rule_action")
    p_rule_add = p_rule_sub.add_parser("add", help="Add a rule")
    p_rule_add.add_argument("--content", required=True)
    p_rule_add.add_argument("--scope", default="global", choices=[e.value for e in RuleScope])
    p_rule_add.add_argument("--domain", default=None)
    p_rule_add.add_argument("--priority", type=int, default=0)
    p_rule_sub.add_parser("list", help="List all rules")

    p_feedback = sub.add_parser("feedback", help="Manage feedback")
    p_fb_sub = p_feedback.add_subparsers(dest="feedback_action")
    p_fb_list = p_fb_sub.add_parser("list", help="List feedback")
    p_fb_list.add_argument("--skill-id", type=int, default=None)
    p_fb_list.add_argument("--aggregate", action="store_true")
    p_fb_add = p_fb_sub.add_parser("add", help="Add feedback on an extraction")
    p_fb_add.add_argument("--extraction-id", type=int, required=True)
    p_fb_add.add_argument("--type", required=True,
                          choices=[e.value for e in CorrectionType])
    p_fb_add.add_argument("--correction", required=True, help="JSON correction data")
    p_fb_add.add_argument("--notes", default=None)
    p_fb_add.add_argument("--by", default=None)

    # --- Run command ---
    p_run = sub.add_parser("run", help="Execute the orchestrator against sources")
    p_run.add_argument("--domain", required=True, help="Skill domain")
    p_run.add_argument("--task-type", required=True, help="Skill task type")
    p_run.add_argument("--source-id", type=int, action="append", default=None,
                       help="Source ID(s) to process (repeatable, default: all active)")
    p_run.add_argument("--model", default="echo", help="Provider: echo, anthropic, or local (default: echo)")
    p_run.add_argument("--model-name", default=None, help="Model name override (provider-specific default)")
    p_run.add_argument("--endpoint", default=None, help="Base URL for local provider (default: http://localhost:8080)")
    p_run.add_argument("--preset", default=None,
                       help="Archetype preset to compose into system prompt (e.g. careful-executor)")
    p_run.add_argument("--task", default="", help="Additional task context")

    # --- Extraction commands ---
    p_ext = sub.add_parser("extraction", help="Manage extractions")
    p_ext_sub = p_ext.add_subparsers(dest="extraction_action")
    p_ext_list = p_ext_sub.add_parser("list", help="List extractions")
    p_ext_list.add_argument("--skill-id", type=int, default=None)
    p_ext_list.add_argument("--status", default=None, choices=[e.value for e in ValidationStatus])
    p_ext_list.add_argument("--limit", type=int, default=50)
    p_ext_show = p_ext_sub.add_parser("show", help="Show extraction details")
    p_ext_show.add_argument("id", type=int)
    p_ext_validate = p_ext_sub.add_parser("validate", help="Mark as validated")
    p_ext_validate.add_argument("id", type=int)
    p_ext_validate.add_argument("--by", default=None)
    p_ext_reject = p_ext_sub.add_parser("reject", help="Mark as rejected")
    p_ext_reject.add_argument("id", type=int)
    p_ext_reject.add_argument("--by", default=None)

    # --- Session commands ---
    p_sess = sub.add_parser("session", help="View execution sessions")
    p_sess_sub = p_sess.add_subparsers(dest="session_action")
    p_sess_list = p_sess_sub.add_parser("list", help="List sessions")
    p_sess_list.add_argument("--status", default=None, choices=[e.value for e in SessionStatus])
    p_sess_list.add_argument("--limit", type=int, default=20)

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
            print(orjson.dumps(data, option=orjson.OPT_INDENT_2).decode())

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

    # --- Experiment harness commands ---
    elif args.command == "db":
        _handle_db(args)

    elif args.command == "skill":
        _handle_skill(args)

    elif args.command == "source":
        _handle_source(args)

    elif args.command == "rule":
        _handle_rule(args)

    elif args.command == "feedback":
        _handle_feedback(args)

    elif args.command == "run":
        _handle_run(args)

    elif args.command == "extraction":
        _handle_extraction(args)

    elif args.command == "session":
        _handle_session(args)


# ---------------------------------------------------------------------------
# Experiment harness command handlers
# ---------------------------------------------------------------------------


def _get_store(db_path: str | None = None):
    from freud_schema.db import connect
    from freud_schema.store import ExperimentStore
    con = connect(db_path)
    return ExperimentStore(con)


def _handle_db(args) -> None:
    from freud_schema.db import connect, get_ddl, get_schema_version, init_schema, reset_schema

    if args.action == "ddl":
        print(get_ddl())
        return

    con = connect(args.db)
    if args.action == "init":
        init_schema(con)
        print("Schema initialized.")
    elif args.action == "reset":
        reset_schema(con)
        print("Schema reset (all data dropped).")
    elif args.action == "status":
        init_schema(con)
        version = get_schema_version(con)
        print(f"  Schema version: {version}")
        for table in ("skills", "sources", "extractions", "sessions", "feedback", "rules"):
            count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  {table:15s} {count:>6} rows")
    con.close()


def _handle_skill(args) -> None:
    from freud_schema.tables import Skill

    store = _get_store(args.db)
    if args.skill_action == "add":
        content = args.content
        if args.file:
            with open(args.file) as f:
                content = f.read()
        if not content:
            print("Provide --content or --file", file=sys.stderr)
            sys.exit(1)
        skill = Skill(
            domain=args.domain, task_type=args.task_type,
            content=content, status=args.status,
        )
        skill_id = store.insert_skill(skill)
        print(f"Skill created: id={skill_id} domain={args.domain} task_type={args.task_type} status={args.status}")
    elif args.skill_action == "list":
        for s in store.list_skills():
            print(f"  [{s.id}] {s.domain}/{s.task_type} v{s.version} ({s.status})")
    else:
        print("Use: skill add|list", file=sys.stderr)


def _handle_source(args) -> None:
    from freud_schema.tables import Source

    store = _get_store(args.db)
    if args.source_action == "add":
        source = Source(content_path=args.path, media_type=args.media_type)
        source_id = store.insert_source(source)
        print(f"Source registered: id={source_id} path={args.path}")
    elif args.source_action == "list":
        for s in store.list_sources():
            print(f"  [{s.id}] {s.content_path} ({s.media_type}) [{s.status}]")
    else:
        print("Use: source add|list", file=sys.stderr)


def _handle_rule(args) -> None:
    from freud_schema.tables import Rule

    store = _get_store(args.db)
    if args.rule_action == "add":
        rule = Rule(
            scope=args.scope, domain=args.domain,
            priority=args.priority, content=args.content,
        )
        rule_id = store.insert_rule(rule)
        print(f"Rule created: id={rule_id} scope={args.scope}")
    elif args.rule_action == "list":
        for r in store.list_rules():
            domain = f" domain={r.domain}" if r.domain else ""
            print(f"  [{r.id}] [{r.scope}{domain}] p={r.priority}: {r.content[:60]}")
    else:
        print("Use: rule add|list", file=sys.stderr)


def _handle_feedback(args) -> None:
    from freud_schema.tables import Feedback

    store = _get_store(args.db)
    if args.feedback_action == "list":
        if args.aggregate and args.skill_id:
            agg = store.aggregate_feedback(args.skill_id)
            if not agg:
                print("No feedback for this skill.")
            else:
                print(f"Feedback for skill {args.skill_id}:")
                for correction_type, count in agg:
                    print(f"  {correction_type:20s} {count:>4}x")
        else:
            fb_list = store.list_feedback(skill_id=args.skill_id)
            if not fb_list:
                print("No feedback found.")
            else:
                for fb in fb_list:
                    print(f"  [{fb.id}] skill={fb.skill_id} type={fb.correction_type} by={fb.created_by or 'anon'}")
    elif args.feedback_action == "add":
        ext = store.get_extraction(args.extraction_id)
        if ext is None:
            print(f"Extraction {args.extraction_id} not found.", file=sys.stderr)
            sys.exit(1)
        try:
            correction = orjson.loads(args.correction)
        except Exception:
            print("--correction must be valid JSON", file=sys.stderr)
            sys.exit(1)
        fb = Feedback(
            extraction_id=args.extraction_id,
            session_id=ext.session_id,
            skill_id=ext.skill_id,
            correction=correction,
            correction_type=args.type,
            notes=args.notes,
            created_by=args.by,
        )
        fb_id = store.insert_feedback(fb)
        print(f"Feedback created: id={fb_id} extraction={args.extraction_id} type={args.type}")
    else:
        print("Use: feedback list|add", file=sys.stderr)


def _handle_run(args) -> None:
    from freud_schema.orchestrator import get_provider, run_simple

    store = _get_store(args.db)

    # Resolve skill
    skill = store.get_active_skill(args.domain, args.task_type)
    if skill is None:
        print(f"No active skill for {args.domain}/{args.task_type}", file=sys.stderr)
        print("Add one with: freud-schema skill add --domain ... --task-type ... --content ... --status active",
              file=sys.stderr)
        sys.exit(1)

    # Resolve source IDs for pre-flight check; let run_simple own the actual resolution
    source_ids = args.source_id  # None means "all active"
    if source_ids is not None and not source_ids:
        print("No sources to process.", file=sys.stderr)
        print("Register sources with: freud-schema source add --path ... --media-type ...",
              file=sys.stderr)
        sys.exit(1)

    # Get provider
    try:
        provider = get_provider(
            args.model,
            model_name=args.model_name,
            base_url=args.endpoint,
        )
    except (ValueError, ImportError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    model_display = args.model_name or args.model
    print(f"Skill: {skill.domain}/{skill.task_type} v{skill.version} (id={skill.id})")
    print(f"Model: {model_display}")
    if args.preset:
        print(f"Preset: {args.preset}")
    print()

    extractions = run_simple(
        store,
        domain=args.domain,
        task_type=args.task_type,
        source_ids=source_ids,
        provider=provider,
        model_name=model_display,
        task_description=args.task,
        preset=args.preset,
    )

    if not extractions:
        print("No extractions produced (no active sources found).")
        return

    source_map = store.get_sources_by_ids([e.source_id for e in extractions])

    for i, ext in enumerate(extractions, 1):
        source = source_map.get(ext.source_id)
        path = source.content_path if source else f"source-{ext.source_id}"
        print(f"[{i}/{len(extractions)}] {path}")
        print(f"  Extraction: id={ext.id} ({ext.validation_status})")
        _print_json(ext.output.get("raw", ""))
        print()

    print(f"Done: {len(extractions)} extraction(s) created.")
    print("Review: freud-schema extraction list")
    print("Validate: freud-schema extraction validate <id>")


def _handle_extraction(args) -> None:
    store = _get_store(args.db)
    if args.extraction_action == "list":
        exts = store.list_extractions(
            skill_id=args.skill_id,
            validation_status=args.status,
            limit=args.limit,
        )
        if not exts:
            print("No extractions found.")
        else:
            source_map = store.get_sources_by_ids([e.source_id for e in exts])
            for e in exts:
                source = source_map.get(e.source_id)
                path = source.content_path if source else "?"
                print(f"  [{e.id}] skill={e.skill_id} source={path} "
                      f"status={e.validation_status} confidence={e.confidence}")
    elif args.extraction_action == "show":
        ext = store.get_extraction(args.id)
        if ext is None:
            print(f"Extraction {args.id} not found.", file=sys.stderr)
            sys.exit(1)
        source = store.get_source(ext.source_id)
        skill = store.get_skill(ext.skill_id)
        print(f"  Extraction: {ext.id}")
        print(f"  Source: {source.content_path if source else '?'} (id={ext.source_id})")
        if skill:
            print(f"  Skill: {skill.domain}/{skill.task_type} v{skill.version} (id={ext.skill_id})")
        else:
            print(f"  Skill: id={ext.skill_id}")
        print(f"  Session: {ext.session_id}")
        print(f"  Status: {ext.validation_status}")
        if ext.confidence is not None:
            print(f"  Confidence: {ext.confidence}")
        if ext.validated_by:
            print(f"  Validated by: {ext.validated_by} at {ext.validated_at}")
        print(f"  Created: {ext.created_at}")
        print(f"\n  Output:")
        _print_json(ext.output, indent="    ")
    elif args.extraction_action == "validate":
        store.update_validation(args.id, status=ValidationStatus.VALIDATED, validated_by=args.by)
        print(f"Extraction {args.id} marked as validated.")
    elif args.extraction_action == "reject":
        store.update_validation(args.id, status=ValidationStatus.REJECTED, validated_by=args.by)
        print(f"Extraction {args.id} marked as rejected.")
    else:
        print("Use: extraction list|show|validate|reject", file=sys.stderr)


def _handle_session(args) -> None:
    store = _get_store(args.db)
    if args.session_action == "list":
        sessions = store.list_sessions(status=args.status, limit=args.limit)
        if not sessions:
            print("No sessions found.")
        else:
            for s in sessions:
                parent = f" parent={s.parent_session_id}" if s.parent_session_id else ""
                skill_info = f" skill={s.skill_id}" if s.skill_id else ""
                print(f"  [{s.id}] {s.agent_role} {s.task_type} [{s.status}]{parent}{skill_info} model={s.model_used}")
    else:
        print("Use: session list", file=sys.stderr)


if __name__ == "__main__":
    main()
