# drive_chaos - shared-drive near-duplicate chaos

This folder models what a shared drive actually looks like after a document has
been passed around: multiple near-duplicate drafts of ONE logical document, plus
detritus, with no metadata beyond the filenames. Everything here is fictional
(Acme Analytics).

The document is a **"Data Platform Strategy" one-pager**. Five files are drafts of
that single document; the prose is 80-90% identical between them, but the argument
drifts across versions:

- `Data Platform Strategy DRAFT.md` and `Data Platform Strategy v2.md` argue for
  building an in-house multi-region active-active pipeline NOW.
- `Data Platform Strategy FINAL.md`, `Data Platform Strategy FINAL v2 (1).md`, and
  `Copy of Data Platform Strategy FINAL v2.md` soften that to "evaluate
  active-active; single-region + DR is adequate for 2026" (reflecting exec steer).
- `Copy of Data Platform Strategy FINAL v2.md` is byte-identical to
  `Data Platform Strategy FINAL v2 (1).md` except a single trailing-word change - a
  true near-duplicate orphan (an accidental "Copy of").
- `~$strategy.tmp.md` is an office-style lock/temp artifact - NOT content.

## Structuring tasks

1. **Cluster** the near-duplicate drafts into one document identity.
2. **Select the canonical/latest version**.
3. **Recognize** the temp/orphan files (`~$strategy.tmp.md`, and the "Copy of"
   duplicate) as non-content.

## Ground truth

The intended canonical file is **`Data Platform Strategy FINAL v2 (1).md`**. It
carries the latest date and the incorporated exec steer, and the "Copy of" file is
a redundant duplicate of it, not a newer version.
