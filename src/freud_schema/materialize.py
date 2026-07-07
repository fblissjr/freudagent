"""The materialize stage (the ego): compile dimension rows into the files
Claude Code actually loads (Phase 3 of the meta-harness plan).

Compiler model, not advisor model: the warehouse is the source of truth;
.claude/rules/*.md is build output. Every compiled file carries a
do-not-edit header, a source line naming the dimension row and its
effective_from (the version identity), and -- when the rule came through
the flywheel -- a provenance footer naming the approving proposal and
its evidence findings. Rollback = store.rollback_dimension + recompile.

Managed-file hygiene: recompilation removes files for rules that are no
longer current+active, but ONLY files carrying the compiled marker --
hand-written files in the same directory are never touched.

Privacy gate (fail-closed): a rendered file containing a home-directory
path or the OS username is NOT written. Fail-closed also means the last
good compile of that rule survives -- a blocked name is neither written
nor removed. Compiled artifacts may be committed to repos; they must be
clean by construction, and this gate is the backstop when they aren't.
"""

from __future__ import annotations

import getpass
import re
from pathlib import Path

from freud_schema.store import ExperimentStore
from freud_schema.tables import Rule, RuleScope, RuleStatus

COMPILED_MARKER = "<!-- compiled by freud-schema"

_HOME_PATH_RE = re.compile(r"/(?:Users|home)/[A-Za-z0-9_.\-]+")  # path-privacy: ignore


def _find_leaks(text: str) -> list[str]:
    leaks = [m.group(0) for m in _HOME_PATH_RE.finditer(text)]
    username = getpass.getuser()
    if username and username in text:
        leaks.append(f"username '{username}'")
    return leaks


def _provenance(store: ExperimentStore, rule_key: str) -> dict | None:
    """Latest approved proposal that produced this rule entity, if any."""
    return store._fetchone(
        """SELECT proposal_key, evidence_finding_keys FROM fact_proposal
           WHERE resulting_dimension_key = ? AND status = 'approved'
           ORDER BY reviewed_at DESC LIMIT 1""",
        [rule_key],
    )


def _render(store: ExperimentStore, rule: Rule) -> str:
    lines = [
        f"{COMPILED_MARKER}: do not edit; change the dimension row and recompile -->",
        f"<!-- source: dim_rule {rule.rule_key} "
        f"effective_from {rule.effective_from.isoformat() if rule.effective_from else '?'} -->",
        "",
        rule.content.rstrip(),
        "",
    ]
    prov = _provenance(store, rule.rule_key)
    if prov:
        evidence = prov["evidence_finding_keys"] or []
        finding_refs = ", ".join(k[:8] for k in evidence) or "none recorded"
        lines.append(
            f"<!-- provenance: proposal {prov['proposal_key'][:8]}; "
            f"findings {finding_refs} -->")
        lines.append("")
    return "\n".join(lines)


def compile_rules(
    store: ExperimentStore,
    out_dir: str | Path,
    scope: RuleScope | None = None,
) -> dict:
    """Render every current active rule to <out_dir>/<name>.md.

    Returns {written, removed, blocked}: blocked entries are
    {"file", "leaks"} dicts from the fail-closed privacy gate.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    rules = [r for r in store.list_rules()
             if r.status == RuleStatus.ACTIVE
             and (scope is None or r.scope == scope)]

    written: list[str] = []
    blocked: list[dict] = []
    keep: set[str] = set()

    for rule in sorted(rules, key=lambda r: r.name):
        fname = f"{rule.name}.md"
        body = _render(store, rule)
        leaks = _find_leaks(body)
        if leaks:
            blocked.append({"file": fname, "leaks": leaks})
            keep.add(fname)  # fail-closed: keep the last good compile
            continue
        keep.add(fname)
        path = out / fname
        if not path.exists() or path.read_text() != body:
            path.write_text(body)
        written.append(fname)

    removed: list[str] = []
    for f in sorted(out.glob("*.md")):
        if f.name in keep:
            continue
        try:
            managed = f.read_text().startswith(COMPILED_MARKER)
        except OSError:
            continue
        if managed:
            f.unlink()
            removed.append(f.name)

    return {"written": written, "removed": removed, "blocked": blocked}
