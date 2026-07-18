# transcripts_raw - raw/clean transcript eval pair

This folder holds a matched **pair** of files covering the SAME meeting: the
2026-06-09 retrospective on the Scheduled Exports GA at Acme Analytics (all
fictional).

- `2026-06-09-exports-ga-retro-raw.txt` - the messy input. A raw auto-transcript
  as an ASR tool would emit it: per-utterance timestamps, uncertain/wrong speaker
  labels (`Speaker 1/2/3`, `[unknown]`), filler words, false starts, and
  `[inaudible]` / `[crosstalk]` markers. No punctuation cleanup.
- `2026-06-09-exports-ga-retro-clean.md` - the ground-truth structuring target:
  the same meeting, speaker-attributed, punctuated, with a summary header and an
  extracted action-items list.

**Structuring task:** diarization cleanup + speaker attribution + action-item
extraction. Turn the raw ASR file into the clean file.

**Speaker mapping (ground truth):**

- `Speaker 1` = ingrid.bauer (PM, facilitator)
- `Speaker 2` = marcus.webb (Eng)
- `Speaker 3` = dana.kim (Eng)
- `[unknown]` = an off-mic participant; utterances are procedural filler
  ("can you hear me", "sorry I was on mute") and carry no content.
