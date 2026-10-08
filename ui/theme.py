"""UI theme — single source of palette + fonts (UI-UPGRADE brief item 1).

``COLORS`` is the only place hex color literals live for the shell:
``app.py``, ``ui/canvas_view.py`` and ``ui/workflow.py`` import from
here (brief acceptance: grep-clean outside this module).

``apply(root)`` installs the ttk style (``clam`` base, dark panels,
accent blue, Segoe UI with TkDefaultFont fallback, flat TButton +
one Accent.TButton) and returns the ``ttk.Style``. Called from
``App.__init__`` and from the verify_gui harness roots so the harness
exercises the same look.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

COLORS: dict[str, str] = {
    # surfaces
    "bg": "#1e1f26",            # root / panel background
    "bg_sunken": "#17181e",     # status bar / readouts
    "bg_elevated": "#262733",   # cards, pill frames
    # text
    "fg": "#e8e9ed",            # primary text / light geometry strokes
    "fg_muted": "#9a9ca8",      # secondary text
    # canvas + geometry
    "canvas_bg": "#17181e",     # viewer canvas background (dark)
    "geometry_fg": "#c8cdd9",   # part strokes on dark bg
    "text_ent_fg": "#aeb4c2",   # MTEXT on canvas
    "point_fg": "#e06c75",      # POINT "+" markers
    # workflow overlays (relative distinction preserved:
    # flash/ghost cyan-family, delete red, flag orange)
    "highlight": "#22d3ee",     # promoted-edge flash (cyan-family)
    "edge2_pick": "#4ade80",    # edge-2 pick-phase (green)
    "ghost": "#22d3ee",         # dashed ghost circles (cyan-family)
    "delete": "#ff4d4d",        # deletion preview (dark-bg-safe red)
    "flag": "#ff9900",          # flagged entities (orange)
    # fold designation rendering (M5b: ACI-7-derived light tone on dark canvas;
    # the exported ACI constant FOLD_COLOR_CONST=7 lives in dxf_io/export.py)
    "fold_designated": "#facc15",  # warm gold — distinct from all workflow overlays
    # accents
    "accent": "#3b82f6",        # Confirm / accent buttons
    "accent_active": "#2563eb",
    "accent_fg": "#ffffff",
    "pill_bg": "#166534",       # floating confirm pill (green card)
    "pill_btn_bg": "#a5d6a7",
    "pill_btn_active": "#81c784",
    "pill_btn_fg": "#1b5e20",
    # chrome
    "separator": "#3a3b45",
    "menu_bg": "#1e1f26",
    "menu_fg": "#e8e9ed",
    "menu_active_bg": "#3b3f4a",
    "menu_active_fg": "#ffffff",
    "select_bg": "#3b82f6",
}

PAD_X = 12          # consistent grid padding (brief: 8/12 px)
PAD_Y = 8
FONT_FAMILY = "Segoe UI"
FALLBACK_FONT = "TkDefaultFont"


def font(size: int = 9, weight: str = "normal") -> tuple[str, int, str] | tuple[str, int]:
    """Theme font tuple; Segoe UI where available, TkDefaultFont name
    otherwise (tk resolves an unknown family to the default font)."""
    return (FONT_FAMILY, size, weight)


def apply(root: tk.Misc) -> ttk.Style:
    """Install the dark theme on ``root``; returns the ttk.Style.

    Presentation only — no widget construction beyond the style map.
    """
    style = ttk.Style(root)
    style.theme_use("clam")

    c = COLORS
    style.configure(".", background=c["bg"], foreground=c["fg"],
                    bordercolor=c["separator"],
                    lightcolor=c["separator"], darkcolor=c["separator"],
                    troughcolor=c["bg_sunken"],
                    fieldbackground=c["bg_sunken"])
    try:
        style.configure(".", font=font(9))
    except tk.TclError:
        style.configure(".", font=FALLBACK_FONT)

    # panels / labels
    style.configure("TFrame", background=c["bg"])
    style.configure("Status.TFrame", background=c["bg_sunken"])
    style.configure("TLabel", background=c["bg"], foreground=c["fg"])
    style.configure("Status.TLabel", background=c["bg_sunken"],
                    foreground=c["fg_muted"], padding=(PAD_X, 4))
    style.configure("StatusBold.TLabel", background=c["bg_sunken"],
                    foreground=c["fg"])

    # buttons: flat, themed
    style.configure("TButton", background=c["bg_elevated"],
                    foreground=c["fg"], relief="flat", borderwidth=0,
                    focuscolor=c["bg"], padding=(PAD_X, PAD_Y // 2))
    style.map("TButton",
              background=[("active", c["menu_active_bg"]),
                         ("disabled", c["bg_elevated"])],
              foreground=[("disabled", c["fg_muted"])])
    style.configure("Accent.TButton", background=c["accent"],
                    foreground=c["accent_fg"], relief="flat", borderwidth=0,
                    focuscolor=c["accent"], padding=(PAD_X, PAD_Y))
    style.map("Accent.TButton",
              background=[("active", c["accent_active"]),
                         ("disabled", c["bg_elevated"])],
              foreground=[("disabled", c["fg_muted"])])

    # separators
    style.configure("TSeparator", background=c["separator"])

    # root + menu colors (tk-level widgets; tk allows these on Windows)
    root.configure(background=c["bg"])
    return style