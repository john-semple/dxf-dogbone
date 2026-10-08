"""Corner-workflow state machine + thin tkinter shell (M3 brief owner file).

SPEC §4.2 / §11.8.1–§11.8.3, ADR-016(g)/(j)/(m).

Layout (brief DoD: "handlers take (state, event) → new state, canvas-free"):

* ``WorkflowState`` — one enum: IDLE → PICK_EDGE1 → PICK_EDGE2 →
  GHOSTS_VISIBLE → SIDE_PICKED(PENDING) → PREVIEW_VISIBLE → CONFIRMED,
  with IDLE-restart on Esc/right-click (no partial state survives).
* ``WorkflowFSM`` — the canvas-free core: pure event handlers over
  (state, event); all engine calls go through the injected ``ports``
  (pick/ghosts/preview/decide/apply/radius). Headless: no tkinter import
  anywhere in this class's path — the FSM is unit-tested directly.
* ``WorkflowUI`` — the tkinter shell: converts canvas events into FSM
  events, renders promoted-edge flash / ghosts / red deletion preview
  as canvas overlays on the M1 Viewer, runs toast + status line,
  auto-zoom, and the first-occurrence flag prompts. No geometry is
  computed here (ADR-006; picking = rules.filters, construction =
  rules.engine).

ADR-016(j): pending corners live HERE (PendingCorner record), never in
ModelState. ADR-016(k): every preview/confirm re-places against the
live model (never applies a stale CornerResult).
"""
from __future__ import annotations

import sys
import tkinter as tk
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Protocol

from geometry.entities import (
    Arc,
    Circ,
    CornerResult,
    Entity,
    Flag,
    PointEnt,
    Pt,
    Refusal,
    Seg,
    Side,
    TextEnt,
)
from model.model import Model
from rules.engine import ghost_candidates, place_corner
from rules.filters import eps_pick_from_scale, promoted_edge_at
from ui.theme import COLORS as THEME, font as theme_font
import ui.messages as msg

from ui.canvas_view import Viewer, flatten_arc
from ui.transform import MIN_SCALE, MAX_SCALE, ViewTransform


# ---------------------------------------------------------------------------
# Canvas-free core
# ---------------------------------------------------------------------------


class WorkflowState(Enum):
    IDLE = auto()
    PICK_EDGE1 = auto()
    PICK_EDGE2 = auto()
    GHOSTS_VISIBLE = auto()
    SIDE_PICKED = auto()      # PENDING preview computed, awaiting confirm
    PREVIEW_VISIBLE = auto()  # brief's name for the preview-on-screen state
    CONFIRMED = auto()


@dataclass(frozen=True)
class PendingCorner:
    """ADR-016(j): a picked corner awaiting apply — lives in the UI layer."""
    edge1_eid: str
    edge2_eid: str
    side: Side
    side_flip: int
    r: float
    db_id: str


@dataclass
class GhostMark:
    """One rendered ghost: dashed candidate circle at a ghost center."""
    side: Side
    side_flip: int
    center: Pt
    r: float
    apex: Pt | None = None  # outward-ray origin for the corridor hit-test


def _ghost_apex(gcs: list[tuple[Side, int, Pt]]) -> Pt | None:
    """Apex from ghost_candidates' rays: for each bisector sign the two
    flips are symmetric about the apex (center = apex ± R·bisector_unit),
    so each sign pair's midpoint IS the apex. None when the pair structure
    is missing (defensive: the corridor hit-test then disables; circles
    still pick)."""
    by_sign: dict[int, list[Pt]] = {}
    for side, _flip, c in gcs:
        by_sign.setdefault(side.sign, []).append(c)
    for cs in by_sign.values():
        if len(cs) == 2:
            return Pt((cs[0].x + cs[1].x) / 2.0, (cs[0].y + cs[1].y) / 2.0)
    return None


CORRIDOR_MIN_PX = 10.0    # lateral forgiveness for outward ghost clicks
CORRIDOR_REACH_PX = 80.0  # how far past a ghost its outward corridor runs
UI_PICK_PX = 10.0         # ergonomic edge-click radius (rules nominal 3px)


def _ray_miss(sx: float, sy: float, gx: float, gy: float,
              ax: float, ay: float, r_px: float, corridor_px: float,
              reach_px: float) -> float | None:
    """Lateral px from the outward ghost ray (apex→center→beyond) when the
    click lies at/beyond the ghost center along that ray, within reach;
    None otherwise (user round-5: clicking 'outside the ghost but in the
    same direction' should pick it). Pure screen-px math."""
    import math
    vx, vy = gx - ax, gy - ay
    n = math.hypot(vx, vy)
    if n <= 0.0:
        return None
    ux, uy = vx / n, vy / n
    wx, wy = sx - ax, sy - ay
    t = wx * ux + wy * uy
    if t < n or t > n + reach_px:
        return None
    lateral = abs(wx * uy - wy * ux)
    if lateral > corridor_px:
        return None
    return lateral


class WorkflowPorts(Protocol):
    """The engine/model boundary the FSM drives (all headless-testable)."""

    def pick_edge(self, p_world: Pt) -> Seg | None: ...
    def ghosts(self, edge1_eid: str, edge2_eid: str, r: float
               ) -> list[tuple[Side, int, Pt]] | Refusal: ...
    def place_preview(self, pending: PendingCorner) -> CornerResult: ...
    def decide_flag(self, flag: Flag, kind: str) -> str | None: ...
    def apply(self, res: CornerResult) -> None: ...
    def radius(self) -> float: ...


