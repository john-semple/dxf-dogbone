"""SnapshotStack — ADR-001 undo model, M4 owner file.

Unbounded deep-copy stack over ``ModelState`` (documents are tiny —
``< 1 MB`` — no deltas; ADR-001/SPEC 11.7, redo added by ADR-027):

* ``push_load`` — once, at load: records the ORIGINAL (for
  Revert-to-Original) AND seeds the undo stack with it, so "the second
  undo after one Apply All lands on the load snapshot = original" (the
  M4 session plan; ADR-001 "undo swaps to the previous snapshot" read
  with load as the stack's first entry). Clears redo.
* ``push`` — immediately before the FIRST mutation of an Apply All
  (one snapshot per batch, unbounded depth). Clears redo: a new edit
  abandons the branch that undo had saved.
* ``undo`` — swap to the previous snapshot; multiple undos permitted;
  ``False`` at stack bottom (the UI disables the button there —
  disabled, never a crash). The state just left is pushed onto the
  redo stack (ADR-027).
* ``redo`` — swap back to the state undo saved; ``False`` when the
  redo stack is empty.
* ``discard_redo`` — a mutation that is not its own undo step (fold
  designation, sticky flag decision) abandons the redo branch.
* ``revert`` — Revert-to-Original (ADR-001 + ADR-009): swap to the
  load snapshot, CLEAR ``flag_decisions`` (their stickiness is
  session-scope), and EMPTY both the undo stack and the redo stack.
  The Revert button itself stays enabled.

Snapshots are full ``ModelState`` deep copies, so ``flag_decisions``
travel in them (CONTRACTS 1; ADR-013 loop-2 amendment: a trim decision
round-trips as ``"trim"``).
"""
from __future__ import annotations

from model.model import Model
from model.state import ModelState


class SnapshotStack:
    """Unbounded snapshot history over one Model (ADR-001)."""

    def __init__(self, model: Model):
        self._model = model
        self._load: ModelState | None = None
        self._stack: list[ModelState] = []
        self._redo: list[ModelState] = []
        # UI hooks. None in headless tests. The queue history in
        # ApplyAllWorkflowUI listens so a trim push stays in order
        # with Apply All.
        self.on_change = None
        self.on_push = None
        self.on_undo = None
        self.on_redo = None
        self.on_load_seed = None
        self.on_redo_abandoned = None
        self.on_revert = None

    # ------------------------------------------------------------ queries
    @property
    def load_snapshot(self) -> ModelState | None:
        """The load-time ORIGINAL (None before the first push_load)."""
        return self._load

    def can_undo(self) -> bool:
        """True when at least one snapshot remains below the current state."""
        return bool(self._stack)

    def can_redo(self) -> bool:
        """True when undo has saved a state that can be restored."""
        return bool(self._redo)

    def _emit(self) -> None:
        cb = self.on_change
        if cb is not None:
            cb()

    def __len__(self) -> int:
        """Undo depth (number of restore steps available)."""
        return len(self._stack)

    # ------------------------------------------------------------ commands
    def push_load(self) -> None:
        """Record the load snapshot and seed the undo stack with it."""
        self._load = self._model.snapshot()
        self._stack = [self._model.snapshot()]  # independent deep copy
        self._redo.clear()
        self._emit()
        if self.on_load_seed is not None:
            self.on_load_seed()

    def push(self) -> None:
        """Snapshot immediately before the first mutation of an Apply All.
        A new edit abandons any redo branch (ADR-027)."""
        self._redo.clear()
        self._stack.append(self._model.snapshot())
        self._emit()
        if self.on_push is not None:
            self.on_push()

    def undo(self) -> bool:
        """Swap to the previous snapshot. False (no-op) at stack bottom —
        the UI disables the button there; never raises. The state just
        left is kept on the redo stack."""
        if not self._stack:
            return False
        self._redo.append(self._model.snapshot())
        self._model.restore(self._stack.pop())
        self._emit()
        if self.on_undo is not None:
            self.on_undo()
        return True

    def redo(self) -> bool:
        """Swap back to the state the last undo left. False (no-op) when
        the redo stack is empty — the UI disables the button there."""
        if not self._redo:
            return False
        self._stack.append(self._model.snapshot())
        self._model.restore(self._redo.pop())
        self._emit()
        if self.on_redo is not None:
            self.on_redo()
        return True

    def discard_redo(self) -> None:
        """Abandon the redo branch after a mutation that is not its own
        undo step (fold designation, sticky flag decision). No-op when
        redo is already empty."""
        if not self._redo:
            return
        self._redo.clear()
        self._emit()
        if self.on_redo_abandoned is not None:
            self.on_redo_abandoned()

    def revert(self) -> None:
        """Revert-to-Original: swap to the load snapshot, clear
        flag_decisions (ADR-009), empty the undo and redo stacks.
        No-op when nothing was ever loaded."""
        if self._load is None:
            return
        self._model.restore(self._load)
        self._model.state.flag_decisions.clear()
        self._stack.clear()
        self._redo.clear()
        self._emit()
        if self.on_revert is not None:
            self.on_revert()