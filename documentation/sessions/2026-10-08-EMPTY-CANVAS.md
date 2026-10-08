# Session 2026-10-08 — Empty canvas opens a DXF from a button

> **Status: Completed**

User request (not a milestone brief): with no DXF loaded, replace the "File > Open DXF" line with a button that adds a DXF. Follow-ups the same sitting: make it larger and quieter, then smaller and grey, matching a filled control rather than a heavy outline.

## Pre-change confirms (per AGENTS.md)

- (a) Brief read: `documentation/briefs/UI-UPGRADE.md` (File bar revision; the empty canvas was not specified there yet).
- (b) Contracts section read: CONTRACTS §5 ownership matrix. This pass touches `app.py`, `ui/messages.py`, `ui/theme.py`, `ui/rounded_button.py`, and `tests/test_app_open_retarget.py`. No engine, rules, geometry, or model changes.
- (c) pytest pre-change: not re-run as a separate gate before the first edit. Post-change output is below.

## What changed

`EMPTY_CANVAS` is "Add a DXF to get started". Under it, `EMPTY_OPEN` ("Add a DXF") calls `App.open_dialog`, the same function as File > Open DXF. The pair is a frame placed at the center of the viewer. It is shown when `source_path` is `None` and hidden after a successful open.

The button is a `RoundedButton` with optional fill, outline, size, and radius. The Export control keeps the accent defaults. The empty-canvas control uses `empty_btn` `#3a3d46`, hover `#484c58`, a 1px edge `#4e5260` (hover `#5c6070`), text `#e8e9ed`, a 12-point label, padding 22×10, and radius 8. The startup status line is "Add a DXF to get started."

## Gates

```
pytest -q
340 passed in 5.20s
```

## Docs

ISSUE-024. Aesthetic brief revision: `documentation/briefs/UI-UPGRADE.md`, "Revision — 2026-10-08 (empty canvas)". The close-session status quote in `documentation/briefs/DEBUGGING.md` now matches the new startup line.
