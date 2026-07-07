"""Transcript ingestion: JSONL session files into the warehouse (Phase 1: sense).

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
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from freud_schema.discovery import SessionFile, default_projects_root, discover_sessions
from freud_schema.store import ExperimentStore
from freud_schema.tables import (
    AgentRole,
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
