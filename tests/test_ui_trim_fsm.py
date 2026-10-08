"""ui/trim_panel.py — headless TrimFSM tests (ADR-025(d)).

Drives the canvas-free FSM directly with fake ports (no tkinter).
Covers: enter/exit, pick → pending preview, refusal toast + stay, confirm
applies (live re-propose), confirm after refusal returns None, exit
clears pick, stray-delete preview surfaces the delete inline message.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from geometry.entities import EditResult, Pt, Seg, Trim
from ui.trim_panel import TrimFSM, TrimMode
import ui.messages as msg


def _seg(eid, ax, ay, bx, by):
    return Seg(eid=eid, a=Pt(ax, ay), b=Pt(bx, by))


@dataclass
class FakePorts:
    primitives: list = field(default_factory=list)
    refusals: dict = field(default_factory=dict)   # eid -> EditResult (not ok)
    results: dict = field(default_factory=dict)    # eid -> EditResult (ok)
    applied: list = field(default_factory=list)
    picked: Seg | None = None

    def pick_edge(self, p_world: Pt) -> Seg | None:
        return self.picked

    def propose(self, p_world: Pt, eid: str) -> EditResult:
        if eid in self.refusals:
            return self.refusals[eid]
        if eid in self.results:
            return self.results[eid]
        return EditResult(ok=False, reason="NO_TARGET: no supporting-geometry intersection found",
                          deletions=[], trims=[])

    def apply(self, res: EditResult) -> None:
        self.applied.append(res)


def _ok_trim(eid="promoted-L1", new_b=Pt(10, 0)):
    return EditResult(
        ok=True, reason=None, deletions=[],
        trims=[Trim(eid=eid, old=(Pt(0, 0), Pt(20, 0)),
                    new=(Pt(0, 0), new_b))],
    )


def _ok_stray(eids=("S1",)):
    return EditResult(ok=True, reason=None, deletions=list(eids), trims=[])


def test_trim_fsm_enter_exit():
    fsm = TrimFSM(ports=FakePorts())
    assert fsm.mode == TrimMode.OFF
    fsm.enter()
    assert fsm.mode == TrimMode.ON
    assert fsm.status == msg.TRIM_MODE_ENTER
    fsm.exit()
    assert fsm.mode == TrimMode.OFF
    assert fsm.status == msg.TRIM_MODE_EXIT
    assert fsm.picked_eid is None and fsm.pending is None


def test_trim_fsm_click_picks_and_proposes():
    ports = FakePorts(picked=_seg("promoted-L1", 0, 0, 20, 0),
                      results={"promoted-L1": _ok_trim()})
    fsm = TrimFSM(ports=ports)
    fsm.enter()
    fsm.click_world(Pt(19.9, 0.05))
    assert fsm.picked_eid == "promoted-L1"
    assert fsm.pending is not None and fsm.pending.ok
    assert fsm.status == msg.TRIM_PREVIEW_STATUS


def test_trim_fsm_click_off_mode_is_noop():
    ports = FakePorts(picked=_seg("promoted-L1", 0, 0, 20, 0),
                      results={"promoted-L1": _ok_trim()})
    fsm = TrimFSM(ports=ports)
    fsm.click_world(Pt(19.9, 0.05))  # mode OFF: nothing happens
    assert fsm.picked_eid is None and fsm.pending is None


def test_trim_fsm_pick_miss_stays():
    ports = FakePorts(picked=None)
    fsm = TrimFSM(ports=ports)
    fsm.enter()
    fsm.click_world(Pt(50, 50))
    assert fsm.picked_eid is None and fsm.pending is None


def test_trim_fsm_refusal_toast_and_stay():
    ports = FakePorts(picked=_seg("promoted-L1", 0, 0, 20, 0),
                      refusals={"promoted-L1": EditResult(
                          ok=False,
                          reason="NO_TARGET: no supporting-geometry intersection found",
                          deletions=[], trims=[])})
    fsm = TrimFSM(ports=ports)
    fsm.enter()
    fsm.click_world(Pt(19.9, 0.05))
    assert fsm.picked_eid is None  # cleared
    assert fsm.pending is None
    assert fsm.inline is not None and "NO_TARGET" in fsm.inline
    assert fsm.status == msg.TRIM_PICK_STATUS  # stayed in pick


def test_trim_fsm_confirm_applies_via_live_repropose():
    ports = FakePorts(picked=_seg("promoted-L1", 0, 0, 20, 0),
                      results={"promoted-L1": _ok_trim()})
    fsm = TrimFSM(ports=ports)
    fsm.enter()
    fsm.click_world(Pt(19.9, 0.05))
    res = fsm.confirm()
    assert res is not None and res.ok
    assert len(ports.applied) == 1
    assert fsm.applied_count == 1
    assert fsm.picked_eid is None and fsm.pending is None
    assert msg.TRIM_TOAST_APPLIED in fsm.status


def test_trim_fsm_confirm_after_refusal_returns_none():
    ports = FakePorts(picked=_seg("promoted-L1", 0, 0, 20, 0),
                      results={"promoted-L1": _ok_trim()},
                      refusals={})
    fsm = TrimFSM(ports=ports)
    fsm.enter()
    # no pick yet: confirm is a no-op
    assert fsm.confirm() is None
    assert ports.applied == []


def test_trim_fsm_confirm_refused_at_repropose_drops_pending():
    """ADR-016(k) discipline: the re-propose at confirm runs against the
    live model; a refusal there cancels with a toast (never a stale
    apply)."""
    ports = FakePorts(picked=_seg("promoted-L1", 0, 0, 20, 0),
                      results={"promoted-L1": _ok_trim()})
    fsm = TrimFSM(ports=ports)
    fsm.enter()
    fsm.click_world(Pt(19.9, 0.05))
    # the model changed under us: the re-propose now refuses
    ports.results.clear()
    ports.refusals["promoted-L1"] = EditResult(
        ok=False, reason="NO_TARGET: no supporting-geometry intersection found",
        deletions=[], trims=[])
    res = fsm.confirm()
    assert res is None
    assert ports.applied == []
    assert fsm.pending is None
    assert "NO_TARGET" in (fsm.inline or "")


def test_trim_fsm_span_delete_preview_inline():
    """A both-sides span deletion uses the span sentence, not the stray one."""
    from rules.manual_edit import SPAN_DELETE_WARNING
    span = EditResult(
        ok=True, reason=None, deletions=["L1"], trims=[],
        warnings=[SPAN_DELETE_WARNING])
    ports = FakePorts(picked=_seg("promoted-L1", 0, 0, 10, 0),
                      results={"promoted-L1": span})
    fsm = TrimFSM(ports=ports)
    fsm.enter()
    fsm.click_world(Pt(5.0, 0.0))
    assert fsm.pending is not None and fsm.pending.deletions == ["L1"]
    assert fsm.inline == msg.TRIM_PREVIEW_SPAN_DELETE
    assert fsm.inline != msg.TRIM_PREVIEW_DELETE
    res = fsm.confirm()
    assert res is not None and res.deletions == ["L1"]
    assert msg.TRIM_SPAN_DELETE_APPLIED in fsm.status
    assert msg.TRIM_DELETE_APPLIED not in fsm.status


def test_trim_fsm_stray_delete_preview_inline():
    ports = FakePorts(picked=_seg("promoted-S1", 0, 0, 20, 0),
                      results={"promoted-S1": _ok_stray(("S1",))})
    fsm = TrimFSM(ports=ports)
    fsm.enter()
    fsm.click_world(Pt(10.0, 0.0))
    assert fsm.pending is not None and fsm.pending.ok
    assert fsm.pending.deletions == ["S1"]
    assert fsm.inline == msg.TRIM_PREVIEW_DELETE


def test_trim_fsm_stray_confirm_applies_delete():
    ports = FakePorts(picked=_seg("promoted-S1", 0, 0, 20, 0),
                      results={"promoted-S1": _ok_stray(("S1",))})
    fsm = TrimFSM(ports=ports)
    fsm.enter()
    fsm.click_world(Pt(10.0, 0.0))
    res = fsm.confirm()
    assert res is not None and res.deletions == ["S1"]
    assert msg.TRIM_DELETE_APPLIED in fsm.status


def test_trim_fsm_exit_clears_pending():
    ports = FakePorts(picked=_seg("promoted-L1", 0, 0, 20, 0),
                      results={"promoted-L1": _ok_trim()})
    fsm = TrimFSM(ports=ports)
    fsm.enter()
    fsm.click_world(Pt(19.9, 0.05))
    assert fsm.pending is not None
    fsm.exit()
    assert fsm.pending is None and fsm.picked_eid is None
    assert fsm.mode == TrimMode.OFF


def test_trim_panel_done_button_exits_and_hides():
    import tkinter as tk

    import pytest

    from model.model import Model
    from model.state import ModelState
    from ui.canvas_view import Viewer
    from ui.trim_panel import TrimPanel

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"no display for tkinter: {exc}")
    root.withdraw()
    try:
        viewer = Viewer(root, width=200, height=200)
        model = Model(ModelState(primitives=[
            Seg("L1", Pt(0, 0), Pt(100, 0)),
        ]))
        viewer.set_model(model.state)
        panel = TrimPanel(root, viewer, model)
        assert panel.mode_btn.cget("text") == msg.TRIM_MODE_TOGGLE_ON
        panel.toggle_mode()
        assert panel.fsm.mode == TrimMode.ON
        assert msg.TRIM_MODE_TOGGLE_OFF == "Done"
        assert panel.mode_btn.cget("text") == msg.TRIM_MODE_TOGGLE_OFF
        assert panel._done_btn is not None
        assert panel._done_btn.cget("text") == msg.TRIM_MODE_TOGGLE_OFF
        assert panel._done_btn.winfo_manager() == "place"
        info = panel._done_btn.place_info()
        assert float(info["relx"]) == 0.5
        assert float(info["rely"]) == 1.0
        assert info["anchor"] == "s"
        panel._done_btn.cget("command")()
        assert panel.fsm.mode == TrimMode.OFF
        assert panel.mode_btn.cget("text") == msg.TRIM_MODE_TOGGLE_ON
        assert panel._done_btn.winfo_manager() == ""
    finally:
        root.destroy()