@dataclass
class WorkflowFSM:
    """(state, event) → new state. Handlers: start / click_world /
    pick_ghost / recompute / confirm / esc (right_click aliases esc).
    Nothing here touches tkinter; ``inline`` carries the current
    one-line message (flash text, inline same-edge note, refusal toast).
    """
    ports: WorkflowPorts
    state: WorkflowState = WorkflowState.IDLE
    edge1_eid: str | None = None
    edge1_seg: Seg | None = None   # promoted run (flash overlay source)
    edge2_eid: str | None = None
    edge2_seg: Seg | None = None
    ghosts: list[GhostMark] = field(default_factory=list)
    pending: PendingCorner | None = None
    preview: CornerResult | None = None
    refusals: list[str] = field(default_factory=list)
    inline: str | None = None
    status: str = msg.STATUS_IDLE
    applied_count: int = 0

    # ------------------------------------------------------------ helpers
    def _clear_pick(self) -> None:
        self.edge1_eid = self.edge2_eid = None
        self.edge1_seg = self.edge2_seg = None
        self.ghosts = []
        self.pending = None
        self.preview = None
        self.inline = None

    def _restart(self, status: str) -> None:
        """Esc/right-click: back to IDLE, no partial state survives."""
        self._clear_pick()
        self.state = WorkflowState.IDLE
        self.status = status

    # ------------------------------------------------------------ events
    def start(self) -> None:
        """Explicit IDLE → PICK_EDGE1 (button or first-session start)."""
        self._clear_pick()
        self.state = WorkflowState.PICK_EDGE1
        self.status = msg.STATUS_PICK_EDGE1

    def click_world(self, p_world: Pt) -> None:
        if self.state == WorkflowState.IDLE:
            # first edge click starts the pick (IDLE → PICK_EDGE1)
            self.state = WorkflowState.PICK_EDGE1
        if self.state == WorkflowState.PICK_EDGE1:
            self._handle_edge_click(p_world, first=True)
        elif self.state == WorkflowState.PICK_EDGE2:
            self._handle_edge_click(p_world, first=False)
        # GHOSTS_VISIBLE: clicks go through the shell's ghost hit-test;
        # SIDE_PICKED: only Confirm/Esc are live. Nothing else to do.

    def _handle_edge_click(self, p_world: Pt, first: bool) -> None:
        seg = self.ports.pick_edge(p_world)
        if seg is None:
            return  # miss: stay in the current pick state
        if first:
            self.edge1_eid = seg.eid
            self.edge1_seg = seg
            self.state = WorkflowState.PICK_EDGE2
            self.status = msg.STATUS_PICK_EDGE2
            self.inline = msg.PROMOTED_FLASH.format(eid=seg.eid)
            return
        # PICK_EDGE2
        if seg.eid == self.edge1_eid:
            # brief item 4: same edge twice → inline message, STAY in
            # PICK_EDGE2 (not a restart)
            self.status = msg.STATUS_PICK_EDGE2
            self.inline = msg.SAME_EDGE_INLINE
            return
        self.edge2_eid = seg.eid
        self.edge2_seg = seg
        self._compute_ghosts()

    def _compute_ghosts(self) -> None:
        assert self.edge1_eid and self.edge2_eid
        gcs = self.ports.ghosts(self.edge1_eid, self.edge2_eid,
                                self.ports.radius())
        if isinstance(gcs, Refusal):
            # apex/band gate: toast + status carry the engine string
            # VERBATIM (brief item 5); edge2 dropped — re-click a second edge
            self.edge2_eid = None
            self.edge2_seg = None
            self.refusals = [gcs.reason]
            self.state = WorkflowState.PICK_EDGE2
            self.status = msg.STATUS_PICK_EDGE2
            self.inline = msg.TOAST_REFUSED.format(reason=gcs.reason)
            return
        self.refusals = []
        r = self.ports.radius()
        apex = _ghost_apex(gcs)  # corridor hit-test origin (round-5)
        self.ghosts = [GhostMark(side, flip, c, r, apex) for side, flip, c in gcs]
        self.state = WorkflowState.GHOSTS_VISIBLE
        self.status = msg.STATUS_GHOSTS
        self.inline = None

    def pick_ghost(self, side: Side, side_flip: int) -> None:
        """Ghost click → that (Side, flip) feeds the real place_corner."""
        if self.state != WorkflowState.GHOSTS_VISIBLE:
            return
        assert self.edge1_eid and self.edge2_eid
        pending = PendingCorner(
            edge1_eid=self.edge1_eid,
            edge2_eid=self.edge2_eid,
            side=side,
            side_flip=side_flip,
            r=self.ports.radius(),
            db_id=f"db-{self.edge1_eid}+{self.edge2_eid}",
        )
        self.pending = pending
        self._enter_preview(self.ports.place_preview(pending))

    def _enter_preview(self, res: CornerResult) -> None:
        if not res.ok:
            # apex-gate / overlap / shallow refusals surface VERBATIM;
            # stay in GHOSTS_VISIBLE so another ghost ray can be tried
            self.pending = None
            self.preview = None
            self.refusals = list(res.refusals)
            self.state = WorkflowState.GHOSTS_VISIBLE
            self.status = msg.STATUS_GHOSTS
            self.inline = msg.TOAST_REFUSED.format(
                reason="; ".join(res.refusals)
            )
            return
        self.preview = res
        self.refusals = list(res.refusals)
        self.state = WorkflowState.SIDE_PICKED
        self.status = msg.STATUS_PREVIEW
        self.inline = None

    def recompute(self) -> None:
        """ADR-016(k): re-place against the live model (never a stale
        result). Called after every flag decision so the preview honors
        current decisions (ADR-009 sticky, no re-prompting)."""
        if self.pending is None:
            return
        self._enter_preview(self.ports.place_preview(self.pending))

    def confirm(self) -> CornerResult | None:
        """Apply the pending corner; None when blocked. Confirm-gate:
        blocked only while any flag is pending (ADR-013; SPEC §11.5)."""
        if self.state != WorkflowState.SIDE_PICKED or self.pending is None:
            return None
        assert self.preview is not None
        if any(f.decision is None for f in self.preview.flags):
            reasons = sorted({f.reason for f in self.preview.flags
                              if f.decision is None})
            self.inline = msg.TOAST_PENDING_FLAG.format(
                reasons=", ".join(reasons)
            )
            return None
        res = self.ports.place_preview(self.pending)  # ADR-016(k) live
        if not res.ok:
            self._enter_preview(res)
            return None
        self.ports.apply(res)
        self.applied_count += 1
        result = res
        self.state = WorkflowState.CONFIRMED
        # CONFIRMED → IDLE(restart): fresh corner, no partial state
        self._restart(msg.TOAST_APPLIED + "  " + msg.STATUS_IDLE)
        return result

    def esc(self) -> None:
        """Esc anywhere → back to IDLE, no partial state survives."""
        self._restart(msg.RESTARTED + " " + msg.STATUS_IDLE)

    right_click = esc

    def notify_flag_decision(self) -> None:
        self.recompute()


