# Debugging tasks — 2026-10-08

> **Status: Done** — tasks 1–7 completed 2026-10-08

Seven independent fixes. Give an agent **one** numbered task. It should read `AGENTS.md`, then this task only. It should not do the other tasks, and it should not edit `documentation/ISSUES.md` (no milestone row owns this file).

When the task is done, append `documentation/sessions/2026-10-08-DEBUG-<n>.md` with what changed and the `pytest -q` output. Do not edit another session log.

`pytest -q` must pass before the session ends. These tasks do not change dogbone geometry, export purity, or the rule that `geometry/`, `rules/`, and `model/` import neither tkinter nor ezdxf.

## Open questions

> **Status: None**

None. Every task below is done.

---

## 1. Second DXF keeps the first file's corner tool

> **Status: Done** — `documentation/sessions/2026-10-08-DEBUG-1.md`

### What happens

Open a DXF, then Open another without restarting. The canvas shows the new drawing. Dogbone clicks still resolve against the first file.

### Why (verified)

`App.open_path` (`app.py`) always does `self.model = Model(result.model_state)` and `self.viewer.set_model(result.model_state)`. `Model` stores that state by reference, so the canvas and `App.model` match.

`App._ensure_workflow` builds `ApplyAllWorkflowUI` only when `self.workflow is None`. That object keeps the first `Model`, the first `ApplyQueue`, and the first `SnapshotStack`. A later Open does not replace them. `WorkflowUI.pick_edge` calls `promoted_edge_at` on `self.model.state.primitives`, which is still the first file.

`trim_panel.model` and `trim_panel.stack` are assigned only inside that first `_ensure_workflow`. `fold_panel.model` is replaced on every Open. `fold_panel.stack` is not.

`ApplyAllWorkflowUI.__init__` calls `WorkflowUI._bind`, which uses `bind(..., add=True)` for `<ButtonPress-1>`, `<Button-3>`, `<Escape>`, and `<Return>`. Those handlers are not removed when the Python object is dropped. Building a second workflow on the same canvas would fire the old handlers and the new ones.

### What to do

Retarget the existing workflow. Do not construct a second `ApplyAllWorkflowUI`.

On every successful `open_path`, including the first:

- Exit fold mode if it is on (`FoldPanel.unbind_canvas` plus the FSM exit), and exit trim mode if it is on, so those modes are not left pointing at the old file.
- Clear any pending trim pick and trim overlays.
- Point `workflow.model`, `workflow.queue.model`, `trim_panel.model`, and `fold_panel.model` at the new `Model`.
- Replace the `SnapshotStack` with a new one for that model. Point `workflow.stack`, `workflow.queue.stack`, `trim_panel.stack`, and `fold_panel.stack` at it. Set `stack.on_change` to `workflow._notify_queue` again. Call `push_load` once for the new file.
- Clear the pending-corner queue (`ApplyQueue.clear`).
- Restart the corner FSM (`workflow.start`) so edge picks and the status line belong to the new file.
- Keep the existing fold `on_load(result.layer_of)` call so auto-preselect runs on the new file only.

Add a **✕ button at the top right** of the window, in a thin bar packed `side=TOP` across the full width before the sidebar is packed, button packed to the right. It is not the window's own close button, and it does not delete the file on disk.

Clicking it while a DXF is loaded opens a yes/no prompt. No leaves the session alone. Yes runs the clear path below. With no file loaded, the button does nothing and does not prompt.

**File > Open DXF** (`open_dialog`, not `open_path`) uses the same prompt when a DXF is already loaded. No returns without the file chooser. Yes runs the clear path, then the existing file chooser, then `open_path` on the chosen file. Cancelling the chooser after Yes leaves the session empty. With no file loaded, Open skips the prompt. Startup `open_path` from the command line does not prompt.

