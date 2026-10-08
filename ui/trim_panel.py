"""Manual trim-to-closest panel + headless FSM (ADR-025 owner file).

Thin tkinter shell ONLY (ADR-006): screen↔world + events →
``rules.manual_edit.trim_to_closest`` (engine) → ``model.apply_edit``
(mutation). No geometry is computed here.

Layout (mirrors ui/fold_panel.py so headless tests drive the FSM
directly and the shell is a thin binding):

* ``TrimFSM`` — canvas-free core: pick a LINE (promoted_edge_at), propose
  trim/extend/stray-delete via the engine, hold the pending EditResult,
  confirm → apply_edit + snapshot push (one push per Confirm, ADR-001).
  No tkinter import — unit-tested directly.
* ``TrimPanel`` — the tkinter shell: bottom-bar toggle button, canvas
  binding REPLACEMENT (M5b pattern: scripts saved + restored on exit;
  never unbind()), red overlay preview + floating Confirm pill, T key.

ADR-025 semantics locked by user answers (2026-10-07): moving endpoint =
run-extent endpoint nearest the click; supporting geometry counts;
extend-when-short / trim-when-past; zero-external-attachment runs propose
deletion (the stray rule); no attachment cascade; folds fully allowed
both ways; NO_TARGET → toast + stay in pick.
"""
from __future__ import annotations

import math
import tkinter as tk
import tkinter.font as tkfont
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Protocol

from geometry.entities import EditResult, Entity, Pt, Seg
from model.model import Model
from model.snapshots import SnapshotStack
from rules.filters import eps_pick_from_scale, promoted_edge_at
from rules.manual_edit import SPAN_DELETE_WARNING, trim_to_closest
from ui.collapsible import CollapsibleSection
from ui.theme import COLORS as THEME, font as theme_font
import ui.messages as msg

# ergonomic pick radius — same as the corner workflow's UI_PICK_PX
UI_PICK_PX = 10.0

# overlay tags (canvas item groups wiped/re-drawn per state)
TRIM_FLASH_TAG = "mtrim_flash"    # the promoted run under the pending edit
TRIM_PREVIEW_TAG = "mtrim_prev"   # red trim/delete preview overlay
TRIM_PILL_TAG = "mtrim_pill"      # floating Confirm pill


class TrimMode(Enum):
    OFF = auto()
    ON = auto()


@dataclass
class TrimFSM:
    """Canvas-free core: (state, event) → new state. Handlers: enter /
    exit / click_world / confirm. The pending EditResult lives HERE
    (never in ModelState — ADR-016(j) discipline applied to manual edits:
    preview is re-proposed on confirm against the live model)."""

    ports: "TrimPorts"
    mode: TrimMode = TrimMode.OFF
    picked_eid: str | None = None
    picked_seg: Seg | None = None
    last_click: Pt | None = None
    pending: EditResult | None = None
    inline: str | None = None
    status: str = ""
    applied_count: int = 0

    # ------------------------------------------------------------ helpers
    def _set_status(self, text: str, inline: str | None = None) -> None:
        self.status = text
        self.inline = inline

    def _clear_pick(self) -> None:
        self.picked_eid = None
        self.picked_seg = None
        self.last_click = None
        self.pending = None
        self.inline = None

    # ------------------------------------------------------------ events
    def enter(self) -> None:
        self.mode = TrimMode.ON
        self._clear_pick()
        self._set_status(msg.TRIM_MODE_ENTER)

    def exit(self) -> None:
        self.mode = TrimMode.OFF
        self._clear_pick()
        self._set_status(msg.TRIM_MODE_EXIT)

    def click_world(self, p_world: Pt) -> None:
        """Click in trim mode: pick the nearest LINE (promoted run), then
        propose the manual edit via the engine. NO_TARGET/UNKNOWN_EDGE →
        toast + stay in pick (user answer 9)."""
        if self.mode != TrimMode.ON:
            return
        seg = self.ports.pick_edge(p_world)
        if seg is None:
            return  # miss: stay in pick
        self.picked_eid = seg.eid
        self.picked_seg = seg
        self.last_click = p_world
        res = self.ports.propose(p_world, seg.eid)
        self.pending = res
        if not res.ok:
            assert res.reason is not None
            self._clear_pick()
            self._set_status(
                msg.TRIM_PICK_STATUS,
                inline=msg.TRIM_TOAST_REFUSED.format(reason=res.reason))
            return
        if res.deletions:
            inline = (msg.TRIM_PREVIEW_SPAN_DELETE
                      if SPAN_DELETE_WARNING in res.warnings
                      else msg.TRIM_PREVIEW_DELETE)
            self._set_status(msg.TRIM_PREVIEW_STATUS, inline=inline)
        else:
            self._set_status(msg.TRIM_PREVIEW_STATUS)

    def confirm(self) -> EditResult | None:
        """Apply the pending edit; None when nothing is pending or the
        re-propose against the live model refused (ADR-016(k) discipline:
        never apply a stale result)."""
        if self.mode != TrimMode.ON or self.picked_eid is None:
            return None
        # live re-propose (the model may have changed since the preview)
        res = self.ports.propose(self.last_click, self.picked_eid)
        if not res.ok:
            assert res.reason is not None
            self._clear_pick()
            self._set_status(
                msg.TRIM_PICK_STATUS,
                inline=msg.TRIM_TOAST_REFUSED.format(reason=res.reason))
            return None
        self.ports.apply(res)
        self.applied_count += 1
        if not res.deletions:
            toast = msg.TRIM_TOAST_APPLIED
        elif SPAN_DELETE_WARNING in res.warnings:
            toast = msg.TRIM_SPAN_DELETE_APPLIED
        else:
            toast = msg.TRIM_DELETE_APPLIED
        self._clear_pick()
        self._set_status(toast + "  " + msg.TRIM_PICK_STATUS)
        return res


