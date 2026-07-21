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
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

from freud_schema.discovery import SessionFile, default_projects_root, discover_sessions
from freud_schema.store import ExperimentStore
from freud_schema.tables import (
    AgentRole,
    Event,
    EventType,
    Message,
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
