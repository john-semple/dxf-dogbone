# Brief — UI-UPGRADE: Theme pass (modernize the tkinter shell)

> **Status: Completed**

**Sequencing:** run AFTER M3 lands (M3 owns `ui/workflow.py` + `ui/messages.py` and is in progress as of 2026-10-07). This pass restyles what M3 builds; doing both concurrently on the same files guarantees a merge mess.

**Files you own:** `ui/theme.py` (new), `app.py` (presentation only), `ui/canvas_view.py` (colors/fonts only), restyle calls in `ui/workflow.py` (visual constants + widget creation ONLY — no FSM/state-machine changes), `tools/verify_gui.py` (only if restyling breaks a selector — see invariant 4), `documentation/ISSUES.md` (append one ISSUE row for this pass), this brief's session log.

**Forbidden:** engine/rules/geometry/model changes; changing `WorkflowState`, event handling, or the `(state, event) -> state` handler contract; changing overlay *semantics* (flash must stay visually distinct from deletion red; flagged distinct from both); adding dependencies (stdlib tkinter only — a library like CustomTkinter requires its own mini-ADR first, see §5); restyling `messagebox` flows away (M3 owns their behavior).

## Why this exists

The shell is classic tk: `tk.Button`, `relief=SUNKEN` labels (`app.py:48-52`), white canvas (`BG = "white"`), hard-coded colors scattered across `canvas_view.py` and `workflow.py:280-285`. User request 2026-10-07: make the UI more modern/aesthetic. The architecture already isolates this — headless handlers and engine are untouched by definition.

## The work (in priority order)

1. **`ui/theme.py` — single source of palette + fonts.**
   - One `COLORS` dict and one `apply(root) -> ttk.Style` entry point called from `App.__init__` and from `tools/verify_gui.py` harness roots (so the harness exercises the same look).
   - Dark panel scheme (`bg #1e1f26`-class, accent blue, muted text), `clam` theme, `Segoe UI` (fallback `TkDefaultFont`), flat `TButton` + one `Accent.TButton` for Confirm, consistent padding (8/12 px grid).
   - Acceptance: no hex color literal remains in `app.py`, `ui/canvas_view.py`, or `ui/workflow.py` — everything imports from `theme.COLORS` (grep-clean is the check).

2. **Canvas dark theme.** Move `BG/FG/TEXT_FG/POINT_FG` in `canvas_view.py` to theme-driven values: dark background, light geometry strokes, readable MTEXT. Recolor workflow overlays for the dark bg while preserving *relative* distinction: `HIGHLIGHT_COLOR`/`GHOST_COLOR` (cyan-family), `DELETE_COLOR` (red, must pass visibility on dark — `#ff4d4d`-class, not pure `#ff0000` if it vibrates), `FLAG_COLOR` (orange), all from `theme.COLORS`.
   - Acceptance: after `run.bat`, load a sample — geometry, gridless part, promoted flash, both ghosts, red deletion preview, orange flags all distinguishable at a glance; M3's human-visual checklist still passes.

3. **Shell layout polish (`app.py`).** Replace the bottom `relief=SUNKEN` label bar with a slim `ttk` status bar (one `Status.TLabel` + `ttk.Separator`); move Confirm into an `Accent.TButton`; wrap summary text in padding, not `bd=1`; menu stays `tk.Menu` but inherits root colors where tk allows.
   - Acceptance: no `relief=` / `bd=` styling left in `app.py`; status/summary text unchanged (same strings, same `StringVar`s — `App` public methods untouched).

4. **Harness safety.** `tools/verify_gui.py` builds `Viewer` + `WorkflowUI` directly (not via `App`), and drives synthetic events against canvas coords — so layout moves are safe, but **constructor signatures of `Viewer` and `WorkflowUI` must not change**. If a restyle breaks a harness step, fix the restyle, not the harness logic (harness edits allowed only for widget-identity lookups).
   - Acceptance: `python tools/verify_gui.py --full` ALL PASS; `pytest -q` green (114+ tests, unchanged count expected — this pass adds no engine tests; add `tests/test_theme.py` only asserting `apply()` runs on a throwaway root and `COLORS` has the required keys).

5. **Optional (time permitting): refusal/toast cards.** If M3's toasts are plain `Toplevel`/labels, restyle them as cards (rounded-look frame, accent left border) — presentation only. Skip if it means touching M3's prompt/decision flow.

## DoD

