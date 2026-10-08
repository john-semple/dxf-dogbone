"""model.apply_edit — ADR-025 mutation tests.

Covers: trim applied to the entity (coordinates replaced, eid/everything
else preserved), stray deletion (primitives gone, fold_eids scrubed,
flag_decisions scrubbed), trimmed fold KEEPS designation, missing-eid
assertions, refusal (res.ok=False) raises, MTEXT/POINT never touched,
snapshot round-trip (undo restores pre-edit state).
"""
from __future__ import annotations

import pytest

from geometry.entities import (
    EditResult,
    PointEnt,
    Pt,
    Seg,
    TextEnt,
    Trim,
)
from model.model import Model
from model.state import ModelState


def _state(*ents, fold_eids=(), next_seq=1):
    st = ModelState()
    st.primitives = list(ents)
    st.fold_eids = set(fold_eids)
    st.next_seq = next_seq
    return st


def test_model_apply_edit_trim_replaces_endpoints():
    l1 = Seg(eid="L1", a=Pt(0, 0), b=Pt(20, 0))
    l2 = Seg(eid="L2", a=Pt(10, -5), b=Pt(10, 5))
    m = Model(_state(l1, l2))
    res = EditResult(
        ok=True, reason=None, deletions=[],
        trims=[Trim(eid="promoted-L1",
                    old=(Pt(0, 0), Pt(20, 0)),
                    new=(Pt(0, 0), Pt(10, 0)))],
    )
    m.apply_edit(res)
    got = m.get("L1")
    assert got is not None and isinstance(got, Seg)
    assert got.a == Pt(0, 0) and got.b == Pt(10, 0)
    # the other entity untouched
    assert m.get("L2") == l2
    # order preserved
    assert [e.eid for e in m.state.primitives] == ["L1", "L2"]


def test_model_apply_edit_stray_deletion_scrubs_all_sets():
    s1 = Seg(eid="S1", a=Pt(0, 0), b=Pt(20, 0))
    other = Seg(eid="OK", a=Pt(0, 50), b=Pt(20, 50))
    st = _state(s1, other, fold_eids={"S1", "OK"})
    st.flag_decisions["S1"] = "delete"
    st.flag_decisions["OK"] = "keep"
    m = Model(st)
    res = EditResult(ok=True, reason=None, deletions=["S1"], trims=[])
    m.apply_edit(res)
    assert m.get("S1") is None
    assert m.get("OK") is not None
    assert m.state.fold_eids == {"OK"}  # scrubed
    assert m.state.flag_decisions == {"OK": "keep"}  # scrubed


def test_model_apply_edit_trim_keeps_fold_designation():
    """A trimmed fold keeps its eid and designation (ADR-025: deletions
    scrub, trims keep)."""
    f1 = Seg(eid="F1", a=Pt(0, 0), b=Pt(20, 0))
    m = Model(_state(f1, fold_eids={"F1"}))
    res = EditResult(
        ok=True, reason=None, deletions=[],
        trims=[Trim(eid="promoted-F1",
                    old=(Pt(0, 0), Pt(20, 0)),
                    new=(Pt(0, 0), Pt(10, 0)))],
    )
    m.apply_edit(res)
    assert "F1" in m.state.fold_eids
    assert m.get("F1").b == Pt(10, 0)


def test_model_apply_edit_missing_deletion_raises():
    m = Model(_state(Seg(eid="L1", a=Pt(0, 0), b=Pt(1, 1))))
    res = EditResult(ok=True, reason=None, deletions=["GHOST"], trims=[])
    with pytest.raises(ValueError, match="not in primitives"):
        m.apply_edit(res)


def test_model_apply_edit_missing_trim_eid_raises():
    m = Model(_state(Seg(eid="L1", a=Pt(0, 0), b=Pt(1, 1))))
    res = EditResult(
        ok=True, reason=None, deletions=[],
        trims=[Trim(eid="GHOST", old=(Pt(0, 0), Pt(1, 1)),
                    new=(Pt(0, 0), Pt(2, 2)))],
    )
    with pytest.raises(ValueError, match="GHOST"):
        m.apply_edit(res)


def test_model_apply_edit_refusal_raises():
    m = Model(_state(Seg(eid="L1", a=Pt(0, 0), b=Pt(1, 1))))
    res = EditResult(ok=False, reason="NO_TARGET", deletions=[], trims=[])
    with pytest.raises(ValueError, match="res.ok"):
        m.apply_edit(res)


def test_model_apply_edit_snapshot_undo_roundtrip():
    """apply_edit is snapshot-compatible: push → apply → undo restores."""
    from model.snapshots import SnapshotStack

    l1 = Seg(eid="L1", a=Pt(0, 0), b=Pt(20, 0))
    m = Model(_state(l1, Seg(eid="T", a=Pt(10, -5), b=Pt(10, 5))))
    stack = SnapshotStack(m)
    stack.push_load()
    stack.push()
    m.apply_edit(EditResult(
        ok=True, reason=None, deletions=[],
        trims=[Trim(eid="promoted-L1",
                    old=(Pt(0, 0), Pt(20, 0)),
                    new=(Pt(0, 0), Pt(10, 0)))]))
    assert m.get("L1").b == Pt(10, 0)
    assert stack.undo()
    assert m.get("L1").b == Pt(20, 0)  # restored


def test_model_apply_edit_point_and_text_untouched():
    l1 = Seg(eid="L1", a=Pt(0, 0), b=Pt(20, 0))
    pt = PointEnt(eid="P1", p=Pt(5, 5))
    tx = TextEnt(eid="TX", p=Pt(7, 7), text="note")
    m = Model(_state(l1, pt, tx))
    m.apply_edit(EditResult(
        ok=True, reason=None, deletions=[],
        trims=[Trim(eid="promoted-L1",
                    old=(Pt(0, 0), Pt(20, 0)),
                    new=(Pt(0, 0), Pt(10, 0)))]))
    assert m.get("P1") == pt
    assert m.get("TX") == tx