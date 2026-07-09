"""Store-ops MCP server (M16): the harness's write surface during sessions.

Claude Code IS the harness, and the harness writes during sessions -- the
lock conventions in CLAUDE.md's old DuckDB MCP section optimized for
read-analysis only, which pushed native-row writes (rules, proposals,
approvals, compile) into a disconnect-the-MCP-server dance, and pushed the
LLM couch layer into writing findings via raw SQL with hand-derived keys
(the /couch skill's documented exception). This module retires both: one
process holds the DuckDB connection for the whole session, every write
goes through ops.py (the same dispatch layer the CLI uses, so the two
surfaces cannot drift), and reads get a real read-only SQL tool instead of
none at all.

Gate design (non-negotiable -- see docs/implementation-plan.md Track H,
Risk paragraph "self-modification without the human atom"):

  (a) rule_add/skill_add accept only the non-compiling status, regardless
      of what a caller asks for. Rules have no draft status; INACTIVE is
      the non-compiling analog (materialize.compile_rules only renders
      status=active). Skills force SkillStatus.DRAFT. Activation is only
      reachable through proposal_add -> proposal_approve.
  (b) proposal_approve is the one human atom's transport: its tool
      description opens with a sentence instructing operators to never
      allowlist it, so the harness's permission prompt fires on every
      call. reviewed_by is a required parameter -- there is no calling
      this tool anonymously.
  (c) query() is read-only, enforced by classify_readonly() at the parser
      level (single-statement, SELECT-type only) before anything reaches
      the connection -- this is what closes the CTE/ATTACH/COPY/PRAGMA
      smuggling bypass class.
  (d) No tool exposes db reset, db ddl, or any raw-write escape hatch.
      Every write tool is a thin wrapper over ops.py, which is itself a
      thin wrapper over ExperimentStore methods -- no new write logic
      lives in this module.
"""

from __future__ import annotations

import re
from datetime import datetime

import duckdb

from freud_schema import ops
from freud_schema.store import ExperimentStore
from freud_schema.tables import (
    CorrectionType,
    FindingScope,
    RuleScope,
    RuleStatus,
    SkillStatus,
    TargetDimension,
)

# Cap on rows returned by query() -- ad-hoc analysis should not be able to
# stream the whole warehouse back through a tool result.
_QUERY_ROW_CAP = 500


def classify_readonly(sql: str) -> None:
    """Raise ValueError unless `sql` is exactly one read-only SELECT.

    Parses at the statement level via duckdb.extract_statements() so
    INSERT/UPDATE/DELETE/DDL/ATTACH/COPY/EXPORT/PRAGMA(-as-SET) and
    multi-statement input ("SELECT 1; DROP TABLE x") are rejected before
    anything reaches the connection -- classification happens BEFORE
    execute, never by trusting a caller's claim that a string "is just a
    SELECT".

    EXPLAIN is deliberately NOT special-cased into an allowed form. DuckDB
    types `EXPLAIN <anything>` as StatementType.EXPLAIN regardless of what
    it wraps, and `EXPLAIN ANALYZE <write>` actually EXECUTES the wrapped
    statement (that's how it gathers runtime stats) -- so allowing EXPLAIN
    without inspecting the wrapped statement would open exactly the
    bypass this gate exists to close. extract_statements() does not expose
    the wrapped statement's type, so there is no cheap way to verify "it
    wraps a SELECT"; the safe fallback -- SELECT only -- is unconditional.
    """
    try:
        statements = duckdb.extract_statements(sql)
    except duckdb.Error as e:
        raise ValueError(f"Cannot parse SQL: {e}") from e
    if len(statements) != 1:
        raise ValueError(
            f"query() accepts exactly one statement, got {len(statements)}: {sql!r}"
        )
    stmt_type = statements[0].type
    if stmt_type != duckdb.StatementType.SELECT:
        raise ValueError(
            f"query() is read-only: expected a SELECT statement, got {stmt_type}"
        )
    # Belt and braces: DuckDB types read-only PRAGMAs (PRAGMA database_list)
    # as SELECT by rewriting them to pragma table functions, so parser type
    # alone lets PRAGMA through. A first-token allowlist closes that:
    # SELECT/WITH/FROM plus DuckDB's SELECT-typed introspection forms
    # (SHOW, DESCRIBE, SUMMARIZE) are the deliberate read surface;
    # everything else is rejected even when typed SELECT.
    first = re.match(
        r"\s*(?:--[^\n]*\n\s*|/\*.*?\*/\s*)*\(*\s*([A-Za-z]+)", sql, re.DOTALL)
    token = first.group(1).upper() if first else ""
    if token not in {"SELECT", "WITH", "FROM", "SHOW", "DESCRIBE", "SUMMARIZE"}:
        raise ValueError(
            f"query() is read-only: statement form '{token}' is not allowed "
            "(SELECT/WITH/FROM/SHOW/DESCRIBE/SUMMARIZE only)"
        )