# ---------------------------------------------------------------------------
# Tkinter shell
# ---------------------------------------------------------------------------

# Overlay colors: theme-driven (UI-UPGRADE brief item 2). Relative
# distinction preserved — flash/ghost cyan-family, delete dark-bg-safe
# red, flag orange; literals live in ui/theme.py.
HIGHLIGHT_COLOR = THEME["highlight"]  # promoted-edge highlight (distinct from red)
EDGE2_PICK_COLOR = THEME["edge2_pick"]  # edge-2 pick-phase highlight (until zoom)
GHOST_COLOR = THEME["ghost"]
GHOST_DASH = (3, 3)
DELETE_COLOR = THEME["delete"]  # thick red for delete/trim preview (brief item 3)
DELETE_WIDTH = 3
FLAG_COLOR = THEME["flag"]     # flagged entities, orange outline
FLAG_WIDTH = 2
CHORD_FOCUS_WIDTH = 5          # the one chord-crosser the card is asking about
# Flag card. Delete's center sits on the ghost-click pointer. Full
# behavior: documentation/sessions/2026-10-08-CHORD-PROMPT.md.
DOCK_MARGIN = 8
DOCK_GAP = 12                  # px between the circle and the card
DOCK_PAD = 10
DOCK_RADIUS = 10
DOCK_BTN_H = 26
DOCK_BTN_GAP = 8


