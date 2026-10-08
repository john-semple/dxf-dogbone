"""SnapshotStack — ADR-001 undo model, M4 owner file.

Unbounded deep-copy stack over ``ModelState`` (documents are tiny —
``< 1 MB`` — no deltas, no redo in V1; ADR-001/SPEC 11.7):

* ``push_load`` — once, at load: records the ORIGINAL (for
  Revert-to-Original) AND seeds the undo stack with it, so "the second
  undo after one Apply All lands on the load snapshot = original" (the
  M4 session plan; ADR-001 "undo swaps to the previous snapshot" read
  with load as the stack's first entry).
* ``push`` — immediately before the FIRST mutation of an Apply All
  (one snapshot per batch, unbounded depth).
* ``undo`` — swap to the previous snapshot; multiple undos permitted;
  ``False`` at stack bottom (the UI disables the button there —
  disabled, never a crash).
* ``revert`` — Revert-to-Original (ADR-001 + ADR-009): swap to the
  load snapshot, CLEAR ``flag_decisions`` (their stickiness is
  session-scope), and EMPTY the undo stack (V1 has no redo; an undo
  past a revert would be undefined). The Revert button itself stays
  enabled.

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

    # ------------------------------------------------------------ queries
    @property
    def load_snapshot(self) -> ModelState | None:
        """The load-time ORIGINAL (None before the first push_load)."""
        return self._load

    def can_undo(self) -> bool:
        """True when at least one snapshot remains below the current state."""
        return bool(self._stack)

    def __len__(self) -> int:
        """Undo depth (number of restore steps available)."""
        return len(self._stack)

    # ------------------------------------------------------------ commands
    def push_load(self) -> None:
        """Record the load snapshot and seed the undo stack with it."""
        self._load = self._model.snapshot()
        self._stack = [self._model.snapshot()]  # independent deep copy

    def push(self) -> None:
        """Snapshot immediately before the first mutation of an Apply All."""
        self._stack.append(self._model.snapshot())

    def undo(self) -> bool:
        """Swap to the previous snapshot. False (no-op) at stack bottom —
        the UI disables the button there; never raises."""
        if not self._stack:
            return False
        self._model.restore(self._stack.pop())
        return True

    def revert(self) -> None:
        """Revert-to-Original: swap to the load snapshot, clear
        flag_decisions (ADR-009), empty the undo stack (no redo in V1).
        No-op when nothing was ever loaded."""
        if self._load is None:
            return
        self._model.restore(self._load)
        self._model.state.flag_decisions.clear()
        self._stack.clear()