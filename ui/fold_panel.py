"""Fold selection panel + headless FSM (M5b brief owner file).

SPEC §4.5, §11.8.4; ADR-024(b). Thin tkinter shell ONLY (ADR-006): screen↔world
+ events → ``rules.folds.validate_fold_against_contours`` (warnings) +
``model.state.fold_eids`` mutation. No geometry is computed here.

Layout (mirrors the M3 workflow.py seam so headless tests drive the FSM
directly and the shell is a thin binding):

* ``FoldFSM`` — canvas-free core: (state, event) handlers over the fold
  designation surface. Holds the active mode, the pending box-select start
  point, and the badge count. No tkinter import.
* ``FoldPorts`` — the engine/model boundary (pick a straight LINE near a
  world point; validate a fold against contours; mutate fold_eids).
* ``FoldPanel`` — the tkinter shell: mode toggle button, pattern entry,
  badge label; binds canvas events (click / shift-click / drag / Esc) and
  converts them into FSM events. No geometry math (ADR-006).

Mode isolation is by binding REPLACEMENT: while fold mode is ON, the
fold panel's handlers REPLACE the canvas's B1/Button-3/Escape scripts
(prior scripts saved + restored on exit — Tk's unbind() would delete
every handler for a sequence, including the Viewer's pan and the corner
workflow's picks). In fold mode: L-click/box = designate, MIDDLE-drag =
pan, wheel = zoom. The corner workflow runs only when fold mode is OFF.

Auto-preselect (ISSUE-003 defaults): at load, straight LINEs whose layer
name case-insensitively contains any of ``bend | fold | centerline`` are
auto-designated. Fires ONCE per load (the App calls
``auto_preselect`` after ``set_model``); user changes after that are
authoritative (undo restores the pre-preselect empty set — preselect state
IS undoable state; the "once per load" rule means no REPEATED auto-firing
on undo, not that preselect is exempt from snapshots). Pattern list
editable (GUI field, persisted per session in-memory only).
"""
from __future__ import annotations

import math
import tkinter as tk
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Protocol

from geometry.entities import Entity, PassThrough, Pt, Seg
from geometry.tolerances import EPS_COINCIDE
from rules.folds import validate_fold_against_contours
import ui.messages as msg

# ISSUE-003 defaults: case-insensitive contains any of these.
DEFAULT_FOLD_PATTERNS: tuple[str, ...] = ("bend", "fold", "centerline")

# CONTRACTS §3 note / SPEC §11.8.4: drag >= 5 px = box select; below = click.
BOX_SELECT_PX: float = 5.0


class FoldMode(Enum):
    """The fold panel's active mode (mode isolation: corner workflow runs
    only when this is OFF; fold designation runs only when this is ON)."""
    OFF = auto()
    ON = auto()


