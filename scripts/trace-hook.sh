#!/bin/bash
# PostToolUse hook: capture tool calls as trace events.
# Writes JSONL records to a buffer file.
#
# NOTE: there is no loader for this buffer. An earlier comment here pointed at a
# `bulk_import_traces` MCP tool that was never built, and nothing else reads the
# file either -- `store.insert_trace()` has no callers outside tests. The buffer
# accumulates and is not ingested. See skill/reference/trace-capture.md.
#
# Usage: Configure as a PostToolUse hook in .claude/settings.json:
#   "hooks": {
#     "PostToolUse": [{
#       "matcher": "*",
#       "command": "bash scripts/trace-hook.sh"
#     }]
#   }
#
# Environment:
#   FREUD_TRACE_BUFFER - Path to JSONL buffer (default: /tmp/freud-traces-$$.jsonl)

BUFFER="${FREUD_TRACE_BUFFER:-/tmp/freud-traces-$$.jsonl}"

# Read tool event from stdin, extract fields, append to buffer
read -r event
echo "$event" | jq -c '{
  trace_type: "tool_call",
  title: (.tool_name // "unknown"),
  content: (.tool_input | tostring | .[0:500]),
  outcome: {result_length: (.tool_output | tostring | length)},
  timestamp: now | todate
}' >> "$BUFFER" 2>/dev/null
