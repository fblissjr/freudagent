<!-- compiled by freud-schema: do not edit; change the dimension row and recompile -->
<!-- source: dim_rule 5d9cffebfa514c207c59d08b334fc3c3 effective_from 2026-07-21T17:15:25.170831 -->


# Repo scope discipline

Do not use Bash to read, list, or search paths outside the current
repository root (home-directory config, sibling projects, unrelated
repos), and do not fetch external content via curl or gh api when
WebFetch/WebSearch exist. Exception: data paths this project's own
CLAUDE.md or docs explicitly sanction (for example, sanctioned
transcript or artifact directories). For anything else outside the
repo, say what you need and why, and let the user decide first.
