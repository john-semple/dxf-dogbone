"""Chord-crosser card: one thick highlight, grey rounded dock, Confirm button."""
from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace

import pytest

tk = pytest.importorskip("tkinter")
messagebox = pytest.importorskip("tkinter.messagebox")

from dxf_io import load
from geometry.entities import Pt, Seg
from model.model import Model
from ui.canvas_view import Viewer
from ui.theme import COLORS
from ui.workflow import (
    CHORD_FOCUS_WIDTH,
    DOCK_GAP,
    WorkflowState,
    WorkflowUI,
)

ROOT = Path(__file__).resolve().parents[1]
BEFORE = ROOT / "samples" / "base-rectangular-before-AI.DXF"
CORNER1_CLICKS = (Pt(44.0, 122.8), Pt(47.0, 122.4))
CORNER1_CENTER = (45.2534, 121.6506)
CORNER2_CLICKS = (Pt(45.0, 44.0), Pt(47.5, 51.5))
CORNER2_CENTER = (47.2451, 49.2717)


def _root() -> tk.Tk:
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"no display for tkinter: {exc}")
    root.withdraw()
    return root


def _ui(root: tk.Tk, radius: float) -> tuple[Model, WorkflowUI]:
    result = load(BEFORE)
    model = Model(result.model_state)
    viewer = Viewer(root, width=1100, height=750)
    viewer.canvas.pack(fill=tk.BOTH, expand=True)
    root.geometry("1200x800")
    root.update()
    viewer.set_model(model.state)
    root.update()
    ui = WorkflowUI(viewer, model, root, radius_mm=radius)
    ui.start()
    return model, ui


def _reach_preview(ui: WorkflowUI, clicks, center) -> None:
    for p in clicks:
        ui.fsm.click_world(p)
        ui._sync_view()
    assert ui.fsm.state == WorkflowState.GHOSTS_VISIBLE
    best = None
    for g in ui.fsm.ghosts:
        d = math.hypot(g.center.x - center[0], g.center.y - center[1])
        if best is None or d < best[0]:
            best = (d, g)
    assert best is not None and best[0] < 0.001
    ui.fsm.pick_ghost(best[1].side, best[1].side_flip)


def _place(ui: WorkflowUI) -> tuple[int, int, int, int]:
    assert ui._dock is not None
    info = ui._dock.place_info()
    return (int(info["x"]), int(info["y"]), int(info["width"]), int(info["height"]))


def _click(ui: WorkflowUI, name: str) -> None:
    x1, y1, x2, y2 = ui._hits[name]
    ui._on_dock_click(SimpleNamespace(x=(x1 + x2) / 2, y=(y1 + y2) / 2))


def _focus_coords(ui: WorkflowUI) -> list[float]:
    items = ui.viewer.canvas.find_withtag(WorkflowUI.CHORD_TAG)
    assert len(items) == 1
    assert float(ui.viewer.canvas.itemcget(items[0], "width")) == CHORD_FOCUS_WIDTH
    return [float(v) for v in ui.viewer.canvas.coords(items[0])]


def _line_screen(ui: WorkflowUI, eid: str) -> list[float]:
    e = ui.model.get(eid)
    assert isinstance(e, Seg)
    x1, y1 = ui.transform.to_screen(e.a)
    x2, y2 = ui.transform.to_screen(e.b)
    return [x1, y1, x2, y2]


