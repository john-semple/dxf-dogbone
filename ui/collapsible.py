"""Collapsible left-rail sections and the scrollable sidebar that holds them.

Presentation only. Panels keep their own widgets and callbacks; this module
only groups those widgets under a header that can be minimized.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ui.theme import COLORS as THEME, font as theme_font

SIDEBAR_WIDTH = 304


class CollapsibleSection(ttk.Frame):
    """A titled block whose body hides when the header is clicked.

    Pack widgets into ``body``. ``set_summary`` puts a short muted note on
    the right of the header so a minimized section still shows its state.
    """

    def __init__(self, master, title: str, *, expanded: bool = True):
        super().__init__(master, style="TFrame")
        self.title = title
        self.expanded = bool(expanded)

        self.header = tk.Frame(self, bg=THEME["bg_elevated"], cursor="hand2")
        self.header.pack(fill=tk.X)

        self._accent = tk.Frame(self.header, bg=THEME["accent"], width=3)
        self._accent.pack(side=tk.LEFT, fill=tk.Y)
        self._accent.pack_propagate(False)

        self._chevron = tk.Label(
            self.header, text="", bg=THEME["bg_elevated"], fg=THEME["accent"],
            font=theme_font(10), padx=8, pady=6, cursor="hand2")
        self._chevron.pack(side=tk.LEFT)

        self._title_lbl = tk.Label(
            self.header, text=title, bg=THEME["bg_elevated"], fg=THEME["fg"],
            font=theme_font(10, "bold"), cursor="hand2")
        self._title_lbl.pack(side=tk.LEFT)

        self._summary = tk.Label(
            self.header, text="", bg=THEME["bg_elevated"], fg=THEME["fg_muted"],
            font=theme_font(9), padx=10, cursor="hand2")
        self._summary.pack(side=tk.RIGHT)

        self.body = ttk.Frame(self, style="TFrame", padding=(12, 6, 10, 8))
        for widget in (self.header, self._accent, self._chevron,
                       self._title_lbl, self._summary):
            widget.bind("<Button-1>", self._on_click)
        self.header.bind("<Enter>", lambda _e: self._paint(THEME["menu_active_bg"]))
        self.header.bind("<Leave>", self._hover_off)
        self._apply_expanded()

    def set_summary(self, text: str) -> None:
        self._summary.configure(text=text)

    def toggle(self) -> None:
        self.expanded = not self.expanded
        self._apply_expanded()

    def _on_click(self, _event=None):
        self.toggle()
        return "break"

    def _apply_expanded(self) -> None:
        self._chevron.configure(text="▾" if self.expanded else "▸")
        if self.expanded:
            if not self.body.winfo_manager():
                self.body.pack(fill=tk.X)
        else:
            self.body.pack_forget()

    def _hover_off(self, _event=None) -> None:
        widget = self.winfo_containing(*self.winfo_pointerxy())
        while widget is not None:
            if widget == self.header:
                return
            widget = getattr(widget, "master", None)
        self._paint(THEME["bg_elevated"])

    def _paint(self, bg: str) -> None:
        for widget in (self.header, self._chevron, self._title_lbl, self._summary):
            widget.configure(bg=bg)


class Sidebar(ttk.Frame):
    """Fixed-width vertical rail. Sections pack into ``body``.

    ``pin`` is a strip above the scroller, so widgets packed there stay
    on screen when the sections scroll. ``body`` holds the section
    column (Dogbone, Folds, Trim). Those sections scroll together, and
    only when the column is taller than the viewport. The wheel does
    nothing when they already fit, and it cannot move the column down
    into blank space. ``on_hover(True/False)`` fires while the pointer
    is over the rail so the app can lend the mouse wheel to this
    scroller instead of the canvas zoom.
    """

    def __init__(self, master, on_hover=None):
        super().__init__(master, style="TFrame")
        self._on_hover = on_hover
        self._hovering = False

        self.pin = ttk.Frame(self, style="TFrame", padding=(8, 8, 8, 6))
        self.pin.pack(side=tk.TOP, fill=tk.X)
        ttk.Separator(self, orient=tk.HORIZONTAL).pack(side=tk.TOP, fill=tk.X)

        self._edge = tk.Frame(self, width=1, bg=THEME["separator"])
        self._edge.pack(side=tk.RIGHT, fill=tk.Y)

        self.canvas = tk.Canvas(
            self, width=SIDEBAR_WIDTH, highlightthickness=0,
            bg=THEME["bg"], yscrollcommand=self._on_yscroll)
        self.scroll = ttk.Scrollbar(
            self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.body = ttk.Frame(self.canvas, style="TFrame", padding=(8, 8, 8, 4))
        self._window = self.canvas.create_window(
            (0, 0), window=self.body, anchor="nw")

        self.body.bind("<Configure>", self._on_body_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)

    def _on_body_configure(self, _event=None) -> None:
        self._sync_scroll()

    def _on_canvas_configure(self, event) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)
        self._sync_scroll()

    def _content_bbox(self) -> tuple[int, int, int, int]:
        bbox = self.canvas.bbox(self._window)
        if bbox is None:
            return (0, 0, 0, 0)
        return bbox

    def _overflows(self) -> bool:
        """True when the section column is taller than the viewport."""
        _x0, y0, _x1, y1 = self._content_bbox()
        return (y1 - y0) > self.canvas.winfo_height() + 1

    def _sync_scroll(self) -> None:
        x0, y0, x1, y1 = self._content_bbox()
        content_h = y1 - y0
        view_h = max(self.canvas.winfo_height(), 1)
        if content_h <= view_h + 1:
            # Region matches the viewport, so the column cannot shift
            # down and leave blank space above it.
            self.canvas.configure(scrollregion=(0, 0, max(x1, 1), view_h))
            self.canvas.yview_moveto(0)
        else:
            self.canvas.configure(scrollregion=(x0, y0, x1, y1))

    def _on_yscroll(self, first: str, last: str) -> None:
        self.scroll.set(first, last)
        if float(last) - float(first) >= 0.999:
            if self.scroll.winfo_ismapped():
                self.scroll.pack_forget()
        elif not self.scroll.winfo_ismapped():
            self.scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _pointer_inside(self) -> bool:
        widget = self.winfo_containing(*self.winfo_pointerxy())
        while widget is not None:
            if widget == self:
                return True
            widget = getattr(widget, "master", None)
        return False

    def _enter(self, _event=None) -> None:
        if self._hovering:
            return
        self._hovering = True
        self.canvas.bind_all("<MouseWheel>", self._wheel)
        if self._on_hover is not None:
            self._on_hover(True)

    def _leave(self, _event=None) -> None:
        if self._pointer_inside():
            return
        if not self._hovering:
            return
        self._hovering = False
        self.canvas.unbind_all("<MouseWheel>")
        if self._on_hover is not None:
            self._on_hover(False)

    def _wheel(self, event):
        if not self._overflows():
            self.canvas.yview_moveto(0)
            return "break"
        self.canvas.yview_scroll(int(-event.delta / 120), "units")
        first, last = self.canvas.yview()
        if float(first) <= 0.0:
            self.canvas.yview_moveto(0)
        elif float(last) >= 1.0:
            span = float(last) - float(first)
            self.canvas.yview_moveto(max(0.0, 1.0 - span))
        return "break"
