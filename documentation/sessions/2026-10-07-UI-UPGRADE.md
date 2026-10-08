# Session 2026-10-07 — UI-UPGRADE: theme pass (modernize the tkinter shell)

Brief: `documentation/briefs/UI-UPGRADE.md` (binding).

## Pre-change confirms (per AGENTS.md)

- (a) Brief read: UI-UPGRADE.md in full.
- (b) Contracts sections read: CONTRACTS §3 (IO — untouched), §4 (verification
  API — verify_gui harness), §5 (ownership matrix — this pass touches only
  `ui/` + `app.py` + `tools/verify_gui.py` root styling).
- (c) pytest pre-change: `pytest -q` → **148 passed**.
- Sequencing precondition met: M3 landed (ISSUES.md M3 row done, session log
  2026-10-07-M3), so `ui/workflow.py` + `ui/messages.py` were stable to restyle.

## Decisions (in-flight)

1. **Brief item 5 (toast cards) = no-op.** M3's "toasts" are status-line
   strings (`fsm.inline` → status callback), not `Toplevel`/label dialogs.
   Converting them to cards would touch M3's prompt/decision flow — forbidden
   by the brief. Skipped per the brief's own escape hatch.
2. **Confirm pill restyled, not redesigned.** `_show_confirm_pill` is the
   sanctioned seam (M3 left it explicitly for this pass). Kept the round-7
   green CONFIRM CORNER look; colors + font moved to theme keys
   (`pill_bg`, `pill_btn_bg`, `pill_btn_active`, `pill_btn_fg`,
   `theme_font(16, "bold")`). No geometry/anchor changes.
3. **`bd=2, relief=RAISED` on the pill frame replaced** with
   `highlightthickness=2, highlightbackground=...` (same raised-card look)
   — the DoD's grep-clean bars hex literals, and app.py's ban on relief/bd
   chrome; keeping a literal `bd=` in workflow.py would half-honor the
   brief's "flat" intent. FS/UI logic untouched.
4. **Segoe UI vs TkDefaultFont:** `theme.font()` returns the family name
   tuple; tk silently substitutes the default family where Segoe UI is
   absent (non-Windows), so no runtime probe was needed. `apply()` wraps
   the style-level font config in `TclError` fallback per the brief's
   fallback requirement.
5. **Status bar layout:** bottom bars pack-first order preserved (M1
   checklist defect — canvas must not squeeze them). `Status.TFrame` +
   `Status.TLabel` (muted fg on sunken bg) + `ttk.Separator` above the
   workflow status line. Strings/StringVars identical; `App` public
   methods untouched (verified by smoke: status/mouse/summary vars +
   Accent.TButton disabled-state behavior).

## Changes

- **`ui/theme.py` (NEW)** — `COLORS` dict (single home for every hex
  literal: surfaces, text, canvas, overlays, accents, pill, chrome) +
  `apply(root) -> ttk.Style` (clam base, dark `#1e1f26`-class, accent blue
  `#3b82f6`, flat `TButton`, `Accent.TButton`, `Status.TLabel`,
  `Status.TFrame`, TSeparator, root bg) + `font()` helper + `PAD_X/PAD_Y`.
