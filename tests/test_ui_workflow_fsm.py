"""ui.workflow state machine — headless unit tests (M3 brief DoD).

The FSM is canvas-free by construction: these tests drive (state, event)
transitions with a fake ports object, no tkinter anywhere. Covers: pick
flow, same-edge stay, ghost-pick → preview, refusals verbatim, flag
prompting + sticky decisions, confirm-gate, Esc restart, summary format.
"""
from __future__ import annotations

import pytest

from geometry.entities import CornerResult, Flag, Pt, Refusal, Seg, Side
import ui.messages as msg
from ui.workflow import GhostMark, PendingCorner, WorkflowFSM, WorkflowState


def seg(eid: str, x1: float, y1: float, x2: float, y2: float) -> Seg:
    return Seg(eid=eid, a=Pt(x1, y1), b=Pt(x2, y2))


CORNER_A = seg("A", 0.0, 0.0, 0.0, 10.0)
CORNER_B = seg("B", 0.0, 0.0, 10.0, 0.0)


class FakePorts:
    """Scripted ports: pick results and preview results per test."""

    def __init__(self, picks: list[Seg | None], previews: list[CornerResult],
                 ghosts=None, flags_policies: dict[str, str] | None = None):
        self.picks = list(picks)
        self.previews = list(previews)
        self._last_preview: CornerResult | None = None
        self._ghosts = ghosts
        self.applied: list[CornerResult] = []
        self.flag_calls: list[str] = []
        self.policies = dict(flags_policies or {})

    def pick_edge(self, p_world: Pt) -> Seg | None:
        return self.picks.pop(0) if self.picks else None

    def ghosts(self, edge1_eid: str, edge2_eid: str, r: float):
        if self._ghosts is not None:
            return self._ghosts
        return [(Side(+1), +1, Pt(1.0, 1.0)), (Side(+1), -1, Pt(-1.0, -1.0)),
                (Side(-1), +1, Pt(2.0, 2.0)), (Side(-1), -1, Pt(-2.0, -2.0))]

    def place_preview(self, pending: PendingCorner) -> CornerResult:
        # ADR-016(k): confirm() re-places live — replay the scripted tail
        # when the queue runs dry so single-result tests still cover the
        # re-place path.
        if self.previews:
            self._last_preview = self.previews.pop(0)
        assert self._last_preview is not None, "place_preview: no script"
        return self._last_preview

    def decide_flag(self, flag: Flag, kind: str) -> str | None:
        self.flag_calls.append(flag.eid)
        return self.policies.get(flag.eid, "delete")

    def apply(self, res: CornerResult) -> None:
        self.applied.append(res)

    def radius(self) -> float:
        return 1.5875


def ok_result(flags: list[Flag] | None = None) -> CornerResult:
    from geometry.entities import Arc, Dogbone
    arc = Arc(eid="arc-pending-db-A+B", center=Pt(1.0, 1.0), r=1.5875,
              start_deg=0.0, end_deg=180.0)
    db = Dogbone(db_id="db-A+B", apex=Pt(0.0, 0.0), center=Pt(1.0, 1.0),
                 r=1.5875, side=Side(+1), edge1_eid="A", edge2_eid="B",
                 arc=arc)
    return CornerResult(ok=True, dogbone=db, deletions=["X"], trims=[],
                        rebuilt=[], refusals=[], flags=flags or [])


def refused_result(*reasons: str) -> CornerResult:
    return CornerResult(ok=False, dogbone=None, deletions=[], trims=[],
                        rebuilt=[], refusals=list(reasons), flags=[])


# ---------------------------------------------------------------- transitions


def test_fsm_start_then_two_edge_clicks_reach_ghosts():
    fsm = WorkflowFSM(ports=FakePorts(picks=[CORNER_A, CORNER_B],
                                      previews=[]))
    assert fsm.state == WorkflowState.IDLE
    fsm.start()
    assert fsm.state == WorkflowState.PICK_EDGE1
    fsm.click_world(Pt(0.1, 5.0))
    assert fsm.state == WorkflowState.PICK_EDGE2
    assert fsm.edge1_eid == "A"
    assert fsm.inline == msg.PROMOTED_FLASH.format(eid="A")
    fsm.click_world(Pt(5.0, 0.1))
    assert fsm.state == WorkflowState.GHOSTS_VISIBLE
    assert len(fsm.ghosts) == 4  # ADR-015(m): four rays
    assert fsm.edge2_eid == "B"


