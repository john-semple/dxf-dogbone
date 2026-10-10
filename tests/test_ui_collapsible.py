"""Left-rail collapsible sections — presentation only."""
from __future__ import annotations

import tkinter as tk

import pytest

from ui.apply_panel import ToolPanel
from ui.collapsible import CollapsibleSection, Sidebar
from ui.fold_panel import FoldPanel
from ui.trim_panel import TrimPanel
import ui.messages as msg


def _root() -> tk.Tk:
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"no display for tkinter: {exc}")
    root.withdraw()
    return root


def test_section_toggle_hides_and_restores_body():
    root = _root()
    try:
        section = CollapsibleSection(root, "Dogbone")
        section.pack()
        tk.Label(section.body, text="inside").pack()
        assert section.expanded is True
        assert section.body.winfo_manager() == "pack"
        assert section._chevron.cget("text") == "▾"
        section.toggle()
        assert section.expanded is False
        assert section.body.winfo_manager() == ""
        assert section._chevron.cget("text") == "▸"
        section.toggle()
        assert section.body.winfo_manager() == "pack"
    finally:
        root.destroy()


def test_section_summary_sits_on_the_header():
    root = _root()
    try:
        section = CollapsibleSection(root, "Folds")
        section.set_summary("3/12")
        assert section._summary.cget("text") == "3/12"
    finally:
        root.destroy()


def test_panels_are_ordered_collapsible_sections():
    """Step 1, Step 2, and Step 3 collapse. Undo/Redo stay in a separate
    commands strip, so minimizing a section does not hide Redo."""
    root = _root()
    try:
        tool = ToolPanel(root)
        fold = FoldPanel(root, None, None)
        trim = TrimPanel(root, None, None)
        tool.commands.pack(fill=tk.X)
        assert tool.dogbone.title == msg.SECTION_DOGBONE
        assert fold.section.title == msg.SECTION_FOLDS
        assert str(fold.mode_btn.cget("style")) == "FoldMode.TButton"
        assert trim.section.title == msg.SECTION_TRIM
        assert str(trim.mode_btn.cget("style")) == "TrimMode.TButton"
        assert trim.hint.cget("text") == msg.TRIM_HINT
        assert list(trim.section.body.pack_slaves())[:2] == [
            trim.mode_btn, trim.hint,
        ]
        assert str(tool.revert_btn.cget("style")) == "Quiet.TButton"
        assert "3.175" in tool.dogbone._summary.cget("text")
        tool.dogbone.toggle()
        assert tool.dogbone.body.winfo_manager() == ""
        assert tool.commands.winfo_manager() == "pack"
        assert str(tool.redo_btn.cget("state")) == "disabled"
        fold.section.toggle()
        trim.section.toggle()
        assert fold.section.expanded is False
        assert trim.section.expanded is False
    finally:
        root.destroy()


def test_app_rail_pins_commands_above_sections():
    from app import App

    root = _root()
    try:
        app = App(root)
        slaves = list(app.sidebar.body.pack_slaves())
        assert slaves == [
            app.fold_panel,
            app.panel.dogbone,
            app.trim_panel,
        ]
        assert app.panel.commands.master is app.sidebar.pin
        assert app.panel.commands in app.sidebar.pin.pack_slaves()
        assert app.panel.dogbone.master is app.sidebar.body
        assert str(app.panel.revert_btn.cget("style")) == "Quiet.TButton"
        btn = _bottom_right_button(app)
        assert btn.cget("text") == msg.EXPORT_MENU
        assert btn.cget("command") == app.export_dialog
        assert btn is app.export_btn
        shape = btn.find_withtag("shape")
        assert btn.type(shape[0]) == "polygon"
        assert len(btn.coords(shape[0])) > 8
    finally:
        root.destroy()


def _show(root: tk.Tk, width: int, height: int) -> None:
    """Map off-screen so the rail gets a real viewport. A withdrawn
    window reports a 1px canvas, which makes every section look tall."""
    root.overrideredirect(True)
    root.geometry(f"{width}x{height}+-2400+-2400")
    root.deiconify()
    root.update()


def test_sidebar_wheel_stays_put_when_sections_fit():
    """Collapsed (or otherwise short) sections stay at the top."""
    root = _root()
    try:
        side = Sidebar(root)
        side.pack(fill=tk.BOTH, expand=True)
        tk.Label(side.body, text="one").pack()
        _show(root, 320, 500)
        assert side._overflows() is False
        side._wheel(type("E", (), {"delta": -120})())
        assert float(side.canvas.yview()[0]) == 0.0
    finally:
        root.destroy()


def test_column_stays_put_until_sections_pass_the_viewport():
    """The three steps move as one column. The wheel leaves them alone
    when they fit, and it cannot open a gap above Step 1."""
    from app import App

    root = _root()
    try:
        app = App(root)
        sections = (
            app.panel.dogbone,
            app.fold_panel.section,
            app.trim_panel.section,
        )
        for section in sections:
            if section.expanded:
                section.toggle()
        _show(root, 360, 700)
        assert app.sidebar._overflows() is False
        top = float(app.sidebar.canvas.yview()[0])
        app.sidebar._wheel(type("E", (), {"delta": -120})())
        app.sidebar._wheel(type("E", (), {"delta": 120})())
        assert float(app.sidebar.canvas.yview()[0]) == top == 0.0
        for section in sections:
            if not section.expanded:
                section.toggle()
        root.geometry("360x220+-2400+-2400")
        root.update()
        assert app.sidebar._overflows() is True
        app.sidebar.canvas.yview_moveto(0)
        app.sidebar._wheel(type("E", (), {"delta": 120})())
        assert float(app.sidebar.canvas.yview()[0]) == 0.0
        app.sidebar._wheel(type("E", (), {"delta": -120})())
        assert float(app.sidebar.canvas.yview()[0]) > 0.0
    finally:
        root.destroy()


def test_sidebar_wheel_scrolls_when_sections_overflow():
    root = _root()
    try:
        side = Sidebar(root)
        side.pack(fill=tk.BOTH, expand=True)
        for i in range(40):
            tk.Label(side.body, text=f"row {i}").pack(anchor="w")
        _show(root, 320, 180)
        assert side._overflows() is True
        side._wheel(type("E", (), {"delta": -120})())
        assert float(side.canvas.yview()[0]) > 0.0
    finally:
        root.destroy()


def _bottom_right_button(app):
    """The button packed on the right of the bottom status bar."""
    for child in app.root.winfo_children():
        if child.winfo_manager() != "pack":
            continue
        if child.pack_info().get("side") != "bottom":
            continue
        for grand in child.winfo_children():
            if grand.pack_info().get("side") == "right":
                return grand
    raise AssertionError("no bottom-right button")
