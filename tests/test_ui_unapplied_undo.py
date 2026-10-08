"""Undo removes a confirmed corner that was never applied.

The pending queue is not part of the snapshot stack. Each confirm records
the stack depth. Undo pops that one corner while the depth still matches,
and leaves the stack alone. A later push (trim or Apply All) is undone
first. Revert keeps the queue and forgets those depths.
"""
from __future__ import annotations

import pytest

from geometry.entities import Pt, Seg, Side
from model.model import Model
from model.snapshots import SnapshotStack
from model.state import ModelState
from ui.workflow import PendingCorner
import ui.messages as msg


def _prims():
    return [
        Seg("e1", Pt(0.0, 0.0), Pt(0.0, -10.0)),
        Seg("e2", Pt(0.0, 0.0), Pt(3.0, 0.0)),
        Seg("e5", Pt(200.0, 0.0), Pt(200.0, -10.0)),
        Seg("e6", Pt(200.0, 0.0), Pt(203.0, 0.0)),
    ]


def _root():
    import tkinter as tk

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"no display for tkinter: {exc}")
    root.withdraw()
    return root


class _Panel:
    def __init__(self):
        self.undo_enabled = None

    def set_pending_count(self, n):
        pass

    def set_undo_enabled(self, enabled):
        self.undo_enabled = enabled

    def set_redo_enabled(self, enabled):
        pass

    def set_revert_enabled(self, enabled):
        pass

    def diameter_mm(self):
        return None


def _ui(root, panel=None):
    from ui.apply_panel import ApplyAllWorkflowUI
    from ui.canvas_view import Viewer

    st = ModelState()
    st.primitives = _prims()
    model = Model(st)
    stack = SnapshotStack(model)
    viewer = Viewer(root, width=400, height=300)
    ui = ApplyAllWorkflowUI(
        viewer, model, root, stack=stack, panel=panel)
    return model, ui


def _confirm(ui, e1, e2):
    ui.fsm.pending = PendingCorner(
        edge1_eid=e1, edge2_eid=e2, side=Side(+1), side_flip=1,
        r=1.0, db_id=f"db-{e1}+{e2}")
    ui.apply(None)


def test_undo_drops_last_unapplied_corner_and_apply_all_skips_it():
    root = _root()
    try:
        model, ui = _ui(root)
        depth = len(ui.stack)
        _confirm(ui, "e1", "e2")
        _confirm(ui, "e5", "e6")
        assert ui.undo()
        assert [p.edge1_eid for p in ui.queue.queue] == ["e1"]
        assert len(ui.stack) == depth
        assert ui.stack.can_undo()
        assert not model.state.dogbones
        assert msg.UNDO_QUEUED in ui.fsm.status

        assert ui.undo()
        assert ui.queue.queue == []
        assert len(ui.stack) == depth
        applied, skips = ui.apply_all()
        assert applied == 0 and skips == []
        assert not model.state.dogbones
    finally:
        root.destroy()


def test_undo_after_apply_drops_the_new_corner_then_the_batch():
    root = _root()
    try:
        model, ui = _ui(root)
        _confirm(ui, "e1", "e2")
        applied, skips = ui.apply_all()
        assert applied == 1 and skips == []
        assert ui._unapplied_depths == []
        kept = len(model.state.dogbones)
        _confirm(ui, "e5", "e6")
        assert ui.undo()
        assert ui.queue.queue == []
        assert len(model.state.dogbones) == kept
        assert ui.undo()
        assert model.state.dogbones == []
        assert [p.edge1_eid for p in ui.queue.queue] == ["e1"]
        assert msg.UNDO_APPLIED in ui.fsm.status
        assert ui.undo()
        assert ui.queue.queue == []
    finally:
        root.destroy()


def test_revert_keeps_the_queue_and_undo_does_not_remove_it():
    root = _root()
    try:
        _model, ui = _ui(root)
        _confirm(ui, "e1", "e2")
        ui.apply_all()
        _confirm(ui, "e5", "e6")
        assert ui.revert_to_original()
        assert [p.edge1_eid for p in ui.queue.queue] == ["e5"]
        assert ui._unapplied_depths == []
        assert not ui.stack.can_undo()
        assert ui.undo() is False
        assert [p.edge1_eid for p in ui.queue.queue] == ["e5"]
    finally:
        root.destroy()


