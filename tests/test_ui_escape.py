"""Escape cancels a corner pick after focus leaves the canvas.

One window: a later ``Tk()`` in the same process stops delivering events,
and a long run of windows has been tripping unrelated Tk errors.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ui.fold_panel import FoldMode
from ui.trim_panel import TrimMode
from ui.workflow import WorkflowState

_SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "syn-L-bracket.dxf"


def _root():
    import tkinter as tk

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"no display for tkinter: {exc}")
    root.withdraw()
    return root


def _park_edge1(app):
    fsm = app.workflow.fsm
    fsm.state = WorkflowState.PICK_EDGE2
    fsm.edge1_eid = "edge-1"
    return fsm


def test_escape_cancels_corner_and_modes_take_priority():
    from app import App

    root = _root()
    try:
        app = App(root)
        app.open_path(_SAMPLE)
        assert "_on_escape" in root.bind("<Escape>")

        fsm = _park_edge1(app)
        before_pick = app.viewer.transform
        assert app.workflow._on_esc(None) == "break"
        assert fsm.state == WorkflowState.IDLE
        assert fsm.edge1_eid is None
        assert app.viewer.transform == before_pick

        fsm = _park_edge1(app)
        assert app._on_escape(None) == "break"
        assert fsm.state == WorkflowState.IDLE
        assert fsm.edge1_eid is None

        fsm = _park_edge1(app)
        app.fold_panel.toggle_mode()
        assert app.fold_panel.fsm.mode == FoldMode.ON
        assert app.fold_panel._on_esc(None) == "break"
        assert app.fold_panel.fsm.mode == FoldMode.OFF
        fsm = _park_edge1(app)
        app.fold_panel.toggle_mode()
        assert app._on_escape(None) == "break"
        assert app.fold_panel.fsm.mode == FoldMode.OFF
        assert fsm.state == WorkflowState.PICK_EDGE2
        assert fsm.edge1_eid == "edge-1"

        fsm = _park_edge1(app)
        app.trim_panel.toggle_mode()
        assert app.trim_panel.fsm.mode == TrimMode.ON
        assert app.trim_panel._on_esc(None) == "break"
        assert app.trim_panel.fsm.mode == TrimMode.OFF
        fsm = _park_edge1(app)
        app.trim_panel.toggle_mode()
        assert app._on_escape(None) == "break"
        assert app.trim_panel.fsm.mode == TrimMode.OFF
        assert fsm.state == WorkflowState.PICK_EDGE2
        assert fsm.edge1_eid == "edge-1"

        from geometry.entities import Arc, CornerResult, Dogbone, Pt, Side

        before_zoom = app.viewer.transform
        app.workflow.fsm.state = WorkflowState.SIDE_PICKED
        app.workflow.fsm.preview = CornerResult(
            ok=True,
            dogbone=Dogbone(
                db_id="t",
                apex=Pt(10.0, 10.0),
                center=Pt(11.0, 11.0),
                r=1.5,
                side=Side(1),
                edge1_eid="a",
                edge2_eid="b",
                arc=Arc(eid="arc", center=Pt(11.0, 11.0), r=1.5,
                        start_deg=0.0, end_deg=90.0),
            ),
            deletions=[],
            trims=[],
            rebuilt=[],
            refusals=[],
            flags=[],
        )
        app.workflow._auto_zoom()
        assert app.viewer.transform != before_zoom
        assert app._on_escape(None) == "break"
        assert app.workflow.fsm.state == WorkflowState.IDLE
        assert app.viewer.transform == before_zoom
    finally:
        root.destroy()
