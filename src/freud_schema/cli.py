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
    SamplingStrategy,
    SessionStatus,
    SkillOrigin,
    SkillStatus,
    TraceFeedbackType,
    TraceType,
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
    p_skill_add.add_argument(
        "--version", type=int, default=1,
        help="Version number; a new version must exceed the current version "
             "for this domain/task_type",
    )
    p_skill_sub.add_parser("list", help="List all skills")
    p_skill_deprecate = p_skill_sub.add_parser("deprecate", help="Deprecate a skill")
    p_skill_deprecate.add_argument("key", help="Skill key or unique prefix")
    p_skill_activate = p_skill_sub.add_parser("activate", help="Activate a skill")
    p_skill_activate.add_argument("key", help="Skill key or unique prefix")
    p_skill_patterns = p_skill_sub.add_parser("patterns", help="Show feedback patterns")
    p_skill_patterns.add_argument("--domain", default=None)
    p_skill_patterns.add_argument("--min-count", type=int, default=3)

    p_source = sub.add_parser("source", help="Manage sources")
    p_source_sub = p_source.add_subparsers(dest="source_action")
    p_source_add = p_source_sub.add_parser("add", help="Register a source")
    p_source_add.add_argument("--path", required=True, help="File path")
    p_source_add.add_argument("--media-type", required=True, help="MIME type")
    p_source_sub.add_parser("list", help="List all sources")

    p_rule = sub.add_parser("rule", help="Manage rules")
    p_rule_sub = p_rule.add_subparsers(dest="rule_action")
    p_rule_add = p_rule_sub.add_parser("add", help="Add a rule")
    p_rule_add.add_argument("--name", required=True, help="Stable identity; compile target filename")
    p_rule_add.add_argument("--content", required=True)
    p_rule_add.add_argument("--scope", default="global", choices=[e.value for e in RuleScope])
    p_rule_add.add_argument("--domain", default=None)
    p_rule_add.add_argument("--priority", type=int, default=0)
    p_rule_sub.add_parser("list", help="List all rules")

    p_feedback = sub.add_parser("feedback", help="Manage feedback")
    p_fb_sub = p_feedback.add_subparsers(dest="feedback_action")
    p_fb_list = p_fb_sub.add_parser("list", help="List feedback")
    p_fb_list.add_argument("--skill-key", default=None, help="Skill key or unique prefix")
    p_fb_list.add_argument("--aggregate", action="store_true")
    p_fb_add = p_fb_sub.add_parser("add", help="Add feedback on an extraction")
    p_fb_add.add_argument("--extraction-key", required=True, help="Extraction key or unique prefix")
    p_fb_add.add_argument("--type", required=True,
                          choices=[e.value for e in CorrectionType])
    p_fb_add.add_argument("--correction", required=True, help="JSON correction data")
    p_fb_add.add_argument("--notes", default=None)
    p_fb_add.add_argument("--by", default=None)

    # --- Extraction commands ---
    p_ext = sub.add_parser("extraction", help="Manage extractions")
    p_ext_sub = p_ext.add_subparsers(dest="extraction_action")
    p_ext_list = p_ext_sub.add_parser("list", help="List extractions")
    p_ext_list.add_argument("--skill-key", default=None, help="Skill key or unique prefix")
    p_ext_list.add_argument("--status", default=None, choices=[e.value for e in ValidationStatus])
    p_ext_list.add_argument("--limit", type=int, default=50)
    p_ext_show = p_ext_sub.add_parser("show", help="Show extraction details")
    p_ext_show.add_argument("key", help="Extraction key or unique prefix")
    p_ext_validate = p_ext_sub.add_parser("validate", help="Mark as validated")
    p_ext_validate.add_argument("key", help="Extraction key or unique prefix")
    p_ext_validate.add_argument("--by", default=None)
    p_ext_reject = p_ext_sub.add_parser("reject", help="Mark as rejected")
    p_ext_reject.add_argument("key", help="Extraction key or unique prefix")
    p_ext_reject.add_argument("--by", default=None)

    # --- Session commands ---
    p_sess = sub.add_parser("session", help="View execution sessions")
    p_sess_sub = p_sess.add_subparsers(dest="session_action")
    p_sess_list = p_sess_sub.add_parser("list", help="List sessions")
    p_sess_list.add_argument("--status", default=None, choices=[e.value for e in SessionStatus])
    p_sess_list.add_argument("--limit", type=int, default=20)
    p_sess_show = p_sess_sub.add_parser("show", help="Show session details")
    p_sess_show.add_argument("key", help="Session key or unique prefix")

    # --- Trace commands ---
    p_trace = sub.add_parser("trace", help="View execution traces")
    p_trace_sub = p_trace.add_subparsers(dest="trace_action")
    p_trace_list = p_trace_sub.add_parser("list", help="List traces for a session")
    p_trace_list.add_argument("--session-key", required=True, help="Session key or unique prefix")
    p_trace_list.add_argument("--type", default=None, choices=[e.value for e in TraceType])
    p_trace_show = p_trace_sub.add_parser("show", help="Show trace details")
    p_trace_show.add_argument("key", help="Trace key or unique prefix")
    p_trace_patterns = p_trace_sub.add_parser("patterns", help="Find recurring traces")
    p_trace_patterns.add_argument("--skill-key", required=True, help="Skill key or unique prefix")
    p_trace_patterns.add_argument("--type", required=True, choices=[e.value for e in TraceType])
    p_trace_patterns.add_argument("--min-count", type=int, default=2)

    # --- Trace feedback commands ---
    p_tfb = sub.add_parser("trace-feedback", help="Manage trace feedback")
    p_tfb_sub = p_tfb.add_subparsers(dest="trace_feedback_action")
    p_tfb_add = p_tfb_sub.add_parser("add", help="Add feedback on a trace")
    p_tfb_add.add_argument("--trace-key", required=True, help="Trace key or unique prefix")
    p_tfb_add.add_argument("--type", required=True, choices=[e.value for e in TraceFeedbackType])
    p_tfb_add.add_argument("--content", required=True)
    p_tfb_add.add_argument("--correction", default=None, help="JSON correction data")
    p_tfb_add.add_argument("--by", default=None)
    p_tfb_list = p_tfb_sub.add_parser("list", help="List trace feedback")
    p_tfb_list.add_argument("--session-key", required=True, help="Session key or unique prefix")
    p_tfb_list.add_argument("--type", default=None, choices=[e.value for e in TraceFeedbackType])

    # --- Ingest commands ---
    p_ingest = sub.add_parser("ingest", help="Ingest external data into the warehouse")
    p_ingest_sub = p_ingest.add_subparsers(dest="ingest_action")
    p_ingest_tr = p_ingest_sub.add_parser(
        "transcripts",
        help="Ingest Claude Code session transcripts (idempotent; re-runs skip existing rows)")
    p_ingest_tr.add_argument(
        "--root", default=None,
        help="Projects root (default: Claude Code's projects directory)")
    p_ingest_tr.add_argument(
        "--project", default=None,
        help="Substring filter on the encoded project directory name")
    p_ingest_tr.add_argument(
        "--since", default=None,
        help="Only files modified on/after this date (YYYY-MM-DD)")

    # --- Couch commands ---
    p_couch = sub.add_parser(
        "couch", help="Analysis passes over the warehouse (SQL finding detectors)")
    p_couch_sub = p_couch.add_subparsers(dest="couch_action")
    p_couch_sub.add_parser(
        "run", help="Run all SQL detectors and record findings (no model calls)")
    p_couch_list = p_couch_sub.add_parser("list", help="List recorded findings")
    p_couch_list.add_argument("--type", default=None, help="Filter by finding_type")
    p_couch_list.add_argument("--limit", type=int, default=30)

    # --- Sampling config commands ---
    p_sc = sub.add_parser("sampling-config", help="Manage sampling configs")
    p_sc_sub = p_sc.add_subparsers(dest="sampling_config_action")
    p_sc_add = p_sc_sub.add_parser("add", help="Add a sampling config")
    p_sc_add.add_argument("--strategy", required=True, choices=[e.value for e in SamplingStrategy])
    p_sc_add.add_argument("--domain", default=None)
    p_sc_add.add_argument("--task-type", default=None)
    p_sc_add.add_argument("--max-samples", type=int, default=3)
    p_sc_sub.add_parser("list", help="List all sampling configs")

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

    elif args.command == "extraction":
        _handle_extraction(args)

    elif args.command == "session":
        _handle_session(args)

    elif args.command == "trace":
        _handle_trace(args)

    elif args.command == "trace-feedback":
        _handle_trace_feedback(args)

    elif args.command == "ingest":
        _handle_ingest(args)
    elif args.command == "couch":
        _handle_couch(args)
    elif args.command == "sampling-config":
        _handle_sampling_config(args)


