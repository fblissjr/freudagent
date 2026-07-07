# /couch -- put the session history on the couch

Last updated: 2026-07-07

Analysis passes over the transcript warehouse that need judgment, not
aggregation. The SQL layer (`freud-schema couch run`, no model calls)
already detects retry loops, tool error clusters, interruption hotspots,
and permission friction. This skill covers the LLM layer: findings a
regex cannot make, chiefly `user_correction_pattern`.

The library contains no model calls by design. The harness (you) is the
intelligence: query candidates via the DuckDB MCP tools, judge them in
scoped subagents, write conclusions back as `fact_finding` rows.

## Workflow

1. **Pick candidate sessions** -- interruption hotspots and high-feedback
   sessions first:

   ```sql
   SELECT session_key, project_key, COUNT(*) AS interruptions
   FROM fact_message
   WHERE role = 'user' AND content_text LIKE '[Request interrupted by user%'
   GROUP BY session_key, project_key
   ORDER BY interruptions DESC LIMIT 10
   ```

2. **Pull the conversational context** per candidate (user messages around
   the interruption or short corrective replies):

   ```sql
   SELECT sequence_num, role, content_text
   FROM fact_message
   WHERE session_key = ? AND is_meta = FALSE
   ORDER BY sequence_num
   ```

3. **Judge in scoped subagents** (tree topology, one candidate cluster per
   subagent): was this a genuine correction/redirection of the agent's
   approach, or just a follow-up question? Subagents return a verdict plus
   a one-line generic description of the pattern -- see privacy rules.

4. **Record findings** via `mcp__duckdb__execute_query`. `finding_type`
   must already exist in `dim_finding_type` (`user_correction_pattern` and
   `recurring_dead_end` are seeded by `couch run`). Keys are
   `md5(finding_type || '|' || scope || '|' || coalesce(project_key,'-1')
   || '|' || summary || '|' || etl_run_id)`:

   ```sql
   INSERT INTO fact_finding (finding_key, finding_type, finding_type_key,
       scope, project_key, evidence_session_keys, occurrence_count, summary,
       record_source, etl_run_id)
   VALUES (?, 'user_correction_pattern', md5('user_correction_pattern'),
       'project', ?, ?, ?, ?, 'derived', ?)
   ```

   Open a `meta_load_log` row first (`operation = 'couch_llm'`) and close
   it with counts when done, same as the SQL layer does.

## Privacy rules (non-negotiable)

Findings feed the compile step, which writes files that may be committed.
Summaries must be clean BY CONSTRUCTION, before they enter the warehouse:

- Describe the PATTERN, never quote the transcript: "user repeatedly
  redirected agent away from editing generated files" -- not the user's
  words.
- No absolute paths, usernames, machine names, URLs, or secrets in
  `summary`. Evidence lives in `evidence_session_keys`; a reviewer with
  DB access can always drill down.
- If a pattern cannot be described without identifying content, do not
  record it as a finding.

## Thresholds

Match the SQL layer's discipline: a finding should be worth a human's
review time. One-off corrections are noise; record a
`user_correction_pattern` only when the same KIND of correction appears
in 2+ sessions (list all of them as evidence).