def test_chord_card_stays_put_and_highlights_one_entity(monkeypatch):
    def _no_modal(*_a, **_k):
        raise AssertionError("chord-crosser must not open a message box")

    monkeypatch.setattr(messagebox, "askyesno", _no_modal)
    root = _root()
    try:
        _model, ui = _ui(root, 1.5875)
        _reach_preview(ui, CORNER1_CLICKS, CORNER1_CENTER)
        ui._sync_view()

        first = ui._pending_chord()
        assert first is not None and first.reason == "CHORD_CROSSER"
        assert ui._dock is not None
        body = " ".join(ui._dock.itemcget(i, "text")
                        for i in ui._dock.find_withtag("body"))
        assert "crosses the relief" in body
        assert "Keep leaves" not in body
        assert len(ui._dock.find_withtag("body")) == 1
        assert ui._dock.itemcget("count", "text") == "1/2"
        bb = ui._dock.bbox("body")
        assert bb is not None
        _x, _y, _w, h = _place(ui)
        assert bb[3] <= ui._hits["delete"][1] - 4
        assert bb[3] < h
        assert ui._dock.itemcget("card", "fill") == COLORS["dock_bg"]
        assert ui._dock.itemcget("delete", "fill") == COLORS["dock_btn"]
        assert len(ui._dock.coords("card")) > 16
        db = ui.fsm.preview.dogbone
        assert db is not None
        cx, cy = ui.transform.to_screen(db.center)
        r_px = db.r * ui.transform.scale
        assert _focus_coords(ui) == pytest.approx(_line_screen(ui, first.eid))

        dock = ui._dock
        origin = _place(ui)
        assert origin[:2] == ui._dock_origin(origin[2], origin[3])
        assert origin[0] == int(round(cx + r_px + DOCK_GAP))
        assert abs((origin[1] + origin[3] / 2) - cy) <= 1
        delete_hit = ui._hits["delete"]
        assert "confirm" not in ui._hits

        _click(ui, "delete")
        second = ui._pending_chord()
        assert second is not None and second.eid != first.eid
        assert ui.model.state.flag_decisions[first.eid] == "delete"
        assert ui._dock is dock
        assert _place(ui) == origin
        assert ui._hits["delete"] == delete_hit
        assert _focus_coords(ui) == pytest.approx(_line_screen(ui, second.eid))
        assert ui._dock.itemcget("count", "text") == "2/2"
        assert "confirm" not in ui._hits

        _click(ui, "delete")
        assert ui._pending_chord() is None
        assert ui.model.state.flag_decisions[second.eid] == "delete"
        assert ui._dock is dock
        confirm_box = _place(ui)
        assert confirm_box[3] < origin[3]
        assert ui._dock.find_withtag("body") == ()
        assert ui._dock.itemcget("confirm-label", "text") == "Confirm"
        assert ui._dock.itemcget("confirm", "fill") == COLORS["dock_btn"]
        assert confirm_box[:2] == origin[:2]
        assert ui.viewer.canvas.find_withtag(WorkflowUI.CHORD_TAG) == ()

        n = len(ui.model.state.dogbones)
        cx = confirm_box[0] + confirm_box[2] / 2
        cy = confirm_box[1] + confirm_box[3] / 2
        ui.viewer._pan_from = (0.0, 0.0)
        ui._on_left(SimpleNamespace(x=cx, y=cy))
        assert len(ui.model.state.dogbones) == n + 1
        assert ui.viewer._pan_from is None
    finally:
        root.destroy()


def test_still_pointer_lights_the_button_without_motion(monkeypatch):
    """The card opens under the pointer. Hover must not wait for a move."""
    root = _root()
    try:
        _model, ui = _ui(root, 1.5875)
        _reach_preview(ui, CORNER1_CLICKS, CORNER1_CENTER)

        def _over_delete(self):
            hit = self._hits.get("delete")
            if hit is None:
                return None
            x1, y1, x2, y2 = hit
            return ((x1 + x2) / 2, (y1 + y2) / 2)

        monkeypatch.setattr(WorkflowUI, "_pointer_on_dock", _over_delete)
        ui._sync_view()
        assert ui._dock is not None
        assert ui._dock.itemcget("delete", "fill") == COLORS["dock_btn_hover"]
        assert ui._dock.itemcget("keep", "fill") == COLORS["dock_btn"]
    finally:
        root.destroy()


def test_stale_local_click_still_hits_the_button():
    """A click just after the card moves carries a stale widget x/y.

    The screen position is the one that counts.
    """
    root = _root()
    try:
        _model, ui = _ui(root, 1.5875)
        _reach_preview(ui, CORNER1_CLICKS, CORNER1_CENTER)
        ui._sync_view()
        flag = ui._pending_chord()
        assert flag is not None and ui._dock is not None
        root.update_idletasks()
        x1, y1, x2, y2 = ui._hits["delete"]
        ui._on_dock_click(SimpleNamespace(
            x=-20, y=-20,
            x_root=ui._dock.winfo_rootx() + (x1 + x2) / 2,
            y_root=ui._dock.winfo_rooty() + (y1 + y2) / 2,
        ))
        assert ui.model.state.flag_decisions[flag.eid] == "delete"
    finally:
        root.destroy()