Clear path: the same retarget as a successful Open, with an empty `ModelState`, `source_path = None`, empty header, and no `workflow.start()`. Status returns to the startup text already in `App.__init__` (`"Add a DXF to get started."`). The canvas shows that same line plus an **Add a DXF** button that calls `open_dialog` (ISSUE-024). Title returns to `"DXF Dogbone"`. `Viewer.set_model` already handles an empty primitive list (`entity_world_bbox` is `None`). Export already refuses when `source_path` is `None`.

Prompt copy, in `ui/messages.py`, same title and body for the ✕ button and for Open:

- Title: `Close current DXF?`
- Body: `This clears the drawing from the session. The file on disk is not deleted.`

`messagebox.askyesno`. File > Open stays enabled.

### Do not

- Do not mint new entity ids. Load already uses DXF handles (`dxf_io/load.py`).
- Do not drop and recreate the canvas bindings.
- Do not change `place_corner` or hit-testing.

### Tests

Add a test that builds `App`, calls `open_path` on two different files under `samples/` (for example `samples/syn-L-bracket.dxf` then `samples/syn-multicorner.dxf`), and asserts:

- `workflow.model` is `App.model`
- `workflow.model.state` primitive eids equal the eids in the second load result
- `trim_panel.model` is that same model
- the pending queue is empty

Add a clear case: after the clear path, `source_path is None`, the viewer has no drawables, and a following `open_path` works (same assertions against that file). `open_path` itself does not prompt; the prompt belongs to the ✕ button and to `open_dialog`.

`tests/test_ui_collapsible.py` builds `App` and checks rail packing. Keep that passing.

---

## 2. Pan and box-select while designating folds

> **Status: Done** — `documentation/sessions/2026-10-08-DEBUG-2.md`

### What happens

Pan works on the drawing until fold designation is turned on. It then does not respond to the same drag.

### Why (verified)

`Viewer` pans on left-drag: `<ButtonPress-1>`, `<B1-Motion>`, `<ButtonRelease-1>` in `ui/canvas_view.py` (`_on_press`, `_on_drag`, `_on_release`). The drag uses `canvas.move("all", ...)` and `ViewTransform.panned_by`.

`FoldPanel.bind_canvas` replaces those Button-1 scripts, plus `<Button-3>` and `<Escape>`, for the whole time fold mode is on. Left-drag becomes box-select (a drag of at least `BOX_SELECT_PX`, which is 5, toggles every straight line in the box). The fold panel installs middle-button pan on `<ButtonPress-2>`, `<B2-Motion>`, `<ButtonRelease-2>` (`_on_pan_press`, `_on_pan_drag`, `_on_pan_release`). Wheel zoom is left alone.

`FOLD_MODE_ENTER` in `ui/messages.py` says "Middle-drag pans; Esc exits." Right-click in this mode calls `_on_right`, which exits fold mode. It is not pan.

This was not reproduced in a running window. The code path above is the reason left-drag pan disappears. Whether middle-drag itself fails to fire on a given mouse was not checked.

### What to do

While fold mode is on:

- Left-drag pans. Use the same move as `Viewer._on_drag`: `canvas.move("all", dx, dy)` and `transform.panned_by`. A left press, drag, and release does not toggle a line and does not box-select.
- Middle-drag box-selects. A middle-button drag of at least `BOX_SELECT_PX` (5) toggles every straight line in the box, which is what left-drag does today. A middle-button release below that threshold toggles the one straight line under the cursor, which is what a left click does today.
- Right-click still exits fold mode. Esc still exits. Wheel zoom stays.

Outside fold mode, left-drag pan stays as it is. Do not change trim mode, which has its own middle-drag pan.

Put a hint on screen only while fold mode is on, top center of the canvas: `Middle-drag to box-select`. Store the string in `ui/messages.py`. Place it with `place` on the canvas widget (`relx=0.5`, `rely=0`, `anchor="n"`), not as a canvas item. `canvas.move("all", ...)` would carry a canvas item away during pan. Hide it on exit.