# ---------------------------------------------------------------------------
# Experiment harness command handlers
# ---------------------------------------------------------------------------


def _get_store(db_path: str | None = None):
    from freud_schema.db import connect
    from freud_schema.store import ExperimentStore
    con = connect(db_path)
    return ExperimentStore(con)


def _resolve_or_exit(store, table: str, key_col: str, prefix: str, label: str) -> str:
    """Resolve a key or unique prefix, or print the error and exit(1).

    Every command that takes an entity reference now takes a key or unique
    key prefix (git-short-hash style) instead of an integer id.
    """
    try:
        return store.resolve_key(table, key_col, prefix)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


def _handle_db(args) -> None:
    from freud_schema.db import connect, get_ddl, get_schema_version, init_schema, reset_schema

    if args.action == "ddl":
        print(get_ddl())
        return

    with connect(args.db) as con:
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
            for table in ("dim_skill", "dim_source", "dim_rule", "dim_sampling_config",
                          "dim_project", "dim_facet_type", "dim_finding_type",
                          "fact_session", "fact_trace", "fact_extraction",
                          "fact_feedback", "fact_trace_feedback",
                          "fact_message", "fact_tool_use", "fact_session_facets",
                          "fact_finding", "fact_proposal", "meta_load_log"):
                row = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                count = row[0] if row else 0
                print(f"  {table:15s} {count:>6} rows")