def test_fsm_miss_click_keeps_state():
    fsm = WorkflowFSM(ports=FakePorts(picks=[None, CORNER_A], previews=[]))
    fsm.start()
    fsm.click_world(Pt(50.0, 50.0))
    assert fsm.state == WorkflowState.PICK_EDGE1
    fsm.click_world(Pt(0.0, 1.0))
    assert fsm.state == WorkflowState.PICK_EDGE2


def test_fsm_same_edge_twice_inline_and_stay():
    fsm = WorkflowFSM(ports=FakePorts(picks=[CORNER_A, CORNER_A, CORNER_B],
                                      previews=[]))
    fsm.start()
    fsm.click_world(Pt(0.0, 1.0))
    fsm.click_world(Pt(0.0, 2.0))
    # same edge twice: inline message, STAY in PICK_EDGE2 (brief item 4)
    assert fsm.state == WorkflowState.PICK_EDGE2
    assert fsm.inline == msg.SAME_EDGE_INLINE
    assert fsm.edge2_eid is None
    fsm.click_world(Pt(1.0, 0.0))
    assert fsm.state == WorkflowState.GHOSTS_VISIBLE


def test_fsm_ghost_refusal_verbatim_and_stay_pick_edge2():
    reason = ("SHALLOW: corner half-angle 5.000 deg outside "
              "[15.000, 165.000] (near-collinear edges)")
    fsm = WorkflowFSM(ports=FakePorts(
        picks=[CORNER_A, CORNER_B], previews=[],
        ghosts=Refusal(reason),
    ))
    fsm.start()
    fsm.click_world(Pt(0.0, 1.0))
    fsm.click_world(Pt(1.0, 0.0))
    assert fsm.state == WorkflowState.PICK_EDGE2
    assert fsm.refusals == [reason]
    assert reason in fsm.inline  # engine string verbatim in the toast


def test_fsm_pick_ghost_places_preview():
    fsm = WorkflowFSM(ports=FakePorts(picks=[CORNER_A, CORNER_B],
                                      previews=[ok_result()]))
    fsm.start()
    fsm.click_world(Pt(0.0, 1.0))
    fsm.click_world(Pt(1.0, 0.0))
    assert fsm.state == WorkflowState.GHOSTS_VISIBLE
    fsm.pick_ghost(Side(+1), +1)
    assert fsm.state == WorkflowState.SIDE_PICKED
    assert fsm.preview is not None and fsm.preview.ok
    assert fsm.pending is not None
    assert fsm.pending.side == Side(+1)
    assert fsm.pending.side_flip == +1


def test_fsm_preview_refusal_returns_to_ghosts_verbatim():
    reason = ("APEX_GATE: apex lies 99.0000 from edge A and 99.0000 from "
              "edge B; limit K*R = 7.9375")
    fsm = WorkflowFSM(ports=FakePorts(picks=[CORNER_A, CORNER_B],
                                      previews=[refused_result(reason)]))
    fsm.start()
    fsm.click_world(Pt(0.0, 1.0))
    fsm.click_world(Pt(1.0, 0.0))
    fsm.pick_ghost(Side(+1), +1)
    assert fsm.state == WorkflowState.GHOSTS_VISIBLE
    assert fsm.refusals == [reason]
    assert reason in fsm.inline
    # another ghost can be tried
    fsm.ports.previews.append(ok_result())  # type: ignore[attr-defined]
    fsm.pick_ghost(Side(-1), -1)
    assert fsm.state == WorkflowState.SIDE_PICKED


def test_fsm_confirm_applies_and_restarts_to_idle():
    ports = FakePorts(picks=[CORNER_A, CORNER_B], previews=[ok_result()])
    fsm = WorkflowFSM(ports=ports)
    fsm.start()
    fsm.click_world(Pt(0.0, 1.0))
    fsm.click_world(Pt(1.0, 0.0))
    fsm.pick_ghost(Side(+1), +1)
    res = fsm.confirm()
    assert res is not None and res.ok
    assert ports.applied == [res]
    assert fsm.applied_count == 1
    assert fsm.state == WorkflowState.IDLE  # CONFIRMED → IDLE(restart)
    assert fsm.edge1_eid is None and fsm.edge2_eid is None
    assert fsm.pending is None and fsm.preview is None