@dataclass
class FoldFSM:
    """Canvas-free core: (state, event) → new state. Handlers: enter /
    exit / click_world / box_select / toggle_eid / auto_preselect. No
    tkinter anywhere in this class's path — headless unit-tested directly.
    """
    ports: "FoldPorts"
    mode: FoldMode = FoldMode.OFF
    fold_eids: set[str] = field(default_factory=set)
    straight_count: int = 0
    badge_text: str = ""
    status: str = ""
    warnings: list[str] = field(default_factory=list)
    _box_start: tuple[float, float] | None = None  # world coords (pending drag)

    # ------------------------------------------------------------ helpers
    def _refresh_badge(self) -> None:
        self.badge_text = msg.FOLD_BADGE.format(
            n=len(self.fold_eids), m=self.straight_count)
        if self.mode == FoldMode.ON:
            self.status = self.badge_text + "  " + msg.FOLD_MODE_ENTER
        else:
            self.status = self.badge_text

    def _set_straight_count(self, primitives: list[Entity]) -> None:
        self.straight_count = sum(
            1 for e in primitives if isinstance(e, Seg)
        )

    def _toggle(self, eid: str, primitives: list[Entity]) -> None:
        """Toggle a fold eid in/out of the designation set; surface
        ``validate_fold_against_contours`` warnings for the newly
        designated fold (non-blocking; never auto-undesignates)."""
        if eid not in self.fold_eids:
            self.fold_eids.add(eid)
            fold = next(
                (e for e in primitives if isinstance(e, Seg) and e.eid == eid),
                None,
            )
            if fold is not None:
                self.warnings = validate_fold_against_contours(
                    fold, primitives, EPS_COINCIDE)
        else:
            self.fold_eids.discard(eid)
            self.warnings = []
        self.ports.set_fold_eids(set(self.fold_eids))
        self._refresh_badge()

    # ------------------------------------------------------------ events
    def enter(self) -> None:
        """Enter fold designation mode (mode toggle ON)."""
        self.mode = FoldMode.ON
        self._refresh_badge()

    def exit(self) -> None:
        """Exit fold mode cleanly (Esc / right-click / toggle OFF). No
        partial state survives (a pending box-select is cleared)."""
        self.mode = FoldMode.OFF
        self._box_start = None
        self._refresh_badge()

    def click_world(self, p_world: Pt, shift: bool = False) -> None:
        """A click (or shift-click — identical toggle semantics) in fold
        mode. Picks the nearest straight LINE; toggle its designation."""
        if self.mode != FoldMode.ON:
            return
        eid = self.ports.pick_fold_line(p_world)
        if eid is None:
            return
        self._toggle(eid, self.ports.primitives)
        # shift is identical to plain click (brief §1: "shift-click toggles
        # too, identical semantics, both directions") — no separate path.

    def box_select(self, p_lo: Pt, p_hi: Pt, shift: bool = False) -> None:
        """A drag >= BOX_SELECT_PX in fold mode. Toggles every straight
        LINE whose geometry intersects the world-space box. Shift is
        identical (brief §1)."""
        if self.mode != FoldMode.ON:
            return
        lo_x, lo_y = min(p_lo.x, p_hi.x), min(p_lo.y, p_hi.y)
        hi_x, hi_y = max(p_lo.x, p_hi.x), max(p_lo.y, p_hi.y)
        for e in self.ports.primitives:
            if not isinstance(e, Seg):
                continue
            ex_lo = min(e.a.x, e.b.x)
            ex_hi = max(e.a.x, e.b.x)
            ey_lo = min(e.a.y, e.b.y)
            ey_hi = max(e.a.y, e.b.y)
            if ex_lo <= hi_x and ex_hi >= lo_x and ey_lo <= hi_y and ey_hi >= lo_y:
                self._toggle(e.eid, self.ports.primitives)
        self._refresh_badge()

    def auto_preselect(self, primitives: list[Entity],
                       layer_of: dict[str, str],
                       patterns: tuple[str, ...] = DEFAULT_FOLD_PATTERNS) -> None:
        """Fires ONCE per load: straight LINEs whose layer name
        case-insensitively contains any pattern are auto-designated.
        User changes after this are authoritative."""
        self._set_straight_count(primitives)
        pats = [p.strip().lower() for p in patterns if p.strip()]
        for e in primitives:
            if not isinstance(e, Seg):
                continue
            layer = (layer_of.get(e.eid) or "").lower()
            if any(p in layer for p in pats):
                self.fold_eids.add(e.eid)
        self.ports.set_fold_eids(set(self.fold_eids))
        self._refresh_badge()

    def set_primitives(self, primitives: list[Entity]) -> None:
        """Refresh the straight-line count (badge denominator) on a model
        change (load / undo / restore). Does NOT re-fire auto-preselect."""
        self._set_straight_count(primitives)
        # drop any fold_eids no longer present (undo past a pre-pick, etc.)
        present = {e.eid for e in primitives if isinstance(e, Seg)}
        self.fold_eids &= present
        self.ports.set_fold_eids(set(self.fold_eids))
        self._refresh_badge()


class FoldPorts(Protocol):
    """The engine/model boundary the FSM drives (all headless-testable)."""

    @property
    def primitives(self) -> list[Entity]: ...
    def pick_fold_line(self, p_world: Pt) -> str | None: ...
    def set_fold_eids(self, eids: set[str]) -> None: ...


# ---------------------------------------------------------------------------
# Tkinter shell
# ---------------------------------------------------------------------------

from tkinter import ttk  # noqa: E402

from ui.theme import COLORS as THEME, font as theme_font  # noqa: E402
from ui.transform import ViewTransform  # noqa: E402


