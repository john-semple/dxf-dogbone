"""M4 SnapshotStack tests — ADR-001/009, SPEC 11.7 (headless, no GUI).

DoD (brief): snapshot->apply n->undo -> state-equals-pre-apply (FULL
ModelState equality incl. flag_decisions); undo at stack bottom is
disabled, not a crash; revert restores the original + clears
flag_decisions + empties the undo stack; undo restores flag decisions
that traveled in the snapshot (ADR-009: undo PRESERVES, only
Revert-to-Original clears).
"""
from __future__ import annotations

import pytest

from geometry.entities import Pt, Seg, Side
from model.model import Model
from model.state import ModelState
from model.snapshots import SnapshotStack
from rules.engine import place_corner


def _two_corner_state() -> ModelState:
    """Two disjoint 90-degree corners (multi-apply depth probe)."""
    segs = [
        Seg(eid="H", a=Pt(-20.0, 0.0), b=Pt(20.0, 0.0)),
        Seg(eid="V", a=Pt(0.0, -20.0), b=Pt(0.0, 20.0)),
        Seg(eid="T", a=Pt(100.0, 0.0), b=Pt(140.0, 0.0)),
        Seg(eid="U", a=Pt(120.0, -20.0), b=Pt(120.0, 20.0)),
    ]
    st = ModelState()
    st.primitives = segs
    return st


def _place(model: Model, r: float = 1.5875):
    return place_corner(
        model.state.primitives, "H", "V",
        Side(+1), r,
        set(model.state.fold_eids),
        list(model.state.dogbones),
        flag_decisions=dict(model.state.flag_decisions),
        db_id="db-H+V",
    )


def _place_second(model: Model, r: float = 1.5875):
    """The OTHER corner (T,U) — disjoint from (H,V)."""
    return place_corner(
        model.state.primitives, "T", "U",
        Side(+1), r,
        set(model.state.fold_eids),
        list(model.state.dogbones),
        flag_decisions=dict(model.state.flag_decisions),
        db_id="db-T+U",
    )


class TestSnapshotStackBasics:
    def test_snapshots_push_undo_restore_exact_state(self):
        model = Model(_two_corner_state())
        stack = SnapshotStack(model)
        stack.push_load()
        pre = model.snapshot()
        res = _place(model)
        assert res.ok, res.refusals
        stack.push()
        model.apply_corner(res)
        assert len(model.state.dogbones) == 1
        assert stack.can_undo()
        assert stack.undo()
        # FULL ModelState equality: primitives, dogbones, fold_eids,
        # flag_decisions, next_seq (dataclass __eq__ field by field)
        assert model.state == pre
        # load snapshot seeds the stack: one more undo to the original
        assert stack.can_undo()
        assert stack.undo()
        assert not stack.can_undo()

    def test_snapshots_unbounded_depth_multi_apply_multi_undo(self):
        """SPEC 11.7: multiple undos permitted; unbounded stack."""
        model = Model(_two_corner_state())
        stack = SnapshotStack(model)
        stack.push_load()
        pre = model.snapshot()
        res = _place(model)
        assert res.ok, res.refusals
        stack.push()
        model.apply_corner(res)
        st1 = model.snapshot()
        res2 = _place_second(model)
        assert res2.ok, res2.refusals
        stack.push()
        model.apply_corner(res2)
        assert len(stack) == 3  # load + pre-batch1 + pre-batch2
        assert len(model.state.dogbones) == 2
        # undo 1 -> state after the first apply only
        assert stack.undo()
        assert model.state == st1
        # undo 2 -> pre-apply of batch 1
        assert stack.undo()
        assert model.state == pre
        # undo 3 -> load snapshot = original
        assert stack.undo()
        assert not stack.can_undo()

    def test_snapshots_undo_at_bottom_disabled_not_crashed(self):
        model = Model(_two_corner_state())
        stack = SnapshotStack(model)
        stack.push_load()
        res = _place(model)
        assert res.ok
        stack.push()
        model.apply_corner(res)
        assert stack.undo()
        assert stack.undo()  # load snapshot
        bottom = model.snapshot()
        # at stack bottom: undo returns False, state untouched —
        # "disabled not crashed" (DoD)
        assert not stack.can_undo()
        assert not stack.undo()
        assert model.state == bottom

    def test_snapshots_flag_decisions_travel_in_snapshots(self):
        """ADR-009/013: decisions are sticky, stored in ModelState,
        travel in snapshots, restored by undo."""
        model = Model(_two_corner_state())
        stack = SnapshotStack(model)
        stack.push_load()
        # seed a sticky decision pre-apply
        model.state.flag_decisions["H"] = "keep"
        pre = model.snapshot()
        res = _place(model)
        assert res.ok
        stack.push()
        model.apply_corner(res)
        # simulate a NEW sticky decision landing between apply and undo
        model.state.flag_decisions["X1"] = "trim"
        assert model.state != pre
        assert stack.undo()
        assert model.state == pre
        assert model.state.flag_decisions == {"H": "keep"}

    def test_snapshots_trim_decision_roundtrips_as_trim(self):
        """ADR-013 loop-2: a trim decision round-trips as 'trim'."""
        model = Model(_two_corner_state())
        stack = SnapshotStack(model)
        stack.push_load()
        model.state.flag_decisions["H"] = "trim"
        pre = model.snapshot()
        res = _place(model)
        assert res.ok
        stack.push()
        model.apply_corner(res)
        assert stack.undo()
        assert model.state.flag_decisions.get("H") == "trim"

    def test_snapshots_revert_restores_original_clears_flags_empties(self):
        """ADR-009: Revert-to-Original = load snapshot + flag_decisions
        cleared + undo stack emptied (no redo in V1; the Revert button
        itself stays enabled)."""
        model = Model(_two_corner_state())
        stack = SnapshotStack(model)
        stack.push_load()
        original = model.snapshot()
        model.state.flag_decisions["H"] = "keep"
        res = _place(model)
        assert res.ok
        stack.push()
        model.apply_corner(res)
        assert len(model.state.dogbones) == 1
        stack.revert()
        assert model.state == original
        assert model.state.flag_decisions == {}
        assert not stack.can_undo()

    def test_snapshots_revert_with_no_load_is_noop(self):
        model = Model(_two_corner_state())
        stack = SnapshotStack(model)
        assert stack.load_snapshot is None
        stack.revert()  # no crash
        assert not stack.can_undo()

    def test_snapshots_deep_copy_independence(self):
        """ADR-001: snapshots are deep copies — later mutations never
        alias into a stored snapshot (export purity's foundation)."""
        import copy

        model = Model(_two_corner_state())
        stack = SnapshotStack(model)
        stack.push_load()
        stack.push()
        stored = stack._stack[-1]
        res = _place(model)
        assert res.ok
        model.apply_corner(res)
        assert stored != model.state
        assert copy.deepcopy(stored) == stored

    def test_snapshots_undo_restore_is_idempotent_safe(self):
        """Undo swaps deep-copied states in; restoring twice cannot alias
        the stored copy (Model.restore deep-copies on the way in)."""
        model = Model(_two_corner_state())
        stack = SnapshotStack(model)
        stack.push_load()
        res = _place(model)
        assert res.ok
        stack.push()
        model.apply_corner(res)
        assert stack.undo()
        first = model.snapshot()
        # push the restored state again and undo: lands on load snapshot
        stack.push()
        assert stack.undo()
        assert stack.undo()
        assert not stack.can_undo()
        assert model.state.dogbones == []