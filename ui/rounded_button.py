"""Accent button with rounded corners.

ttk's clam theme only paints square buttons. This canvas draws the
fill itself so the status-bar Export control can have soft corners.
"""
from __future__ import annotations

import math
import tkinter as tk
from tkinter import font as tkfont

from ui.theme import COLORS, PAD_X, PAD_Y, font as theme_font

_RADIUS = 6


def _rounded_points(x1: float, y1: float, x2: float, y2: float,
                    r: float, n: int = 8) -> list[float]:
    """Outline of a rounded rectangle, y increasing downward."""
    r = min(r, (x2 - x1) / 2.0, (y2 - y1) / 2.0)

    def arc(cx: float, cy: float, a0: float, a1: float) -> list[float]:
        pts: list[float] = []
        for i in range(n + 1):
            t = math.radians(a0 + (a1 - a0) * i / n)
            pts.extend((cx + r * math.cos(t), cy + r * math.sin(t)))
        return pts

    return (
        arc(x2 - r, y1 + r, -90, 0)
        + arc(x2 - r, y2 - r, 0, 90)
        + arc(x1 + r, y2 - r, 90, 180)
        + arc(x1 + r, y1 + r, 180, 270)
    )


class RoundedButton(tk.Canvas):
    """Fixed-size rounded button. ``cget('text')`` and ``cget('command')``
    match the ttk button the shell used to pack here.

    Defaults are the accent Export control. Pass fill, outline, and
    padding to draw a quieter variant.
    """

    def __init__(
        self,
        master: tk.Misc,
        text: str,
        command,
        *,
        fill: str | None = None,
        outline: str | None = None,
        active_fill: str | None = None,
        active_outline: str | None = None,
        fg: str | None = None,
        font_size: int = 9,
        pad_x: int | None = None,
        pad_y: int | None = None,
        radius: float = _RADIUS,
        outline_width: float = 1,
        canvas_bg: str | None = None,
    ) -> None:
        face = theme_font(font_size)
        measure = tkfont.Font(root=master, font=face)
        px = PAD_X if pad_x is None else pad_x
        py = PAD_Y if pad_y is None else pad_y
        w = measure.measure(text) + px * 2
        h = measure.metrics("linespace") + py * 2
        super().__init__(
            master, width=w, height=h,
            bg=COLORS["bg_sunken"] if canvas_bg is None else canvas_bg,
            highlightthickness=0, bd=0,
            cursor="hand2",
        )
        self._text = text
        self._command = command
        self._fill_color = COLORS["accent"] if fill is None else fill
        self._outline_color = self._fill_color if outline is None else outline
        self._active_fill = (
            COLORS["accent_active"] if active_fill is None else active_fill)
        self._active_outline = (
            self._active_fill if active_outline is None else active_outline)
        self._hover = False
        inset = max(1.0, outline_width)
        self._shape = self.create_polygon(
            _rounded_points(inset, inset, w - inset, h - inset, radius),
            smooth=False,
            fill=self._fill_color,
            outline=self._outline_color,
            width=outline_width,
            tags="shape",
        )
        self.create_text(
            w / 2, h / 2, text=text, anchor="center",
            fill=COLORS["accent_fg"] if fg is None else fg,
            font=face, tags="label",
        )
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonRelease-1>", self._on_release)

    def cget(self, key: str):
        if key == "text":
            return self._text
        if key == "command":
            return self._command
        return super().cget(key)

    def _paint(self, fill: str, outline: str) -> None:
        self.itemconfig(self._shape, fill=fill, outline=outline)

    def _on_enter(self, _ev=None) -> None:
        self._hover = True
        self._paint(self._active_fill, self._active_outline)

    def _on_leave(self, _ev=None) -> None:
        self._hover = False
        self._paint(self._fill_color, self._outline_color)

    def _on_release(self, ev) -> None:
        if self._command is None:
            return
        if 0 <= ev.x <= self.winfo_width() and 0 <= ev.y <= self.winfo_height():
            self._command()
