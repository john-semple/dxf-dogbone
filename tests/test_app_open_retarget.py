"""Opening a second DXF retargets the existing workflow; clear empties the session."""
from __future__ import annotations

from pathlib import Path

import pytest

import ui.messages as msg
from ui.theme import COLORS as THEME
from dxf_io import load
from geometry.entities import Side
from ui.workflow import PendingCorner, WorkflowState

_SAMPLES = Path(__file__).resolve().parents[1] / "samples"
_FIRST = _SAMPLES / "syn-L-bracket.dxf"
_SECOND = _SAMPLES / "syn-multicorner.dxf"


def _root():
    import tkinter as tk

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"no display for tkinter: {exc}")
    root.withdraw()
    return root


def _app(root):
    from app import App

    return App(root)


def _eids(state) -> list[str]:
    return [e.eid for e in state.primitives]


def _assert_open(app, path: Path) -> None:
    loaded = load(path)
    assert app.workflow is not None
    assert app.workflow.model is app.model
    assert app.trim_panel.model is app.model
    assert app.fold_panel.model is app.model
    assert app.workflow.queue.model is app.model
    assert app.trim_panel.stack is app.workflow.stack
    assert app.fold_panel.stack is app.workflow.stack
    assert app.workflow.queue.stack is app.workflow.stack
    assert _eids(app.workflow.model.state) == _eids(loaded.model_state)
    assert app.workflow.queue.queue == []
    assert app.workflow._unapplied_depths == []
    assert app.workflow._batches == []
    assert app.source_path == path


def test_empty_canvas_hint_tracks_whether_a_file_is_open():
    root = _root()
    try:
        app = _app(root)
        assert app.empty_label.cget("text") == msg.EMPTY_CANVAS
        assert app.empty_open.cget("text") == msg.EMPTY_OPEN
        assert app.empty_open.cget("command") == app.open_dialog
        assert app.empty_hint.place_info().get("relx") == "0.5"
        app.open_path(_FIRST)
        assert app.empty_hint.place_info() == {}
        app.clear_session()
        assert app.empty_hint.place_info().get("relx") == "0.5"
    finally:
        root.destroy()


def test_file_button_replaces_the_native_menubar():
    root = _root()
    try:
        app = _app(root)
        assert app.root.cget("menu") == ""
        assert app.file_btn.cget("text") == "File"
        assert str(app.file_chip.pack_info()["side"]) == "left"
        assert app.file_chip.master is app.close_btn.master
        assert app.file_chip.cget("bg") == THEME["file_chip"]
        assert str(app.close_btn.master.cget("style")) == "TopBar.TFrame"
        assert str(app.close_btn.cget("style")) == "BarQuiet.TButton"
        labels = [
            app.file_menu.entrycget(i, "label")
            for i in range(app.file_menu.index("end") + 1)
            if app.file_menu.type(i) == "command"
        ]
        assert labels == ["Open DXF...", msg.EXPORT_MENU, "Exit"]
        assert app.root.bind("<Alt-f>")
    finally:
        root.destroy()


def test_close_button_sits_on_a_top_strip():
    root = _root()
    try:
        app = _app(root)
        assert app.close_btn.cget("text") == "✕"
        assert str(app.close_btn.pack_info()["side"]) == "right"
        slaves = list(root.pack_slaves())
        bar = app.close_btn.master
        assert str(bar.pack_info()["side"]) == "top"
        assert slaves.index(bar) < slaves.index(app.sidebar)
    finally:
        root.destroy()


def test_second_open_retargets_the_same_workflow(monkeypatch):
    def _prompt(*_a, **_k):
        raise AssertionError("open_path prompted")

    monkeypatch.setattr("app.messagebox.askyesno", _prompt)
    root = _root()
    try:
        app = _app(root)
        app.open_path(_FIRST)
        workflow = app.workflow
        workflow.fsm.pending = PendingCorner(
            edge1_eid="e1", edge2_eid="e2", side=Side(+1), side_flip=1,
            r=1.0, db_id="db-e1+e2")
        workflow.apply(None)
        assert workflow.queue.queue
        assert workflow._unapplied_depths
        app.open_path(_SECOND)
        assert app.workflow is workflow
        _assert_open(app, _SECOND)
    finally:
        root.destroy()


def test_clear_session_then_open(monkeypatch):
    def _prompt(*_a, **_k):
        raise AssertionError("clear prompted")

    monkeypatch.setattr("app.messagebox.askyesno", _prompt)
    root = _root()
    try:
        app = _app(root)
        app.open_path(_FIRST)
        app.clear_session()
        assert app.source_path is None
        assert app.header == {}
        assert app.viewer._drawables == []
        assert app.root.title() == "DXF Dogbone"
        assert app.status_var.get() == "Add a DXF to get started."
        assert app.workflow.fsm.state == WorkflowState.IDLE
        app.open_path(_SECOND)
        _assert_open(app, _SECOND)
    finally:
        root.destroy()


def test_close_dxf_without_file_does_not_prompt(monkeypatch):
    called: list[tuple] = []

    def _prompt(*args, **kwargs):
        called.append(args)
        return False

    monkeypatch.setattr("app.messagebox.askyesno", _prompt)
    root = _root()
    try:
        app = _app(root)
        app.close_dxf()
        assert called == []
        assert app.source_path is None
    finally:
        root.destroy()


def test_close_dxf_no_leaves_the_session(monkeypatch):
    seen: list[tuple[str, str]] = []

    def _prompt(title, body, **_k):
        seen.append((title, body))
        return False

    monkeypatch.setattr("app.messagebox.askyesno", _prompt)
    root = _root()
    try:
        app = _app(root)
        app.open_path(_FIRST)
        app.close_dxf()
        assert seen == [(msg.CLOSE_DXF_TITLE, msg.CLOSE_DXF_BODY)]
        assert app.source_path == _FIRST
        assert app.viewer._drawables
    finally:
        root.destroy()


def test_open_dialog_no_skips_the_chooser(monkeypatch):
    monkeypatch.setattr("app.messagebox.askyesno", lambda *_a, **_k: False)

    def _chooser(**_k):
        raise AssertionError("file chooser opened")

    monkeypatch.setattr("app.filedialog.askopenfilename", _chooser)
    root = _root()
    try:
        app = _app(root)
        app.open_path(_FIRST)
        app.open_dialog()
        assert app.source_path == _FIRST
    finally:
        root.destroy()


def test_open_dialog_yes_then_cancel_leaves_the_session_empty(monkeypatch):
    monkeypatch.setattr("app.messagebox.askyesno", lambda *_a, **_k: True)
    monkeypatch.setattr("app.filedialog.askopenfilename", lambda **_k: "")
    root = _root()
    try:
        app = _app(root)
        app.open_path(_FIRST)
        app.open_dialog()
        assert app.source_path is None
        assert app.viewer._drawables == []
        assert app.status_var.get() == "Add a DXF to get started."
    finally:
        root.destroy()


def test_open_dialog_without_file_skips_the_prompt(monkeypatch):
    called: list[tuple] = []

    def _prompt(*args, **_k):
        called.append(args)
        return True

    monkeypatch.setattr("app.messagebox.askyesno", _prompt)
    monkeypatch.setattr("app.filedialog.askopenfilename", lambda **_k: "")
    root = _root()
    try:
        app = _app(root)
        app.open_dialog()
        assert called == []
    finally:
        root.destroy()
