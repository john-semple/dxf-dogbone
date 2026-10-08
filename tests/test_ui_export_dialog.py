"""Export dialog: filename, watermark preview, Back leaves the model alone."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path

import pytest

from dxf_io.export import WATERMARK_TEXTS
from geometry.entities import Pt, Seg, TextEnt
from model.model import Model
from model.state import ModelState
from ui.export_dialog import ExportDialog, default_export_filename

_ROOT: tk.Tk | None = None


def _root() -> tk.Tk:
    global _ROOT
    if _ROOT is None or not _ROOT.winfo_exists():
        try:
            _ROOT = tk.Tk()
        except tk.TclError as exc:
            pytest.skip(f"no display for tkinter: {exc}")
        _ROOT.withdraw()
    return _ROOT


def _model() -> Model:
    state = ModelState(
        primitives=[
            Seg(eid="L1", a=Pt(0, 0), b=Pt(10, 0)),
            TextEnt(eid="W1", p=Pt(1, 1), text=WATERMARK_TEXTS[0]),
            TextEnt(eid="W2", p=Pt(1, 2), text=WATERMARK_TEXTS[1]),
            TextEnt(eid="N1", p=Pt(1, 3), text="shop note"),
        ],
        next_seq=1,
    )
    return Model(state)


def test_ui_export_dialog_default_filename():
    assert default_export_filename(Path("base-rectangular-before-AI.DXF")) == (
        "base-rectangular-before-AI_dogbone.dxf"
    )


def test_ui_export_dialog_back_preserves_state_and_preview_hides_watermark(tmp_path):
    root = _root()
    model = _model()
    before = model.snapshot()
    source = tmp_path / "part.dxf"
    dialog = ExportDialog(
        root,
        model,
        {"$ACADVER": "AC1015", "$INSUNITS": 4},
        source,
        before,
        tmp_path,
    )
    try:
        assert dialog._filename.get() == "part_dogbone.dxf"
        assert dialog._remove.get() is True
        preview = [
            e.text for e in dialog._prepared.state.primitives if isinstance(e, TextEnt)
        ]
        assert preview == ["shop note"]
        dialog._remove.set(False)
        shown = [
            e.text for e in dialog._prepared.state.primitives if isinstance(e, TextEnt)
        ]
        assert WATERMARK_TEXTS[0] in shown and WATERMARK_TEXTS[1] in shown
        dialog.back()
        assert model.snapshot() == before
        assert dialog.saved_path is None
        assert not (tmp_path / "part_dogbone.dxf").exists()
    finally:
        if dialog.winfo_exists():
            dialog.destroy()


def test_ui_export_dialog_ok_writes_file_and_log(tmp_path):
    root = _root()
    model = _model()
    before = model.snapshot()
    source = tmp_path / "part.dxf"
    dialog = ExportDialog(
        root,
        model,
        {"$ACADVER": "AC1015", "$INSUNITS": 4},
        source,
        before,
        tmp_path,
    )
    try:
        dialog.ok()
        out = tmp_path / "part_dogbone.dxf"
        assert out.is_file()
        assert Path(str(out) + ".export_log.md").is_file()
        assert dialog.saved_path == out
        assert model.snapshot() == before
    finally:
        if dialog.winfo_exists():
            dialog.destroy()
