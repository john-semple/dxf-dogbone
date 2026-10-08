# 2026-10-08 — Flag card

Handoff for the interactive flag prompt. Presentation only. Engine sticky decisions, the confirm-gate, and export are unchanged.

Read this file before editing the card. The paragraphs below describe the behavior as it is now.

## What the user sees

Picking a ghost zooms to the corner, then asks about each pending flag one at a time. Chord-crossers come first, then the other reasons.

- The entity the question is about is drawn in thick orange (`CHORD_TAG`, width 5, theme `flag`). Other flagged entities stay the thin orange outline. An entity that was just deleted turns red with the rest of the deletion preview.
- The card is muted grey with rounded corners (`dock_bg`, `dock_btn`, `dock_text`, `dock_muted`, `dock_edge` in `ui/theme.py`). It is not red, orange, or accent blue. The square widget corners are the canvas background, so the drawn shape reads as rounded.
- Copy is one line from `ui/messages.py` (`FLAG_CARD_BODY`), fully visible above the buttons. Chord-crosser: "This {kind} crosses the relief." Cascade: "This {kind} is no longer attached to the part." Circle: "This circle lies in the relief." Note: "This note lies in the relief." Arc ending inside: "This arc ends inside the relief." Kind is `line`, `arc`, `circle`, `point`, or `note`.
- **Delete** is under the pointer that picked the ghost. **Keep** is on that same row, immediately to the right. The text sits above the buttons. The user must not have to move down from the click to reach Delete.
- If that placement would cover the relief circle, the card steps to the nearest side that clears the circle (right, left, below, above of the circle), staying as close to the pointer as it can. The zoom is not panned.
- That button spot is pinned for the rest of the preview. The next flag does not move Delete. After the last answer, **Confirm** is only the word Confirm on its own rounded button, with no blank text line above it, and its center is that same pinned spot.
- A click counts without waiting and without moving the pointer. The card window does not take the click: on Windows `_install_click_through` answers `WM_NCHITTEST` with `HTTRANSPARENT`, and the click lands on the viewer canvas. `_relay_dock_click` hit-tests that point against the buttons. There is no pause before Confirm.
- The button under that pointer is already the lighter grey (`dock_btn_hover`) when the card is drawn, and again when the next flag or Confirm is drawn. `<Motion>` is what repaints it, and the pointer has not moved, so `_hover_under_pointer` reads the pointer and paints once. A later move still updates from `<Motion>`.
- The count sits at the top right in `dock_muted` (`FLAG_CARD_COUNT`, `{n}/{m}`): `1/3`, `2/3`, `3/3`, including `1/1`. It is the flags asked for this preview, snapshotted in `_ask_eids` the first time the card opens. Chord-crossers come first. Confirm has no count.
- A double-click on Delete answers two flags when two are pending, because Delete stays put. A double-click on the last Delete also presses Confirm, because Confirm is already under the pointer.
- Esc still abandons the whole corner. Enter still confirms the corner. The bottom-right button is Export DXF, not this card.

`decide_flag` is the harness yes/no. The interactive preview does not call it.

## What must stay true

- Decisions are still `ModelState.flag_decisions[eid]` in `{"delete","keep","trim"}`, sticky for the session, honored on recompute, cleared only by Revert-to-Original (ADR-009/013). The card writes `delete` or `keep` only. ARC chord-crosser trim is still available to the engine and to scripted tests; the card does not offer a Trim button.
- Confirm stays blocked while any flag on the preview has `decision is None`.
- Do not destroy and recreate the dock between two answers. `_choose_chord` repaints overlays and updates the same canvas. `_sync_view` destroys the dock; calling it from the button handler drops the second half of a double-click onto the drawing.
- The dock is a `tk.Canvas` **placed on** the viewer canvas. It is not a canvas item. Pan (`move("all")`) and `redraw()` (`delete("all")`) must not be what positions it. The thick highlight is a canvas item, so a wheel zoom wipes the highlight until the next preview paint; the card stays.
- No hex literals in `ui/workflow.py`. New colours go in `ui/theme.py`.
- `tools/verify_gui.py` never opens this card. It calls `_prompt_pending_flags`, and its subclass replaces `decide_flag` with scripted answers. Do not route that path through the card.

## Where it lives

| Piece | Where |
|---|---|
| Card, highlight, placement, click-through, hover | `ui/workflow.py` — `_dock_origin`, `_place_dock`, `_show_flag_contents`, `_show_confirm_contents`, `_choose_chord`, `_highlight_pending_chord`, `_pending_flag`, `_ask_progress`, `_relay_dock_click`, `_install_click_through`, `_hover_under_pointer`, `_pointer_on_dock` |
| Strings | `ui/messages.py` — `FLAG_CARD_BODY`, `FLAG_CARD_COUNT`, `CHORD_CARD_DELETE`, `CHORD_CARD_KEEP` |
| Greys | `ui/theme.py` — `dock_bg`, `dock_btn`, `dock_btn_hover`, `dock_text`, `dock_muted`, `dock_edge` |
| Tests | `tests/test_ui_chord_prompt.py` |

Pointer anchor: `_on_left` stores the ghost-click screen point in `_dock_anchor` and clears `_dock_pinned` / `_button_at` before `pick_ghost`. `_sync_view` clears those three when the state is no longer `SIDE_PICKED`. `_button_at` is the screen point Delete (and later Confirm) must occupy.

No-pointer fallback (harness and tests that never set `_dock_anchor`): the card sits just to the right of the relief circle, vertically centered. `_dock_origin` ignores the button hotspot in that case.

## Tests last run for this work

`tests/test_ui_chord_prompt.py` covers one thick highlight, Delete staying put across two chord-crossers, the `1/2` then `2/2` count, Confirm with no body text on that same spot, a canvas click confirming immediately, a stale widget coordinate still hitting via the screen position, the button under a still pointer already using `dock_btn_hover`, pointer placement, stepping aside when the pointer is on the circle, and a cascade flag using the same card (`1/1`).

`pytest -q` → 328 passed.

Re-run `python tools/verify_gui.py --full` if you change the harness seam or `_sync_view`'s preview order. The harness still answers flags through `_prompt_pending_flags`, not this card.