class WorkflowUI:
    """Thin shell binding the FSM to the M1 Viewer canvas.

    Owns: overlay rendering (promoted-edge flash, ghosts, deletion
    preview), toast + status line, auto-zoom at preview entry,
    first-occurrence flag prompts, and the Confirm button.
    """
    GHOST_TAG = "m3_ghost"
    FLASH_TAG = "m3_flash"
    DELETE_TAG = "m3_delete"
    FLAG_TAG = "m3_flag"
    CHORD_TAG = "m3_chord"   # thick outline of the chord-crosser under the card
    PILL_TAG = "m3_pill"

    def __init__(self, viewer: Viewer, model: Model, root: tk.Misc,
                 on_status=None, radius_mm: float = 3.175 / 2.0,
                 on_state=None):
        self.viewer = viewer
        self.model = model
        self.root = root
        self._on_status = on_status
        self._on_state = on_state  # App refreshes Confirm affordances via it
        self._radius_mm = radius_mm  # default tool dia 3.175 → R 1.5875
        self._dock: tk.Canvas | None = None
        self._hits: dict[str, tuple[float, float, float, float]] = {}
        self._dock_mode = ""
        self._dock_anchor: tuple[float, float] | None = None
        self._dock_pinned: tuple[int, int] | None = None
        self._button_at: tuple[float, float] | None = None
        self._confirm_ready_at = 0.0
        self._ask_eids: list[str] | None = None
        self._hit_proc = None
        self._hit_old = None
        self._hit_hwnd: int | None = None
        self._view_before_zoom: ViewTransform | None = None
        self.fsm = WorkflowFSM(ports=self)
        self._bind()

    # ------------------------------------------------------------- ports
    @property
    def transform(self) -> ViewTransform:
        return self.viewer.transform

    def _primitives(self) -> list[Entity]:
        return self.model.state.primitives

    def pick_edge(self, p_world: Pt) -> Seg | None:
        # ergonomic pick radius: the rules' nominal PICK_PX (3 px) makes
        # thin lines hard to hit; the shell picks with a wider radius via
        # the existing ``pick_px`` parameter (rules defaults untouched)
        eps_pick = eps_pick_from_scale(self.transform.scale,
                                       pick_px=UI_PICK_PX)
        return promoted_edge_at(self._primitives(), p_world, eps_pick)

    def ghosts(self, edge1_eid: str, edge2_eid: str, r: float):
        return ghost_candidates(self._primitives(), edge1_eid, edge2_eid, r)

    def place_preview(self, pending: PendingCorner) -> CornerResult:
        return place_corner(
            self._primitives(),
            pending.edge1_eid,
            pending.edge2_eid,
            pending.side,
            pending.r,
            set(self.model.state.fold_eids),
            list(self.model.state.dogbones),
            flag_decisions=dict(self.model.state.flag_decisions),
            db_id=pending.db_id,
            side_flip=pending.side_flip,
        )

    def decide_flag(self, flag: Flag, kind: str) -> str | None:
        """Yes/no for the headless harness (ADR-009 sticky per session).

        The interactive card does not call this. A harness replaces it.
        Yes = delete, no = keep (trim stays engine-scripted)."""
        from tkinter import messagebox  # late: headless tests never hit it
        text = msg.FLAG_PROMPT_TEXT.format(kind=kind, eid=flag.eid,
                                           reason=flag.reason)
        yes = messagebox.askyesno(msg.FLAG_PROMPT_TITLE, text)
        decision = "delete" if yes else "keep"
        self.model.state.flag_decisions[flag.eid] = decision
        return decision

    def apply(self, res: CornerResult) -> None:
        self.model.apply_corner(res)
        self.viewer.set_model(self.model.state)

    def radius(self) -> float:
        return self._radius_mm

    # ------------------------------------------------------------ binding
    def _bind(self) -> None:
        c = self.viewer.canvas
        c.bind("<ButtonPress-1>", self._on_left, add=True)
        c.bind("<Motion>", self._on_canvas_motion, add=True)
        c.bind("<Button-3>", self._on_right, add=True)
        c.bind("<Escape>", self._on_esc, add=True)
        c.bind("<Return>", self._on_enter, add=True)
        c.focus_set()

    def _on_enter(self, _ev) -> None:
        """Enter = confirm (no-op unless a preview is pending)."""
        self.confirm_click()

    def start(self) -> None:
        self.fsm.start()
        self._sync_view()

    # ------------------------------------------------------------- events
    def _on_left(self, ev) -> None:
        if self._relay_dock_click(ev):
            return
        if self.fsm.state == WorkflowState.GHOSTS_VISIBLE:
            hit = self._ghost_at(ev.x, ev.y)
            if hit is not None:
                self._dock_anchor = (float(ev.x), float(ev.y))
                self._dock_pinned = None
                self._button_at = None
                self.fsm.pick_ghost(hit.side, hit.side_flip)
                self._sync_view()
                return
        w = self.transform.to_world(ev.x, ev.y)
        self.fsm.click_world(w)
        self._sync_view()

    def _on_right(self, _ev) -> None:
        self._abort_pick()

    def _on_esc(self, _ev) -> str:
        self._abort_pick()
        return "break"

    def _abort_pick(self) -> None:
        """Esc / right-click. A preview close-up returns to the view from
        before that auto-zoom."""
        restore = (
            self.fsm.state == WorkflowState.SIDE_PICKED
            and self._view_before_zoom is not None
        )
        saved = self._view_before_zoom
        self._view_before_zoom = None
        self.fsm.esc()
        if restore and saved is not None:
            self.viewer.transform = saved
            self.viewer.redraw()
        self._sync_view()

    def confirm_click(self) -> CornerResult | None:
        """Confirm button entry point; returns the applied result."""
        res = self.fsm.confirm()
        if res is not None:
            # apply() triggered set_model → full redraw; overlays already
            # wiped by the viewer — nothing stale left to clear.
            # The close-up is over; the next preview must remember the
            # view the user is on then, not this one.
            self._view_before_zoom = None
            self._destroy_pill()
            self._on_state_notify()
        else:
            self._sync_view()
        return res

    def _on_state_notify(self) -> None:
        if self._on_state is not None:
            self._on_state()
        if self._on_status is not None:
            text = self.fsm.status
            if self.fsm.inline:
                text = f"{text}    {self.fsm.inline}"
            self._on_status(text)

    # ----------------------------------------------------------- hit-test
    def _ghost_at(self, sx: float, sy: float) -> GhostMark | None:
        """Ghost hit-test (user round-5):
        1. click INSIDE a dashed ghost circle picks it (nearest center wins
           overlaps), plus PICK_PX grace on the outline;
        2. a click OUTSIDE the ghost but along its outward ray (apex→
           center→beyond, corridor as wide as the ghost + grace, capped
           reach) picks it — 'in the same direction as the ghost'."""
        import math
        from geometry.tolerances import PICK_PX
        inside: list[tuple[float, GhostMark]] = []
        near: list[tuple[float, GhostMark]] = []
        corridor: list[tuple[float, GhostMark]] = []
        for g in self.fsm.ghosts:
            gx, gy = self.transform.to_screen(g.center)
            d = math.hypot(sx - gx, sy - gy)
            r_px = g.r * self.transform.scale
            if d <= r_px:
                inside.append((d, g))
                continue
            if abs(d - r_px) <= PICK_PX:
                near.append((abs(d - r_px), g))
            if g.apex is not None:
                ax, ay = self.transform.to_screen(g.apex)
                lateral = _ray_miss(sx, sy, gx, gy, ax, ay, r_px,
                                    r_px + CORRIDOR_MIN_PX,
                                    CORRIDOR_REACH_PX)
                if lateral is not None:
                    corridor.append((lateral, g))
        for pool in (inside, near, corridor):
            if pool:
                return min(pool, key=lambda t: t[0])[1]
        return None

    # ----------------------------------------------------------- rendering
    def _clear_overlays(self) -> None:
        c = self.viewer.canvas
        for tag in (self.FLASH_TAG, self.GHOST_TAG, self.DELETE_TAG,
                    self.FLAG_TAG, self.CHORD_TAG):
            c.delete(tag)
        self._destroy_pill()

    def _destroy_pill(self) -> None:
        self._remove_click_through()
        if self._dock is not None:
            try:
                self._dock.destroy()
            except tk.TclError:
                pass
        self._dock = None
        self._hits = {}
        self._dock_mode = ""

    def _canvas_px(self) -> tuple[int, int]:
        c = self.viewer.canvas
        w = c.winfo_width()
        h = c.winfo_height()
        if w <= 1:
            w = int(c.cget("width"))
        if h <= 1:
            h = int(c.cget("height"))
        return max(1, w), max(1, h)

    def _clamp_dock(self, x: float, y: float, width: int, height: int) -> tuple[int, int]:
        w, h = self._canvas_px()
        x = int(min(max(round(x), DOCK_MARGIN), max(w - width - DOCK_MARGIN, DOCK_MARGIN)))
        y = int(min(max(round(y), DOCK_MARGIN), max(h - height - DOCK_MARGIN, DOCK_MARGIN)))
        return x, y

    @staticmethod
    def _covers_circle(x: float, y: float, width: int, height: int,
                       cx: float, cy: float, r_px: float) -> bool:
        import math
        nearest_x = min(max(cx, x), x + width)
        nearest_y = min(max(cy, y), y + height)
        return math.hypot(cx - nearest_x, cy - nearest_y) < r_px + 2

    def _dock_origin(self, width: int, height: int,
                     hotspot: tuple[float, float] = (0.0, 0.0)) -> tuple[int, int]:
        """Top-left of the card.

        ``hotspot`` is the point inside the card (Delete, or Confirm) that
        should sit on the pointer. If that covers the relief circle, the
        card steps aside. With no pointer (the harness), the card sits just
        to the right of the circle and ``hotspot`` is ignored.
        """
        import math
        w, h = self._canvas_px()
        res = self.fsm.preview
        db = res.dogbone if res is not None else None
        if db is None:
            return DOCK_MARGIN, DOCK_MARGIN
        cx, cy = self.transform.to_screen(db.center)
        r_px = db.r * self.transform.scale
        if self._dock_anchor is None:
            x = cx + r_px + DOCK_GAP
            y = cy - height / 2
            if x + width > w - DOCK_MARGIN:
                x = cx - r_px - DOCK_GAP - width
            return self._clamp_dock(x, y, width, height)
        ax, ay = self._dock_anchor
        hx, hy = hotspot
        pref = self._clamp_dock(ax - hx, ay - hy, width, height)
        if not self._covers_circle(*pref, width, height, cx, cy, r_px):
            return pref
        candidates = (
            (cx + r_px + DOCK_GAP, ay - hy),
            (cx - r_px - DOCK_GAP - width, ay - hy),
            (ax - hx, cy + r_px + DOCK_GAP),
            (ax - hx, cy - r_px - DOCK_GAP - height),
        )
        best: tuple[int, int] | None = None
        best_d = 0.0
        for raw_x, raw_y in candidates:
            pos = self._clamp_dock(raw_x, raw_y, width, height)
            if self._covers_circle(*pos, width, height, cx, cy, r_px):
                continue
            d = math.hypot((pos[0] + hx) - ax, (pos[1] + hy) - ay)
            if best is None or d < best_d:
                best, best_d = pos, d
        return best if best is not None else pref

    def _ensure_dock(self) -> None:
        """One canvas for the chord card and for Confirm.

        Placed on the viewer canvas, not inserted as a canvas item: pan
        moves every canvas item, and a full redraw deletes them. The widget
        background matches the drawing so the square corners outside the
        rounded shape disappear.
        """
        if self._dock is not None:
            return
        dock = tk.Canvas(
            self.viewer.canvas, highlightthickness=0, bd=0,
            bg=THEME["canvas_bg"], cursor="hand2")
        dock.bind("<Button-1>", self._on_dock_click)
        dock.bind("<Motion>", self._on_dock_motion)
        dock.bind("<Leave>", self._on_dock_leave)
        self._dock = dock

    def _place_dock(self, width: int, height: int,
                    hotspot: tuple[float, float]) -> None:
        """Put ``hotspot`` (widget coords) on the pointer and pin that spot.

        Confirm reuses the pin, so its center lands where Delete was.
        """
        assert self._dock is not None
        if self._dock_anchor is None:
            if self._dock_pinned is None:
                self._dock_pinned = self._dock_origin(width, height)
            x, y = self._clamp_dock(*self._dock_pinned, width, height)
        else:
            if self._button_at is None:
                top = self._dock_origin(width, height, hotspot)
                self._dock_pinned = top
                self._button_at = (top[0] + hotspot[0], top[1] + hotspot[1])
            x, y = self._clamp_dock(
                self._button_at[0] - hotspot[0],
                self._button_at[1] - hotspot[1],
                width, height)
        if self._same_place(x, y, width, height):
            return
        self._dock.configure(width=width, height=height)
        self._dock.place(x=x, y=y, width=width, height=height)
        self._dock.update_idletasks()
        self._install_click_through()

    def _dock_font(self):
        import tkinter.font as tkfont
        assert self._dock is not None
        return tkfont.Font(root=self._dock, font=theme_font(9))

    @staticmethod
    def _rounded_points(x1: float, y1: float, x2: float, y2: float,
                        r: float, steps: int = 8) -> list[float]:
        """Corner samples in canvas space (y grows downward)."""
        import math
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

    def _round_rect(self, x1: float, y1: float, x2: float, y2: float,
                    r: float, **kwargs) -> int:
        assert self._dock is not None
        return self._dock.create_polygon(
            self._rounded_points(x1, y1, x2, y2, r),
            smooth=False, **kwargs)

    def _hit_at(self, x: float, y: float) -> str | None:
        for name, (x1, y1, x2, y2) in self._hits.items():
            if x1 <= x <= x2 and y1 <= y <= y2:
                return name
        return None

    def _same_place(self, x: int, y: int, width: int, height: int) -> bool:
        dock = self._dock
        if dock is None:
            return False
        try:
            info = dock.place_info()
        except tk.TclError:
            return False
        if not info:
            return False
        return (int(float(info["x"])) == int(x)
                and int(float(info["y"])) == int(y)
                and int(float(info["width"])) == int(width)
                and int(float(info["height"])) == int(height))

    def _install_click_through(self) -> None:
        """Send clicks to the canvas, which already has correct coordinates.

        A card window placed under the pointer does not receive a click
        until the mouse moves. Returning HTTRANSPARENT makes Windows
        deliver that click to the canvas instead.
        """
        dock = self._dock
        if dock is None or self._hit_proc is not None or sys.platform != "win32":
            return
        try:
            hwnd = int(dock.winfo_id())
        except (tk.TclError, ValueError):
            return
        if not hwnd:
            return
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        LRESULT = ctypes.c_ssize_t
        user32.GetWindowLongPtrW.restype = ctypes.c_void_p
        user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.SetWindowLongPtrW.restype = ctypes.c_void_p
        user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
        user32.CallWindowProcW.restype = LRESULT
        user32.CallWindowProcW.argtypes = [
            ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
        ]
        old = user32.GetWindowLongPtrW(hwnd, -4)
        if not old:
            return

        @ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        def _proc(h, msg, wparam, lparam):
            if msg == 0x0084:  # WM_NCHITTEST
                return -1      # HTTRANSPARENT
            return user32.CallWindowProcW(old, h, msg, wparam, lparam)

        user32.SetWindowLongPtrW(hwnd, -4, ctypes.cast(_proc, ctypes.c_void_p))
        self._hit_proc = _proc
        self._hit_old = old
        self._hit_hwnd = hwnd

    def _remove_click_through(self) -> None:
        if self._hit_proc is None or self._hit_hwnd is None or self._hit_old is None:
            self._hit_proc = None
            return
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.SetWindowLongPtrW.restype = ctypes.c_void_p
            user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
            user32.SetWindowLongPtrW(self._hit_hwnd, -4, self._hit_old)
        except (OSError, AttributeError):
            pass
        self._hit_proc = None
        self._hit_old = None
        self._hit_hwnd = None

    def _local_on_dock(self, ev) -> tuple[float, float] | None:
        """Dock-local point from the click's screen position.

        Tk's event x/y stay stale until the mouse moves after the card
        is placed. The screen position does not.
        """
        x_root = getattr(ev, "x_root", None)
        y_root = getattr(ev, "y_root", None)
        dock = self._dock
        if x_root is None or y_root is None or dock is None:
            return None
        try:
            lx = x_root - dock.winfo_rootx()
            ly = y_root - dock.winfo_rooty()
            w = int(dock.winfo_width())
            h = int(dock.winfo_height())
        except tk.TclError:
            return None
        if 0 <= lx <= w and 0 <= ly <= h:
            return (lx, ly)
        return None

    def _local_from_canvas(self, ev) -> tuple[float, float] | None:
        dock = self._dock
        if dock is None:
            return None
        try:
            info = dock.place_info()
        except tk.TclError:
            return None
        if not info:
            return None
        dx = float(info["x"])
        dy = float(info["y"])
        dw = float(info["width"])
        dh = float(info["height"])
        if dx <= ev.x <= dx + dw and dy <= ev.y <= dy + dh:
            return (ev.x - dx, ev.y - dy)
        return None

    def _relay_dock_click(self, ev) -> bool:
        """A canvas click whose point lies on the card."""
        if self._dock is None or not self._hits:
            return False
        local = self._local_on_dock(ev)
        if local is None:
            local = self._local_from_canvas(ev)
        if local is None:
            return False
        self.viewer._pan_from = None
        self._activate(self._hit_at(*local))
        return True

    def _on_dock_click(self, ev) -> None:
        local = self._local_on_dock(ev)
        if local is None:
            local = (ev.x, ev.y)
        self._activate(self._hit_at(*local))

    def _activate(self, name: str | None) -> None:
        if name == "delete":
            self._choose_chord("delete")
        elif name == "keep":
            self._choose_chord("keep")
        elif name == "confirm":
            self._on_dock_confirm()

    def _on_canvas_motion(self, ev) -> None:
        """Hover for the card. Clicks pass through, so motion does too."""
        local = self._local_from_canvas(ev) if self._dock is not None else None
        if local is None:
            self._on_dock_leave()
            try:
                if self.viewer.canvas.cget("cursor") == "hand2":
                    self.viewer.canvas.configure(cursor="")
            except tk.TclError:
                pass
            return
        try:
            self.viewer.canvas.configure(cursor="hand2")
        except tk.TclError:
            pass
        self._on_dock_motion(type("_Ev", (), {"x": local[0], "y": local[1]})())

    def _pointer_on_dock(self) -> tuple[float, float] | None:
        """Dock-local pointer, or None when the card is not on screen."""
        dock = self._dock
        if dock is None:
            return None
        try:
            if not dock.winfo_viewable():
                return None
            return (
                float(dock.winfo_pointerx() - dock.winfo_rootx()),
                float(dock.winfo_pointery() - dock.winfo_rooty()),
            )
        except tk.TclError:
            return None

    def _hover_under_pointer(self) -> None:
        """Paint the lighter button without waiting for a motion event.

        The card is placed under the pointer that picked the ghost. That
        pointer has not moved, so ``<Motion>`` has not run yet.
        """
        local = self._pointer_on_dock()
        if local is None:
            return
        self._on_dock_motion(type("_Ev", (), {"x": local[0], "y": local[1]})())

    def _on_dock_motion(self, ev) -> None:
        if self._dock is None:
            return
        name = self._hit_at(ev.x, ev.y)
        for key in self._hits:
            fill = THEME["dock_btn_hover"] if key == name else THEME["dock_btn"]
            self._dock.itemconfig(key, fill=fill)

    def _on_dock_leave(self, _ev=None) -> None:
        if self._dock is None:
            return
        for key in self._hits:
            self._dock.itemconfig(key, fill=THEME["dock_btn"])

    def _show_flag_contents(self, flag: Flag) -> None:
        assert self._dock is not None
        kind = msg.CHORD_CARD_KIND.get(self._kind_of(flag.eid), "entity")
        template = msg.FLAG_CARD_BODY.get(flag.reason, "This {kind} needs a decision.")
        line = template.format(kind=kind)
        n, m = self._ask_progress(flag.eid)
        count = msg.FLAG_CARD_COUNT.format(n=n, m=m)
        font = self._dock_font()
        line_h = font.metrics("linespace") + 2
        count_w = font.measure(count)
        text_w = font.measure(line) + 12 + count_w
        min_btn = max(font.measure(msg.CHORD_CARD_DELETE),
                      font.measure(msg.CHORD_CARD_KEEP)) + 22
        inner = max(text_w, min_btn * 2 + DOCK_BTN_GAP)
        btn_w = (inner - DOCK_BTN_GAP) / 2
        width = int(DOCK_PAD * 2 + inner)
        text_top = DOCK_PAD
        btn_top = text_top + line_h + 8
        height = int(btn_top + DOCK_BTN_H + DOCK_PAD)
        delete_center = (DOCK_PAD + btn_w / 2, btn_top + DOCK_BTN_H / 2)
        self._place_dock(width, height, delete_center)
        self._dock.delete("all")
        self._round_rect(
            1, 1, width - 2, height - 2, DOCK_RADIUS,
            fill=THEME["dock_bg"], outline=THEME["dock_edge"], width=1,
            tags=("card",))
        self._dock.create_text(
            DOCK_PAD, text_top, text=line, anchor="nw",
            fill=THEME["dock_text"], font=theme_font(9), tags=("body",))
        self._dock.create_text(
            width - DOCK_PAD, text_top, text=count, anchor="ne",
            fill=THEME["dock_muted"], font=theme_font(9), tags=("count",))
        labels = (("delete", msg.CHORD_CARD_DELETE, DOCK_PAD),
                  ("keep", msg.CHORD_CARD_KEEP, DOCK_PAD + btn_w + DOCK_BTN_GAP))
        self._hits = {}
        for name, label, bx in labels:
            x2 = bx + btn_w
            y2 = btn_top + DOCK_BTN_H
            self._round_rect(
                bx, btn_top, x2, y2, DOCK_BTN_H / 2,
                fill=THEME["dock_btn"], outline="", tags=(name,))
            self._dock.create_text(
                (bx + x2) / 2, (btn_top + y2) / 2, text=label,
                fill=THEME["dock_text"], font=theme_font(9),
                tags=(f"{name}-label",))
            self._hits[name] = (bx, btn_top, x2, y2)
        self._dock_mode = "flag"
        self._hover_under_pointer()

    def _show_confirm_contents(self) -> None:
        """A single rounded Confirm button. No message line above it."""
        assert self._dock is not None
        font = self._dock_font()
        width = int(font.measure(msg.BTN_CONFIRM) + 36)
        height = DOCK_BTN_H + 4
        self._place_dock(width, height, (width / 2, height / 2))
        self._dock.delete("all")
        self._round_rect(
            1, 1, width - 2, height - 2, height / 2,
            fill=THEME["dock_btn"], outline=THEME["dock_edge"], width=1,
            tags=("confirm",))
        self._dock.create_text(
            width / 2, height / 2, text=msg.BTN_CONFIRM,
            fill=THEME["dock_text"], font=theme_font(9),
            tags=("confirm-label",))
        self._hits = {"confirm": (0, 0, width, height)}
        self._dock_mode = "confirm"
        self._hover_under_pointer()

    def _present_dock(self) -> None:
        """Show the flag card, or a Confirm button alone beside the circle."""
        res = self.fsm.preview
        if res is None or res.dogbone is None:
            return
        self._ensure_dock()
        flag = self._pending_flag()
        if flag is not None:
            self._show_flag_contents(flag)
        else:
            self._confirm_ready_at = 0.0
            self._show_confirm_contents()

    def _on_dock_confirm(self) -> None:
        """Confirm from the card. A click counts as soon as the button is up."""
        self.confirm_click()

    def _choose_chord(self, decision: str) -> None:
        """Record one flag answer and update the dock in place.

        Does not rebuild the frame or call ``_sync_view``: destroying the
        button between the two halves of a double-click would drop the
        second click onto the canvas.
        """
        flag = self._pending_flag()
        if flag is None or self._dock is None:
            return
        self.model.state.flag_decisions[flag.eid] = decision
        self.fsm.notify_flag_decision()
        if self.fsm.state != WorkflowState.SIDE_PICKED or self._dock is None:
            self._sync_view()
            return
        self._paint_side_picked()
        nxt = self._pending_flag()
        if nxt is not None:
            self._show_flag_contents(nxt)
        else:
            self._confirm_ready_at = 0.0
            self._show_confirm_contents()
        self._on_state_notify()

    def _ask_progress(self, eid: str) -> tuple[int, int]:
        """1-based place of this question among the ones asked this preview."""
        if self._ask_eids is None:
            res = self.fsm.preview
            flags = [] if res is None else [f for f in res.flags if f.decision is None]
            chords = [f.eid for f in flags if f.reason == "CHORD_CROSSER"]
            rest = [f.eid for f in flags if f.reason != "CHORD_CROSSER"]
            self._ask_eids = chords + rest
        eids = self._ask_eids
        if eid in eids:
            return eids.index(eid) + 1, len(eids)
        return 1, max(len(eids), 1)

    def _pending_flag(self) -> Flag | None:
        """Next unanswered flag. Chord-crossers come before the others."""
        res = self.fsm.preview
        if res is None:
            return None
        pending = [f for f in res.flags if f.decision is None]
        for f in pending:
            if f.reason == "CHORD_CROSSER":
                return f
        return pending[0] if pending else None

    def _pending_chord(self) -> Flag | None:
        res = self.fsm.preview
        if res is None:
            return None
        for f in res.flags:
            if f.reason == "CHORD_CROSSER" and f.decision is None:
                return f
        return None

    def _flash_promoted(self, seg: Seg,
                        color: str = HIGHLIGHT_COLOR) -> None:
        """Promoted-edge highlight (brief item 1; user round-6): the full
        run extent stays highlighted until the NEXT promotion replaces it
        — no timer. _clear_overlays wipes it on state changes
        (restart/confirm); the flash tag carries exactly one run at a
        time (delete-then-draw keeps ghosts and other overlays intact).
        Round-7: edge 2 renders red during the pick/ghost phase ("what am
        I about to cut"), returning to cyan once the preview lands."""
        c = self.viewer.canvas
        t = self.transform
        c.delete(self.FLASH_TAG)
        x1, y1 = t.to_screen(seg.a)
        x2, y2 = t.to_screen(seg.b)
        c.create_line(x1, y1, x2, y2, fill=color, width=2,
                      tags=(self.FLASH_TAG,))
        self._flash_items = []

    def _draw_ghosts(self) -> None:
        c = self.viewer.canvas
        t = self.transform
        for g in self.fsm.ghosts:
            cx, cy = t.to_screen(g.center)
            r_px = g.r * t.scale
            c.create_oval(cx - r_px, cy - r_px, cx + r_px, cy + r_px,
                           outline=GHOST_COLOR, dash=GHOST_DASH, width=1,
                           tags=(self.GHOST_TAG,))

    def _outline_entity(self, e: Entity, color: str, width: int,
                        tag: str) -> None:
        """Colored OVERLAY tracing the entity (underlying black items stay
        untouched; overlays are tagged and wiped on the next sync)."""
        c = self.viewer.canvas
        t = self.transform
        if isinstance(e, Seg):
            x1, y1 = t.to_screen(e.a)
            x2, y2 = t.to_screen(e.b)
            c.create_line(x1, y1, x2, y2, fill=color, width=width,
                          tags=(tag,))
        elif isinstance(e, Arc):
            pts: list[float] = []
            for p in flatten_arc(e):
                pts.extend(t.to_screen(p))
            if pts:
                c.create_line(*pts, fill=color, width=width, tags=(tag,))
        elif isinstance(e, Circ):
            x1, y1 = t.to_screen(Pt(e.center.x - e.r, e.center.y + e.r))
            x2, y2 = t.to_screen(Pt(e.center.x + e.r, e.center.y - e.r))
            c.create_oval(x1, y1, x2, y2, outline=color, width=width,
                          tags=(tag,))
        elif isinstance(e, PointEnt):
            sx, sy = t.to_screen(e.p)
            c.create_text(sx, sy, text="+", anchor="center", fill=color,
                          font=theme_font(12, "bold"), tags=(tag,))
        elif isinstance(e, TextEnt):
            sx, sy = t.to_screen(e.p)
            c.create_text(sx, sy, text=e.text or " ", anchor="w", fill=color,
                          font=theme_font(10, "bold"), tags=(tag,))

    def _draw_preview(self) -> None:
        """Deletion preview: thick red delete/trim, orange flagged, dashed
        candidate circle + solid ghost arc. Brief item 3; the summary line
        lives in ``summary_line``."""
        res = self.fsm.preview
        if res is None or not res.ok or res.dogbone is None:
            return
        c = self.viewer.canvas
        t = self.transform
        by_eid = {e.eid: e for e in self._primitives()}
        red_eids = set(res.deletions) | {tr.eid for tr in res.trims}
        flagged = {f.eid for f in res.flags}
        for eid in sorted(red_eids):
            e = by_eid.get(eid)
            if e is not None:
                self._outline_entity(e, DELETE_COLOR, DELETE_WIDTH,
                                     self.DELETE_TAG)
        for eid in sorted(flagged - red_eids):
            e = by_eid.get(eid)
            if e is not None:
                self._outline_entity(e, FLAG_COLOR, FLAG_WIDTH,
                                     self.FLAG_TAG)
        db = res.dogbone
        cx, cy = t.to_screen(db.center)
        r_px = db.r * t.scale
        c.create_oval(cx - r_px, cy - r_px, cx + r_px, cy + r_px,
                     outline=GHOST_COLOR, dash=GHOST_DASH, width=1,
                     tags=(self.GHOST_TAG,))
        pts: list[float] = []
        for p in flatten_arc(db.arc):
            pts.extend(t.to_screen(p))
        if pts:
            c.create_line(*pts, fill=GHOST_COLOR, width=2,
                          tags=(self.GHOST_TAG,))

    # ------------------------------------------------------------- autozoom
    def _auto_zoom(self) -> None:
        """Auto-zoom to the corner window: 4× tool DIAMETER (8r) across the
        smaller canvas dimension, centered on the apex (brief item 3)."""
        res = self.fsm.preview
        if res is None or res.dogbone is None:
            return
        db = res.dogbone
        if self._view_before_zoom is None:
            self._view_before_zoom = self.viewer.transform
        w, h = self._canvas_px()
        span = max(8.0 * db.r, 1e-3)
        scale = min(w, h) * 0.8 / span
        scale = min(MAX_SCALE, max(MIN_SCALE, scale))
        self.viewer.transform = ViewTransform(
            scale=scale,
            ox=w / 2.0 - db.apex.x * scale,
            oy=h / 2.0 + db.apex.y * scale,
        )
        self.viewer.redraw()

    # ---------------------------------------------------------------- sync
    def _sync_view(self) -> None:
        if self.fsm.state != WorkflowState.SIDE_PICKED:
            self._dock_anchor = None
            self._dock_pinned = None
            self._button_at = None
            self._ask_eids = None
        self._clear_overlays()
        st = self.fsm.state
        # persistent promoted-edge highlight (round-6): shows the most
        # recently promoted run until the next promotion / restart /
        # confirm wipes it. Edge 1's highlight persists into PICK_EDGE2
        # (re-clicking edge 1 keeps its highlight); edge 2's replaces it.
        if st == WorkflowState.PICK_EDGE2 and self.fsm.edge1_seg is not None:
            self._flash_promoted(self.fsm.edge1_seg)
        if st == WorkflowState.GHOSTS_VISIBLE:
            if self.fsm.edge2_seg is not None:
                # round-7/8: edge 2 reads GREEN until the preview/zoom
                # lands (user preference: not red)
                self._flash_promoted(self.fsm.edge2_seg, EDGE2_PICK_COLOR)
            elif self.fsm.edge1_seg is not None:
                self._flash_promoted(self.fsm.edge1_seg)
            if self.fsm.ghosts:
                self._draw_ghosts()
        if st == WorkflowState.SIDE_PICKED and self.fsm.preview is not None:
            # Zoom and draw before the card so the corner is on screen.
            self._auto_zoom()  # redraws the canvas — draw overlays after
            self._paint_side_picked()
            self._present_dock()
        if self._on_state is not None:
            self._on_state()  # App refreshes the bottom Confirm button
        if self._on_status is not None:
            text = self.fsm.status
            if self.fsm.inline:
                text = f"{text}    {self.fsm.inline}"
            self._on_status(text)

    def _paint_side_picked(self) -> None:
        """Deletion preview, promoted-edge flash, and the thick chord mark.

        Does not touch the dock frame. ``viewer.redraw`` wipes canvas items,
        so this is only safe when the geometry underneath is already drawn.
        """
        c = self.viewer.canvas
        for tag in (self.FLASH_TAG, self.GHOST_TAG, self.DELETE_TAG,
                    self.FLAG_TAG, self.CHORD_TAG):
            c.delete(tag)
        self._draw_preview()
        if self.fsm.edge2_seg is not None:
            self._flash_promoted(self.fsm.edge2_seg, HIGHLIGHT_COLOR)
        self._highlight_pending_chord()

    def _highlight_pending_chord(self) -> None:
        flag = self._pending_flag()
        if flag is None:
            return
        e = self.model.get(flag.eid)
        if e is None:
            return
        self._outline_entity(e, FLAG_COLOR, CHORD_FOCUS_WIDTH, self.CHORD_TAG)

    def _prompt_pending_flags(self) -> None:
        """First occurrence → prompt yes/no; decision persisted via
        model.flag_decisions[eid] (sticky; recompute honors existing
        decisions — no re-prompting; ADR-009).

        Headless harness entry. The interactive preview uses the side card
        for every pending flag and does not call this.
        """
        res = self.fsm.preview
        if res is None:
            return
        for f in res.flags:
            if f.decision is None:
                self.decide_flag(f, self._kind_of(f.eid))
        self.fsm.notify_flag_decision()  # re-place with decisions (ADR-016(k))

    def _kind_of(self, eid: str) -> str:
        e = self.model.get(eid)
        if isinstance(e, Seg):
            return "LINE"
        if isinstance(e, Arc):
            return "ARC"
        if isinstance(e, Circ):
            return "CIRCLE"
        if isinstance(e, PointEnt):
            return "POINT"
        if isinstance(e, TextEnt):
            return "MTEXT"
        return "ENTITY"

    # -------------------------------------------------------------- summary
    def summary_line(self) -> str:
        """The brief's EXACT summary text from the current preview."""
        res = self.fsm.preview
        if res is None:
            return ""
        del_lines = sum(1 for eid in res.deletions
                        if isinstance(self.model.get(eid), Seg))
        del_arcs = sum(1 for eid in res.deletions
                       if isinstance(self.model.get(eid), Arc))
        flag_circles = sum(1 for f in res.flags
                           if self._kind_of(f.eid) == "CIRCLE")
        flag_mtexts = sum(1 for f in res.flags
                          if self._kind_of(f.eid) == "MTEXT")
        line = msg.deletion_summary(del_lines, del_arcs, len(res.trims),
                                    flag_circles, flag_mtexts)
        extra = res.refusals + res.warnings
        if extra:
            line += msg.DASH + msg.reasons_text(extra)
        return line