def _handle_skill(args) -> None:
    from freud_schema.tables import Skill

    with _get_store(args.db) as store:
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
                version=args.version,
                content=content, status=SkillStatus(args.status),
            )
            skill_key = store.insert_skill(skill)
            print(f"Skill created: key={skill_key} domain={args.domain} task_type={args.task_type} v{args.version} status={args.status}")
        elif args.skill_action == "list":
            for s in store.list_skills():
                origin_tag = f" [{s.origin.value}]" if s.origin != SkillOrigin.HUMAN_AUTHORED else ""
                parent_tag = f" parent={s.parent_skill_key[:8]}" if s.parent_skill_key else ""
                print(f"  [{s.skill_key[:8]}] {s.domain}/{s.task_type} v{s.version} ({s.status.value}){origin_tag}{parent_tag}")
        elif args.skill_action == "patterns":
            results = store.get_skills_with_feedback_patterns(
                domain=args.domain, min_feedback_count=args.min_count,
            )
            if not results:
                print("No skills with feedback patterns above threshold.")
            else:
                for r in results:
                    skill = r["skill"]
                    print(f"  [{skill.skill_key[:8]}] {skill.domain}/{skill.task_type} v{skill.version} -- {r['total_feedback']} total feedback")
                    for ct, cnt in r["patterns"]:
                        print(f"    {ct:20s} {cnt:>4}x")
        elif args.skill_action in ("deprecate", "activate"):
            skill_key = _resolve_or_exit(store, "dim_skill", "skill_key", args.key, "Skill")
            action = store.deprecate_skill if args.skill_action == "deprecate" else store.activate_skill
            action(skill_key)
            verb = "deprecated" if args.skill_action == "deprecate" else "activated"
            print(f"Skill {skill_key[:8]} {verb}.")
        else:
            print("Use: skill add|list|deprecate|activate", file=sys.stderr)


def _handle_source(args) -> None:
    from freud_schema.tables import Source

    with _get_store(args.db) as store:
        if args.source_action == "add":
            source = Source(content_path=args.path, media_type=args.media_type)
            source_key = store.insert_source(source)
            print(f"Source registered: key={source_key} path={args.path}")
        elif args.source_action == "list":
            for s in store.list_sources():
                print(f"  [{s.source_key[:8]}] {s.content_path} ({s.media_type}) [{s.status.value}]")
        else:
            print("Use: source add|list", file=sys.stderr)


def _handle_rule(args) -> None:
    from freud_schema.tables import Rule

    with _get_store(args.db) as store:
        if args.rule_action == "add":
            rule = Rule(
                name=args.name, scope=RuleScope(args.scope), domain=args.domain,
                priority=args.priority, content=args.content,
            )
            rule_key = store.insert_rule(rule)
            print(f"Rule created: key={rule_key} name={args.name} scope={args.scope}")
        elif args.rule_action == "list":
            for r in store.list_rules():
                domain = f" domain={r.domain}" if r.domain else ""
                print(f"  [{r.rule_key[:8]}] {r.name} [{r.scope.value}{domain}] p={r.priority}: {r.content[:60]}")
        else:
            print("Use: rule add|list", file=sys.stderr)


