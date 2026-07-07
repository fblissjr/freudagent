"""Transcript discovery for Claude Code's projects directory (Phase 1: sense).

Built fresh against the layout verified on disk 2026-07-07 (ccutils'
discovery module targets an obsolete flat layout and is deliberately
not reused). Under `<HOME>/.claude/projects`:

    <encoded-project>/<session-uuid>.jsonl            root sessions
    <encoded-project>/<session-uuid>/subagents/
        agent-<id>.jsonl                              subagent sessions
        agent-<id>.meta.json                          {agentType, description, toolUseId}

Subagent transcripts carry the PARENT's sessionId inside the file
(verified 100% on real data 2026-07-07), so a subagent's identity must
be derived from its path (parent uuid + agent id), never from the
internal field. The optional .meta.json sidecar names the spawning
agent type and the parent's Agent tool_use id.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class SessionFile:
    """One discovered transcript file, root or subagent."""

    path: Path
    project_dir: str
    parent_native_session_id: str | None = None
    agent_id: str | None = None
    meta: dict | None = None

    @property
    def is_subagent(self) -> bool:
        return self.parent_native_session_id is not None


def default_projects_root() -> Path:
    """Claude Code's transcript root for the current user."""
    return Path.home() / ".claude" / "projects"


def _load_meta(jsonl_path: Path) -> dict | None:
    meta_path = jsonl_path.with_name(jsonl_path.stem + ".meta.json")
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _mtime_ok(path: Path, since: datetime | None) -> bool:
    if since is None:
        return True
    return datetime.fromtimestamp(path.stat().st_mtime) >= since


def discover_sessions(
    root: str | Path,
    project: str | None = None,
    since: datetime | None = None,
) -> list[SessionFile]:
    """Find all session transcripts under a projects root.

    project: substring filter against the encoded project directory name.
    since: only files modified at or after this time (incremental ingest).
    """
    root = Path(root)
    found: list[SessionFile] = []
    if not root.is_dir():
        return found

    for proj_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        if project and project not in proj_dir.name:
            continue
        # Root sessions: top-level <uuid>.jsonl
        for f in sorted(proj_dir.glob("*.jsonl")):
            if _mtime_ok(f, since):
                found.append(SessionFile(path=f, project_dir=proj_dir.name))
        # Subagent sessions: <parent-uuid>/subagents/agent-<id>.jsonl
        for f in sorted(proj_dir.glob("*/subagents/agent-*.jsonl")):
            if not _mtime_ok(f, since):
                continue
            found.append(SessionFile(
                path=f,
                project_dir=proj_dir.name,
                parent_native_session_id=f.parent.parent.name,
                agent_id=f.stem.removeprefix("agent-"),
                meta=_load_meta(f),
            ))
    return found
