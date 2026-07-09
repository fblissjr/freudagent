<!-- compiled by freud-schema: do not edit; change the dimension row and recompile -->
<!-- source: dim_rule 600458d4ed677e534fffb362005afb1c effective_from 2026-07-09T13:24:00.678540 -->


# External search cutoff

When an external search or fetch fails or returns thin results twice
in a row, stop expanding with further query variations. Summarize what
was and was not found, prefer local sources (installed packages, local
clones, vendored code), and ask how to proceed before launching
another round of external queries.