def _handle_feedback(args) -> None:
    from freud_schema.tables import Feedback

    with _get_store(args.db) as store:
        if args.feedback_action == "list":
            skill_key = None
            if args.skill_key:
                skill_key = _resolve_or_exit(store, "dim_skill", "skill_key", args.skill_key, "Skill")
            if args.aggregate and skill_key:
                agg = store.aggregate_feedback(skill_key)
                if not agg:
                    print("No feedback for this skill.")
                else:
                    print(f"Feedback for skill {skill_key[:8]}:")
                    for entry in agg:
                        fields = ", ".join(entry["fields"]) if entry["fields"] else ""
                        fields_str = f" (fields: {fields})" if fields else ""
                        print(f"  {entry['correction_type']:20s} {entry['count']:>4}x{fields_str}")
            else:
                fb_list = store.list_feedback(skill_key=skill_key)
                if not fb_list:
                    print("No feedback found.")
                else:
                    for fb in fb_list:
                        print(f"  [{fb.feedback_key[:8]}] skill={fb.skill_key[:8]} type={fb.correction_type.value} by={fb.created_by or 'anon'}")
        elif args.feedback_action == "add":
            extraction_key = _resolve_or_exit(
                store, "fact_extraction", "extraction_key", args.extraction_key, "Extraction",
            )
            ext = store.get_extraction(extraction_key)
            try:
                correction = orjson.loads(args.correction)
            except Exception:
                print("--correction must be valid JSON", file=sys.stderr)
                sys.exit(1)
            fb = Feedback(
                extraction_key=extraction_key,
                session_key=ext.session_key,
                skill_key=ext.skill_key,
                correction=correction,
                correction_type=CorrectionType(args.type),
                notes=args.notes,
                created_by=args.by,
            )
            fb_key = store.insert_feedback(fb)
            print(f"Feedback created: key={fb_key} extraction={extraction_key[:8]} type={args.type}")
        else:
            print("Use: feedback list|add", file=sys.stderr)


def _handle_extraction(args) -> None:
    with _get_store(args.db) as store:
        if args.extraction_action == "list":
            skill_key = None
            if args.skill_key:
                skill_key = _resolve_or_exit(store, "dim_skill", "skill_key", args.skill_key, "Skill")
            exts = store.list_extractions(
                skill_key=skill_key,
                validation_status=ValidationStatus(args.status) if args.status else None,
                limit=args.limit,
            )
            if not exts:
                print("No extractions found.")
            else:
                for e in exts:
                    path = e.source_path or "?"
                    skill_tag = e.skill_key[:8] if e.skill_key else "?"
                    print(f"  [{e.extraction_key[:8]}] skill={skill_tag} source={path} "
                          f"status={e.validation_status.value} confidence={e.confidence}")
        elif args.extraction_action == "show":
            extraction_key = _resolve_or_exit(
                store, "fact_extraction", "extraction_key", args.key, "Extraction",
            )
            ext = store.get_extraction(extraction_key)
            print(f"  Extraction: {ext.extraction_key}")
            print(f"  Source: {ext.source_path or '?'} (key={ext.source_key})")
            if ext.skill_domain:
                print(f"  Skill: {ext.skill_domain}/{ext.skill_task_type} v{ext.skill_version} (key={ext.skill_key})")
            else:
                print(f"  Skill: key={ext.skill_key}")
            print(f"  Session: {ext.session_key}")
            print(f"  Status: {ext.validation_status.value}")
            if ext.confidence is not None:
                print(f"  Confidence: {ext.confidence}")
            if ext.validated_by:
                print(f"  Validated by: {ext.validated_by} at {ext.validated_at}")
            print(f"  Created: {ext.created_at}")
            print(f"\n  Output:")
            _print_json(ext.output, indent="    ")
        elif args.extraction_action == "validate":
            extraction_key = _resolve_or_exit(
                store, "fact_extraction", "extraction_key", args.key, "Extraction",
            )
            store.update_validation(extraction_key, status=ValidationStatus.VALIDATED, validated_by=args.by)
            print(f"Extraction {extraction_key[:8]} marked as validated.")
        elif args.extraction_action == "reject":
            extraction_key = _resolve_or_exit(
                store, "fact_extraction", "extraction_key", args.key, "Extraction",
            )
            store.update_validation(extraction_key, status=ValidationStatus.REJECTED, validated_by=args.by)
            print(f"Extraction {extraction_key[:8]} marked as rejected.")
        else:
            print("Use: extraction list|show|validate|reject", file=sys.stderr)