- `pytest -q` green; `python tools/verify_m2.py` ALL PASS; `python tools/verify_gui.py` ALL PASS (M3's `--full` included)
- Grep-clean: no hex literals outside `ui/theme.py` (exceptions: none in `app.py`/`ui/`; `tools/preview.py` SVG colors are out of scope)
- Human visual checklist: load `samples/before` + `after` DXFs — dark canvas, part legible, status bar readable, Confirm accented, flash/ghost/delete/flag colors mutually distinct
- ISSUES.md: one appended issue row (not a milestone-M# row — those are single-writer), status `done`, linking this brief + session log
- Session log with test output pasted

## Citations

User request 2026-10-07 (session log of the M3 pass or this pass, whichever records it). AGENTS.md invariants 1–2 (this pass touches only `ui/`). CONTRACTS §3/§5 for `Viewer`/`WorkflowUI` signatures. M3 brief (overlay semantics + human checklist this pass must not regress). Cut-list note: if overrun, ship items 1–2 only (palette + canvas) — that's already 80% of the perceived modernity.

## Revision — 2026-10-08 (left rail)

The palette, canvas, and status bar from this brief are unchanged. The shell gained a left rail the same day (session log `documentation/sessions/2026-10-08-UI-SECTIONS.md`, ISSUE-021). Current layout:

- **Pinned strip** at the top of the rail, above the scroller. It does not collapse and does not scroll away. Undo and Redo are normal buttons, side by side. **Revert to Original** sits under them as `Quiet.TButton` (muted text, no filled chip), **left-aligned** with the other labels in the rail. It is not centered: the gap between Undo and Redo is where the eye lands, and centering a rare destructive command there would give it the weight of a third button.
- **Collapsible sections** below a separator, in order: **Step 1 — Designate Fold Lines**, **Step 2 — Dogbone**, **Step 3 — Trim** (titles updated 2026-10-09; see the revision below). They are one column. A header click minimizes that section. A minimized header keeps a short summary (tool diameter and queued count, fold `n/m`, trim `on`).
- The column scrolls only when it is taller than the rail, for example when the sections are expanded or the fold-layer list is long. The three sections move together. When they already fit, the wheel does nothing, and the column cannot be shifted down into blank space above Step 1. While the pointer is over the rail and the column does overflow, the wheel scrolls the sections instead of zooming the drawing.
- Under **Trim to Closest**, a muted line reads: "Click a line near the end you want to trim or extend. Ctrl+Z undoes." The string is `TRIM_HINT` in `ui/messages.py`.

## Revision — 2026-10-08 (File bar)

Item 3's native menubar is gone. On Windows that strip stays system-white, so `root.config(menu=...)` is not used. The commands still live on a `tk.Menu` popup (session log `documentation/sessions/2026-10-08-FILE-BAR.md`, ISSUE-023).

- **Top strip** (`TopBar.TFrame`, `bar_bg` `#32343e`) spans the window above the rail and the canvas. A 1px separator (`#3a3b45`) runs under it. It is a step lighter than the rail (`#1e1f26`) so the shelf is visible.
- **File** is a chip on the left (`file_chip` `#3e4250`, hover `#484c58`). Click or Alt+F posts the menu under the chip: Open DXF, Export DXF, Exit. There is no blue tick. The row and the chip are short: chip packed with `pady=2`, label `padx=8` `pady=2`.
- **✕** stays on the right of the same strip (`BarQuiet.TButton`, muted text, padding `(8, 2)`). It clears the session. It is not the window close button.
- **Export DXF** remains the accent button at the bottom right of the status bar. It calls the same `export_dialog` as the menu item.

## Revision — 2026-10-08 (empty canvas)

With no DXF loaded, the canvas is not a menu instruction. A centered hint (`EMPTY_CANVAS`, "Add a DXF to get started") sits above an **Add a DXF** button (`EMPTY_OPEN`). The button calls `open_dialog`, the same path as File > Open DXF. It is a `RoundedButton` on the canvas background, not the blue Export control: fill `empty_btn` `#3a3d46`, hover `#484c58`, hairline edge `#4e5260` (hover `#5c6070`), text `#e8e9ed`, 12-point label, padding 22×10, radius 8. The status line in that state is "Add a DXF to get started." Opening a file hides the hint; clearing the session shows it again. Session log `documentation/sessions/2026-10-08-EMPTY-CANVAS.md`, ISSUE-024.

## Revision — 2026-10-09 (step order)

The three collapsible sections are a numbered workflow. Titles live in `ui/messages.py`:

- **Step 1 — Designate Fold Lines** (`SECTION_FOLDS`), packed first
- **Step 2 — Dogbone** (`SECTION_DOGBONE`)
- **Step 3 — Trim** (`SECTION_TRIM`)

The Step 1 title wraps (`wraplength=140` on the section header) so it stays beside the fold count. Undo, Redo, and Revert stay on the pinned strip. Scroll behavior is unchanged. No extra process paragraph was added to the panels; Step 3 still has `TRIM_HINT`, and Step 1 still has the keyword and layer hints. Session log `documentation/sessions/2026-10-09-RAIL-STEPS.md`.

