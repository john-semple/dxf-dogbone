"""Fold-mode shell: left-click selects, left-drag pans, right-drag box-selects.

The FSM tests drive click_world / box_select directly. These call the
canvas handlers FoldPanel installs while fold mode is on.
"""
from __future__ import annotations

import tkinter as tk

import pytest

from geometry.entities import Arc, Pt, Seg
from model.model import Model
from model.state import ModelState
import ui.messages as msg
from ui.canvas_view import Viewer
from ui.fold_panel import BOX_SELECT_PX, FoldMode, FoldPanel


class _Ev:
    def __init__(self, x: float, y: float, state: int = 0):
        self.x = x
        self.y = y
        self.state = state


def _open():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"no display for tkinter: {exc}")
    root.withdraw()
    viewer = Viewer(root, width=200, height=200)
    model = Model(ModelState(primitives=[
        Seg("L1", Pt(0, 0), Pt(100, 0)),
    ]))
    viewer.set_model(model.state)
    panel = FoldPanel(root, viewer, model)
    panel.toggle_mode()
    return root, panel


def _watch(panel: FoldPanel) -> list:
    seen: list = []
    panel.fsm.box_select = lambda *a, **k: seen.append(("box", k.get("shift")))
    panel.fsm.click_world = lambda *a, **k: seen.append(("click", k.get("shift")))
    return seen


def test_fold_panel_left_click_selects_and_drag_pans():
    root, panel = _open()
    try:
        seen = _watch(panel)
        ox, oy = panel.viewer.transform.ox, panel.viewer.transform.oy
        panel._on_left_press(_Ev(10, 20))
        panel._on_left_drag(_Ev(12, 21))
        panel._on_left_release(_Ev(12, 21, state=0x1))
        assert seen == [("click", True)]
        assert (panel.viewer.transform.ox, panel.viewer.transform.oy) == (ox, oy)

        seen.clear()
        panel._on_left_press(_Ev(10, 20))
        panel._on_left_drag(_Ev(40, 55))
        panel._on_left_release(_Ev(40, 55))
        assert seen == []
        assert panel.viewer.transform.ox == ox + 30
        assert panel.viewer.transform.oy == oy + 35
        assert panel._fold_handlers()["<ButtonPress-1>"] == panel._on_left_press
        assert panel._fold_handlers()["<ButtonRelease-1>"] == panel._on_left_release
        assert panel._hint is not None
        assert panel._hint.winfo_manager() == "place"
        assert panel._hint.cget("text") == "Right-drag to box-select"
        info = panel._hint.place_info()
        assert float(info["relx"]) == 0.5
        assert float(info["rely"]) == 0.0
        assert info["anchor"] == "n"
    finally:
        root.destroy()


def test_fold_panel_right_drag_box_selects_only_past_threshold():
    root, panel = _open()
    try:
        seen = _watch(panel)
        assert panel._fold_handlers()["<Button-3>"] == panel._on_right_press
        assert panel._fold_handlers()["<ButtonRelease-3>"] == panel._on_right_release

        panel._on_right_press(_Ev(0, 0))
        panel._on_right_drag(_Ev(3, 1))
        assert panel._box_item is not None
        assert panel.viewer.canvas.coords(panel._box_item) == [0.0, 0.0, 3.0, 1.0]
        panel._on_right_release(_Ev(BOX_SELECT_PX - 1, 0))
        assert seen == []
        assert panel._box_item is None
        assert panel.fsm.mode == FoldMode.ON

        panel._on_right_press(_Ev(10, 20, state=0x1))
        panel._on_right_drag(_Ev(10, 20 + BOX_SELECT_PX, state=0x1))
        item = panel._box_item
        assert item is not None
        assert panel.viewer.canvas.coords(item) == [
            10.0, 20.0, 10.0, 20.0 + BOX_SELECT_PX]
        panel._on_right_release(_Ev(10, 20 + BOX_SELECT_PX, state=0x1))
        assert seen == [("box", True)]
        assert panel._box_item is None
        assert item not in panel.viewer.canvas.find_all()
    finally:
        root.destroy()