class TrimPorts(Protocol):
    """The engine/model boundary the FSM drives (all headless-testable)."""

    def pick_edge(self, p_world: Pt) -> Seg | None: ...
    def propose(self, p_world: Pt, eid: str) -> EditResult: ...
    def apply(self, res: EditResult) -> None: ...


# ---------------------------------------------------------------------------
# Tkinter shell
# ---------------------------------------------------------------------------

from tkinter import ttk  # noqa: E402

from ui.canvas_view import Viewer  # noqa: E402

DELETE_COLOR = THEME["delete"]
DELETE_WIDTH = 3
FLASH_COLOR = THEME["highlight"]


class TrimPanel(ttk.Frame):
    """Left-side panel: mode toggle button. Thin shell — binds canvas
    events in trim mode (REPLACEMENT pattern: prior scripts saved and
    restored verbatim on exit; never unbind()) and converts them to FSM
    events. Preview rendering: thick red overlay of the run's post-edit
    extent (trim/extend) or of the doomed run (stray-delete) + a
    floating Confirm pill near the run."""

    def __init__(self, master, viewer: Viewer, model: Model | None,
                 stack: SnapshotStack | None = None, on_status=None):
        super().__init__(master, style="TFrame")
        self.viewer = viewer
        self.model = model  # may be None at construction; App sets it
        self.stack = stack
        self._on_status = on_status
        self.fsm = TrimFSM(ports=self)
        self._bound = False
        self._saved_bindings: dict[str, str] = {}
        self._pan_from: tuple[float, float] | None = None
        self._pill: tk.Canvas | None = None

        self.section = CollapsibleSection(self, msg.SECTION_TRIM)
        self.section.pack(fill=tk.X, pady=(0, 6))
        self.mode_btn = ttk.Button(self.section.body, text=msg.TRIM_MODE_TOGGLE_ON,
                                   style="TrimMode.TButton",
                                   command=self.toggle_mode)
        self.mode_btn.pack(fill=tk.X)
        self.hint = tk.Label(
            self.section.body, text=msg.TRIM_HINT,
            bg=THEME["bg"], fg=THEME["fg_muted"],
            font=theme_font(9), wraplength=248, justify="left", anchor="w",
        )
        self.hint.pack(anchor="w", fill=tk.X, pady=(4, 0))
        self._emit_status()

    # ------------------------------------------------------------- ports
    @property
    def _primitives(self) -> list[Entity]:
        if self.model is None:
            return []
        return self.model.state.primitives

    def pick_edge(self, p_world: Pt) -> Seg | None:
        eps_pick = eps_pick_from_scale(self.viewer.transform.scale,
                                       pick_px=UI_PICK_PX)
        return promoted_edge_at(self._primitives, p_world, eps_pick)

    def propose(self, p_world: Pt, eid: str) -> EditResult:
        return trim_to_closest(self._primitives, p_world, eid)

    def apply(self, res: EditResult) -> None:
        assert self.model is not None
        if self.stack is not None:
            self.stack.push()  # one push per Confirm (ADR-001/ADR-025(c))
        self.model.apply_edit(res)
        self.viewer.set_model(self.model.state)

    # --------------------------------------------------------- mode toggle
    def toggle_mode(self) -> None:
        if self.fsm.mode == TrimMode.OFF:
            self.fsm.enter()
            self.bind_canvas()
        else:
            self.fsm.exit()
            self.unbind_canvas()
        self._refresh_button()
        self._emit_status()
        self._clear_overlays()

    def _refresh_button(self) -> None:
        on = self.fsm.mode == TrimMode.ON
        self.mode_btn.config(
            text=(msg.TRIM_MODE_TOGGLE_OFF if on else msg.TRIM_MODE_TOGGLE_ON))
        self.section.set_summary(msg.SECTION_MODE_ON if on else "")

    def _emit_status(self) -> None:
        if self._on_status is not None:
            text = self.fsm.status
            if self.fsm.inline:
                text = f"{text}    {self.fsm.inline}"
            self._on_status(text)

    # ------------------------------------------------------- canvas events
    def bind_canvas(self) -> None:
        """Trim-mode bindings REPLACE the canvas's B1/Button-3/Escape/
        middle-drag scripts (saved for verbatim restore on exit). The
        corner workflow and viewer pan are suspended while trim mode is
        ON (mode isolation, M5b binding-regression precedent)."""
        if self._bound:
            return
        c = self.viewer.canvas
        handlers = {
            "<ButtonPress-1>": self._on_left,
            "<Button-3>": self._on_right,
            "<Escape>": self._on_esc,
            "<ButtonPress-2>": self._on_pan_press,
            "<B2-Motion>": self._on_pan_drag,
            "<ButtonRelease-2>": self._on_pan_release,
        }
        for seq, handler in handlers.items():
            self._saved_bindings[seq] = c.bind(seq)
            c.bind(seq, handler)
        self._bound = True

    def unbind_canvas(self) -> None:
        if not self._bound:
            return
        c = self.viewer.canvas
        for seq, script in self._saved_bindings.items():
            c.bind(seq, script)
        self._saved_bindings.clear()
        self._bound = False
        self._pan_from = None
        self._clear_overlays()

    def _on_left(self, ev) -> None:
        w = self.viewer.transform.to_world(ev.x, ev.y)
        self.fsm.click_world(w)
        self._sync_view()
        self._emit_status()

    def _on_right(self, _ev) -> None:
        self.fsm.exit()
        self.unbind_canvas()
        self._refresh_button()
        self._emit_status()

    def _on_esc(self, _ev) -> str:
        self._on_right(None)
        return "break"

    def _on_pan_press(self, ev) -> None:
        self._pan_from = (ev.x, ev.y)

    def _on_pan_drag(self, ev) -> None:
        if self._pan_from is None:
            return
        dx, dy = ev.x - self._pan_from[0], ev.y - self._pan_from[1]
        if dx == 0 and dy == 0:
            return
        self._pan_from = (ev.x, ev.y)
        self.viewer.canvas.move("all", dx, dy)
        self.viewer.transform = self.viewer.transform.panned_by(dx, dy)

    def _on_pan_release(self, _ev) -> None:
        self._pan_from = None

    # ----------------------------------------------------------- rendering
    def _clear_overlays(self) -> None:
        c = self.viewer.canvas
        for tag in (TRIM_FLASH_TAG, TRIM_PREVIEW_TAG, TRIM_PILL_TAG):
            c.delete(tag)
        self._destroy_pill()

    def _destroy_pill(self) -> None:
        if self._pill is not None:
            try:
                self._pill.destroy()
            except tk.TclError:
                pass
            self._pill = None

    def _sync_view(self) -> None:
        """Re-draw the preview overlays from the FSM's pending state."""
        self._clear_overlays()
        res = self.fsm.pending
        if res is None or not res.ok or self.fsm.picked_seg is None:
            return
        c = self.viewer.canvas
        t = self.viewer.transform
        seg = self.fsm.picked_seg
        # flash the picked run (cyan, thin) so the user sees what they hit
        x1, y1 = t.to_screen(seg.a)
        x2, y2 = t.to_screen(seg.b)
        c.create_line(x1, y1, x2, y2, fill=FLASH_COLOR, width=2,
                      tags=(TRIM_FLASH_TAG,))
        if res.deletions:
            # stray: whole run previews in delete-red
            c.create_line(x1, y1, x2, y2, fill=DELETE_COLOR,
                          width=DELETE_WIDTH, tags=(TRIM_PREVIEW_TAG,))
        else:
            for tr in res.trims:
                new_a, new_b = tr.new
                nx1, ny1 = t.to_screen(new_a)
                nx2, ny2 = t.to_screen(new_b)
                c.create_line(nx1, ny1, nx2, ny2, fill=DELETE_COLOR,
                              width=DELETE_WIDTH,
                              tags=(TRIM_PREVIEW_TAG,))
        self._show_confirm_pill()

    def _show_confirm_pill(self) -> None:
        """Floating confirm near the run's moving end.

        Same pill as the dogbone Confirm button and the flag choices:
        muted grey fill, light label, fully rounded ends.
        """
        self._destroy_pill()
        if self.fsm.pending is None or self.fsm.picked_seg is None:
            return
        res = self.fsm.pending
        seg = self.fsm.picked_seg
        t = self.viewer.transform
        # anchor: the moving endpoint (or run midpoint for stray-delete)
        if res.trims:
            moving = (res.trims[0].new[0] if _end_is_a(seg, res)
                      else res.trims[0].new[1])
        else:
            moving = Pt((seg.a.x + seg.b.x) / 2.0,
                         (seg.a.y + seg.b.y) / 2.0)
        cx, cy = t.to_screen(moving)
        label = msg.TRIM_PILL_CONFIRM
        font = tkfont.Font(root=self.viewer.canvas, font=theme_font(9))
        width = int(font.measure(label) + 36)
        height = 30
        w = max(1, self.viewer.canvas.winfo_width())
        h = max(1, self.viewer.canvas.winfo_height())
        x = min(max(cx + 12, 8), max(w - width - 8, 8))
        y = min(max(cy - height - 8, 8), max(h - height - 8, 8))
        pill = tk.Canvas(
            self.viewer.canvas, width=width, height=height,
            highlightthickness=0, bd=0, bg=THEME["canvas_bg"],
            cursor="hand2")
        _paint_trim_pill(pill, width, height, label, hover=False)

        def _hover(on: bool) -> None:
            _paint_trim_pill(pill, width, height, label, hover=on)

        pill.bind("<Enter>", lambda _e: _hover(True))
        pill.bind("<Leave>", lambda _e: _hover(False))
        pill.bind("<Button-1>", lambda _e: self.confirm_click())
        self.viewer.canvas.create_window(x, y, window=pill, anchor="nw",
                                         tags=(TRIM_PILL_TAG,))
        self._pill = pill

    # ------------------------------------------------------------- confirm
    def confirm_click(self) -> EditResult | None:
        res = self.fsm.confirm()
        self._clear_overlays()
        self._emit_status()
        return res


