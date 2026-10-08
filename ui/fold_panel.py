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
* ``FoldPanel`` — the tkinter shell: mode toggle button, keyword entry,
  one checkbox per layer that has straight lines, badge label; binds
  canvas events (left-click / left-drag pan / right-drag box-select /
  Esc) and converts them into FSM events. No geometry math (ADR-006).

Mode isolation is by binding REPLACEMENT: while fold mode is ON, the
fold panel's handlers REPLACE the canvas's B1/Button-3/Escape scripts
(prior scripts saved + restored on exit — Tk's unbind() would delete
every handler for a sequence, including the Viewer's pan and the corner
workflow's picks). In fold mode: a left click toggles one line, a left
drag pans, a right drag box-selects, wheel zooms. Esc exits. The corner
workflow runs only when fold mode is OFF.

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
from ui.collapsible import CollapsibleSection
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

from ui.theme import COLORS, font as theme_font  # noqa: E402
from ui.transform import ViewTransform  # noqa: E402


class FoldPanel(ttk.Frame):
    """Left-side panel: mode toggle, keyword entry, layer checks, badge.
    Thin shell — binds canvas events in fold mode and converts them to FSM events.

    The panel does NOT own canvas bindings permanently; the App installs
    them via ``bind_canvas`` / ``unbind_canvas`` when the mode toggles so
    the corner workflow's bindings stay untouched while fold mode is OFF
    (mode isolation, brief §1)."""

    def __init__(self, master, viewer, model, on_status=None,
                 patterns: tuple[str, ...] = DEFAULT_FOLD_PATTERNS):
        super().__init__(master, style="TFrame")
        self.viewer = viewer
        self.model = model  # may be None at construction; set via on_load
        self._on_status = on_status
        self._patterns = list(patterns)
        self.fsm = FoldFSM(ports=self)
        self.stack = None  # SnapshotStack, set when the workflow is built
        self._bound = False
        self._box_start_screen: tuple[float, float] | None = None
        # Tk's unbind(seq) deletes EVERY handler for a sequence, not just
        # ours — the scripts present before fold mode are saved here and
        # restored verbatim on exit (the only safe teardown).
        self._saved_bindings: dict[str, str] = {}
        self._left_start: tuple[float, float] | None = None
        self._left_panned = False
        self._pan_from: tuple[float, float] | None = None
        self._box_item: int | None = None
        self._hint: tk.Label | None = None

        self.section = CollapsibleSection(self, msg.SECTION_FOLDS)
        self.section.pack(fill=tk.X, pady=(0, 6))
        body = self.section.body

        self.mode_btn = ttk.Button(body, text=msg.FOLD_MODE_TOGGLE_ON,
                                   style="FoldMode.TButton",
                                   command=self.toggle_mode)
        self.mode_btn.pack(fill=tk.X, pady=(0, 8))

        self.pattern_label = ttk.Label(body, text=msg.FOLD_PATTERN_LABEL,
                                       style="TLabel")
        self.pattern_label.pack(anchor="w")
        self.pattern_hint = tk.Label(
            body, text=msg.FOLD_PATTERN_HINT,
            bg=COLORS["bg"], fg=COLORS["fg_muted"],
            font=theme_font(9), wraplength=248, justify="left", anchor="w",
        )
        self.pattern_hint.pack(anchor="w", fill=tk.X, pady=(2, 0))
        self.pattern_var = tk.StringVar(
            master=self, value=", ".join(self._patterns))
        self.pattern_entry = ttk.Entry(body, textvariable=self.pattern_var,
                                       width=22, font=theme_font(9))
        self.pattern_entry.pack(fill=tk.X, pady=(2, 0))
        self.pattern_entry.bind("<FocusOut>", self._patterns_edited)
        self.pattern_entry.bind("<Return>", self._patterns_edited)

        self._layer_of: dict[str, str] = {}
        self._layer_vars: dict[str, tk.BooleanVar] = {}
        self._layer_buttons: dict[str, ttk.Checkbutton] = {}
        self._layer_key: list[tuple[str, int]] | None = None
        self._layer_sync = False
        self._layer_rule = ttk.Separator(body, orient="horizontal")
        self.layer_heading = tk.Label(
            body, text=msg.FOLD_LAYER_HEADING,
            bg=COLORS["bg"], fg=COLORS["fg"],
            font=theme_font(9), anchor="w",
        )
        self.layer_hint = tk.Label(
            body, text=msg.FOLD_LAYER_HINT,
            bg=COLORS["bg"], fg=COLORS["fg_muted"],
            font=theme_font(9), wraplength=248, justify="left", anchor="w",
        )
        self._layer_rows = ttk.Frame(body, style="TFrame")
        self._layer_rows.pack(fill=tk.X, pady=(2, 0))

        self.badge_var = tk.StringVar(master=self, value="")
        self.badge_label = ttk.Label(body, textvariable=self.badge_var,
                                     style="TLabel")
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
        summary = f"{len(self.fsm.fold_eids)}/{self.fsm.straight_count}"
        if self.fsm.mode == FoldMode.ON:
            summary += f"  ·  {msg.SECTION_MODE_ON}"
        self.section.set_summary(summary)
        self.mode_btn.config(
            text=(msg.FOLD_MODE_TOGGLE_OFF if self.fsm.mode == FoldMode.ON
                  else msg.FOLD_MODE_TOGGLE_ON))
        if self._on_status is not None:
            self._on_status(self.fsm.status)
        self._sync_layer_checks()

    # ------------------------------------------------------- canvas events
    def bind_canvas(self) -> None:
        """Install fold-mode canvas bindings. Mode isolation is by
        REPLACEMENT (not add=True): Tk runs every add=True handler, so an
        added fold handler would let the corner workflow pick edges
        while the user designates folds. Fold mode replaces the B1 /
        Button-3 / Escape scripts (saved for verbatim restore on exit).
        A left click toggles a line, a left drag pans, a right drag
        box-selects. Wheel-zoom stays."""
        if self._bound:
            return
        c = self.viewer.canvas
        for seq, handler in self._fold_handlers().items():
            self._saved_bindings[seq] = c.bind(seq)
            c.bind(seq, handler)  # replace: corner workflow is suspended
        self._show_box_hint()
        self._bound = True

    def _show_box_hint(self) -> None:
        """On-canvas hint while fold mode is on. A placed widget, not a
        canvas item: canvas.move("all") would carry an item away on pan."""
        c = self.viewer.canvas
        if self._hint is None:
            self._hint = tk.Label(
                c, text=msg.FOLD_BOX_HINT,
                bg=COLORS["bg_elevated"], fg=COLORS["fg"],
                font=theme_font(9), padx=8, pady=2,
            )
        self._hint.place(relx=0.5, rely=0, anchor="n")

    def _hide_box_hint(self) -> None:
        if self._hint is not None:
            self._hint.place_forget()

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
        self._left_start = None
        self._left_panned = False
        self._pan_from = None
        self._clear_box_preview()
        self._hide_box_hint()

    def _fold_handlers(self) -> dict[str, object]:
        return {
            "<ButtonPress-1>": self._on_left_press,
            "<B1-Motion>": self._on_left_drag,
            "<ButtonRelease-1>": self._on_left_release,
            "<Shift-ButtonPress-1>": self._on_left_press,
            "<Shift-B1-Motion>": self._on_left_drag,
            "<Shift-ButtonRelease-1>": self._on_left_release,
            "<Button-3>": self._on_right_press,
            "<B3-Motion>": self._on_right_drag,
            "<ButtonRelease-3>": self._on_right_release,
            "<Shift-Button-3>": self._on_right_press,
            "<Shift-B3-Motion>": self._on_right_drag,
            "<Shift-ButtonRelease-3>": self._on_right_release,
            "<Escape>": self._on_esc,
        }

    def _on_left_press(self, ev) -> None:
        self._left_start = (ev.x, ev.y)
        self._left_panned = False
        self._pan_from = None

    def _on_left_drag(self, ev) -> None:
        """Pan once the pointer has moved BOX_SELECT_PX. A shorter move
        stays a click and does not shift the drawing."""
        if self._left_start is None:
            return
        if not self._left_panned:
            sx, sy = self._left_start
            if math.hypot(ev.x - sx, ev.y - sy) < BOX_SELECT_PX:
                return
            self._left_panned = True
            self._pan_from = self._left_start
        if self._pan_from is None:
            return
        dx, dy = ev.x - self._pan_from[0], ev.y - self._pan_from[1]
        if dx == 0 and dy == 0:
            return
        self._pan_from = (ev.x, ev.y)
        self.viewer.canvas.move("all", dx, dy)
        self.viewer.transform = self.viewer.transform.panned_by(dx, dy)

    def _on_left_release(self, ev) -> None:
        if self._left_start is None:
            return
        panned = self._left_panned
        self._left_start = None
        self._left_panned = False
        self._pan_from = None
        if panned:
            return
        before = self._fold_eids_before()
        self.fsm.click_world(
            self.viewer.transform.to_world(ev.x, ev.y),
            shift=bool(ev.state & 0x1))
        self._note_designation(before)

    def _on_right_press(self, ev) -> None:
        self._box_start_screen = (ev.x, ev.y)
        self._clear_box_preview()

    def _on_right_drag(self, ev) -> None:
        """Rubber-band the selection box in screen space. The designation
        still resolves on release."""
        if self._box_start_screen is None:
            return
        sx, sy = self._box_start_screen
        c = self.viewer.canvas
        if self._box_item is None:
            self._box_item = c.create_rectangle(
                sx, sy, ev.x, ev.y,
                outline=COLORS["fold_designated"],
                fill=COLORS["fold_designated"],
                stipple="gray25",
                dash=(3, 3),
                width=1,
            )
        else:
            c.coords(self._box_item, sx, sy, ev.x, ev.y)

    def _clear_box_preview(self) -> None:
        if self._box_item is None:
            return
        self.viewer.canvas.delete(self._box_item)
        self._box_item = None

    def _on_right_release(self, ev) -> None:
        """A right drag of at least BOX_SELECT_PX toggles every straight
        line in the box. A shorter right click does not toggle and does
        not leave fold mode."""
        if self._box_start_screen is None:
            self._clear_box_preview()
            return
        sx0, sy0 = self._box_start_screen
        self._box_start_screen = None
        self._clear_box_preview()
        if math.hypot(ev.x - sx0, ev.y - sy0) < BOX_SELECT_PX:
            return
        before = self._fold_eids_before()
        t = self.viewer.transform
        self.fsm.box_select(
            t.to_world(sx0, sy0), t.to_world(ev.x, ev.y),
            shift=bool(ev.state & 0x1))
        self._note_designation(before)

    def _fold_eids_before(self) -> set[str]:
        if self.model is None:
            return set()
        return set(self.model.state.fold_eids)

    def _note_designation(self, before: set[str]) -> None:
        """A user designation is not its own undo step. If it changed the
        set, the redo branch (saved by a prior undo) is abandoned.
        on_model_change syncs folds without coming through here, so an
        undo/redo refresh does not clear the branch it just created."""
        if (self.stack is not None and self.model is not None
                and self.model.state.fold_eids != before):
            self.stack.discard_redo()
        self._refresh_badge()

    def _on_esc(self, _ev) -> str:
        self.fsm.exit()
        self.unbind_canvas()
        self._refresh_badge()
        return "break"

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
        self._layer_of = dict(layer_of)
        self.fsm.fold_eids = set()
        self.fsm.auto_preselect(
            self.model.state.primitives, self._layer_of, self.patterns())
        self._refresh_badge()

    def on_model_change(self) -> None:
        """Refresh the badge and layer checks on undo/restore
        (fold_eids travel in snapshots — restore may have changed them).
        Does not re-fire auto-preselect."""
        if self.model is None:
            return
        self.fsm.fold_eids = set(self.model.state.fold_eids)
        self.fsm.set_primitives(self.model.state.primitives)
        self._refresh_badge()

    def _layers_with_segs(self) -> list[tuple[str, list[str]]]:
        """Distinct layers that contain a straight line, in the order
        those layer names first appear in ``layer_of``."""
        if self.model is None:
            return []
        seg_ids = {
            e.eid for e in self.model.state.primitives if isinstance(e, Seg)
        }
        order: list[str] = []
        buckets: dict[str, list[str]] = {}
        for eid, name in self._layer_of.items():
            if name not in buckets:
                order.append(name)
                buckets[name] = []
            if eid in seg_ids:
                buckets[name].append(eid)
        return [(name, buckets[name]) for name in order if buckets[name]]

    def _layer_fully_on(self, eids: list[str]) -> bool:
        """Checked only when every straight line on the layer is designated.
        A mixed layer stays unchecked until the user clicks it."""
        return bool(eids) and all(eid in self.fsm.fold_eids for eid in eids)

    def _sync_layer_checks(self) -> None:
        rows = self._layers_with_segs()
        key = [(name, len(eids)) for name, eids in rows]
        self._show_layer_header(bool(rows))
        if key != self._layer_key:
            self._rebuild_layer_rows(rows)
            return
        self._layer_sync = True
        try:
            for name, eids in rows:
                self._layer_vars[name].set(self._layer_fully_on(eids))
        finally:
            self._layer_sync = False

    def _rebuild_layer_rows(self, rows: list[tuple[str, list[str]]]) -> None:
        self._layer_sync = True
        try:
            for child in self._layer_rows.winfo_children():
                child.destroy()
            self._layer_vars = {}
            self._layer_buttons = {}
            for name, eids in rows:
                var = tk.BooleanVar(
                    master=self, value=self._layer_fully_on(eids))
                btn = ttk.Checkbutton(
                    self._layer_rows,
                    text=msg.FOLD_LAYER_ROW.format(name=name, count=len(eids)),
                    variable=var,
                    command=lambda n=name: self._on_layer_toggle(n),
                )
                btn.pack(anchor="w", fill=tk.X, padx=(4, 0))
                self._layer_vars[name] = var
                self._layer_buttons[name] = btn
            self._layer_key = [(name, len(eids)) for name, eids in rows]
        finally:
            self._layer_sync = False

    def _show_layer_header(self, show: bool) -> None:
        """The layer group is a separate block from the import keywords.
        With no straight-line layers, the heading stays hidden."""
        if show:
            if self.layer_heading.winfo_manager():
                return
            self._layer_rule.pack(fill=tk.X, pady=(10, 0), before=self._layer_rows)
            self.layer_heading.pack(anchor="w", pady=(8, 0), before=self._layer_rows)
            self.layer_hint.pack(
                anchor="w", fill=tk.X, pady=(2, 2), before=self._layer_rows)
            return
        for widget in (self._layer_rule, self.layer_heading, self.layer_hint):
            if widget.winfo_manager():
                widget.pack_forget()

    def _on_layer_toggle(self, layer: str) -> None:
        """Check adds every straight line on the layer. Uncheck removes
        them. A mixed layer is shown unchecked, so its first click adds
        them all. Same undo treatment as a canvas designation."""
        if self._layer_sync or layer not in self._layer_vars:
            return
        want_on = bool(self._layer_vars[layer].get())
        eids: set[str] = set()
        for name, members in self._layers_with_segs():
            if name == layer:
                eids = set(members)
                break
        before = self._fold_eids_before()
        current = set(self.fsm.fold_eids)
        if want_on:
            current |= eids
        else:
            current -= eids
        self.fsm.fold_eids = current
        self.set_fold_eids(current)
        self._note_designation(before)