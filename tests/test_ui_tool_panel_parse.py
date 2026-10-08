"""ToolPanel diameter parsing — the "3/16"\" and 0.25\" inch-override
(user request 2026-10-07) plus mm/inch toggle interplay. Headless-ish:
a withdrawn session root, no mainloop."""
from __future__ import annotations

import tkinter as tk

import pytest

from ui.apply_panel import ToolPanel

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


@pytest.fixture()
def panel():
    root = _root()
    yield ToolPanel(root)
    # keep the shared root for the next test; destroyed at session end
    # by the interpreter exiting (pytest never mainloops)


class TestDiameterParse:
    def test_panel_plain_mm(self, panel):
        panel._dia_text.set("3.175")
        assert panel.diameter_mm() == pytest.approx(3.175)

    def test_panel_fraction_mm(self, panel):
        panel._dia_text.set("7/2")
        assert panel.diameter_mm() == pytest.approx(3.5)

    def test_panel_quote_forces_inches_in_mm_mode(self, panel):
        """The user request: trailing " converts to mm even in mm
        mode."""
        panel._dia_text.set('0.25"')
        assert panel.diameter_mm() == pytest.approx(6.35)

    def test_panel_quote_fraction_forces_inches(self, panel):
        panel._dia_text.set('1/8"')
        assert panel.diameter_mm() == pytest.approx(3.175)

    def test_panel_quote_in_inch_mode_same_value(self, panel):
        panel._toggle_unit()  # -> inch
        panel._dia_text.set('0.25"')
        assert panel.diameter_mm() == pytest.approx(6.35)

    def test_panel_inch_mode_no_quote(self, panel):
        panel._toggle_unit()  # -> inch
        panel._dia_text.set("0.25")
        assert panel.diameter_mm() == pytest.approx(6.35)

    def test_panel_quick_button_sets_unit_value(self, panel):
        """Quick buttons adopt the CURRENT unit: mm mode -> mm text."""
        panel.set_diameter_mm(6.35)
        assert panel._dia_text.get() == "6.35"
        assert panel.diameter_mm() == pytest.approx(6.35)

    def test_panel_quick_button_inch_mode(self, panel):
        panel._toggle_unit()  # -> inch
        panel.set_diameter_mm(6.35)
        assert panel._dia_text.get() == "0.25"
        assert panel.diameter_mm() == pytest.approx(6.35)

    def test_panel_invalid_entry_returns_none(self, panel):
        for bad in ("", "abc", "-3", 'abc"', '1/0"', '"'):
            panel._dia_text.set(bad)
            assert panel.diameter_mm() is None, bad

    def test_panel_quote_with_spaces(self, panel):
        panel._dia_text.set(' 1/4 " ')
        assert panel.diameter_mm() == pytest.approx(6.35)

    def test_panel_readout_shows_mm_after_quote(self, panel):
        """Typing 0.25" keystroke-by-keystroke into a CLEARED field:
        the final KeyRelease refreshes the readout to the converted
        mm value."""
        panel._dia_text.set("")  # clear the 3.175 default first
        for ch in '0.25"':
            panel._dia_text.set(panel._dia_text.get() + ch)
            panel._entry_edited(None)
        assert "6.35" in panel.readout["text"]
        assert "R 3.175" in panel.readout["text"]