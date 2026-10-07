"""Canvas view — renders a ModelState on a tkinter Canvas with pan/zoom.

M1 scope (brief): render LINE/ARC/CIRCLE/POINT/MTEXT; pan via canvas.move
(dirty-region, no rebuild); zoom = full redraw at cursor (single zoom-factor
transform, SPEC 11.8.6); MTEXT renders last; NO hover (cut-list item).

One canvas item per drawable primitive (PassThrough never rendered):
LINE -> create_line, ARC -> flattened polyline (screen-accurate at any zoom;
avoids Tk's arc-angle flip), CIRCLE -> create_oval, POINT -> "+" text marker,
MTEXT -> create_text. Rendering helpers here are presentation-only flattening,
not rule math (geometry math is M2's, in geometry/).
"""
from __future__ import annotations

import math
import tkinter as tk

from geometry.entities import Arc, Circ, Entity, PassThrough, PointEnt, Pt, Seg, TextEnt
from model.state import ModelState
from ui.transform import ViewTransform

BG = "white"
FG = "black"
TEXT_FG = "#404040"
POINT_FG = "#c00000"
MARGIN = 0.08  # fraction of view size kept empty around the part on fit
ZOOM_STEP = 1.25


def flatten_arc(a: Arc, min_seg: int = 12, max_seg: int = 256) -> list[Pt]:
    """Arc points (world coords), CCW start->end; angular step ~1.5 deg."""
    sweep = (a.end_deg - a.start_deg) % 360.0
    if sweep <= 0.0:
        sweep = 360.0
    n = max(min_seg, min(max_seg, int(sweep / 1.5) + 1))
    pts = []
    for i in range(n + 1):
        ang = math.radians(a.start_deg + sweep * i / n)
        pts.append(Pt(a.center.x + a.r * math.cos(ang),
                      a.center.y + a.r * math.sin(ang)))
    return pts


def entity_world_bbox(ents: list[Entity]) -> tuple[float, float, float, float] | None:
    """(minx, miny, maxx, maxy) over drawables; None when nothing to draw."""
    lo: list[float] = []
    hi: list[float] = []
    for e in ents:
        if isinstance(e, Seg):
            lo += [min(e.a.x, e.b.x), min(e.a.y, e.b.y)]
            hi += [max(e.a.x, e.b.x), max(e.a.y, e.b.y)]
        elif isinstance(e, (Arc, Circ)):
            lo += [e.center.x - e.r, e.center.y - e.r]
            hi += [e.center.x + e.r, e.center.y + e.r]
        elif isinstance(e, (PointEnt, TextEnt)):
            lo += [e.p.x, e.p.y]
            hi += [e.p.x, e.p.y]
    if not lo:
        return None
    return min(lo[0::2]), min(lo[1::2]), max(hi[0::2]), max(hi[1::2])


