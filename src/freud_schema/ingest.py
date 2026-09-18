"""Ingestion: transcripts and generic event streams into the warehouse
(Phase 1: ingest).

Grain produced per transcript file:
- one fact_session row (accumulating snapshot: completed_at/model_used
  advance when a resumed session's file grows),
- one fact_message row per user/assistant entry,
- one fact_tool_use row per tool_use content block, joined to its
  tool_result where present,
- one dim_project row per distinct project path (from the session's cwd).

Idempotency is a property of key generation, not a separate mechanism:
message keys are (session_key, entry_uuid), tool-use keys are
(session_key, tool_use_id), so re-ingesting an unchanged file computes
existing keys and every insert skips. A grown file inserts only its new
entries. rows_written in meta_load_log is computed from table-count
deltas, so the idempotency guarantee is measurable, not assumed.

This is a CLI-time operation: DuckDB is single-process, so it must run
when the MCP server does not hold the database lock.

M5 adds a generic IngestAdapter protocol so transcripts stop being the
only source that can ingest: discover(root, since) finds ingestable
units, parse(unit) streams typed RawEvents out of one unit.
TranscriptAdapter conforms to the protocol's shape but ingest_transcripts()
does not route through it -- the direct path below (discover_sessions +
_ingest_file) is unchanged and stays the one the existing test suite
exercises; typed tables (fact_session/message/tool_use) are projections
for sources rich enough to deserve them. JsonlEventAdapter is the second
reference adapter: it writes the generic fact_event grain via
ingest_events(), the smallest possible proof that a non-transcript stream
flows end-to-end into the warehouse idempotently.

ingest_labels() loads labels about already-ingested messages -- typed
answers to registered questions, from a model, a person, a rule or a
synthetic answer key -- into fact_message_facets. It is not an adapter:
a label is a judgment about a fact_message row, not something a source
said happened, so it does not ride the event grain.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

import orjson

from freud_schema.discovery import SessionFile, default_projects_root, discover_sessions
from freud_schema.store import ExperimentStore
from freud_schema.tables import (
    AgentRole,
    Event,
    EventType,
    FacetMethod,
    FacetOutputType,
    FacetType,
    LabelerKind,
    LabelUnit,
    Message,
    MessageFacet,
    MessageRole,
    Project,
    RecordSource,
    Session,
    SessionStatus,
    ToolUse,
)
from freud_schema.vendor.ccutils_parsers import (
    AssistantEntry,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserEntry,
    iter_typed_entries,
    parse_content_block,
)

_TASK_DESCRIPTION_MAX = 500
_RESULT_TEXT_MAX = 2000

# Tables whose count deltas define rows_written for an ingest run.
# dim_project is deliberately excluded from both sides of the ledger:
# projects are shared across files, so counting ensure_project calls as
# candidates would report false skips on the very first run.
_COUNTED_TABLES = ("fact_session", "fact_message", "fact_tool_use")


# ---------------------------------------------------------------------------
# IngestAdapter protocol (M5) -- discover + parse, source-agnostic
# ---------------------------------------------------------------------------


@dataclass
class SourceUnit:
    """One discoverable unit of ingestable work -- the adapter protocol's
    generalization of SessionFile (one transcript file) / one JSONL event
    file. native_stream_id is the identity stream_key_for keys off; id is
    adapter-defined and stable across runs."""

    id: str
    path: Path
    native_stream_id: str
    meta: dict | None = None


@dataclass
class RawEvent:
    """One adapter-parsed event, pre-key-derivation. Fields map directly
    onto Event's non-lineage columns; key derivation, registry
    validation, and lineage stamping happen in the ingest orchestrator
    (ingest_events), not here -- adapters only parse."""

    id: str | None
    type: str
    timestamp: datetime | None
    actor: str | None
    payload: dict | None
    content_text: str | None = None


@runtime_checkable
class IngestAdapter(Protocol):
    """Protocol every ingest source implements (M5): discover() finds
    ingestable units under a root; parse() streams typed events out of one
    unit. TranscriptAdapter and JsonlEventAdapter are the two reference
    implementations -- TranscriptAdapter continues to write the typed
    fact_session/fact_message/fact_tool_use tables exactly as
    ingest_transcripts() always has (typed tables are projections for
    sources rich enough to deserve them); JsonlEventAdapter writes the
    generic fact_event grain via ingest_events().

    An adapter MAY additionally define `normalize(self, text: str) -> str`
    (amendment 6's optional template-mining hook) -- ingest_events() calls
    it when present to fill Event.signature. There is no abstract method
    for it here because typing.Protocol cannot express "optional method";
    callers probe with hasattr() instead.
    """

    def discover(
        self, root: str | Path, since: datetime | None = None,
    ) -> list[SourceUnit]:
        ...

    def parse(self, unit: SourceUnit) -> Iterator[RawEvent]:
        ...


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _blocks(content) -> list:
    """Normalize a message content payload (str or block list) to blocks."""
    if content is None:
        return []
    if isinstance(content, str):
        return [TextBlock(type="text", text=content)]
    if isinstance(content, list):
        return [parse_content_block(b) for b in content if isinstance(b, dict)]
    return []


def _text_of(blocks: list) -> str:
    return "\n".join(b.text for b in blocks if isinstance(b, TextBlock) and b.text)


def _thinking_of(blocks: list) -> str | None:
    """The turn's reasoning, kept verbatim.

    Separate from _text_of on purpose: thinking is not what the agent said, it
    is why, and conflating them would make the two impossible to tell apart
    downstream.
    """
    parts = [b.thinking for b in blocks
             if isinstance(b, ThinkingBlock) and b.thinking]
    return "\n".join(parts) or None


def _result_text(content) -> str | None:
    """Flatten a tool_result content payload to a bounded string."""
    if content is None:
        return None
    if isinstance(content, str):
        return content[:_RESULT_TEXT_MAX]
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content
                 if isinstance(b, dict) and b.get("type") == "text"]
        joined = "\n".join(p for p in parts if p)
        return joined[:_RESULT_TEXT_MAX] if joined else None
    return None


class TranscriptAdapter:
    """IngestAdapter conformance for Claude Code transcripts. discover()
    and parse() reuse the same discovery/parsing primitives as
    ingest_transcripts()/_ingest_file() below, but ingest_transcripts()
    itself is untouched and remains the production write path (typed
    fact_session/fact_message/fact_tool_use tables -- typed tables are
    projections for sources rich enough to deserve them). This class
    exists so transcripts satisfy IngestAdapter's shape alongside
    JsonlEventAdapter; it does not replace the existing pipeline, and
    nothing in ingest_transcripts() routes through it."""

    def discover(
        self, root: str | Path, since: datetime | None = None,
    ) -> list[SourceUnit]:
        return [
            SourceUnit(
                id=sf.path_identity or sf.path.stem,
                path=sf.path,
                native_stream_id=sf.path_identity or sf.path.stem,
                meta=sf.meta,
            )
            for sf in discover_sessions(root, since=since)
        ]

    def parse(self, unit: SourceUnit) -> Iterator[RawEvent]:
        for entry in iter_typed_entries(unit.path):
            ts = _parse_ts(getattr(entry, "timestamp", None))
            if isinstance(entry, UserEntry):
                blocks = _blocks((entry.message or {}).get("content"))
                yield RawEvent(
                    id=entry.uuid, type="user_message", timestamp=ts,
                    actor="user", payload=None,
                    content_text=_text_of(blocks) or None,
                )
            elif isinstance(entry, AssistantEntry):
                msg = entry.message or {}
                blocks = _blocks(msg.get("content"))
                yield RawEvent(
                    id=entry.uuid, type="assistant_message", timestamp=ts,
                    actor="assistant",
                    payload={"model": msg["model"]} if msg.get("model") else None,
                    content_text=_text_of(blocks) or None,
                )


# ---------------------------------------------------------------------------
# Signature masking (amendment 6: optional normalization hook)
# ---------------------------------------------------------------------------

_SIG_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
_SIG_QUOTED_RE = re.compile(r'"[^"]*"|\'[^\']*\'')
_SIG_HEX_RE = re.compile(r"\b[0-9a-fA-F]{8,}\b")
# Any digit run, not \b\d+\b: variable numbers routinely carry unit
# suffixes ("382s", "48ms", "2MB") or id prefixes ("run4521"), and a
# word-boundary pattern leaves those unmasked -- two events with the same
# template would then get different signatures, defeating the signature's
# whole purpose (caught live on the first M5 smoke test).
_SIG_NUMBER_RE = re.compile(r"\d+")


def mask_signature(text: str) -> str:
    """Drain-style-lite template signature: mask variable-shaped
    substrings (UUIDs, quoted strings, hex strings >= 8 chars, bare
    numbers) to stable placeholders, so high-volume variable text
    collapses to a shared signature (docs/implementation-plan.md
    amendment 6, "storage split made explicit"). Order matters -- UUIDs
    and quoted strings are masked whole before the looser hex/number
    passes run, so a UUID's hyphen-separated segments don't get partially
    masked and a number inside a quoted string doesn't leak out as a
    separate placeholder.

    This is NOT real template mining (no token clustering, no learned
    templates, no external deps) -- it is a cheap, deterministic
    normalization step good enough to collapse the obvious cases. A later
    milestone can swap in Drain proper without changing the
    fact_event.signature contract (one VARCHAR column).
    """
    masked = _SIG_UUID_RE.sub("<UUID>", text)
    masked = _SIG_QUOTED_RE.sub("<STR>", masked)
    masked = _SIG_HEX_RE.sub("<HEX>", masked)
    masked = _SIG_NUMBER_RE.sub("<NUM>", masked)
    return masked


class JsonlEventAdapter:
    """Reference IngestAdapter for newline-delimited JSON event streams:
    one file per stream (native_stream_id = the file's path relative to
    root), one JSON object per line: {id, type, timestamp, actor, payload}
    plus an optional "text" field. The smallest possible proof that a
    non-transcript source flows end-to-end into fact_event idempotently
    (M5's goal). normalize() is the amendment-6 hook: ingest_events()
    calls it (via hasattr) to fill Event.signature from content_text."""

    def discover(
        self, root: str | Path, since: datetime | None = None,
    ) -> list[SourceUnit]:
        root = Path(root)
        if not root.is_dir():
            return []
        units = []
        for path in sorted(root.rglob("*.jsonl")):
            if since is not None:
                mtime = datetime.fromtimestamp(path.stat().st_mtime)
                if mtime < since:
                    continue
            rel = path.relative_to(root).as_posix()
            units.append(SourceUnit(id=rel, path=path, native_stream_id=rel))
        return units

    def parse(self, unit: SourceUnit) -> Iterator[RawEvent]:
        with open(unit.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                yield RawEvent(
                    id=str(row["id"]) if row.get("id") is not None else None,
                    type=row.get("type") or "unknown",
                    timestamp=_parse_ts(row.get("timestamp")),
                    actor=row.get("actor"),
                    payload=row.get("payload"),
                    content_text=row.get("text"),
                )

    def normalize(self, text: str) -> str:
        return mask_signature(text)


def _ingest_file(store: ExperimentStore, sf: SessionFile, etl_run_id: str) -> tuple[int, int]:
    """Ingest one transcript file.

    Returns (entries_read, rows_attempted) where rows_attempted counts
    the session row plus every message/tool-use insert this run tried
    (whether it wrote or skipped on an existing key).
    """
    session_id: str | None = None
    cwd: str | None = None
    first_user_text: str | None = None
    last_model: str | None = None
    last_ts: datetime | None = None
    messages: list[Message] = []
    tool_uses: list[dict] = []          # accumulated tool_use blocks
    tool_results: dict[str, dict] = {}  # tool_use_id -> {is_error, text}
    entries_read = 0

    for seq, entry in enumerate(iter_typed_entries(sf.path)):
        entries_read += 1
        if session_id is None and getattr(entry, "session_id", None):
            session_id = entry.session_id
        if cwd is None and getattr(entry, "cwd", None):
            cwd = entry.cwd
        ts = _parse_ts(getattr(entry, "timestamp", None))
        if ts is not None and (last_ts is None or ts > last_ts):
            last_ts = ts

        if isinstance(entry, UserEntry):
            blocks = _blocks((entry.message or {}).get("content"))
            text = _text_of(blocks)
            if first_user_text is None and text and not entry.is_meta:
                first_user_text = text
            for b in blocks:
                if isinstance(b, ToolResultBlock) and b.tool_use_id:
                    tool_results[b.tool_use_id] = {
                        "is_error": b.is_error,
                        "text": _result_text(b.content),
                    }
            messages.append(Message(
                session_key="",  # filled in after session_key is known
                role=MessageRole.USER,
                entry_uuid=entry.uuid,
                parent_uuid=entry.parent_uuid,
                sequence_num=seq,
                occurred_at=ts,
                content_text=text or None,
                is_meta=bool(entry.is_meta),
                is_sidechain=bool(entry.is_sidechain),
                is_compact_summary=bool(getattr(entry, "is_compact_summary", False)),
                etl_run_id=etl_run_id,
            ))
        elif isinstance(entry, AssistantEntry):
            msg = entry.message or {}
            blocks = _blocks(msg.get("content"))
            usage = msg.get("usage") or {}
            if msg.get("model"):
                last_model = msg["model"]
            for b in blocks:
                if isinstance(b, ToolUseBlock):
                    tool_uses.append({
                        "tool_use_id": b.id,
                        "tool_name": b.name,
                        "tool_input": b.input if isinstance(b.input, dict) else None,
                        "entry_uuid": entry.uuid,
                        "sequence_num": seq,
                        "occurred_at": ts,
                    })
            messages.append(Message(
                session_key="",
                role=MessageRole.ASSISTANT,
                entry_uuid=entry.uuid,
                parent_uuid=entry.parent_uuid,
                sequence_num=seq,
                occurred_at=ts,
                content_text=_text_of(blocks) or None,
                has_thinking=any(isinstance(b, ThinkingBlock) for b in blocks),
                thinking_text=_thinking_of(blocks),
                stop_reason=msg.get("stop_reason"),
                input_tokens=usage.get("input_tokens"),
                output_tokens=usage.get("output_tokens"),
                is_meta=bool(entry.is_meta),
                is_sidechain=bool(entry.is_sidechain),
                etl_run_id=etl_run_id,
            ))

    # Subagent identity comes from the path (SessionFile.path_identity),
    # never the internal sessionId, which is the parent's.
    native_session_id = sf.path_identity or session_id or sf.path.stem
    project_path = cwd or sf.project_dir
    project_key = store.ensure_project(Project(
        project_path=project_path,
        project_name=Path(project_path).name,
        record_source=RecordSource.TRANSCRIPT_INGEST,
    ))

    meta = sf.meta or {}
    if sf.is_subagent:
        task_description = meta.get("description") or first_user_text
        task_type = meta.get("agentType")
        parent_session_key = ExperimentStore.session_key_for(
            RecordSource.TRANSCRIPT_INGEST, sf.parent_native_session_id)
    else:
        task_description = first_user_text
        task_type = None
        parent_session_key = None
    if task_description:
        task_description = task_description[:_TASK_DESCRIPTION_MAX]

    session_key = store.insert_session(Session(
        native_session_id=native_session_id,
        project_key=project_key,
        task_description=task_description,
        task_type=task_type,
        parent_session_key=parent_session_key,
        agent_role=AgentRole.SUBAGENT if sf.is_subagent else AgentRole.ORCHESTRATOR,
        model_used=last_model,
        status=SessionStatus.COMPLETED,
        record_source=RecordSource.TRANSCRIPT_INGEST,
        etl_run_id=etl_run_id,
    ))
    # Accumulating snapshot: resumed sessions grow; advance the end time.
    store.update_session_progress(
        session_key, completed_at=last_ts, model_used=last_model)

    # Bulk inserts: one existing-key fetch per table, then inserts for the
    # misses only -- the batched existence check is what makes unchanged
    # re-ingest cheap. insert_messages returns the entry_uuid ->
    # message_key map so the key recipe stays in the store.
    for msg in messages:
        msg.session_key = session_key
        msg.project_key = project_key
    message_keys = store.insert_messages(messages)

    tool_use_rows = []
    for tu in tool_uses:
        result = tool_results.get(tu["tool_use_id"], {})
        tool_use_rows.append(ToolUse(
            session_key=session_key,
            project_key=project_key,
            message_key=message_keys.get(tu["entry_uuid"]),
            tool_use_id=tu["tool_use_id"],
            tool_name=tu["tool_name"],
            tool_input=tu["tool_input"],
            is_error=result.get("is_error"),
            result_text=result.get("text"),
            sequence_num=tu["sequence_num"],
            occurred_at=tu["occurred_at"],
            etl_run_id=etl_run_id,
        ))
    store.insert_tool_uses(tool_use_rows)

    attempted = 1 + len(messages) + len(tool_uses)
    return entries_read, attempted


def ingest_transcripts(
    store: ExperimentStore,
    *,
    root: str | Path | None = None,
    project: str | None = None,
    since: datetime | None = None,
) -> dict:
    """Ingest Claude Code transcripts into the warehouse.

    Returns stats: {etl_run_id, sessions, rows_read, rows_written,
    rows_skipped}. The same numbers land in meta_load_log.
    """
    root = Path(root) if root is not None else default_projects_root()
    files = discover_sessions(root, project=project, since=since)
    # Roots before subagents so parent sessions exist first (no FK, but
    # it keeps parent_session_key references resolvable mid-run).
    files.sort(key=lambda f: f.is_subagent)

    with store.load_run("ingest_transcripts",
                        record_source=RecordSource.TRANSCRIPT_INGEST) as stats:
        before = {t: store.count_rows(t) for t in _COUNTED_TABLES}
        attempted = 0
        for sf in files:
            with store.transaction():
                file_read, file_attempted = _ingest_file(
                    store, sf, stats.etl_run_id)
            stats.rows_read += file_read
            attempted += file_attempted
        after = {t: store.count_rows(t) for t in _COUNTED_TABLES}
        stats.rows_written = sum(after[t] - before[t] for t in _COUNTED_TABLES)
        stats.rows_skipped = max(0, attempted - stats.rows_written)

    return {
        "sessions": len(files),
        "etl_run_id": stats.etl_run_id,
        "rows_read": stats.rows_read,
        "rows_written": stats.rows_written,
        "rows_skipped": stats.rows_skipped,
    }


def _ensure_event_type(store: ExperimentStore, event_type: str) -> str:
    """Register event_type if unseen; idempotent, mirrors couch's
    register-before-write pattern for finding_type."""
    existing = store.get_event_type(event_type)
    if existing is not None:
        return existing.event_type_key
    return store.register_event_type(EventType(
        event_type=event_type, record_source=RecordSource.EVENT_INGEST,
    ))


def ingest_events(
    store: ExperimentStore,
    *,
    root: str | Path,
    stream_type: str | None = None,
    since: datetime | None = None,
) -> dict:
    """Ingest a generic newline-delimited JSON event stream into
    fact_event via JsonlEventAdapter -- M5's proof that a non-transcript
    source flows end-to-end through the same idempotent, lineage-stamped
    path as transcripts. Registers each distinct event type in
    dim_event_type (record_source=event_ingest) before writing rows.

    stream_type is accepted but not yet used to select among adapters --
    there is exactly one reference adapter today (JsonlEventAdapter); the
    parameter is reserved so this function's shape doesn't need to change
    when a second adapter lands.

    Returns stats: {etl_run_id, streams, rows_read, rows_written,
    rows_skipped}. The same numbers land in meta_load_log.
    """
    adapter = JsonlEventAdapter()
    units = adapter.discover(root, since=since)

    with store.load_run("ingest_events",
                        record_source=RecordSource.EVENT_INGEST) as stats:
        before = store.count_rows("fact_event")
        attempted = 0
        registered_types: set[str] = set()
        for unit in units:
            stream_key = store.stream_key_for(
                RecordSource.EVENT_INGEST, unit.native_stream_id)
            events: list[Event] = []
            for seq, raw in enumerate(adapter.parse(unit)):
                stats.rows_read += 1
                if raw.type not in registered_types:
                    _ensure_event_type(store, raw.type)
                    registered_types.add(raw.type)
                signature = None
                if raw.content_text and hasattr(adapter, "normalize"):
                    signature = adapter.normalize(raw.content_text)
                events.append(Event(
                    stream_key=stream_key,
                    native_event_id=raw.id,
                    event_type=raw.type,
                    occurred_at=raw.timestamp,
                    actor=raw.actor,
                    payload=raw.payload,
                    content_text=raw.content_text,
                    signature=signature,
                    sequence_num=seq,
                    record_source=RecordSource.EVENT_INGEST,
                    etl_run_id=stats.etl_run_id,
                ))
            with store.transaction():
                store.insert_events(events)
            attempted += len(events)
        after = store.count_rows("fact_event")
        stats.rows_written = after - before
        stats.rows_skipped = max(0, attempted - stats.rows_written)

    return {
        "streams": len(units),
        "etl_run_id": stats.etl_run_id,
        "rows_read": stats.rows_read,
        "rows_written": stats.rows_written,
        "rows_skipped": stats.rows_skipped,
    }


# ---------------------------------------------------------------------------
# Labels on messages (fact_message_facets)
# ---------------------------------------------------------------------------

# Choice values, question ids and labeler names must be slugs. That keeps
# free text -- and so transcript text -- out of the label table by
# construction, and it is what makes finding summaries built from label
# values safe to compile.
_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_VERSION_RE = re.compile(r"^v?([1-9][0-9]*)$")
_LABEL_SOURCE_MAX = 200

# Text the client or a hook writes into the user role. An exchange unit is
# a reply a person typed, so a label on any of these is refused -- the same
# typed-reply rule the labelers apply, enforced again here so a labeler bug
# cannot put findings on command output or a hook's reminder. Shell-mode
# records (a `!` command and its output) are included: the command is typed,
# but it is a shell line, not a reply to the assistant.
INJECTED_USER_PREFIXES = [
    "<command-name>", "<command-message>", "<command-args>",
    "<local-command-stdout>", "<local-command-stderr>",
    "<bash-input>", "<bash-stdout>", "<bash-stderr>",
    "<system-reminder>", "[Request interrupted by user",
]

# Question type -> how its value is stored.
_QUESTION_OUTPUT = {
    "choice": FacetOutputType.TEXT,
    "score": FacetOutputType.NUMERIC,
}


def options_hash(pairs: list[list[str]]) -> str:
    """sha256 of the ordered [label, description] option pairs, the
    serialization agreed with the labeler: compact JSON, non-ASCII kept,
    UTF-8. Byte-identical to JSON.stringify(pairs) in JavaScript."""
    return hashlib.sha256(
        json.dumps(pairs, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _parse_question_version(raw) -> int | None:
    """Accept N or "vN" (N >= 1); anything else is None."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw if raw >= 1 else None
    if isinstance(raw, str):
        m = _VERSION_RE.match(raw.strip())
        return int(m.group(1)) if m else None
    return None


def _is_slug(val) -> bool:
    return isinstance(val, str) and bool(_SLUG_RE.match(val))


def _is_number(val) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool)


def _is_probability(val) -> bool:
    return _is_number(val) and 0.0 <= float(val) <= 1.0


def _question_definition(row: dict) -> str:
    """The stored definition of a question: type, text and static
    options, serialized so an edited question under the same version is
    detectable rather than silently merged."""
    return orjson.dumps(
        {"type": row.get("type"), "text": row.get("text"),
         "options": row.get("options")},
        option=orjson.OPT_SORT_KEYS,
    ).decode("utf-8")


def register_label_questions(store: ExperimentStore, path: str | Path) -> int:
    """Register each question in a questions.jsonl file as a
    dim_facet_type row (facet_id = question_id, prompt_version = the
    parsed question_version, prompt_text = the full definition).

    Idempotent for an unchanged question. A question whose definition
    changed under the same version raises: a changed prompt is a new
    version, never an edit, or labels made under the old wording become
    indistinguishable from labels made under the new one.

    Returns the number of newly registered questions.
    """
    registered = 0
    for lineno, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = orjson.loads(line)
        except orjson.JSONDecodeError as e:
            raise ValueError(f"questions line {lineno}: not JSON") from e
        qid = row.get("question_id")
        version = _parse_question_version(row.get("question_version"))
        output_type = _QUESTION_OUTPUT.get(row.get("type"))
        if not _is_slug(qid) or version is None or output_type is None:
            raise ValueError(
                f"questions line {lineno}: needs a slug question_id, a "
                f"question_version (N or vN) and type choice|score")
        definition = _question_definition(row)
        existing = store.get_facet_type(qid, version)
        if existing is not None:
            # A question first registered from labels alone has no stored
            # definition; there is nothing to conflict with, and registry
            # rows are append-only, so it keeps its empty text.
            if existing.prompt_text is not None and existing.prompt_text != definition:
                raise ValueError(
                    f"Question {qid} v{version} is already registered with a "
                    f"different definition -- bump question_version instead "
                    f"of editing it")
            continue
        store.register_facet_type(FacetType(
            facet_id=qid, prompt_version=version,
            method=FacetMethod.TYPED_MODEL, output_type=output_type,
            prompt_text=definition,
            description="Exchange label question",
            record_source=RecordSource.LABEL_INGEST,
        ))
        registered += 1
    return registered


def _label_from_row(
    store: ExperimentStore, row: dict, etl_run_id: str,
    inferred_types: dict[tuple[str, int], FacetOutputType],
) -> tuple[MessageFacet | None, str | None]:
    """Validate one label row and build its MessageFacet. Returns
    (facet, None) or (None, reject_reason). Existence of the labeled
    messages is checked later, for the whole file in one query."""
    try:
        unit_type = LabelUnit(row.get("unit_type"))
    except ValueError:
        return None, "bad_unit_type"
    try:
        labeler_kind = LabelerKind(row.get("labeler_kind"))
    except ValueError:
        return None, "bad_labeler_kind"
    native_session_id = row.get("native_session_id")
    user_uuid = row.get("user_entry_uuid")
    if not isinstance(native_session_id, str) or not native_session_id \
            or not isinstance(user_uuid, str) or not user_uuid:
        return None, "missing_unit_key"
    assistant_uuid = row.get("assistant_entry_uuid")
    if assistant_uuid is not None and not isinstance(assistant_uuid, str):
        return None, "missing_unit_key"
    qid = row.get("question_id")
    version = _parse_question_version(row.get("question_version"))
    if not _is_slug(qid) or version is None:
        return None, "bad_question"
    labeler = row.get("labeler")
    labeler_version = row.get("labeler_version")
    if not _is_slug(labeler) or (labeler_version is not None and not _is_slug(labeler_version)):
        return None, "bad_labeler"

    probability = row.get("probability")
    probabilities = row.get("probabilities")
    confidence = row.get("confidence")
    if labeler_kind != LabelerKind.MODEL and (
            probability is not None or probabilities is not None):
        # A probability on a person's, rule's or key's label means the row
        # is mislabeled -- and a mislabeled model row in the human slice is
        # the contamination the kind column exists to prevent.
        return None, "probability_on_non_model"
    if labeler_kind == LabelerKind.MODEL and probability is None:
        # The detectors' probability floor applies to model labels; one
        # with no probability would otherwise pass it as if certain.
        return None, "missing_probability"
    if probability is not None and not _is_probability(probability):
        return None, "bad_probability"
    if probabilities is not None and not (
            isinstance(probabilities, dict)
            and all(_is_slug(k) and _is_probability(v) for k, v in probabilities.items())):
        return None, "bad_probability"
    if confidence is not None and not _is_number(confidence):
        return None, "bad_probability"

    for field in ("options_hash", "input_content_hash"):
        val = row.get(field)
        if val is not None and not (isinstance(val, str) and _HEX64_RE.match(val)):
            return None, "bad_hash"
    state_truncated = row.get("state_truncated", False)
    if not isinstance(state_truncated, bool):
        return None, "bad_state_truncated"
    label_source = row.get("source")
    if label_source is not None and (
            not isinstance(label_source, str) or len(label_source) > _LABEL_SOURCE_MAX):
        return None, "bad_source"
    raw_labeled_at = row.get("labeled_at")
    labeled_at = None
    if raw_labeled_at is not None:
        labeled_at = _parse_ts(raw_labeled_at) if isinstance(raw_labeled_at, str) else None
        if labeled_at is None:
            return None, "bad_labeled_at"

    ft = store.get_facet_type(qid, version)
    value = row.get("value")
    if ft is not None:
        output_type = ft.output_type
    elif (qid, version) in inferred_types:
        output_type = inferred_types[(qid, version)]
    else:
        # No questions file defined this question. Infer its type from the
        # first value seen; it is registered later, and only if a label
        # using it survives every check.
        if _is_slug(value):
            output_type = FacetOutputType.TEXT
        elif _is_number(value):
            output_type = FacetOutputType.NUMERIC
        else:
            return None, "bad_value"
        inferred_types[(qid, version)] = output_type
    value_text = value_numeric = None
    if output_type == FacetOutputType.TEXT:
        if not _is_slug(value):
            return None, "bad_value"
        value_text = value
    elif output_type == FacetOutputType.NUMERIC:
        if not _is_number(value):
            return None, "bad_value"
        value_numeric = float(value)
    else:
        return None, "bad_value"

    session_key = store.session_key_for(RecordSource.TRANSCRIPT_INGEST, native_session_id)
    return MessageFacet(
        unit_type=unit_type,
        session_key=session_key,
        message_key=store.message_key_for(session_key, user_uuid),
        context_message_key=(store.message_key_for(session_key, assistant_uuid)
                             if assistant_uuid else None),
        facet_id=qid,
        prompt_version=version,
        options_hash=row.get("options_hash"),
        labeler_kind=labeler_kind,
        labeler=labeler,
        labeler_version=labeler_version,
        value_text=value_text,
        value_numeric=value_numeric,
        probability=float(probability) if probability is not None else None,
        probabilities=probabilities,
        confidence=float(confidence) if confidence is not None else None,
        input_content_hash=row.get("input_content_hash"),
        state_truncated=state_truncated,
        labeled_at=labeled_at,
        label_source=label_source,
        record_source=RecordSource.LABEL_INGEST,
        etl_run_id=etl_run_id,
    ), None


def _typed_reply_reject(ref: dict, context_message_key: str | None) -> str | None:
    """Why a user message is not a typed reply, or None if it is. An
    exchange unit is text a person typed in the main session, answering an
    assistant turn."""
    if not ref["has_text"]:
        return "no_text"  # e.g. a tool-result carrier
    if ref["is_meta"]:
        return "meta_entry"
    if ref["is_compact_summary"]:
        return "compact_summary"
    if ref["is_sidechain"]:
        return "subagent_message"  # its "user" is the orchestrating agent
    if ref["is_injected"]:
        return "injected_text"
    if context_message_key is None:
        return "no_assistant_turn"  # e.g. a session's opening prompt
    return None


def ingest_labels(
    store: ExperimentStore,
    *,
    path: str | Path,
    questions: str | Path | None = None,
) -> dict:
    """Load a label JSONL file into fact_message_facets.

    Each row labels one already-ingested user message (keyed by
    native_session_id + user_entry_uuid, the same recipe transcript
    ingest uses). Rows that fail validation, or whose messages are not in
    the warehouse, are rejected and counted by reason -- never written
    partially. Re-ingesting the same file writes nothing.

    questions: optional questions.jsonl, registered first so each
    question carries its full definition.

    Returns {etl_run_id, questions_registered, rows_read, rows_written,
    rows_existing, rejected: {reason: count}}. The load log records
    rows_skipped = rows_read - rows_written (existing plus rejected).
    """
    path = Path(path)
    # One transaction for the whole file: a failure part-way leaves no
    # registered questions and no labels behind.
    with store.load_run("ingest_labels", record_source=RecordSource.LABEL_INGEST) as stats, \
            store.transaction():
        questions_registered = (register_label_questions(store, questions)
                                if questions is not None else 0)
        inferred_types: dict[tuple[str, int], FacetOutputType] = {}
        rejected: Counter[str] = Counter()
        candidates: list[MessageFacet] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            stats.rows_read += 1
            try:
                row = orjson.loads(line)
            except orjson.JSONDecodeError:
                rejected["malformed"] += 1
                continue
            if not isinstance(row, dict):
                rejected["malformed"] += 1
                continue
            facet, reason = _label_from_row(store, row, stats.etl_run_id, inferred_types)
            if facet is None:
                rejected[reason] += 1
            else:
                candidates.append(facet)

        refs = store.get_message_refs(
            [f.message_key for f in candidates]
            + [f.context_message_key for f in candidates if f.context_message_key],
            injected_prefixes=INJECTED_USER_PREFIXES)
        valid: list[MessageFacet] = []
        for f in candidates:
            ref = refs.get(f.message_key)
            reason = None
            if ref is None:
                reason = "unknown_message"
            elif ref["role"] != MessageRole.USER.value:
                reason = "not_user_message"
            elif f.unit_type == LabelUnit.EXCHANGE:
                reason = _typed_reply_reject(ref, f.context_message_key)
            if reason is None and f.context_message_key and (
                    refs.get(f.context_message_key) is None
                    or refs[f.context_message_key]["role"] != MessageRole.ASSISTANT.value):
                reason = "unknown_context"
            if reason:
                rejected[reason] += 1
            else:
                valid.append(f)

        for qid, version in sorted({(f.facet_id, f.prompt_version) for f in valid}):
            if (qid, version) in inferred_types:
                store.register_facet_type(FacetType(
                    facet_id=qid, prompt_version=version,
                    method=FacetMethod.TYPED_MODEL,
                    output_type=inferred_types[(qid, version)],
                    description="Exchange label question (registered from "
                                "labels; no definition supplied)",
                    record_source=RecordSource.LABEL_INGEST,
                ))
                questions_registered += 1
        stats.rows_written = store.insert_message_facets(valid)
        stats.rows_skipped = stats.rows_read - stats.rows_written

    return {
        "etl_run_id": stats.etl_run_id,
        "questions_registered": questions_registered,
        "rows_read": stats.rows_read,
        "rows_written": stats.rows_written,
        "rows_existing": len(valid) - stats.rows_written,
        "rejected": dict(sorted(rejected.items())),
    }
