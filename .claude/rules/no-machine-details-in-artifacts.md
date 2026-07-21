<!-- compiled by freud-schema: do not edit; change the dimension row and recompile -->
<!-- source: dim_rule ba43f4713f8b6561edfbf4e973b47e0f effective_from 2026-07-21T16:58:42.139153 -->


# No machine details in committed artifacts

Never write machine-specific or identity-revealing details into anything
git-controlled: no absolute home paths, usernames, hostnames, local folder
locations, names of locally-installed models or tools, or descriptions of
credential and signing setup -- in code, tests, docs, changelogs, or commit
messages. Do not add meta-commentary about privacy scrubbing to committed
artifacts either: noting what was removed advertises exactly what was
hidden. Keep environment specifics in gitignored local files and reference
them generically from committed content. Before committing, silently
generalize or remove any such detail; where an example needs an
environment-specific value, use a placeholder.