def build_server(store: ExperimentStore, db_path: str | None = None):
    """Construct the FastMCP server and register every store-ops tool.

    Imports the mcp package inside this function (provider convention,
    same as ClaudeProvider/OpenAICompatProvider in orchestrator.py):
    importing freud_schema.mcp_server never requires the mcp extra;
    calling build_server()/serve() does.
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        raise ImportError(
            "MCP SDK not installed. Run: uv sync --extra mcp"
        ) from None

    server = FastMCP(
        "freud-schema",
        instructions=(
            f"Store-ops server for the freud-schema warehouse ({db_path or 'default DB'}). "
            "This process holds the single DuckDB connection for the session -- "
            "no other tool should also open this file. Reads: query(sql) is "
            "read-only (single SELECT statement only; writes/DDL/multi-statement "
            "input are rejected before they reach the connection). Writes: every "
            "write tool goes through the same dispatch layer the CLI uses. "
            "rule_add/skill_add always create non-compiling drafts -- the only "
            "path from a draft to something that loads into a session is "
            "proposal_add -> proposal_approve, and proposal_approve must never "
            "be allowlisted."
        ),
    )

    # -- Read-only --------------------------------------------------------

    @server.tool(
        name="query",
        description=(
            "Run a read-only SQL query against the warehouse. Exactly one "
            "SELECT statement (CTEs/WITH are fine); INSERT/UPDATE/DELETE/"
            "DDL/ATTACH/COPY/PRAGMA/multi-statement input is rejected before "
            "it reaches the connection. Rows are capped at 500; the result "
            "notes when output was truncated."
        ),
    )
    def query(sql: str) -> dict:
        classify_readonly(sql)
        cursor = store.con.execute(sql)
        if cursor.description is None:
            return {"columns": [], "rows": [], "truncated": False}
        columns = [d[0] for d in cursor.description]
        rows = cursor.fetchmany(_QUERY_ROW_CAP)
        truncated = cursor.fetchone() is not None
        return {
            "columns": columns,
            "rows": [list(r) for r in rows],
            "truncated": truncated,
        }

    # -- Gated writes: self-modification without the human atom -----------
    # See the module docstring's gate design (a). Both tools accept a
    # `status` argument so a caller can see what it asked for was ignored,
    # but the value passed to ops.* is always the non-compiling one.

    @server.tool(
        name="rule_add",
        description=(
            "Create or evolve a rule -- ALWAYS created with status=inactive, "
            "regardless of any status passed here. Inactive rules do not "
            "compile (materialize/compile only renders status=active rules "
            "into .claude/rules/*.md). To activate a rule, use proposal_add "
            "to propose it and proposal_approve (human approval gate) to "
            "apply it -- this tool cannot activate anything by itself."
        ),
    )
    def rule_add(
        name: str,
        content: str,
        scope: str = "global",
        domain: str | None = None,
        priority: int = 0,
        tenant_id: str = "default",
        status: str | None = None,  # accepted, always ignored -- see above
    ) -> dict:
        return ops.rule_add(
            store, name=name, content=content, scope=RuleScope(scope),
            domain=domain, priority=priority, tenant_id=tenant_id,
            status=RuleStatus.INACTIVE,
        )

    @server.tool(
        name="skill_add",
        description=(
            "Create a new skill version -- ALWAYS created with status=draft, "
            "regardless of any status passed here. Draft skills are not "
            "returned by get_active_skill and are not loaded into runner "
            "context. To activate a skill, use proposal_add to propose it "
            "and proposal_approve (human approval gate) to apply it -- this "
            "tool cannot activate anything by itself."
        ),
    )
    def skill_add(
        domain: str,
        task_type: str,
        content: str,
        version: int = 1,
        tenant_id: str = "default",
        status: str | None = None,  # accepted, always ignored -- see above
    ) -> dict:
        return ops.skill_add(
            store, domain=domain, task_type=task_type, content=content,
            version=version, tenant_id=tenant_id, status=SkillStatus.DRAFT,
        )

    # -- Ungated writes: no dimension activation reachable from these -----

    @server.tool(
        name="source_add",
        description=(
            "Register a source. hash_baseline=True records the file's "
            "sha256 as the staleness baseline couch's stale_source detector "
            "compares future reads against."
        ),
    )
    def source_add(
        path: str,
        media_type: str,
        tenant_id: str = "default",
        hash_baseline: bool = False,
    ) -> dict:
        return ops.source_add(
            store, path=path, media_type=media_type, tenant_id=tenant_id,
            hash_baseline=hash_baseline,
        )

    @server.tool(
        name="feedback_add",
        description=(
            "Add feedback (a human correction) on an extraction, closing "
            "the flywheel loop. extraction_key may be a full key or a "
            "unique prefix."
        ),
    )
    def feedback_add(
        extraction_key: str,
        correction_type: str,
        correction: dict,
        notes: str | None = None,
        created_by: str | None = None,
    ) -> dict:
        return ops.feedback_add(
            store, extraction_key=extraction_key,
            correction_type=CorrectionType(correction_type),
            correction=correction, notes=notes, created_by=created_by,
        )

    @server.tool(
        name="finding_add",
        description=(
            "Record one couch finding from LLM judgment (retires the /couch "
            "skill's raw-INSERT exception -- this is now the one write path "
            "for findings, same as every SQL detector). finding_type must "
            "already be registered in dim_finding_type."
        ),
    )
    def finding_add(
        finding_type: str,
        summary: str,
        scope: str = "project",
        project_key: str | None = None,
        evidence_session_keys: list[str] | None = None,
        occurrence_count: int | None = None,
    ) -> dict:
        return ops.finding_add(
            store, finding_type=finding_type, summary=summary,
            scope=FindingScope(scope), project_key=project_key,
            evidence_session_keys=evidence_session_keys,
            occurrence_count=occurrence_count,
        )

    @server.tool(
        name="extraction_validate",
        description="Mark an extraction validated. key may be a full key or a unique prefix.",
    )
    def extraction_validate(key: str, validated_by: str | None = None) -> dict:
        return ops.extraction_validate(store, key=key, validated_by=validated_by)

    @server.tool(
        name="extraction_reject",
        description="Mark an extraction rejected. key may be a full key or a unique prefix.",
    )
    def extraction_reject(key: str, validated_by: str | None = None) -> dict:
        return ops.extraction_reject(store, key=key, validated_by=validated_by)

    @server.tool(
        name="proposal_add",
        description=(
            "Draft a proposal (pending). Applies nothing by itself -- "
            "proposal_approve is the only path from here to an activated "
            "dimension row."
        ),
    )
    def proposal_add(
        target: str,
        natural_key: dict,
        content: str,
        version: int | None = None,
        evidence: list[str] | None = None,
    ) -> dict:
        return ops.proposal_add(
            store, target=TargetDimension(target), natural_key=natural_key,
            content=content, version=version, evidence=evidence,
        )

    @server.tool(
        name="proposal_reject",
        description="Reject a pending proposal. No dimension change is applied.",
    )
    def proposal_reject(key: str, reviewed_by: str | None = None) -> dict:
        return ops.proposal_reject(store, key=key, reviewed_by=reviewed_by)

    # -- The one human atom -------------------------------------------------
    # Gate design (b): this sentence is load-bearing. Whatever configures
    # tool permissions for this server must never put proposal_approve on
    # an allowlist -- every call has to surface the harness's permission
    # prompt, because that prompt IS the human atom's transport.

    @server.tool(
        name="proposal_approve",
        description=(
            "HUMAN APPROVAL GATE — never allowlist this tool; every call "
            "must surface the permission prompt. Approves a pending "
            "proposal, applying it to the target dimension (SCD-2 "
            "evolution) -- the only way a draft rule or skill created via "
            "rule_add/skill_add becomes something that compiles or loads "
            "into a session. reviewed_by is required: it records who "
            "clicked approve."
        ),
    )
    def proposal_approve(key: str, reviewed_by: str) -> dict:
        return ops.proposal_approve(store, key=key, reviewed_by=reviewed_by)

    # -- Analysis / lifecycle operations ------------------------------------

    @server.tool(
        name="couch_run",
        description=(
            "Run every deterministic SQL/hybrid finding detector over the "
            "warehouse and record fact_finding rows (no model calls). "
            "include_filesystem=False skips detectors that read the "
            "filesystem (stale_source)."
        ),
    )
    def couch_run(include_filesystem: bool = True) -> dict:
        return ops.couch_run(store, include_filesystem=include_filesystem)

    @server.tool(
        name="compile",
        description=(
            "Render current active rules to <out_dir>/<name>.md (materialize). "
            "Only status=active rules render -- drafts created via rule_add "
            "stay dormant until a proposal activates them. Fail-closed "
            "privacy gate: files containing a home path or the OS username "
            "are blocked, not written."
        ),
    )
    def compile(
        out_dir: str,
        scope: str | None = None,
        tenant_id: str = "default",
    ) -> dict:
        return ops.compile_rules(
            store, out_dir=out_dir,
            scope=RuleScope(scope) if scope else None, tenant_id=tenant_id,
        )

    @server.tool(
        name="ingest_transcripts",
        description=(
            "Ingest Claude Code session transcripts into the warehouse. "
            "Idempotent by key construction -- re-running against unchanged "
            "files writes zero rows. since (YYYY-MM-DD) filters by file "
            "mtime; project filters by substring match on the encoded "
            "project directory name."
        ),
    )
    def ingest_transcripts(
        root: str | None = None,
        project: str | None = None,
        since: str | None = None,
    ) -> dict:
        since_dt = None
        if since:
            try:
                since_dt = datetime.fromisoformat(since)
            except ValueError as e:
                raise ValueError(
                    f"Invalid since date: {since} (expected YYYY-MM-DD)"
                ) from e
        return ops.ingest_transcripts(
            store, root=root, project=project, since=since_dt,
        )

    return server


def serve(db_path: str | None = None) -> None:
    """Open the warehouse, build the server, and run it over stdio.

    This process becomes the single connection holder for the session --
    the same role the generic duckdb MCP server plays today, replaced
    because that server has no write tools and no gate. Closes the
    connection on exit (including on error) so the file is never left
    locked by an aborted server process.
    """
    from freud_schema.db import connect

    con = connect(db_path)
    store = ExperimentStore(con)
    try:
        server = build_server(store, db_path)
        server.run(transport="stdio")
    finally:
        store.close()