def _handle_session(args) -> None:
    with _get_store(args.db) as store:
        if args.session_action == "list":
            sessions = store.list_sessions(
                status=SessionStatus(args.status) if args.status else None,
                limit=args.limit,
            )
            if not sessions:
                print("No sessions found.")
            else:
                for s in sessions:
                    parent = f" parent={s.parent_session_key[:8]}" if s.parent_session_key else ""
                    skill_info = f" skill={s.skill_key[:8]}" if s.skill_key else ""
                    print(f"  [{s.session_key[:8]}] {s.agent_role.value} {s.task_type} [{s.status.value}]{parent}{skill_info} model={s.model_used}")
        elif args.session_action == "show":
            session_key = _resolve_or_exit(store, "fact_session", "session_key", args.key, "Session")
            session = store.get_session(session_key)
            print(f"  Session: {session.session_key}")
            print(f"  Task: {session.task_description}")
            print(f"  Type: {session.task_type}")
            print(f"  Role: {session.agent_role.value}")
            print(f"  Status: {session.status.value}")
            print(f"  Model: {session.model_used}")
            if session.skill_key:
                print(f"  Skill: {session.skill_key}")
            if session.parent_session_key:
                print(f"  Parent: {session.parent_session_key}")
            print(f"  Created: {session.created_at}")
            if session.completed_at:
                print(f"  Completed: {session.completed_at}")
            if session.context_loaded:
                print(f"\n  Context loaded:")
                _print_json(session.context_loaded, indent="    ")
            if session.token_usage:
                print(f"\n  Token usage:")
                _print_json(session.token_usage, indent="    ")
            if session.result:
                print(f"\n  Result:")
                _print_json(session.result, indent="    ")
        else:
            print("Use: session list|show", file=sys.stderr)


def _handle_trace(args) -> None:
    from freud_schema.tables import Trace, TraceType

    with _get_store(args.db) as store:
        if args.trace_action == "list":
            session_key = _resolve_or_exit(store, "fact_session", "session_key", args.session_key, "Session")
            traces = store.get_session_traces(session_key)
            if args.type:
                traces = [t for t in traces if t.trace_type == args.type]
            if not traces:
                print("No traces found.")
            else:
                for t in traces:
                    indent = "  " * t.depth
                    duration = f" ({t.duration_ms}ms)" if t.duration_ms else ""
                    print(f"  {indent}[{t.trace_key[:8]}] [{t.trace_type.value}] {t.title}{duration}")
        elif args.trace_action == "show":
            trace_key = _resolve_or_exit(store, "fact_trace", "trace_key", args.key, "Trace")
            trace = store.get_trace(trace_key)
            print(f"  Trace: {trace.trace_key}")
            print(f"  Session: {trace.session_key}")
            print(f"  Type: {trace.trace_type}")
            print(f"  Title: {trace.title}")
            print(f"  Depth: {trace.depth}, Order: {trace.sequence_order}")
            if trace.parent_trace_key:
                print(f"  Parent: {trace.parent_trace_key}")
            if trace.content:
                print(f"  Content: {trace.content}")
            if trace.reasoning:
                print(f"  Reasoning: {trace.reasoning}")
            if trace.alternatives:
                print(f"\n  Alternatives:")
                _print_json(trace.alternatives, indent="    ")
            if trace.outcome:
                print(f"\n  Outcome:")
                _print_json(trace.outcome, indent="    ")
            if trace.child_session_key:
                print(f"  Child session: {trace.child_session_key}")
            if trace.duration_ms:
                print(f"  Duration: {trace.duration_ms}ms")
            children = store.get_trace_children(trace.trace_key)
            if children:
                print(f"\n  Children ({len(children)}):")
                for c in children:
                    print(f"    [{c.trace_key[:8]}] [{c.trace_type}] {c.title}")
            tf_data = store.get_trace_with_feedback(trace.trace_key)
            if tf_data and tf_data["feedback"]:
                print(f"\n  Feedback ({len(tf_data['feedback'])}):")
                for fb in tf_data["feedback"]:
                    print(f"    [{fb.feedback_type.value}] {fb.content}")
        elif args.trace_action == "patterns":
            skill_key = _resolve_or_exit(store, "dim_skill", "skill_key", args.skill_key, "Skill")
            patterns = store.get_recurring_traces(
                skill_key,
                TraceType(args.type),
                min_occurrences=args.min_count,
            )
            if not patterns:
                print("No recurring patterns found.")
            else:
                for p in patterns:
                    print(f"  [{p['count']}x] {p['title']}")
                    print(f"    Sessions: {p['session_keys']}")
                    print(f"    Example trace: {p['example_trace_key']}")
        else:
            print("Use: trace list|show|patterns", file=sys.stderr)