class Viewer:
    """Owns the canvas, transform, and rendering of one ModelState."""

    def __init__(self, master: tk.Misc, width: int = 1100, height: int = 750,
                 on_status=None):
        self.canvas = tk.Canvas(master, width=width, height=height,
                                bg=BG, highlightthickness=0)
        self.transform = ViewTransform(scale=1.0, ox=0.0, oy=0.0)
        self._drawables: list[Entity] = []
        self._item_of: dict[str, int] = {}
        self._eid_of: dict[int, str] = {}
        self._on_status = on_status
        self._pan_from: tuple[float, float] | None = None

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Motion>", self._on_motion)

    # ------------------------------------------------------------ model

    def set_model(self, state: ModelState) -> None:
        self._drawables = [e for e in state.primitives if not isinstance(e, PassThrough)]
        self.fit()
        self.redraw()

    def fit(self) -> None:
        """Zoom/center so all drawables fit the canvas with MARGIN."""
        self.canvas.update_idletasks()
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w <= 1:
            w = int(self.canvas.cget("width"))
        if h <= 1:
            h = int(self.canvas.cget("height"))
        w, h = max(1, w), max(1, h)
        bbox = entity_world_bbox(self._drawables)
        if bbox is None:
            self.transform = ViewTransform(scale=1.0, ox=w / 2.0, oy=h / 2.0)
            return
        minx, miny, maxx, maxy = bbox
        span_x = max(maxx - minx, 1e-9)
        span_y = max(maxy - miny, 1e-9)
        scale = min(w * (1.0 - 2.0 * MARGIN) / span_x,
                    h * (1.0 - 2.0 * MARGIN) / span_y)
        scale = max(scale, 1e-6)
        cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
        self.transform = ViewTransform(scale=scale, ox=w / 2.0 - cx * scale,
                                       oy=h / 2.0 + cy * scale)

    # ---------------------------------------------------------- rendering

    def redraw(self) -> None:
        c = self.canvas
        c.delete("all")
        self._item_of.clear()
        self._eid_of.clear()
        t = self.transform
        texts: list[TextEnt] = []

        for e in self._drawables:  # MTEXT renders last
            if isinstance(e, TextEnt):
                texts.append(e)
                continue
            item = self._create(e, t)
            if item is not None:
                self._register(e.eid, item)

        for e in texts:
            sx, sy = t.to_screen(e.p)
            item = c.create_text(sx, sy, text=e.text or " ",
                                 anchor="w", fill=TEXT_FG, font=("TkDefaultFont", 9))
            self._register(e.eid, item)

    def _create(self, e: Entity, t: ViewTransform) -> int | None:
        c = self.canvas
        if isinstance(e, Seg):
            x1, y1 = t.to_screen(e.a)
            x2, y2 = t.to_screen(e.b)
            return c.create_line(x1, y1, x2, y2, fill=FG, width=1)
        if isinstance(e, Arc):
            pts = [t.to_screen(p) for p in flatten_arc(e)]
            return c.create_line(*pts, fill=FG, width=1, smooth=False)
        if isinstance(e, Circ):
            x1, y1 = t.to_screen(Pt(e.center.x - e.r, e.center.y + e.r))
            x2, y2 = t.to_screen(Pt(e.center.x + e.r, e.center.y - e.r))
            return c.create_oval(x1, y1, x2, y2, outline=FG, width=1)
        if isinstance(e, PointEnt):
            sx, sy = t.to_screen(e.p)
            return c.create_text(sx, sy, text="+", anchor="center",
                                 fill=POINT_FG, font=("TkDefaultFont", 10))
        return None

    def _register(self, eid: str, item: int) -> None:
        self._item_of[eid] = item
        self._eid_of[item] = eid

    def item_count(self) -> int:
        return len(self.canvas.find_all())

    # ------------------------------------------------------------ events

    def _on_press(self, ev) -> None:
        self._pan_from = (ev.x, ev.y)

    def _on_drag(self, ev) -> None:
        if self._pan_from is None:
            return
        dx, dy = ev.x - self._pan_from[0], ev.y - self._pan_from[1]
        if dx == 0 and dy == 0:
            return
        self._pan_from = (ev.x, ev.y)
        self.canvas.move("all", dx, dy)  # dirty-region pan: no rebuild
        self.transform = self.transform.panned_by(dx, dy)
        self._emit_status()

    def _on_release(self, _ev) -> None:
        self._pan_from = None

    def _on_wheel(self, ev) -> None:
        factor = ZOOM_STEP ** (ev.delta / 120.0)
        self.transform = self.transform.zoomed_at(ev.x, ev.y, factor)
        self.redraw()
        self._emit_status()

    def _on_motion(self, ev) -> None:
        self._emit_status(ev.x, ev.y)

    # ------------------------------------------------------------ status

    def _emit_status(self, sx: float | None = None, sy: float | None = None) -> None:
        if self._on_status is None:
            return
        if sx is None:
            w = self._world_center()
            parts = [f"x={w.x:.3f}  y={w.y:.3f}"]
        else:
            w = self.transform.to_world(sx, sy)
            parts = [f"x={w.x:.3f}  y={w.y:.3f}"]
        parts.append(f"zoom={self.transform.scale:.4g} px/mm")
        parts.append(f"entities={len(self._drawables)}")
        self._on_status("   |   ".join(parts))

    def _world_center(self) -> Pt:
        w = max(1, self.canvas.winfo_width())
        h = max(1, self.canvas.winfo_height())
        return self.transform.to_world(w / 2.0, h / 2.0)