class _Stack:
    def __init__(self) -> None:
        self.discarded = 0

    def discard_redo(self) -> None:
        self.discarded += 1


def test_fold_panel_layer_checks_follow_straight_lines():
    """One checkbox per layer that has a straight line, in layer_of order.
    Keywords check matching layers on load. A mixed layer stays unchecked
    until clicked, and that click designates every straight line on it."""
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"no display for tkinter: {exc}")
    root.withdraw()
    try:
        viewer = Viewer(root, width=200, height=200)
        model = Model(ModelState(primitives=[
            Seg("L0", Pt(0, 0), Pt(10, 0)),
            Seg("B1", Pt(0, 20), Pt(10, 20)),
            Seg("B2", Pt(0, 40), Pt(10, 40)),
            Arc("A1", Pt(50, 50), 5, 0, 90),
        ]))
        viewer.set_model(model.state)
        panel = FoldPanel(root, viewer, model)
        panel.stack = _Stack()
        panel.on_load({
            "T1": "TITLE",
            "L0": "0",
            "B1": "BEND",
            "A1": "BEND",
            "B2": "BEND",
        })
        assert [b.cget("text") for b in panel._layer_buttons.values()] == [
            "0 (1)", "BEND (2)",
        ]
        assert panel.layer_heading.winfo_manager() == "pack"
        assert panel.layer_heading.cget("text") == msg.FOLD_LAYER_HEADING
        assert panel.layer_hint.cget("text") == msg.FOLD_LAYER_HINT
        assert panel.fsm.fold_eids == {"B1", "B2"}
        assert panel._layer_vars["BEND"].get() is True
        assert panel._layer_vars["0"].get() is False
        assert "A1" not in panel.fsm.fold_eids

        panel._layer_buttons["BEND"].invoke()
        assert panel.fsm.fold_eids == set()
        assert panel._layer_vars["BEND"].get() is False
        assert panel.stack.discarded == 1

        model.state.fold_eids = {"B2"}
        panel.on_model_change()
        assert panel.fsm.fold_eids == {"B2"}
        assert panel._layer_vars["BEND"].get() is False

        panel._layer_buttons["BEND"].invoke()
        assert panel.fsm.fold_eids == {"B1", "B2"}
        panel._layer_buttons["BEND"].invoke()
        assert panel.fsm.fold_eids == set()

        before = set(panel.fsm.fold_eids)
        panel.fsm.fold_eids.add("L0")
        panel.set_fold_eids(panel.fsm.fold_eids)
        panel._note_designation(before)
        assert panel._layer_vars["0"].get() is True

        panel.pattern_var.set("score")
        panel._patterns_edited(None)
        assert panel.fsm.fold_eids == {"L0"}

        model.state.primitives = [
            Seg("S1", Pt(0, 0), Pt(5, 0)),
            Seg("B1", Pt(0, 20), Pt(10, 20)),
        ]
        panel.on_load({"S1": "score", "B1": "BEND"})
        assert panel.fsm.fold_eids == {"S1"}
        assert [b.cget("text") for b in panel._layer_buttons.values()] == [
            "score (1)", "BEND (1)",
        ]

        model.state.primitives = []
        model.state.fold_eids = set()
        panel.on_model_change()
        assert panel._layer_buttons == {}
        assert panel.layer_heading.winfo_manager() == ""
        assert panel.fsm.fold_eids == set()
    finally:
        root.destroy()


def test_fold_panel_box_hint_hidden_on_exit():
    root, panel = _open()
    try:
        assert panel.fsm.mode == FoldMode.ON
        assert msg.FOLD_BOX_HINT == "Right-drag to box-select"
        assert panel._hint.winfo_manager() == "place"
        panel.toggle_mode()
        assert panel.fsm.mode == FoldMode.OFF
        assert panel._hint.winfo_manager() == ""
    finally:
        root.destroy()
