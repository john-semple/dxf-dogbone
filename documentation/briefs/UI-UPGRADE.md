# Brief — UI-UPGRADE: Theme pass (modernize the tkinter shell)

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
