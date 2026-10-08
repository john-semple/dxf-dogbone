"""ui.theme — UI-UPGRADE brief item 4: apply() runs on a throwaway
root and COLORS carries the required keys. Presentation-only; asserts
nothing about engine/rules/model."""
from __future__ import annotations

import tkinter as tk

import pytest

from ui.theme import COLORS, apply

REQUIRED_KEYS = {
    "bg", "fg", "fg_muted", "canvas_bg", "geometry_fg", "text_ent_fg",
    "point_fg", "highlight", "edge2_pick", "ghost", "delete", "flag",
    "accent", "accent_fg",
}


def test_theme_colors_has_required_keys():
    missing = REQUIRED_KEYS - set(COLORS)
    assert not missing, f"COLORS missing keys: {sorted(missing)}"


def test_theme_apply_runs_on_throwaway_root():
    root = tk.Tk()
    root.withdraw()  # never visible; destroyed in finally
    try:
        from tkinter import ttk
        style = apply(root)
        assert isinstance(style, ttk.Style)
        assert style.theme_use() == "clam"
        assert style.lookup("FoldMode.TButton", "padding") == style.lookup(
            "Accent.TButton", "padding")
        assert style.lookup("TrimMode.TButton", "padding") == style.lookup(
            "FoldMode.TButton", "padding")
        assert style.lookup("FoldMode.TButton", "background") == style.lookup(
            "TButton", "background")
        assert style.lookup("TrimMode.TButton", "background") == style.lookup(
            "TButton", "background")
    finally:
        root.destroy()


def test_theme_apply_reachable_headless():
    """The harness pattern: a withdrawn root + apply must not raise
    even when called twice (idempotent restyle)."""
    try:
        root = tk.Tk()
    except tk.TclError as exc:  # no display (CI): skip, not fail
        pytest.skip(f"no display for tkinter: {exc}")
    try:
        apply(root)
        apply(root)
    finally:
        root.destroy()