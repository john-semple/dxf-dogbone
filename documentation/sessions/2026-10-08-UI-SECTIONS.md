# Session 2026-10-08 — UI sections: collapsible left rail

> **Status: Completed**

User request (not a milestone brief): organize the left-side controls into visual sections that can be minimized. Redo and the M6 message strings were already in the tree; export is still a File-menu flow, not a rail panel, so it was not given a section.

## Pre-change confirms (per AGENTS.md)

- (a) Brief read: `documentation/briefs/UI-UPGRADE.md` (the landed theme pass this builds on). No new milestone brief owns this request.
- (b) Contracts section read: CONTRACTS §5 ownership matrix. This pass touches only `ui/` + `app.py`. No engine, rules, geometry, or model changes. `Viewer` / `WorkflowUI` constructors unchanged.
- (c) pytest pre-change: `pytest -q` → **292 passed**.

## What changed

Left rail order is now Dogbone, Folds, Trim, History. Each block is a `CollapsibleSection` (header click minimizes the body; chevron flips). A minimized header keeps a short summary: tool diameter and queued count, fold `n/m`, trim `on`. The rail scrolls when the window is shorter than the stack; while the pointer is over the rail the wheel scrolls sections instead of zooming the drawing.

History (Undo, Redo, Revert) moved out of the tool block to the bottom so the editing tools stay together. Quick-size highlight uses `Selected.TButton` (accent color, same padding as the other size buttons) so the active size does not stretch its row.

## Gates

```
pytest -q
296 passed in 3.05s

python tools/verify_gui.py --full --folds --trim
ALL PASS
```

(292 pre-change + 4 tests in `tests/test_ui_collapsible.py`.)

## Follow-up (same day): pin Undo/Redo/Revert

User agreed Undo and Redo should stay visible at the top of the rail, with Revert kept there but quieter. `Sidebar.pin` sits above the scroller. `ToolPanel.commands` packs into that strip: Undo and Redo as normal buttons, Revert as `Quiet.TButton` (muted text, no filled chip), left-aligned under Undo. Centering Revert was considered and rejected the same day: the gap between Undo and Redo is where the eye lands, and a centered destructive command would read as a third button. The ruling is recorded on the aesthetic brief (`documentation/briefs/UI-UPGRADE.md`, "Revision — 2026-10-08"). The collapsible History section is gone. Section order is Dogbone, Folds, Trim.
