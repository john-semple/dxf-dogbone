"""M4 ApplyQueue tests — headless batch driver (no tkinter).

SPEC 4.4/11.7 + ADR-016(j)(k): pendings apply in click order; each
re-places live; any refusal (overlap included, tangent passes) or
newly-pending flag -> warn-and-skip with the engine string verbatim;
skips are dropped; snapshot pushed immediately before the FIRST
mutation; undo at stack bottom disabled not crashed.
"""
from __future__ import annotations

from geometry.entities import Pt, Seg, Side
from model.model import Model
from model.state import ModelState
from model.snapshots import SnapshotStack
from rules.engine import place_corner
from ui.apply_panel import ApplyQueue

from ui.workflow import PendingCorner


def _corner_a_prims():
    return [
        Seg("e1", Pt(0.0, 0.0), Pt(0.0, -10.0)),
        Seg("e2", Pt(0.0, 0.0), Pt(3.0, 0.0)),
    ]


def _corner_b_prims(dx):
    return _corner_a_prims() + [
        Seg("e3", Pt(3.175 + dx, 5.0), Pt(3.175 + dx, -10.0)),
        Seg("e4", Pt(3.175 + dx, 0.0), Pt(13.175 + dx, 0.0)),
    ]


def _state(prims) -> ModelState:
    st = ModelState()
    st.primitives = list(prims)
    return st


def _pending(e1: str, e2: str, r: float = 1.5875, flip: int = +1,
             db: str | None = None) -> PendingCorner:
    return PendingCorner(
        edge1_eid=e1, edge2_eid=e2, side=Side(+1), side_flip=flip,
        r=r, db_id=db or f"db-{e1}+{e2}",
    )


class TestApplyQueueOrder:
    def test_queue_apply_all_two_corners_click_order(self):
        model = Model(_state(_corner_b_prims(0.0) + [
            Seg("e5", Pt(200.0, 0.0), Pt(200.0, -10.0)),
            Seg("e6", Pt(200.0, 0.0), Pt(203.0, 0.0)),
        ]))
        stack = SnapshotStack(model)
        stack.push_load()
        q = ApplyQueue(model, stack)
        q.enqueue(_pending("e1", "e2"))
        q.enqueue(_pending("e5", "e6"))
        applied, skips = q.apply_all()
        assert applied == 2 and skips == []
        assert len(model.state.dogbones) == 2
        # click order preserved: first queued dogbone is e1/e2
        assert model.state.dogbones[0].edge1_eid == "e1"
        assert model.state.dogbones[1].edge1_eid == "e5"
        # exactly ONE snapshot pushed per batch (pre-batch state)
        assert len(stack) == 2  # load + one pre-batch
        pre = stack._stack[-1]
        assert pre.dogbones == []

    def test_queue_empty_apply_all_noop(self):
        model = Model(_state(_corner_a_prims()))
        stack = SnapshotStack(model)
        stack.push_load()
        q = ApplyQueue(model, stack)
        applied, skips = q.apply_all()
        assert applied == 0 and skips == []
        assert len(stack) == 1  # only the load seed
        assert not model.state.dogbones


class TestApplyQueueWarnSkip:
    def test_queue_overlap_true_refused_and_skipped_verbatim(self):
        """DoD: overlap-true refused; warn-and-skip carries the engine
        string verbatim; the skipped corner is dropped."""
        model = Model(_state(_corner_b_prims(-0.01)))
        stack = SnapshotStack(model)
        stack.push_load()
        q = ApplyQueue(model, stack)
        # corner A applies fine standalone
        res_a = place_corner(model.state.primitives, "e1", "e2", Side(+1),
                             1.5875, set(), [], side_flip=+1)
        assert res_a.ok
        q.enqueue(_pending("e1", "e2"))
        q.enqueue(_pending("e3", "e4"))
        applied, skips = q.apply_all()
        assert applied == 1
        assert len(skips) == 1
        assert skips[0] == (
            "OVERLAP: dogbone circle overlaps existing dogbone db-e1+e2 "
            "(strict with EPS_COINCIDE; tangent circles are allowed)"
        )
        assert len(model.state.dogbones) == 1
        assert not q.queue  # skipped corner dropped

    def test_queue_overlap_tangent_passes(self):
        """DoD: tangent circles pass — both corners apply."""
        model = Model(_state(_corner_b_prims(0.0)))
        stack = SnapshotStack(model)
        stack.push_load()
        q = ApplyQueue(model, stack)
        q.enqueue(_pending("e1", "e2"))
        q.enqueue(_pending("e3", "e4"))
        applied, skips = q.apply_all()
        assert applied == 2, skips
        assert skips == []
        assert len(model.state.dogbones) == 2

    def test_queue_snapshot_only_when_first_mutation(self):
        """A batch where every pending is refused pushes NO snapshot."""
        model = Model(_state(_corner_a_prims()))
        stack = SnapshotStack(model)
        stack.push_load()
        q = ApplyQueue(model, stack)
        # same edge twice: UNKNOWN/parallel refusal at re-place
        q.enqueue(_pending("e1", "e1"))
        applied, skips = q.apply_all()
        assert applied == 0
        assert len(skips) == 1
        assert len(stack) == 1  # load seed only — nothing was mutated

    def test_queue_unknown_edge_skipped_verbatim(self):
        model = Model(_state(_corner_a_prims()))
        stack = SnapshotStack(model)
        stack.push_load()
        q = ApplyQueue(model, stack)
        q.enqueue(_pending("e1", "gone"))
        applied, skips = q.apply_all()
        assert applied == 0 and len(skips) == 1
        assert "UNKNOWN_EDGE" in skips[0]