def test_revert_then_confirm_undo_removes_only_the_new_corner():
    root = _root()
    try:
        model, ui = _ui(root)
        _confirm(ui, "e1", "e2")
        ui.apply_all()
        _confirm(ui, "e1", "e2")
        ui.revert_to_original()
        _confirm(ui, "e5", "e6")
        assert [p.edge1_eid for p in ui.queue.queue] == ["e1", "e5"]
        assert ui.undo()
        assert [p.edge1_eid for p in ui.queue.queue] == ["e1"]
        assert not model.state.dogbones
        assert ui.undo() is False
        assert [p.edge1_eid for p in ui.queue.queue] == ["e1"]
    finally:
        root.destroy()


def test_trim_push_is_undone_before_the_queued_corner():
    root = _root()
    try:
        model, ui = _ui(root)
        _confirm(ui, "e1", "e2")
        ui.stack.push()
        model.state.flag_decisions["probe"] = "keep"
        assert ui.undo()
        assert "probe" not in model.state.flag_decisions
        assert [p.edge1_eid for p in ui.queue.queue] == ["e1"]
        assert msg.UNDO_TOAST in ui.fsm.status
        assert ui.undo()
        assert ui.queue.queue == []
        assert msg.UNDO_QUEUED in ui.fsm.status
    finally:
        root.destroy()


def test_redo_restores_the_drawing_and_not_the_removed_corner():
    root = _root()
    try:
        model, ui = _ui(root)
        _confirm(ui, "e1", "e2")
        ui.apply_all()
        assert ui.undo()
        assert model.state.dogbones == []
        assert ui.stack.can_redo()
        _confirm(ui, "e5", "e6")
        assert ui.stack.can_redo()
        assert [p.edge1_eid for p in ui.queue.queue] == ["e1", "e5"]
        assert ui.undo()
        assert [p.edge1_eid for p in ui.queue.queue] == ["e1"]
        assert model.state.dogbones == []
        assert ui.stack.can_redo()
        assert ui.redo()
        assert len(model.state.dogbones) == 1
        assert ui.queue.queue == []
    finally:
        root.destroy()


def test_radius_replace_then_undo_pops_the_last_corner():
    root = _root()
    try:
        _model, ui = _ui(root)
        _confirm(ui, "e1", "e2")
        _confirm(ui, "e5", "e6")
        ui.on_radius_change()
        assert ui.undo()
        assert [p.edge1_eid for p in ui.queue.queue] == ["e1"]
    finally:
        root.destroy()


def test_undo_button_enables_for_a_confirm_after_revert():
    root = _root()
    try:
        panel = _Panel()
        _model, ui = _ui(root, panel=panel)
        _confirm(ui, "e1", "e2")
        ui.apply_all()
        ui.revert_to_original()
        assert ui.stack.can_undo() is False
        assert panel.undo_enabled is False
        _confirm(ui, "e5", "e6")
        assert ui.stack.can_undo() is False
        assert panel.undo_enabled is True
    finally:
        root.destroy()


def test_undo_apply_all_then_each_corner_newest_first():
    root = _root()
    try:
        model, ui = _ui(root)
        _confirm(ui, "e1", "e2")
        _confirm(ui, "e5", "e6")
        applied, skips = ui.apply_all()
        assert applied == 2 and skips == []
        assert ui.queue.queue == []
        assert ui.undo()
        assert model.state.dogbones == []
        assert [p.edge1_eid for p in ui.queue.queue] == ["e1", "e5"]
        assert ui.undo()
        assert [p.edge1_eid for p in ui.queue.queue] == ["e1"]
        assert model.state.dogbones == []
        assert ui.undo()
        assert ui.queue.queue == []
        assert model.state.dogbones == []
    finally:
        root.destroy()


def test_trim_after_apply_is_undone_before_the_batch_returns():
    root = _root()
    try:
        model, ui = _ui(root)
        _confirm(ui, "e1", "e2")
        ui.apply_all()
        assert len(model.state.dogbones) == 1
        ui.stack.push()
        model.state.flag_decisions["probe"] = "keep"
        assert ui.undo()
        assert "probe" not in model.state.flag_decisions
        assert ui.queue.queue == []
        assert len(model.state.dogbones) == 1
        assert ui.undo()
        assert model.state.dogbones == []
        assert [p.edge1_eid for p in ui.queue.queue] == ["e1"]
    finally:
        root.destroy()


def test_skipped_apply_all_forgets_the_confirm():
    root = _root()
    try:
        _model, ui = _ui(root)
        _confirm(ui, "e1", "e1")
        applied, skips = ui.apply_all()
        assert applied == 0 and len(skips) == 1
        assert ui.queue.queue == []
        assert ui._unapplied_depths == []
    finally:
        root.destroy()