def _handle_trace_feedback(args) -> None:
    from freud_schema.tables import TraceFeedback, TraceFeedbackType

    with _get_store(args.db) as store:
        if args.trace_feedback_action == "add":
            trace_key = _resolve_or_exit(store, "fact_trace", "trace_key", args.trace_key, "Trace")
            trace = store.get_trace(trace_key)
            correction = None
            if args.correction:
                try:
                    correction = orjson.loads(args.correction)
                except Exception:
                    print("--correction must be valid JSON", file=sys.stderr)
                    sys.exit(1)
            tf = TraceFeedback(
                trace_key=trace_key,
                session_key=trace.session_key,
                feedback_type=TraceFeedbackType(args.type),
                content=args.content,
                correction=correction,
                created_by=args.by,
            )
            tf_key = store.insert_trace_feedback(tf)
            print(f"Trace feedback created: key={tf_key} trace={trace_key[:8]} type={args.type}")
        elif args.trace_feedback_action == "list":
            session_key = _resolve_or_exit(store, "fact_session", "session_key", args.session_key, "Session")
            fb_list = store.list_trace_feedback(
                session_key=session_key,
                feedback_type=TraceFeedbackType(args.type) if args.type else None,
            )
            if not fb_list:
                print("No trace feedback found.")
            else:
                for fb in fb_list:
                    print(f"  [{fb.trace_feedback_key[:8]}] trace={fb.trace_key[:8]} [{fb.feedback_type.value}] {fb.content[:60]} by={fb.created_by or 'anon'}")
        else:
            print("Use: trace-feedback add|list", file=sys.stderr)


def _handle_ingest(args) -> None:
    from datetime import datetime

    from freud_schema.ingest import ingest_transcripts

    if args.ingest_action != "transcripts":
        print("Use: ingest transcripts", file=sys.stderr)
        sys.exit(1)
    since = None
    if args.since:
        try:
            since = datetime.fromisoformat(args.since)
        except ValueError:
            print(f"Invalid --since date: {args.since} (expected YYYY-MM-DD)",
                  file=sys.stderr)
            sys.exit(1)
    with _get_store(args.db) as store:
        stats = ingest_transcripts(
            store, root=args.root, project=args.project, since=since)
    print(f"Ingest run {stats['etl_run_id'][:8]} completed:")
    print(f"  sessions:     {stats['sessions']:>8}")
    print(f"  rows read:    {stats['rows_read']:>8}")
    print(f"  rows written: {stats['rows_written']:>8}")
    print(f"  rows skipped: {stats['rows_skipped']:>8}")


def _handle_couch(args) -> None:
    from freud_schema.couch import run_couch

    with _get_store(args.db) as store:
        if args.couch_action == "run":
            stats = run_couch(store)
            print(f"Couch run {stats['etl_run_id'][:8]}: "
                  f"{stats['findings']} finding(s) recorded.")
        elif args.couch_action == "list":
            findings = store.list_findings(
                finding_type=args.type, limit=args.limit)
            if not findings:
                print("No findings recorded.")
            for f in findings:
                proj = f" project={f.project_key[:8]}" if f.project_key else ""
                print(f"  [{f.finding_key[:8]}] {f.finding_type}{proj} "
                      f"n={f.occurrence_count}: {f.summary}")
        else:
            print("Use: couch run|list", file=sys.stderr)
            sys.exit(1)


def _handle_sampling_config(args) -> None:
    from freud_schema.tables import SamplingConfig

    with _get_store(args.db) as store:
        if args.sampling_config_action == "add":
            config = SamplingConfig(
                strategy=SamplingStrategy(args.strategy),
                domain=args.domain,
                task_type=args.task_type,
                max_samples=args.max_samples,
            )
            config_key = store.insert_sampling_config(config)
            print(f"Sampling config created: key={config_key} strategy={args.strategy}")
        elif args.sampling_config_action == "list":
            configs = store.list_sampling_configs()
            if not configs:
                print("No sampling configs found.")
            else:
                for c in configs:
                    domain = c.domain or "*"
                    task = c.task_type or "*"
                    print(f"  [{c.config_key[:8]}] {domain}/{task} strategy={c.strategy.value} max={c.max_samples} [{c.status.value}]")
        else:
            print("Use: sampling-config add|list", file=sys.stderr)


if __name__ == "__main__":
    main()
