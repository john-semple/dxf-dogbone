"""Ctrl+Z undoes and Ctrl+Y redoes, same path as the history buttons."""
from __future__ import annotations

from pathlib import Path

import pytest

_SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "syn-L-bracket.dxf"


def _root():
    import tkinter as tk

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"no display for tkinter: {exc}")
    root.withdraw()
    return root


def test_ctrl_z_undoes_and_ctrl_y_redoes():
    from app import App

    root = _root()
    try:
        app = App(root)
        assert "_on_undo_key" in root.bind("<Control-z>")
        assert "_on_undo_key" in root.bind("<Control-Z>")
        assert "_on_redo_key" in root.bind("<Control-y>")
        assert "_on_redo_key" in root.bind("<Control-Y>")

        app.open_path(_SAMPLE)
        app.workflow.stack.push()
        app.model.state.flag_decisions["probe"] = "keep"
        assert app._on_undo_key() == "break"
        assert "probe" not in app.model.state.flag_decisions
        assert app.workflow.stack.can_redo()

        assert app._on_redo_key() == "break"
        assert app.model.state.flag_decisions["probe"] == "keep"
        assert not app.workflow.stack.can_redo()
    finally:
        root.destroy()


def test_undo_keys_with_no_file_do_not_crash():
    from app import App

    root = _root()
    try:
        app = App(root)
        assert app.workflow is None
        assert app._on_undo_key() == "break"
        assert app._on_redo_key() == "break"
        assert app.workflow is None
    finally:
        root.destroy()
