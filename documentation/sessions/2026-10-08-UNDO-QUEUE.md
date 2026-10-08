# 2026-10-08 — Undo of queued corners and Apply All

## What changed

Confirming a corner records the snapshot-stack depth. Undo removes that one queued corner while the depth still matches, and does not pop a snapshot. A trim or other snapshot that landed after the confirm is undone first.

Apply All remembers the queue it consumed. Undo of that snapshot restores the pre-apply drawing and puts those corners back, including skipped ones. Further Undos remove them newest-first. Redo of that Apply All puts the dogbones back and takes those corners off the list. An Apply All that skips every corner pushes no snapshot and does not come back on Undo.

Revert still keeps the queue and forgets this history. Opening another file or clearing the session clears both.

Recorded as ADR-029. SPEC §11.7 and CONTRACTS §5 match it.

## Tests

`pytest -q` — 340 passed. `verify_apply_undo_sequence` and `verify_revert_flow` passed.