def test_fsm_confirm_blocked_while_flag_pending():
    pending_flag = Flag("C1", "CIRCLE_IN_WINDOW",
                        frozenset({"delete", "keep"}), None)
    ports = FakePorts(picks=[CORNER_A, CORNER_B],
                     previews=[ok_result([pending_flag])])
    fsm = WorkflowFSM(ports=ports)
    fsm.start()
    fsm.click_world(Pt(0.0, 1.0))
    fsm.click_world(Pt(1.0, 0.0))
    fsm.pick_ghost(Side(+1), +1)
    assert any(f.decision is None for f in fsm.preview.flags)
    res = fsm.confirm()
    assert res is None  # confirm-gate: pending flag blocks (ADR-013)
    assert ports.applied == []
    assert fsm.state == WorkflowState.SIDE_PICKED
    assert "pending" in fsm.inline.lower() or "awaiting" in fsm.inline.lower()


def test_fsm_flag_decision_recompute_unblocks_confirm():
    """ADR-009: decision made → recompute honors it, no re-prompt, confirm
    applies the DECIDED result (delete path)."""
    flag = Flag("C1", "CIRCLE_IN_WINDOW", frozenset({"delete", "keep"}),
                None)
    decided = Flag("C1", "CIRCLE_IN_WINDOW", frozenset({"delete", "keep"}),
                   "delete")
    ports = FakePorts(picks=[CORNER_A, CORNER_B],
                     previews=[ok_result([flag]), ok_result([decided]),
                               ok_result([decided])])
    fsm = WorkflowFSM(ports=ports)
    fsm.start()
    fsm.click_world(Pt(0.0, 1.0))
    fsm.click_world(Pt(1.0, 0.0))
    fsm.pick_ghost(Side(+1), +1)
    # simulate the shell: decide then recompute
    fsm.ports.decide_flag(fsm.preview.flags[0], "CIRCLE")
    fsm.notify_flag_decision()
    assert fsm.preview.flags[0].decision == "delete"
    res = fsm.confirm()  # confirm re-places live (ADR-016(k))
    assert res is not None and res.ok
    assert ports.applied == [res]


def test_fsm_esc_restarts_from_any_state_no_partial_survives():
    fsm = WorkflowFSM(ports=FakePorts(picks=[CORNER_A, CORNER_B] * 2,
                                      previews=[ok_result()]))
    fsm.start()
    fsm.click_world(Pt(0.0, 1.0))
    fsm.click_world(Pt(1.0, 0.0))
    assert fsm.state == WorkflowState.GHOSTS_VISIBLE
    fsm.esc()
    assert fsm.state == WorkflowState.IDLE
    assert fsm.edge1_eid is None and fsm.edge2_eid is None
    assert fsm.ghosts == [] and fsm.pending is None and fsm.preview is None
    # mid-preview restart
    fsm.start()
    fsm.click_world(Pt(0.0, 1.0))
    fsm.click_world(Pt(1.0, 0.0))
    fsm.pick_ghost(Side(+1), +1)
    assert fsm.state == WorkflowState.SIDE_PICKED
    fsm.right_click()
    assert fsm.state == WorkflowState.IDLE
    assert fsm.pending is None and fsm.preview is None


def test_fsm_confirm_ignores_place_refusal_then_applies():
    """Confirm re-places live: a refusal at confirm time surfaces verbatim
    and nothing is applied."""
    reason = "OVERLAP: dogbone circle overlaps existing dogbone db-A+B (strict with EPS_COINCIDE; tangent circles are allowed)"
    ports = FakePorts(picks=[CORNER_A, CORNER_B],
                     previews=[ok_result(), refused_result(reason),
                               ok_result()])
    fsm = WorkflowFSM(ports=ports)
    fsm.start()
    fsm.click_world(Pt(0.0, 1.0))
    fsm.click_world(Pt(1.0, 0.0))
    fsm.pick_ghost(Side(+1), +1)
    out = fsm.confirm()
    assert out is None
    assert ports.applied == []
    assert fsm.state == WorkflowState.GHOSTS_VISIBLE
    assert fsm.refusals == [reason]
    # re-pick a ghost after the refusal: back to preview, then applies
    fsm.pick_ghost(Side(-1), +1)
    assert fsm.state == WorkflowState.SIDE_PICKED
    res = fsm.confirm()
    assert res is not None and res.ok


# ---------------------------------------------------------------- messages


def test_messages_deletion_summary_exact_format():
    s = msg.deletion_summary(2, 1, 1, 1, 1)
    assert s == ("Deleting: 2 LINE, 1 ARC — Trimming: 1 — "
                 "Flagged: 1 CIRCLE, 1 MTEXT")


def test_messages_deletion_summary_zero_terms_verbatim():
    s = msg.deletion_summary(0, 0, 0, 0, 0)
    assert s == ("Deleting: 0 LINE, 0 ARC — Trimming: 0 — "
                 "Flagged: 0 CIRCLE, 0 MTEXT")