class TestApplyQueueSnapshots:
    def test_queue_undo_restores_pre_batch_exact(self):
        """snapshot -> apply n -> undo -> state-equals-pre-apply (FULL
        ModelState equality incl. flag_decisions)."""
        model = Model(_state(_corner_b_prims(0.0) + [
            Seg("e5", Pt(200.0, 0.0), Pt(200.0, -10.0)),
            Seg("e6", Pt(200.0, 0.0), Pt(203.0, 0.0)),
        ]))
        stack = SnapshotStack(model)
        stack.push_load()
        model.state.flag_decisions["e1"] = "keep"
        pre = model.snapshot()
        q = ApplyQueue(model, stack)
        q.enqueue(_pending("e1", "e2"))
        q.enqueue(_pending("e5", "e6"))
        applied, skips = q.apply_all()
        assert applied == 2 and skips == []
        assert stack.undo()
        assert model.state == pre
        assert model.state.flag_decisions == {"e1": "keep"}

    def test_queue_undo_at_bottom_disabled_not_crashed(self):
        model = Model(_state(_corner_a_prims()))
        stack = SnapshotStack(model)
        stack.push_load()
        q = ApplyQueue(model, stack)
        q.enqueue(_pending("e1", "e2"))
        applied, _ = q.apply_all()
        assert applied == 1
        assert stack.undo()          # pre-batch
        assert stack.undo()          # load snapshot (original)
        bottom = model.snapshot()
        assert not stack.can_undo()
        assert not stack.undo()      # disabled, not crashed
        assert model.state == bottom

    def test_queue_revert_clears_flags_keeps_pendings(self):
        """Revert keeps the pending queue (eids stable; re-placed at
        use) but clears flag_decisions (ADR-009)."""
        model = Model(_state(_corner_a_prims()))
        stack = SnapshotStack(model)
        stack.push_load()
        original = model.snapshot()
        model.state.flag_decisions["e1"] = "keep"
        q = ApplyQueue(model, stack)
        q.enqueue(_pending("e1", "e2"))
        applied, _ = q.apply_all()
        assert applied == 1
        q.enqueue(_pending("e1", "e2"))  # a new pending after apply
        stack.revert()
        assert model.state == original
        assert model.state.flag_decisions == {}
        assert not stack.can_undo()
        assert len(q.queue) == 1  # queue survived the revert


class TestApplyQueueReplacesLive:
    def test_queue_replaces_live_not_stale(self):
        """ADR-016(k): two queued corners that OVERLAP each other — the
        second must see the first (live dogbones list) and skip. Uses
        the overlapping-pair fixture (e1/e2 then e3/e4 at dx=-0.01)."""
        model = Model(_state(_corner_b_prims(-0.01)))
        stack = SnapshotStack(model)
        stack.push_load()
        q = ApplyQueue(model, stack)
        q.enqueue(_pending("e1", "e2"))
        q.enqueue(_pending("e3", "e4"))
        applied, skips = q.apply_all()
        assert applied == 1
        assert len(skips) == 1
        assert "OVERLAP" in skips[0]

    def test_queue_pending_flag_at_replace_skipped(self):
        """Decision 2: new pending flags surfacing at Apply-All
        re-place -> warn-and-skip (flag flow completes first)."""
        from geometry.entities import (
            Circ, Flag, CornerResult, Dogbone, Arc,
        )

        model = Model(_state(_corner_a_prims()))
        stack = SnapshotStack(model)
        stack.push_load()
        q = ApplyQueue(model, stack)

        def scripted_place(pending):
            arc = Arc(eid="arc-pending-x", center=Pt(1.0, 1.0), r=1.0,
                      start_deg=0.0, end_deg=180.0)
            db = Dogbone(db_id=pending.db_id, apex=Pt(0.0, 0.0),
                         center=Pt(1.0, 1.0), r=pending.r,
                         side=pending.side, edge1_eid=pending.edge1_eid,
                         edge2_eid=pending.edge2_eid, arc=arc)
            return CornerResult(
                ok=True, dogbone=db, deletions=[], trims=[], rebuilt=[],
                refusals=[],
                flags=[Flag("C1", "CIRCLE_IN_WINDOW",
                            frozenset({"delete", "keep"}), None)],
            )

        q._place = scripted_place
        q.enqueue(_pending("e1", "e2"))
        applied, skips = q.apply_all()
        assert applied == 0
        assert len(skips) == 1
        assert "awaiting decision" in skips[0]
        assert not model.state.dogbones
        assert len(stack) == 1  # no snapshot pushed — nothing applied