Change `FOLD_MODE_ENTER` so it no longer says middle-drag pans. `tests/test_ui_fold_fsm.py::test_fold_fsm_toggle_mode_on_off` asserts `FOLD_MODE_ENTER in fsm.status`. Update that assertion if the constant no longer contains the old sentence. The FSM copies the constant. Which mouse button calls `click_world` / `box_select` is shell behavior in `FoldPanel`.

### Do not

- Do not change corner-workflow picking while fold mode is off.
- Do not bind Space.

### Tests

The FSM tests in `tests/test_ui_fold_fsm.py` call `click_world` and `box_select` directly. Keep those passing. Add a shell-level check that the left-button handler pans and does not call `box_select`, and that the middle-button release calls `box_select` only once the drag reaches `BOX_SELECT_PX`. If that needs a real display, say so in the session log and cover the branch with a direct call on the handler.

---

## 3. Trim of a line attached at both ends

> **Status: Done** — `documentation/sessions/2026-10-08-DEBUG-3.md`

### What happens

Trim to Closest on a line whose ends both meet other geometry pulls one end off its joint and swings the segment around the other end. The expected result is that the line is removed.

### Why (verified)

`rules/manual_edit.py:trim_to_closest`. ADR-025 and the `trim_to_closest` block in `documentation/CONTRACTS.md` say:

