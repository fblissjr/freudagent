"""Vendored Claude Code transcript parsers from ccutils.

See the provenance headers in models.py / history.py for the upstream
commit. models.py is the typed layer: 12 discriminated entry types with
Unknown* fallbacks and extra="allow" everywhere -- built for a JSONL
format that is not a public contract.
"""

from freud_schema.vendor.ccutils_parsers.models import (
    AssistantEntry,
    SessionLogEntry,
    SummaryEntry,
    SystemEntry,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserEntry,
    iter_typed_entries,
    parse_content_block,
    parse_log_entry,
)

__all__ = [
    "AssistantEntry",
    "SessionLogEntry",
    "SummaryEntry",
    "SystemEntry",
    "TextBlock",
    "ThinkingBlock",
    "ToolResultBlock",
    "ToolUseBlock",
    "UserEntry",
    "iter_typed_entries",
    "parse_content_block",
    "parse_log_entry",
]
