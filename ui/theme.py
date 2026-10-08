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
    "bar_bg": "#32343e",        # top strip, one step above the rail
    "file_chip": "#3e4250",     # File control on the top strip
    "file_chip_hover": "#484c58",
    # text
    "fg": "#e8e9ed",            # primary text / light geometry strokes
    "fg_muted": "#9a9ca8",      # secondary text
    "canvas_empty": "#6e7280",  # empty-canvas prompt (quieter than fg_muted)
    "empty_btn": "#3a3d46",     # empty-canvas open button (filled grey)
    "empty_btn_hover": "#484c58",
    "empty_btn_edge": "#4e5260",
    "empty_btn_edge_hover": "#5c6070",
    "empty_btn_fg": "#e8e9ed",
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
    # chord card + confirm — muted greys, quieter than the overlay reds
    "dock_bg": "#2c2e36",
    "dock_btn": "#3a3d46",
    "dock_btn_hover": "#484c58",
    "dock_text": "#d4d6de",
    "dock_muted": "#9a9ca6",
    "dock_edge": "#454852",
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
    style.configure("TCheckbutton", background=c["bg"], foreground=c["fg"],
                    indicatorcolor=c["bg_elevated"], focuscolor=c["bg"])
    style.map("TCheckbutton",
              background=[("active", c["bg"]), ("disabled", c["bg"])],
              foreground=[("disabled", c["fg_muted"])],
              indicatorcolor=[("selected", c["accent"]),
                              ("pressed", c["menu_active_bg"])])
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
    # TButton colors. Vertical padding matches Accent.TButton so
    # Designate Folds and Trim to Closest are the same height as Apply All.
    style.configure("FoldMode.TButton", padding=(PAD_X, PAD_Y))
    style.configure("TrimMode.TButton", padding=(PAD_X, PAD_Y))
    style.configure("Accent.TButton", background=c["accent"],
                    foreground=c["accent_fg"], relief="flat", borderwidth=0,
                    focuscolor=c["accent"], padding=(PAD_X, PAD_Y))
    style.map("Accent.TButton",
              background=[("active", c["accent_active"]),
                         ("disabled", c["bg_elevated"])],
              foreground=[("disabled", c["fg_muted"])])
    # Selected quick-size: accent fill at the same padding as TButton so
    # the grid row does not grow when a size is active.
    style.configure("Selected.TButton", background=c["accent"],
                    foreground=c["accent_fg"], relief="flat", borderwidth=0,
                    focuscolor=c["accent"], padding=(PAD_X, PAD_Y // 2))
    style.map("Selected.TButton",
              background=[("active", c["accent_active"]),
                         ("disabled", c["bg_elevated"])],
              foreground=[("disabled", c["fg_muted"])])
    # Revert sits with Undo/Redo but stays text-weight: no filled chip.
    style.configure("Quiet.TButton", background=c["bg"],
                    foreground=c["fg_muted"], relief="flat", borderwidth=0,
                    focuscolor=c["bg"], padding=(4, 2))
    style.map("Quiet.TButton",
              background=[("active", c["bg"]),
                         ("disabled", c["bg"])],
              foreground=[("active", c["fg"]),
                         ("disabled", c["separator"])])
    # Top strip is a shelf. The ✕ stays quiet on that shelf.
    style.configure("TopBar.TFrame", background=c["bar_bg"],
                    borderwidth=0, relief="flat")
    style.configure("BarQuiet.TButton", background=c["bar_bg"],
                    foreground=c["fg_muted"], relief="flat", borderwidth=0,
                    focuscolor=c["bar_bg"], padding=(8, 2))
    style.map("BarQuiet.TButton",
              background=[("active", c["bar_bg"]),
                         ("disabled", c["bar_bg"])],
              foreground=[("active", c["fg"]),
                         ("disabled", c["separator"])])

    # separators + the sidebar scrollbar (dark trough, no light chrome)
    style.configure("TSeparator", background=c["separator"])
    style.configure("Vertical.TScrollbar", background=c["bg_elevated"],
                    troughcolor=c["bg_sunken"], bordercolor=c["bg"],
                    arrowcolor=c["fg_muted"], lightcolor=c["bg_elevated"],
                    darkcolor=c["bg_elevated"])
    style.map("Vertical.TScrollbar",
              background=[("active", c["menu_active_bg"])])

    # root + menu colors (tk-level widgets; tk allows these on Windows)
    root.configure(background=c["bg"])
    return style