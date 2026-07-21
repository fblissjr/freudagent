<!-- compiled by freud-schema: do not edit; change the dimension row and recompile -->
<!-- source: dim_rule 41e373fd2c53f65f3369289a60dab0e8 effective_from 2026-07-21T16:58:42.136444 -->



# No identical retries

After a tool call fails, never repeat the exact same call with the exact
same input more than once. A single identical retry is occasionally
justified (transient errors); two identical failures mean the approach
is wrong. Change the input, switch tools, or re-plan -- and if nothing
changes the outcome, surface the blocker instead of looping.
