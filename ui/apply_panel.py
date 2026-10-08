"""M4 Apply-All layer — SPEC 4.4/11.7, ADR-001/005/009/016(j)(k).

Three pieces:

* ``ApplyQueue`` — the headless batch driver. In click order, each
  queued ``PendingCorner`` is RE-PLACED live against the current model
  (ADR-016(k): never a stale CornerResult) immediately before its
  ``Model.apply_corner``. Any refusal or newly-pending flag at
  re-place time -> warn-and-skip (engine string verbatim; the corner
  is dropped — ISSUE-005 registers the V1.1 shrink-R alternative).
  One snapshot per batch, pushed immediately before the first
  mutation (ADR-001).
* ``ToolPanel`` — the left-side tkinter panel: tool-diameter entry +
  mm/inch toggle + quick-pick size buttons (user ruling 2026-10-07,
  decision 7), pending-corners readout, Apply All / Undo / Redo /
  Revert-to-Original.
* ``ApplyAllWorkflowUI`` — the M4 seam over M3's ``WorkflowUI``
  (base class byte-identical): Confirm = ENQUEUE (SPEC 5: single
  Apply All) via the ``apply`` port override; ``radius`` reads the
  panel; undo/redo/revert drive the SnapshotStack; queued corners show
  dashed ghost overlays; radius edits re-place live.

No geometry is computed here (ADR-006): construction stays in
rules.engine; snapshots stay in model.snapshots.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from geometry.entities import CornerResult, Pt
from model.model import Model
from model.snapshots import SnapshotStack
from ui.collapsible import CollapsibleSection
from ui.theme import COLORS as THEME, font as theme_font
from ui.workflow import (
    GHOST_COLOR,
    GHOST_DASH,
    PendingCorner,
    Viewer,
    WorkflowState,
    WorkflowUI,
)
import ui.messages as msg

# Quick-pick tool buttons (user ruling 2026-10-07, decision 7): fixed
# constants, presentation-only setters on the same diameter state as
# the free-entry field. English: 1/16", 1/8", 1/4". Metric ascending.
QUICK_MM = (2.0, 3.0, 4.0, 6.0, 8.0)
QUICK_IN = (('1/16"', 1.5875), ('1/8"', 3.175), ('1/4"', 6.35))

PENDING_TAG = "m4_pending"   # queued-corner ghost overlays


class ApplyQueue:
    """Headless batch driver over one Model + SnapshotStack (M4 core).

    ``apply_all`` re-places every queued pending live (ADR-016(k)),
    applies in click order, warn-and-skips refusals, and pushes exactly
    one snapshot before the first successful mutation (ADR-001).
    Directly unit-testable: no tkinter anywhere in this class.
    """

    def __init__(self, model: Model, stack: SnapshotStack, place=None):
        self.model = model
        self.stack = stack
        self.queue: list[PendingCorner] = []
        if place is not None:
            self._place = place  # injectable for tests

    def enqueue(self, pending: PendingCorner) -> None:
        """Click order is apply order — duplicates land as-is (labels
        are cosmetic; real arc eids mint at apply)."""
        self.queue.append(pending)

    def clear(self) -> None:
        self.queue.clear()

    def _place(self, pending: PendingCorner) -> CornerResult:
        """Live re-place against the CURRENT model (ADR-016(k))."""
        from rules.engine import place_corner  # ui may import rules

        return place_corner(
            self.model.state.primitives,
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

    def apply_all(self) -> tuple[int, list[str]]:
        """Apply every queued pending in click order. Returns
        (applied_count, skip_reasons) — reasons carry the engine
        strings verbatim (toast + preview-summary entry). The batch
        consumes the queue: applied corners are gone, skipped corners
        are DROPPED (V1; ISSUE-005 registers the V1.1 shrink-R
        alternative) — the workflow returns to PICK_EDGE1 cleanly."""
        if not self.queue:
            return 0, []
        applied = 0
        skips: list[str] = []
        snapshot_taken = False
        for pending in self.queue:
            res = self._place(pending)
            ok = res.ok and not any(f.decision is None for f in res.flags)
            if not ok:
                if not res.ok:
                    skips.append("; ".join(res.refusals))
                else:
                    reasons = sorted({f.reason for f in res.flags
                                     if f.decision is None})
                    skips.append(msg.TOAST_PENDING_FLAG.format(
                        reasons=", ".join(reasons)))
                continue
            if not snapshot_taken:
                self.stack.push()  # immediately before the FIRST mutation
                snapshot_taken = True
            self.model.apply_corner(res)
            applied += 1
        self.queue.clear()
        return applied, skips


class ToolPanel(ttk.Frame):
    """Diameter entry, unit toggle, quick-pick buttons, pending readout,
    Apply All, and Undo / Redo / Revert. All actions delegate to the
    callbacks the App passes in.

    The tool widgets live in the collapsible ``dogbone`` section, parented
    to ``master`` so it scrolls with the other sections. Undo, Redo, and
    Revert live in ``commands``, parented to ``command_parent`` when the
    shell passes one (the rail's pinned strip). This frame itself stays
    unpacked.
    """

    def __init__(self, master, on_apply_all=None, on_undo=None,
                 on_redo=None, on_revert=None, on_radius_change=None,
                 command_parent=None):
        super().__init__(master, style="TFrame")
        self._on_apply_all = on_apply_all
        self._on_undo = on_undo
        self._on_redo = on_redo
        self._on_revert = on_revert
        self._on_radius_change = on_radius_change

        self._unit_in = tk.BooleanVar(value=False)  # False = mm
        self._dia_text = tk.StringVar(value="3.175")
        self._pending_var = tk.StringVar(value=msg.STATUS_QUEUE_EMPTY)
        self._pending_n = 0

        self.dogbone = CollapsibleSection(master, msg.SECTION_DOGBONE)
        body = self.dogbone.body
        row = ttk.Frame(body, style="TFrame")
        row.pack(fill=tk.X)
        ttk.Label(row, text=msg.LABEL_DIAMETER,
                  style="TLabel").pack(side=tk.LEFT)
        self.unit_btn = ttk.Button(
            row, text=msg.UNIT_MM, width=5,
            command=self._toggle_unit)
        self.unit_btn.pack(side=tk.RIGHT, padx=(4, 0))
        self.dia_entry = ttk.Entry(row, textvariable=self._dia_text,
                                   width=10, font=theme_font(10))
        self.dia_entry.pack(side=tk.RIGHT, padx=(4, 0))
        self.dia_entry.bind("<KeyRelease>", self._entry_edited)

        self.readout = ttk.Label(body, text="", style="TLabel")
        self.readout.pack(anchor="w", pady=(4, 0))

        # quick-pick buttons, TWO columns (user ruling): English | Metric
        grid = ttk.Frame(body, style="TFrame")
        grid.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(grid, text="Quick sizes", style="TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w")
        self._quick_buttons: list[tuple[float, ttk.Button]] = []
        for i, (label, dia) in enumerate(QUICK_IN):
            b = ttk.Button(grid, text=f"{label} ({dia:.4g} mm)",
                           style="TButton",
                           command=lambda d=dia: self.set_diameter_mm(d))
            b.grid(row=1 + i, column=0, sticky="ew", padx=(0, 4), pady=2)
            self._quick_buttons.append((dia, b))
        for i, dia in enumerate(QUICK_MM):
            b = ttk.Button(grid, text=f"{dia:g} mm", style="TButton",
                           command=lambda d=dia: self.set_diameter_mm(d))
            b.grid(row=1 + i, column=1, sticky="ew", padx=(4, 0), pady=2)
            self._quick_buttons.append((dia, b))
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        self.pending_label = ttk.Label(body, textvariable=self._pending_var,
                                       style="TLabel", wraplength=248,
                                       justify="left")
        self.pending_label.pack(anchor="w", pady=(8, 0))

        self.apply_btn = ttk.Button(body, text=msg.BTN_APPLY_ALL,
                                    style="Accent.TButton",
                                    command=self._apply_all)
        self.apply_btn.pack(fill=tk.X, pady=(8, 2))

        # Pinned above the sections. Undo/Redo are the real buttons;
        # Revert is text-weight so a misclick is less likely.
        cmd_master = master if command_parent is None else command_parent
        self.commands = ttk.Frame(cmd_master, style="TFrame")
        hist = ttk.Frame(self.commands, style="TFrame")
        hist.pack(fill=tk.X)
        self.undo_btn = ttk.Button(hist, text=msg.BTN_UNDO,
                                    command=self._undo)
        self.undo_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        self.redo_btn = ttk.Button(hist, text=msg.BTN_REDO,
                                    command=self._redo)
        self.redo_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 0))
        self.revert_btn = ttk.Button(self.commands, text=msg.BTN_REVERT,
                                     style="Quiet.TButton",
                                     command=self._revert)
        self.revert_btn.pack(anchor="w", pady=(4, 0))
        # initial state: nothing loaded, nothing queued, nothing to undo
        self.apply_btn.config(state=tk.DISABLED)
        self.undo_btn.config(state=tk.DISABLED)
        self.redo_btn.config(state=tk.DISABLED)
        self.revert_btn.config(state=tk.DISABLED)
        self._refresh_readout()
        self._highlight_quick()

    # --------------------------------------------------------- diameter
    def diameter_mm(self) -> float | None:
        """Current diameter in mm, or None when the entry is invalid
        (empty / non-numeric / non-positive).

        A trailing ``"`` (user request 2026-10-07) forces INCH
        interpretation regardless of the unit toggle — ``0.25"`` and
        ``1/8"`` always convert to 6.35 / 3.175 mm."""
        text = self._dia_text.get().strip()
        inches = False
        if text.endswith('"'):
            inches = True
            text = text[:-1].strip()
        if not text:
            return None
        try:
            value = self._parse_fraction(text)
        except (ValueError, ZeroDivisionError):
            return None
        if value <= 0.0:
            return None
        if inches or self._unit_in.get():
            return value * msg.MM_PER_IN
        return value

    def _parse_fraction(self, text: str) -> float:
        """Plain floats in the current unit + simple fractions ("3/16")."""
        if "/" in text:
            num, den = text.split("/", 1)
            return float(num.strip()) / float(den.strip())
        return float(text)

    def set_diameter_mm(self, dia_mm: float) -> None:
        """Presentation-only setter: entry adopts the value in the
        CURRENT unit; quick buttons never flip the unit."""
        if self._unit_in.get():
            self._dia_text.set(f"{dia_mm / msg.MM_PER_IN:g}")
        else:
            self._dia_text.set(f"{dia_mm:g}")
        self._radius_changed()

    def _toggle_unit(self) -> None:
        current = self.diameter_mm()
        self._unit_in.set(not self._unit_in.get())
        self.unit_btn.config(
            text=msg.UNIT_IN if self._unit_in.get() else msg.UNIT_MM)
        if current is not None:
            self.set_diameter_mm(current)

    def _entry_edited(self, _ev) -> None:
        self._radius_changed()

    def _radius_changed(self) -> None:
        self._refresh_readout()
        self._highlight_quick()
        if self._on_radius_change is not None:
            self._on_radius_change()

    def _refresh_readout(self) -> None:
        dia = self.diameter_mm()
        if dia is None:
            self.readout.config(text="—", foreground=THEME["fg_muted"])
        else:
            unit = msg.UNIT_IN if self._unit_in.get() else msg.UNIT_MM
            self.readout.config(
                text=msg.DIA_READOUT.format(dia=dia, unit=unit, r=dia / 2.0),
                foreground=THEME["fg"])
        self._sync_summary()

    def _sync_summary(self) -> None:
        """Header note so a minimized Dogbone section still shows the tool."""
        dia = self.diameter_mm()
        if dia is None:
            text = "—"
        else:
            unit = msg.UNIT_IN if self._unit_in.get() else msg.UNIT_MM
            text = f"Ø {dia:.4g} {unit}"
        if self._pending_n:
            text += f"  ·  {self._pending_n} queued"
        self.dogbone.set_summary(text)

    def _highlight_quick(self) -> None:
        """Active size highlights (incl. the 1/8\" default at load)."""
        dia = self.diameter_mm()
        for qdia, btn in self._quick_buttons:
            if dia is not None and abs(qdia - dia) <= 1e-9:
                btn.config(style="Selected.TButton")
            else:
                btn.config(style="TButton")

    # ------------------------------------------------------ state slots
    def set_pending_count(self, n: int) -> None:
        self._pending_n = n
        if n:
            self._pending_var.set(msg.STATUS_PENDING_COUNT.format(n=n))
        else:
            self._pending_var.set(msg.STATUS_QUEUE_EMPTY)
        self.apply_btn.config(state=tk.NORMAL if n else tk.DISABLED)
        self._sync_summary()

    def set_undo_enabled(self, enabled: bool) -> None:
        """Stack-bottom disable (DoD: disabled, not crashed)."""
        self.undo_btn.config(
            state=tk.NORMAL if enabled else tk.DISABLED)

    def set_redo_enabled(self, enabled: bool) -> None:
        """Empty-redo disable (same rule as undo: disabled, not crashed)."""
        self.redo_btn.config(
            state=tk.NORMAL if enabled else tk.DISABLED)

    def set_revert_enabled(self, enabled: bool) -> None:
        self.revert_btn.config(
            state=tk.NORMAL if enabled else tk.DISABLED)

    # -------------------------------------------------------- callbacks
    def _apply_all(self) -> None:
        if self._on_apply_all is not None:
            self._on_apply_all()

    def _undo(self) -> None:
        if self._on_undo is not None:
            self._on_undo()

    def _redo(self) -> None:
        if self._on_redo is not None:
            self._on_redo()

    def _revert(self) -> None:
        if self._on_revert is not None:
            self._on_revert()


class ApplyAllWorkflowUI(WorkflowUI):
    """The M4 seam over M3's WorkflowUI — base class byte-identical.

    Confirm ENQUEUES (SPEC 5: toggle multiple corners -> all pending
    changes previewed -> single Apply All) instead of mutating:
    the ``apply`` port (called by the untouched M3 FSM at confirm)
    lands the corner in the queue with the CURRENT radius.
    """

    def __init__(self, viewer: Viewer, model: Model, root: tk.Misc,
                 stack: SnapshotStack, on_status=None,
                 radius_mm: float = 3.175 / 2.0, on_state=None,
                 panel: ToolPanel | None = None):
        self.stack = stack
        self.queue = ApplyQueue(model, stack)
        self.panel = panel
        self._last_valid_r = radius_mm
        # Stack depth at each confirm that has not been applied.
        # A suffix of the queue: Revert can leave older corners that
        # Undo must not remove.
        self._unapplied_depths: list[int] = []
        # Apply All batches, newest last: (push gen, corners, depths).
        # Undo of that snapshot puts the corners back; further Undos
        # remove them newest-first. Redo applies the batch again.
        self._batches: list[tuple] = []
        self._batch_redo: list[tuple] = []
        self._undo_gens: list[int] = []
        self._redo_gens: list[int] = []
        self._next_gen = 0
        super().__init__(viewer, model, root, on_status=on_status,
                         radius_mm=radius_mm, on_state=on_state)
        # load snapshot: the model was constructed from the loaded
        # state — record it now (ADR-001; seeds the undo stack).
        self.bind_history_hooks(stack)
        stack.push_load()
        self._notify_queue()

    # ------------------------------------------------------------- ports
    def apply(self, res: CornerResult) -> None:
        """M4 override: Confirm = enqueue, never mutate (the batch
        driver owns mutation)."""
        pending = self.fsm.pending
        if pending is not None:
            # adopt the CURRENT radius (WYSIWYG with ADR-016(k)):
            # queued pendings re-place with the current R at Apply
            # All — mixed-tool parts apply in separate batches.
            from dataclasses import replace
            self.queue.enqueue(replace(pending, r=self.radius()))
            # Depth after this confirm. A later trim or Apply All
            # pushes, so Undo restores that drawing change first.
            self._unapplied_depths.append(len(self.stack))
        self._notify_queue()

    def decide_flag(self, flag, kind: str) -> str | None:
        """A sticky flag decision mutates the model without its own
        snapshot. That abandons the redo branch (ADR-027)."""
        self.stack.discard_redo()
        return super().decide_flag(flag, kind)

    def radius(self) -> float:
        """Panel field drives R; invalid entry falls back to the last
        valid value (never a half-typed garbage radius)."""
        if self.panel is not None:
            dia = self.panel.diameter_mm()
            if dia is not None:
                self._last_valid_r = dia / 2.0
            return self._last_valid_r
        return self._radius_mm

    # -------------------------------------------------------- queue view
    def _notify_queue(self) -> None:
        if self.panel is not None:
            self.panel.set_pending_count(len(self.queue.queue))
            self.panel.set_undo_enabled(
                self.stack.can_undo() or self._unapplied_ready())
            self.panel.set_redo_enabled(self.stack.can_redo())
            self.panel.set_revert_enabled(
                self.stack.load_snapshot is not None)

    def _restart_to_pick_edge1(self, toast: str) -> None:
        """Decision 4: after Apply All / Undo / Redo / Revert the workflow
        restarts CLEANLY at PICK_EDGE1 (no half-state)."""
        self.fsm._restart(toast)   # clears every pick field -> IDLE
        self.fsm.start()           # IDLE -> PICK_EDGE1
        self.fsm.status = f"{toast}  {msg.STATUS_PICK_EDGE1}"
        self._sync_view()
        self._notify_queue()

    # ----------------------------------------------------- apply all etc
    def apply_all(self) -> tuple[int, list[str]]:
        """Drive the batch: snapshot -> re-place each pending live ->
        apply in click order; skips dropped with engine strings."""
        saved_q = tuple(self.queue.queue)
        saved_d = tuple(self._unapplied_depths)
        top_before = self._undo_gens[-1] if self._undo_gens else None
        applied, skips = self.queue.apply_all()
        # Applied and skipped corners are both gone from the queue.
        self.clear_unapplied_undo()
        top_after = self._undo_gens[-1] if self._undo_gens else None
        if top_after is not None and top_after != top_before:
            self._batches.append((top_after, saved_q, saved_d))
        if applied:
            self.viewer.set_model(self.model.state)
        toast = msg.APPLY_ALL_TOAST.format(
            n=applied, s="" if applied == 1 else "s")
        if not applied and not skips:
            toast = msg.APPLY_ALL_NONE
        if skips:
            toast += "  " + msg.APPLY_ALL_SKIPPED.format(
                n=len(skips), s="" if len(skips) == 1 else "s",
                reasons=" | ".join(skips))
        self._restart_to_pick_edge1(toast)
        return applied, skips

    def bind_history_hooks(self, stack: SnapshotStack) -> None:
        """Point snapshot notifications at this workflow.

        File retarget replaces the stack. The new one must call these
        before ``push_load``, or Apply All history from the previous
        file would still be live.
        """
        stack.on_push = self._on_stack_push
        stack.on_undo = self._on_stack_undo
        stack.on_redo = self._on_stack_redo
        stack.on_load_seed = self._on_load_seed
        stack.on_redo_abandoned = self._on_redo_abandoned
        stack.on_revert = self._on_stack_revert

    def _on_stack_push(self) -> None:
        self._next_gen += 1
        self._undo_gens.append(self._next_gen)
        self._redo_gens.clear()
        self._batch_redo.clear()

    def _on_stack_undo(self) -> None:
        if self._undo_gens:
            self._redo_gens.append(self._undo_gens.pop())

    def _on_stack_redo(self) -> None:
        if self._redo_gens:
            self._undo_gens.append(self._redo_gens.pop())

    def _on_load_seed(self) -> None:
        self._next_gen += 1
        self._undo_gens = [self._next_gen]
        self._redo_gens.clear()
        self._batches.clear()
        self._batch_redo.clear()
        self._unapplied_depths.clear()

    def _on_redo_abandoned(self) -> None:
        self._redo_gens.clear()
        self._batch_redo.clear()

    def _on_stack_revert(self) -> None:
        self._batches.clear()
        self._batch_redo.clear()
        self._undo_gens.clear()
        self._redo_gens.clear()
        self._unapplied_depths.clear()

    @staticmethod
    def _corner_key(pending: PendingCorner) -> tuple:
        return (
            pending.edge1_eid, pending.edge2_eid, pending.side,
            pending.side_flip, pending.db_id,
        )

    def _drop_restored_batch(self, saved: tuple) -> None:
        """Remove the applied corners from the front of the queue.

        Redo puts those dogbones back on the drawing. Corners confirmed
        after the undo stay queued.
        """
        n = 0
        for pending, old in zip(self.queue.queue, saved):
            if self._corner_key(pending) != self._corner_key(old):
                break
            n += 1
        if n:
            del self.queue.queue[:n]
            del self._unapplied_depths[:n]

    def clear_unapplied_undo(self) -> None:
        """Forget confirm-undo depths. Does not change the pending queue.

        Apply All calls this because the queue was consumed. Revert and
        file retarget call it so a later stack length cannot match a
        depth from before that boundary and remove a corner that must stay.
        """
        self._unapplied_depths.clear()

    def _unapplied_ready(self) -> bool:
        """True when the newest confirm is still the latest drawing step."""
        return bool(
            self._unapplied_depths
            and self.queue.queue
            and self._unapplied_depths[-1] == len(self.stack)
        )

    def undo(self) -> bool:
        """Undo the newest unapplied confirm, or else the previous snapshot.

        A confirm records the stack depth. Undo removes that one corner
        only while the depth still matches, and does not touch the
        snapshot stack (the load seed stays). A trim that pushed
        afterward is undone first. Undo of an Apply All restores the
        drawing, puts that batch back on the queue, and later Undos
        remove those corners newest-first.
        """
        if (self._unapplied_depths
                and self._unapplied_depths[-1] == len(self.stack)):
            if self.queue.queue:
                self.queue.queue.pop()
                self._unapplied_depths.pop()
                self._restart_to_pick_edge1(msg.UNDO_QUEUED)
                return True
            # Depth with nothing queued: drop the stale record.
            self._unapplied_depths.clear()
        if not self.stack.can_undo():
            self._restart_to_pick_edge1(msg.UNDO_EMPTY)
            return False
        top_gen = self._undo_gens[-1] if self._undo_gens else None
        batch = None
        if self._batches and self._batches[-1][0] == top_gen:
            batch = self._batches.pop()
        self.stack.undo()
        if batch is not None:
            _gen, saved_q, saved_d = batch
            self.queue.queue = list(saved_q)
            self._unapplied_depths = list(saved_d)
            self._batch_redo.append(batch)
        self.viewer.set_model(self.model.state)
        toast = msg.UNDO_APPLIED if batch is not None else msg.UNDO_TOAST
        self._restart_to_pick_edge1(toast)
        return True

    def redo(self) -> bool:
        """Redo = restore the state undo just left + redraw + clean restart.
        Empty redo stack: disabled button (panel), False here — never a crash."""
        if not self.stack.can_redo():
            self._restart_to_pick_edge1(msg.REDO_EMPTY)
            return False
        redone_gen = self._redo_gens[-1] if self._redo_gens else None
        self.stack.redo()
        if (self._batch_redo and redone_gen is not None
                and self._batch_redo[-1][0] == redone_gen):
            batch = self._batch_redo.pop()
            self._batches.append(batch)
            self._drop_restored_batch(batch[1])
        self.viewer.set_model(self.model.state)
        self._restart_to_pick_edge1(msg.REDO_TOAST)
        return True

    def revert_to_original(self) -> bool:
        """Revert-to-Original: load snapshot + clear flag_decisions
        (ADR-009) + empty undo stack. The pending queue is KEPT (user
        decision 5: eids are stable; re-placed at use)."""
        if self.stack.load_snapshot is None:
            return False
        self.stack.revert()
        # The queue stays (decision 5). Its corners are no longer undo steps.
        self.clear_unapplied_undo()
        self.viewer.set_model(self.model.state)
        self._restart_to_pick_edge1(msg.REVERT_TOAST)
        return True

    def on_radius_change(self) -> None:
        """Radius edit -> decision 3: queued pendings ADOPT THE CURRENT R
        (mixed-tool parts apply in separate batches; per-corner R is
        V1.1/ISSUE-006); the active pick's ghosts/preview re-place live
        (ADR-016(k) WYSIWYG); queued ghost overlays redraw."""
        from dataclasses import replace
        r = self.radius()
        self.queue.queue = [replace(p, r=r) for p in self.queue.queue]
        if self.fsm.state == WorkflowState.GHOSTS_VISIBLE:
            self.fsm._compute_ghosts()
        elif (self.fsm.state == WorkflowState.SIDE_PICKED
                and self.fsm.pending is not None):
            self.fsm.recompute()
        self._sync_view()

    def confirm_click(self) -> CornerResult | None:
        """M3's confirm, plus: the enqueued corner updates the panel and
        the status line says QUEUED (not M3's 'applied' — the batch
        driver owns application). User request 2026-10-07: after the
        preview's close-up auto-zoom, confirming zooms back OUT to fit
        the whole part (the close-up has served its review purpose)."""
        res = super().confirm_click()
        if res is not None:
            self.fsm.start()  # M3 restarts to IDLE; M4 -> PICK_EDGE1
            self.fsm.status = (
                msg.ENQUEUED_TOAST.format(n=len(self.queue.queue))
                + "  " + msg.STATUS_PICK_EDGE1
            )
            self.viewer.fit()  # zoom out from the corner close-up
            self.viewer.redraw()
            self._sync_view()
            self._notify_queue()
        return res

    # ----------------------------------------------------- queue overlays
    def _draw_pending_ghosts(self) -> None:
        """Dashed overlays of the QUEUED corners (distinguish the batch
        from the active pick's ghosts)."""
        c = self.viewer.canvas
        t = self.transform
        for pending in self.queue.queue:
            center = self._pending_center(pending)
            if center is None:
                continue
            cx, cy = t.to_screen(center)
            r_px = pending.r * t.scale
            c.create_oval(cx - r_px, cy - r_px, cx + r_px, cy + r_px,
                          outline=GHOST_COLOR, dash=GHOST_DASH, width=1,
                          tags=(PENDING_TAG,))

    def _pending_center(self, pending: PendingCorner) -> Pt | None:
        """Ghost center of a queued corner re-derived from the live
        model (undo/revert can have moved geometry; a queued ghost must
        never lie about where its dogbone will land)."""
        from geometry.entities import Refusal
        from rules.engine import ghost_candidates

        gcs = ghost_candidates(
            self.model.state.primitives, pending.edge1_eid,
            pending.edge2_eid, pending.r)
        if isinstance(gcs, Refusal):
            return None
        for side, flip, center in gcs:
            if side == pending.side and flip == pending.side_flip:
                return center
        return None

    def _clear_overlays(self) -> None:
        super()._clear_overlays()
        self.viewer.canvas.delete(PENDING_TAG)

    def _sync_view(self) -> None:
        super()._sync_view()
        self._draw_pending_ghosts()