def test_confirm_without_a_chord_uses_the_same_dock():
    root = _root()
    try:
        model, ui = _ui(root, 1.5875)
        model.state.flag_decisions["85"] = "delete"
        model.state.flag_decisions["89"] = "delete"
        _reach_preview(ui, CORNER1_CLICKS, CORNER1_CENTER)
        ui._sync_view()
        assert ui._pending_chord() is None
        assert ui._dock is not None
        box = _place(ui)
        assert box[:2] == ui._dock_origin(box[2], box[3])
        assert ui._dock.find_withtag("body") == ()
        assert ui._dock.itemcget("confirm-label", "text") == "Confirm"
        assert ui._hits.keys() == {"confirm"}
        assert ui._confirm_ready_at == 0.0
    finally:
        root.destroy()


def test_other_flags_use_the_same_card(monkeypatch):
    def _no_modal(*_a, **_k):
        raise AssertionError("flag card must not open a message box")

    monkeypatch.setattr(messagebox, "askyesno", _no_modal)
    root = _root()
    try:
        _model, ui = _ui(root, 3.175)
        _reach_preview(ui, CORNER2_CLICKS, CORNER2_CENTER)
        ui._sync_view()
        flag = ui._pending_flag()
        assert flag is not None and flag.reason == "CASCADE_DANGLING"
        assert ui._pending_chord() is None
        assert ui._dock is not None
        body = " ".join(ui._dock.itemcget(i, "text")
                        for i in ui._dock.find_withtag("body"))
        assert body == "This line is no longer attached to the part."
        assert ui._dock.itemcget("count", "text") == "1/1"
        assert "confirm" not in ui._hits
        assert len(ui.viewer.canvas.find_withtag(WorkflowUI.CHORD_TAG)) == 1
        assert float(ui.viewer.canvas.itemcget(
            ui.viewer.canvas.find_withtag(WorkflowUI.CHORD_TAG)[0],
            "width")) == CHORD_FOCUS_WIDTH

        _w, h = ui._canvas_px()
        _reseat(ui, (90.0, h - 90.0))
        x, y, _w, _h = _place(ui)
        dx1, dy1, dx2, dy2 = ui._hits["delete"]
        assert x + (dx1 + dx2) / 2 == pytest.approx(90.0, abs=1)
        assert y + (dy1 + dy2) / 2 == pytest.approx(h - 90.0, abs=1)

        _click(ui, "delete")
        assert ui.model.state.flag_decisions[flag.eid] == "delete"
        assert ui._pending_flag() is None
        assert ui._dock.find_withtag("body") == ()
        assert ui._hits.keys() == {"confirm"}
    finally:
        root.destroy()


def _reseat(ui: WorkflowUI, anchor: tuple[float, float]) -> None:
    ui._dock_anchor = anchor
    ui._dock_pinned = None
    ui._button_at = None
    ui._destroy_pill()
    ui._present_dock()


def test_card_follows_the_pointer_when_it_misses_the_circle():
    root = _root()
    try:
        _model, ui = _ui(root, 1.5875)
        _reach_preview(ui, CORNER1_CLICKS, CORNER1_CENTER)
        ui._sync_view()
        _w, _h = ui._canvas_px()
        anchor = (90.0, _h - 90.0)
        _reseat(ui, anchor)
        x, y, _w, _h = _place(ui)
        dx1, dy1, dx2, dy2 = ui._hits["delete"]
        assert x + (dx1 + dx2) / 2 == pytest.approx(anchor[0], abs=1)
        assert y + (dy1 + dy2) / 2 == pytest.approx(anchor[1], abs=1)
        assert y < anchor[1]
    finally:
        root.destroy()


def test_card_steps_aside_when_the_pointer_is_on_the_circle():
    root = _root()
    try:
        _model, ui = _ui(root, 1.5875)
        _reach_preview(ui, CORNER1_CLICKS, CORNER1_CENTER)
        ui._sync_view()
        db = ui.fsm.preview.dogbone
        assert db is not None
        cx, cy = ui.transform.to_screen(db.center)
        r_px = db.r * ui.transform.scale
        _reseat(ui, (cx, cy))
        x, y, w, h = _place(ui)
        nearest_x = min(max(cx, x), x + w)
        nearest_y = min(max(cy, y), y + h)
        assert math.hypot(cx - nearest_x, cy - nearest_y) >= r_px - 1
        assert math.hypot(x - cx, y - cy) < w + h + DOCK_GAP
    finally:
        root.destroy()