- **`ui/canvas_view.py`** — `BG/FG/TEXT_FG/POINT_FG` now theme-driven
  (`canvas_bg` #17181e, `geometry_fg` #c8cdd9, `text_ent_fg`, `point_fg`);
  inline `("TkDefaultFont", N)` fonts → `theme_font(N)`. No render-logic
  changes.
- **`ui/workflow.py`** — overlay constants now read from `theme.COLORS`:
  `HIGHLIGHT_COLOR`/`GHOST_COLOR` = `#22d3ee` (cyan-family, was #00b0f0),
  `EDGE2_PICK_COLOR` = `#4ade80`, `DELETE_COLOR` = `#ff4d4d` (was pure
  #ff0000 — dark-bg-safe per brief), `FLAG_COLOR` = `#ff9900` (unchanged).
  Pill + `_outline_entity` fonts theme-driven. **Zero FSM/state-machine/
  handler changes** — visual constants + widget creation only.
- **`app.py`** — `theme_apply(root)` first line of `__init__`; menubar
  themed (bg/fg/active pairs); bottom bar = `ttk.Frame(Status.TFrame)` +
  `Status.TLabel`s + Confirm as `Accent.TButton` + `ttk.Separator`; no
  `relief=`/`bd=` anywhere.
- **`tools/verify_gui.py`** — `theme_apply(root)` after both `tk.Tk()`
  roots (harness exercises the same look). Constructor signatures of
  `Viewer`/`WorkflowUI` untouched; no harness-logic edits.
- **`tests/test_theme.py` (NEW)** — 3 tests: required COLORS keys,
  `apply()` on a throwaway root (clam + returns ttk.Style), double-apply
  idempotency (with no-display skip).

## Test output (pasted)

```
> .venv\Scripts\python.exe -m pytest -q
151 passed in 1.01s        (148 pre-change + 3 new test_theme tests)

> .venv\Scripts\python.exe tools\verify_m2.py
M2 corner-local golden gate
  pytest pin: pytest==9.1.1
  load: before=121 entities, after=104 entities
  corner2 (right T-junction, R=3.175): PASS - center/rebuilt/span vs after-file within 0.001 [deletions=['B9', 'BA'], flags=['BA']]
  corner3 (left T-junction, R=3.175): PASS - center/rebuilt/span vs after-file within 0.001 [deletions=['B4', 'B5'], flags=['B4']]
  corner1 (top, R=1.5875): PASS - self-consistent construction; tear pocket fully cleaned (85-89); user arc EXCLUDED per 2026-10-05 decision (divergence 0.4537 mm; M6 residual)
ALL PASS

> .venv\Scripts\python.exe tools\verify_gui.py --full
file                                     result
base-rectangular-before-AI.DXF           PASS - 121 items ok; dump previews/items-base-rectangular-before-AI.json
base-rectangular - partially radiused.DXF PASS - 104 items ok; dump previews/items-base-rectangular - partially radiused.json
M3 corner workflow (--full)              PASS - corner2 (right T-junction, R=3.175): dogbone applied center=(47.2451, 49.2717) deletions=['B9', 'BA'] | corner3 (left T-junction, R=3.175): dogbone applied center=(-47.2451, 49.2717) deletions=['B4', 'B5'] | corner1 (top, R=1.5875): dogbone applied): center=(45.2534, 121.6506) deletions=['85', '86', '87', '88', '89'] | parallel-pair refusal toast: PASS (engine string verbatim)
ALL PASS

Grep-clean check (Select-String '#[0-9a-fA-F]{6}' over app.py + ui\*.py + tools\verify_gui.py):
  → hits ONLY in ui\theme.py (COLORS dict). app.py, ui/canvas_view.py,
    ui/workflow.py, ui/messages.py, ui/transform.py, ui/theme-docstring: clean.
  → app.py relief=/bd= scan: clean (one comment mentioning the ban reworded).

App smoke (withdrawn root): style=clam, Accent.TButton bg #3b82f6,
Status.TLabel bg #17181e, viewer canvas bg #17181e, post-load status
"base-rectangular-before-AI.DXF: 121 entities loaded", Confirm disabled
until SIDE_PICKED (Accent.TButton style present). OK.
```

## DoD checklist (brief)

- [x] `pytest -q` green — 151 (148 + 3 theme tests; count change expected: brief says "adds no engine tests; add tests/test_theme.py")
- [x] `python tools/verify_m2.py` ALL PASS
- [x] `python tools/verify_gui.py --full` ALL PASS
- [x] Grep-clean: no hex literals outside `ui/theme.py` (app.py/ui/ — tools/preview.py untouched, out of scope)
- [x] `Viewer`/`WorkflowUI` constructor signatures unchanged (harness builds both directly, still passes)
- [x] Overlay semantics preserved: flash/ghost cyan-family, delete red (#ff4d4d, dark-bg-safe), flag orange — relative distinction intact; edge-2 green pick-phase kept (M3 round-7/8 user preference)
- [x] ISSUES.md: ISSUE-017 row appended (status done), links this brief + session log
- [ ] **Human visual checklist PENDING user** — load before+after DXFs via `run.bat`: dark canvas, part legible, status bar readable, Confirm accented, flash/ghost/delete/flag mutually distinct at a glance. Same sitting can close ISSUE-016's M3 checklist (ghost visibility, flash-vs-red distinction, auto-zoom framing, refusal toast).

## Blockers

None. Docs-conflict scan: none found — UI-UPGRADE brief is self-consistent with CONTRACTS §3/§5 and the M3 brief's overlay-semantics requirements.