class FoldPanel(ttk.Frame):
    """Left-side panel: mode toggle, pattern entry, badge. Thin shell —
    binds canvas events in fold mode and converts them to FSM events.

    The panel does NOT own canvas bindings permanently; the App installs
    them via ``bind_canvas`` / ``unbind_canvas`` when the mode toggles so
    the corner workflow's bindings stay untouched while fold mode is OFF
    (mode isolation, brief §1)."""

    def __init__(self, master, viewer, model, on_status=None,
                 patterns: tuple[str, ...] = DEFAULT_FOLD_PATTERNS):
        super().__init__(master, style="TFrame", padding=(10, 10))
        self.viewer = viewer
        self.model = model  # may be None at construction; set via on_load
        self._on_status = on_status
        self._patterns = list(patterns)
        self.fsm = FoldFSM(ports=self)
        self._bound = False
        self._box_start_screen: tuple[float, float] | None = None
        # Tk's unbind(seq) deletes EVERY handler for a sequence, not just
        # ours — the scripts present before fold mode are saved here and
        # restored verbatim on exit (the only safe teardown).
        self._saved_bindings: dict[str, str] = {}
        self._pan_from: tuple[float, float] | None = None  # middle-drag pan

        ttk.Label(self, text="Folds", style="TLabel",
                  font=theme_font(10, "bold")).pack(anchor="w", pady=(0, 6))

        self.mode_btn = ttk.Button(self, text=msg.FOLD_MODE_TOGGLE_ON,
                                   style="TButton",
                                   command=self.toggle_mode)
        self.mode_btn.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(self, text=msg.FOLD_PATTERN_LABEL,
                  style="TLabel").pack(anchor="w")
        self.pattern_var = tk.StringVar(value=", ".join(self._patterns))
        pattern_entry = ttk.Entry(self, textvariable=self.pattern_var,
                                  width=22, font=theme_font(9))
        pattern_entry.pack(fill=tk.X, pady=(2, 0))
        pattern_entry.bind("<FocusOut>", self._patterns_edited)
        pattern_entry.bind("<Return>", self._patterns_edited)

        self.badge_var = tk.StringVar(value="")
        self.badge_label = ttk.Label(self, textvariable=self.badge_var,
                                     style="StatusBold.TLabel")
        self.badge_label.pack(anchor="w", pady=(8, 0))
        self._refresh_badge()

    # ------------------------------------------------------------- ports
    @property
    def primitives(self) -> list[Entity]:
        if self.model is None:
            return []
        return self.model.state.primitives

    def pick_fold_line(self, p_world: Pt) -> str | None:
        """Pick the nearest straight LINE within a screen-pick radius
        (straight LINEs only — arcs/circles/points/text never designated,
        SPEC §4.5). No promotion (folds are individual lines)."""
        if self.model is None:
            return None
        from rules.filters import eps_pick_from_scale
        # ergonomic pick radius (matches the corner workflow's UI_PICK_PX)
        eps_pick = eps_pick_from_scale(self.viewer.transform.scale, pick_px=10.0)
        best: tuple[float, str] | None = None
        for e in self.model.state.primitives:
            if not isinstance(e, Seg):
                continue
            from geometry import geomops as go
            d = go.point_seg_dist(p_world, e.a, e.b)
            if d <= eps_pick and (best is None or d < best[0]):
                best = (d, e.eid)
        return best[1] if best is not None else None

    def set_fold_eids(self, eids: set[str]) -> None:
        if self.model is not None:
            self.model.state.fold_eids = set(eids)
        self.viewer.fold_eids = set(eids)
        self.viewer.redraw()

    # --------------------------------------------------------- mode toggle
    def toggle_mode(self) -> None:
        if self.model is None:
            return
        if self.fsm.mode == FoldMode.OFF:
            self.fsm.set_primitives(self.model.state.primitives)
            self.fsm.enter()
            self.bind_canvas()
        else:
            self.fsm.exit()
            self.unbind_canvas()
        self._refresh_badge()

    def _refresh_badge(self) -> None:
        self.badge_var.set(self.fsm.badge_text)
        self.mode_btn.config(
            text=(msg.FOLD_MODE_TOGGLE_OFF if self.fsm.mode == FoldMode.ON
                  else msg.FOLD_MODE_TOGGLE_ON))
        if self._on_status is not None:
            self._on_status(self.fsm.status)

    # ------------------------------------------------------- canvas events
    def bind_canvas(self) -> None:
        """Install fold-mode canvas bindings. Mode isolation is by
        REPLACEMENT (not add=True): Tk runs every add=True handler, so an
        added fold handler would let the corner workflow pick edges
        while the user designates folds. Fold mode replaces the B1 /
        Button-3 / Escape scripts (saved for verbatim restore on exit);
        wheel-zoom stays (untouched binding) and middle-drag pans."""
        if self._bound:
            return
        c = self.viewer.canvas
        handlers = self._fold_handlers()
        for seq in ("<ButtonPress-2>", "<B2-Motion>", "<ButtonRelease-2>"):
            handlers[seq] = self._pan_handler(seq)
        for seq, handler in handlers.items():
            self._saved_bindings[seq] = c.bind(seq)
            c.bind(seq, handler)  # replace: corner workflow is suspended
        self._bound = True

    def _pan_handler(self, seq: str):
        return {
            "<ButtonPress-2>": self._on_pan_press,
            "<B2-Motion>": self._on_pan_drag,
            "<ButtonRelease-2>": self._on_pan_release,
        }[seq]

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

    def unbind_canvas(self) -> None:
        if not self._bound:
            return
        c = self.viewer.canvas
        # restore the pre-fold-mode script for each sequence (never
        # unbind(): that would kill the Viewer's pan and the corner
        # workflow's handlers too)
        for seq, script in self._saved_bindings.items():
            c.bind(seq, script)
        self._saved_bindings.clear()
        self._bound = False
        self._box_start_screen = None
        self._pan_from = None

    def _fold_handlers(self) -> dict[str, object]:
        return {
            "<ButtonPress-1>": self._on_press,
            "<B1-Motion>": self._on_drag,
            "<ButtonRelease-1>": self._on_release,
            "<Shift-ButtonPress-1>": self._on_press,
            "<Shift-B1-Motion>": self._on_drag,
            "<Shift-ButtonRelease-1>": self._on_release,
            "<Button-3>": self._on_right,
            "<Escape>": self._on_esc,
        }

    def _on_press(self, ev) -> None:
        # record the screen start (box-select threshold check on release)
        self._box_start_screen = (ev.x, ev.y)

    def _on_drag(self, _ev) -> None:
        pass  # the box resolves on release (V1: no live box preview)

    def _on_release(self, ev) -> None:
        if self._box_start_screen is None:
            return
        sx0, sy0 = self._box_start_screen
        self._box_start_screen = None
        dx = ev.x - sx0
        dy = ev.y - sy0
        moved = math.hypot(dx, dy)
        shift = bool(ev.state & 0x1)  # Shift modifier bit
        t = self.viewer.transform
        if moved >= BOX_SELECT_PX:
            p_lo = t.to_world(sx0, sy0)
            p_hi = t.to_world(ev.x, ev.y)
            self.fsm.box_select(p_lo, p_hi, shift=shift)
        else:
            w = t.to_world(ev.x, ev.y)
            self.fsm.click_world(w, shift=shift)
        self._refresh_badge()

    def _on_right(self, _ev) -> None:
        """Right-click = exit fold mode cleanly (no partial state)."""
        self.fsm.exit()
        self.unbind_canvas()
        self._refresh_badge()

    def _on_esc(self, _ev) -> None:
        self.fsm.exit()
        self.unbind_canvas()
        self._refresh_badge()

    # ----------------------------------------------------------- patterns
    def _patterns_edited(self, _ev) -> None:
        text = self.pattern_var.get()
        self._patterns = [p.strip() for p in text.split(",") if p.strip()]

    def patterns(self) -> tuple[str, ...]:
        return tuple(self._patterns)

    # ---------------------------------------------------- load integration
    def on_load(self, layer_of: dict[str, str]) -> None:
        """The App calls this after set_model on every Open. Fires
        auto-preselect ONCE per load (user changes after that are
        authoritative)."""
        if self.model is None:
            return
        self.fsm.fold_eids = set()
        self.fsm.auto_preselect(
            self.model.state.primitives, layer_of, self.patterns())
        self._refresh_badge()

    def on_model_change(self) -> None:
        """Refresh the badge on undo/restore (fold_eids travel in
        snapshots — restore may have changed them)."""
        if self.model is None:
            return
        self.fsm.fold_eids = set(self.model.state.fold_eids)
        self.fsm.set_primitives(self.model.state.primitives)
        self._refresh_badge()