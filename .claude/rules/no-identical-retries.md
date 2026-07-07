<!-- compiled by freud-schema: do not edit; change the dimension row and recompile -->
<!-- source: dim_rule 16de12a3a30b9ba4908efec81639c3fa effective_from 2026-07-07T14:38:35.747580 -->

# No identical retries

After a tool call fails, never repeat the exact same call with the exact
same input more than once. A single identical retry is occasionally
justified (transient errors); two identical failures mean the approach
is wrong. Change the input, switch tools, or re-plan -- and if nothing
changes the outcome, surface the blocker instead of looping.

<!-- provenance: proposal 16bd0b4f; findings 1e5c7ccb, 13848f92, 6c5377e3, 3002b068, 5b186d46, 6bbe54e2, b034d95d, e926234c, b0b523bc, e7db00e3, 53335578, fbd21149, 9acfae7c, a3ecd0f6, adbf745d, 32a5208a -->