def _rounded_points(x1: float, y1: float, x2: float, y2: float,
                    r: float, steps: int = 8) -> list[float]:
    """Corner samples in canvas space (y grows downward).

    Same construction as the dogbone dock pills.
    """
    r = min(r, (x2 - x1) / 2, (y2 - y1) / 2)
    pts: list[float] = []
    corners = (
        (x2 - r, y1 + r, 270, 360),
        (x2 - r, y2 - r, 0, 90),
        (x1 + r, y2 - r, 90, 180),
        (x1 + r, y1 + r, 180, 270),
    )
    for cx, cy, a0, a1 in corners:
        for i in range(steps + 1):
            a = math.radians(a0 + (a1 - a0) * i / steps)
            pts.append(cx + r * math.cos(a))
            pts.append(cy + r * math.sin(a))
    return pts


def _paint_trim_pill(canvas: tk.Canvas, width: int, height: int,
                     label: str, *, hover: bool) -> None:
    """Draw the trim confirm as the dogbone dock button."""
    canvas.delete("all")
    fill = THEME["dock_btn_hover"] if hover else THEME["dock_btn"]
    canvas.create_polygon(
        _rounded_points(1, 1, width - 2, height - 2, height / 2),
        smooth=False, fill=fill, outline=THEME["dock_edge"], width=1,
        tags=("confirm",))
    canvas.create_text(
        width / 2, height / 2, text=label,
        fill=THEME["dock_text"], font=theme_font(9),
        tags=("confirm-label",))


def _end_is_a(seg: Seg, res: EditResult) -> bool:
    """True when the pending trim moves endpoint ``a`` (the new pair's
    ``a`` differs from the picked run's ``a`` within a hair)."""
    if not res.trims:
        return False
    new_a, _new_b = res.trims[0].new
    return (math.hypot(new_a.x - seg.a.x, new_a.y - seg.a.y)
            > math.hypot(new_a.x - seg.b.x, new_a.y - seg.b.y))