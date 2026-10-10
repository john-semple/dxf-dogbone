# 2026-10-09 — Rail step order

User request, not a milestone. The left rail already had collapsible sections and a pinned Undo/Redo/Revert strip (session logs `documentation/sessions/2026-10-08-UI-SECTIONS.md` and `documentation/sessions/2026-10-08-RAIL.md`).

## What changed

Section order in `Sidebar.body` is now:

1. **Step 1 — Designate Fold Lines** (`SECTION_FOLDS`, `FoldPanel`)
2. **Step 2 — Dogbone** (`SECTION_DOGBONE`, `ToolPanel.dogbone`)
3. **Step 3 — Trim** (`SECTION_TRIM`, `TrimPanel`)

The Step 1 title wraps (`wraplength=140`) so it stays beside the fold count. Undo, Redo, and Revert stay on `Sidebar.pin`.

Docs updated the same day: `README.md` Use, `documentation/briefs/UI-UPGRADE.md` ("Revision — 2026-10-09"), ISSUE-021, and the Sidebar sentence in `documentation/briefs/DEBUGGING.md`. Earlier session logs were left as written.

## Not changed

No extra process paragraph was added to the panels. Step 1 still has the keyword and layer hints. Step 2 still has no static hint; the status line carries the click instructions. Step 3 still has `TRIM_HINT`. Folds may still be designated after corners; the step numbers are the rail order, not a gate.

## Gates

```
pytest -q tests/test_ui_collapsible.py tests/test_ui_escape.py tests/test_app_open_retarget.py
17 passed, 1 skipped
```
