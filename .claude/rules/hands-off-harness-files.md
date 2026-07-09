<!-- compiled by freud-schema: do not edit; change the dimension row and recompile -->
<!-- source: dim_rule 88e53d4fd3b565360e53eed392c39842 effective_from 2026-07-09T11:48:23.189715 -->

# Hands off harness-managed files

Never programmatically overwrite harness-managed files (auto-generated
memory or index files, session state) via shell scripts or direct
writes -- they are owned by the harness, and direct writes fail or
corrupt state. If their content is stale or wrong, flag it in
conversation instead of editing it.

<!-- provenance: proposal 742ba5de; findings e0dd7456 -->