- Zero external attachments (`build_adjacency` minus the run's own members, `EPS_COINCIDE`) deletes the whole run.
- Otherwise the run-extent endpoint nearest the click moves to the closest supporting-geometry point. For another `Seg`, that point is the perpendicular foot of the moving endpoint on the other segment's infinite line (`t` is not clamped to the segment). The other endpoint stays put. If the foot is not on the picked line's axis, the segment rotates.

"External attachment" is endpoint coincidence only. `geometry/adjacency.py:attachment_points` uses a segment's two endpoints, an arc's two endpoints, a POINT, or an MTEXT insert. A crossing in the middle of a segment is not an attachment. Circles have no attachment points.

Existing tests that must keep passing if the one-end path is unchanged include `test_manual_edit_one_end_attached_trims_not_deletes`, `test_manual_edit_trim_overshoot_to_line`, `test_manual_edit_extend_short_to_line`, and `test_manual_edit_supporting_line_counts_target_short` in `tests/test_rules_manual_edit.py`.

### What to do

The piece to remove is the collinear span that contains the click, walked in both directions, stopping at the first intersection on each side. Do not rotate the line. Do not delete collinear geometry past that intersection.

An intersection here is either:

- an endpoint of the collinear piece that lies within `eps_coincide` of an attachment point of an entity that is not part of the piece, or
- a crossing of external geometry through the interior of the piece.

Collinear neighbors with only an endpoint gap between them, and no other geometry at that joint, stay in the same piece. That is the difference from deleting one DXF segment, and the difference from deleting the whole `chain_run` when the run continues through a joint.

If both sides of that span are intersections and every member lies wholly inside it, return a deletion of those entity-level eids (`ok=True`, `trims=[]`). That is the reported bug: a segment between two corners, plus an off-axis line that today wins as a perpendicular foot.

If a member continues past the intersection, do not delete that member. Shorten it on its own axis to the intersection point. `Model.apply_edit` already does that kind of member surgery for a `Trim`, and it returns immediately when `deletions` is non-empty, so it will not apply a trim in the same result. Use a deletion when the span covers whole entities only. Use one on-axis `Trim` when a member must survive past the intersection. Read `apply_edit` before adding a third mutation shape.

One end attached, or neither end attached, stays on the current path. The stray rule (zero external attachments deletes the whole run) stays. Do not change the perpendicular-foot math for those cases.

`TrimFSM.click_world` (`ui/trim_panel.py`) shows `TRIM_PREVIEW_DELETE` ("Stray line (no attachments) — the whole run will be deleted.") for every result with `deletions`. Put a pinned warning on this deletion, constant in `rules/manual_edit.py`, and branch the status text on it. Add a string in `ui/messages.py` that says the collinear span up to the nearest intersection on each side will be deleted. Do not reuse the stray sentence.

This amends ADR-025. Append the next ADR in `documentation/DECISIONS.md` (ADR-027 is the latest). Update the `trim_to_closest` comment in `documentation/CONTRACTS.md`. Do not rewrite the old ADR body.

### Tests

Add a fixture: a segment with a wall at each endpoint, plus another segment whose infinite-line foot is off the picked segment's axis (the case that rotates today). Assert `ok`, no trims, and deletions equal that segment's entity-level eids.

Add a second fixture: two collinear segments sharing an endpoint, a third line meeting only at that shared endpoint, and a wall at the far end of the clicked segment. Click the first segment. Assert the second segment is not deleted. The shared endpoint is the first intersection.

Keep the one-end and stray tests green without editing their expected geometry.

Add a trim-FSM assertion that this preview inline is the new string, not `TRIM_PREVIEW_DELETE`. `tests/test_ui_trim_fsm.py::test_trim_fsm_stray_delete_preview_inline` covers the stray wording; leave that case on the stray string.

---

## 4. Start maximized

> **Status: Done** — `documentation/sessions/2026-10-08-DEBUG-4.md`

### What happens

The window opens at a fixed 1200×800.

### Why (verified)

`App.__init__` calls `root.geometry("1200x800")`. Nothing sets the window state.

### What to do

At the end of `App.__init__`, after the widgets exist, call `root.state("zoomed")` so the window opens maximized on Windows. Keep `geometry("1200x800")` so an un-maximize has a size. Do not use fullscreen (`attributes("-fullscreen")`); the title bar, File menu, and side rail stay visible.

If `state("zoomed")` raises, catch it and continue with the geometry. Startup must not crash.

`tests/test_ui_collapsible.py` constructs `App`. Those assertions are about the rail, not the window size. Keep them passing.

### Do not

- Do not change `ExportDialog.geometry`.

---

## 5. Fold layer list

> **Status: Done** — `documentation/sessions/2026-10-08-DEBUG-5.md`

### What happens

The Folds section shows a label "Auto-pick layers:" and one entry whose default text is `bend, fold, centerline`. It does not list the layers in the file, and it does not say what the text does.

### Why (verified)

`FoldPanel` (`ui/fold_panel.py`) stores `DEFAULT_FOLD_PATTERNS = ("bend", "fold", "centerline")`. The entry is `pattern_var`. On FocusOut or Return, `_patterns_edited` splits on commas and stores the stripped tokens. It does not run selection again.

`FoldFSM.auto_preselect` runs from `FoldPanel.on_load`, which `App.open_path` calls once per Open. For each straight `Seg`, if `layer_of[eid].lower()` contains any pattern, that eid is added to `fold_eids`. Match is a substring, case-insensitive. There is no "first name is the part, second name is the folds" rule.

`layer_of` is built in `dxf_io/load.py` as eid → DXF layer name. `FoldPanel` does not keep it after `on_load`.

`tests/test_ui_fold_fsm.py` pins this: `test_fold_fsm_auto_preselect_fires_once_per_load`, `test_fold_fsm_auto_preselect_case_insensitive`, `test_fold_fsm_auto_preselect_user_authoritative_after`, `test_fold_fsm_auto_preselect_custom_patterns`, `test_fold_panel_default_patterns`.

### What to do

Keep the keyword entry. Replace the label `Auto-pick layers:` with `Bend import keywords`. Under it, one sentence: `On import, straight lines on layers whose names contain these words are marked as bends.` Default text stays `bend, fold, centerline`. Comma-separated, case-insensitive substring match, unchanged. Editing the box still only updates the words used on the next Open. It does not re-run selection on the file already open. Strings live in `ui/messages.py`.

Under that, add a checkbox for each layer in the file.

- Remember `layer_of` on the panel from `on_load`.
- One row per distinct layer that contains at least one `Seg`, in the order layers are first inserted into `layer_of` (load walks modelspace; Python dicts keep that order). Skip layers that have no straight lines. Arcs, circles, points, and text are not fold lines (`pick_fold_line` already ignores them).
- Label: layer name, then the straight-line count on that layer.
- On load, `auto_preselect` still designates straight lines whose layer name contains any keyword in the box. Those layers start checked. Other layers start unchecked. Keep `DEFAULT_FOLD_PATTERNS` in code.
- Check on: add every `Seg` eid on that layer to `fold_eids`.
- Check off: remove every `Seg` eid on that layer from `fold_eids`.
- Mixed layer (some of its lines designated, some not): show the box unchecked, and do not change `fold_eids` until the user clicks it. A click from that state designates all of the layer's straight lines. The next click clears them.
- After a manual fold click, undo, redo, or revert, refresh the checks from `fold_eids` (`on_model_change` already runs on undo/redo/revert).
- User edits still win over a second automatic pass. Do not call `auto_preselect` again on undo. The existing once-per-load tests stay true.
- A long list scrolls with the rail when the column is taller than the viewport. `Sidebar` already scrolls Dogbone, Folds, and Trim together in that case. Do not add a new window.

`test_fold_fsm_auto_preselect_custom_patterns` calls `auto_preselect` with an explicit pattern tuple. Leave that function able to take patterns. Update `test_fold_panel_default_patterns` so it still finds the entry, the default text `bend, fold, centerline`, and the new label.

### Do not

- Do not change fold export or `rules/folds.py`.
- Do not designate arcs.

---

## 6. Escape cancels a bad corner pick

> **Status: Done** — `documentation/sessions/2026-10-08-DEBUG-6.md`

### What happens

Picking two parallel lines (or any other refused pair) leaves edge 1 highlighted and asks for edge 2. Escape does not cancel once focus has left the drawing. The refusal text does not mention Escape.

### Why (verified)

A refused pair is handled in `WorkflowFSM._compute_ghosts` (`ui/workflow.py`). On `Refusal` it clears edge 2 only, stays in `PICK_EDGE2`, and sets `inline` to `TOAST_REFUSED` with the engine reason unchanged. Parallel edges produce the engine string `PARALLEL: edges are parallel or collinear (no supporting-line intersection)` from `rules/engine.py`. The status line is `STATUS_PICK_EDGE2` ("Click edge 2.") plus that inline. `WorkflowUI._sync_view` writes it through `on_status` to `App.status_var`. There is no modal for this refusal.

`WorkflowFSM.esc` already clears both edges, ghosts, and the preview, and returns to `IDLE`. `tests/test_ui_workflow_fsm.py::test_fsm_esc_restarts_from_any_state_no_partial_survives` pins that. The FSM is not stuck. The key binding is.

`WorkflowUI._bind` binds `<Escape>` on the canvas only, with `add=True`, and calls `focus_set` once. Nothing in `ui/canvas_view.py` sets `takefocus` or focuses the canvas on click. After focus moves to the side panel (the diameter entry, a section header, a button), the canvas binding does not run. The T key works from anywhere because `App.__init__` binds `<t>` and `<T>` on the root. Tk delivers a root binding while a child is focused, then the child, because the toplevel is on the widget's bindtags. A canvas handler that does not `return "break"` lets the event continue to the root.

`STATUS_PREVIEW` already says "press Esc to restart." `STATUS_PICK_EDGE1`, `STATUS_PICK_EDGE2`, `STATUS_GHOSTS`, and `TOAST_REFUSED` do not.

Fold mode and trim mode also bind canvas Escape, and they replace the corner workflow's script while they are on. Fold Escape exits fold mode. Trim Escape must keep exiting trim mode.

### What to do

Add one root `<Escape>` binding in `App`, same place as the T binding. Handler:

1. Fold mode on: exit fold mode the way `FoldPanel._on_esc` does, then `return "break"`.
2. Else trim mode on: exit trim mode, then `return "break"`.
3. Else if the corner workflow exists: `workflow.fsm.esc()`, `_sync_view`, `_update_confirm`, then `return "break"`.

Make the existing canvas Escape handlers (`WorkflowUI._on_esc`, `FoldPanel._on_esc`, and the trim panel's Escape handler) `return "break"` so a focused canvas does not run both the canvas handler and the root handler. Check the trim handler's name in `ui/trim_panel.py` before editing; it is the script installed for `<Escape>` while trim mode is on.

Add "Press Esc to cancel." to the bottom status line only. Put it on `STATUS_PICK_EDGE1`, `STATUS_PICK_EDGE2`, and `STATUS_GHOSTS`. When a refusal inline is shown, the status text must still contain the engine reason verbatim (`test_fsm_ghost_refusal_verbatim_and_stay_pick_edge2` uses `reason in fsm.inline`) and must also contain "Press Esc to cancel." Do not paraphrase the engine reason. Do not add a messagebox.

`test_fsm_same_edge_twice_inline_and_stay` compares `fsm.inline` to `SAME_EDGE_INLINE` exactly. Leave that constant's text, or update the test in the same change if you add the Esc sentence there too. Adding it is reasonable; the user asked for the refusal case specifically. Do not change `SAME_EDGE_INLINE` unless you update that assertion.

### Do not

- Do not clear edge 1 on a refusal. Escape is the abort. A different second edge must still be allowed, which is what `_compute_ghosts` does now.
- Do not change the `PARALLEL:` string in `rules/engine.py`.
- Task 7 replaces the bottom-right Confirm button. This task only needs the summary line to keep updating. If `_update_confirm` has been renamed, call the method that still refreshes `summary_var`.

---

## 7. Bottom-right Confirm becomes Export DXF

> **Status: Done** — `documentation/sessions/2026-10-08-DEBUG-7.md`

### What happens

The button at the bottom right reads Confirm and does not appear to do anything.

### Why (verified)

`App.__init__` packs `self.confirm_btn` on the bottom bar, `side=RIGHT`, command `on_confirm`. `_update_confirm` enables it only while the corner FSM is `SIDE_PICKED`. The rest of the time it is disabled.

`on_confirm` calls `workflow.confirm_click()`. On this workflow that enqueues the corner for Apply All. It does not export. The control that actually confirms a corner after the preview zoom is the floating "CONFIRM CORNER" pill from `WorkflowUI._show_confirm_pill`. Enter still calls `confirm_click` from `WorkflowUI._on_enter`.

File > Export DXF calls `App.export_dialog`. That opens `ExportDialog`. It refuses with `EXPORT_NEED_FILE` when no file is open.

### What to do

Replace the bottom-right Confirm button with an Export DXF button in the same pack position. Its command is `export_dialog`, the same method as the File menu item. Label it with `msg.EXPORT_MENU` (`"Export DXF..."`). Leave it enabled. `export_dialog` already explains when no file is open.

Keep the summary label. `_update_confirm` may still refresh `summary_var` on state changes. It must not look up `confirm_btn` after that button is gone. Remove `on_confirm` if nothing calls it.

Keep the floating CONFIRM CORNER pill and the Enter key. Those still confirm a corner.

### Do not

- Do not change `ExportDialog` or the export engine.
- Do not remove Apply All.

### Tests

`tests/test_ui_collapsible.py` builds `App` and does not mention `confirm_btn`. Keep it passing. Add an assertion that the bottom-right button's text is `msg.EXPORT_MENU` and that its command is `App.export_dialog`.
