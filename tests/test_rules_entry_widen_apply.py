"""ADR-032 — apply mints throat + arc atomically; undo restores."""
from __future__ import annotations

from geometry.entities import Seg
from model.model import Model
from model.snapshots import SnapshotStack
from rules.engine import ENTRY_WIDENED
from tests.test_rules_entry_widen_geometry import _acute_notch, _place_air


def test_rules_entry_widen_apply_mints_throat_atomic_undo():
    prims, _ = _acute_notch(40.0)
    res = _place_air(prims)
    assert res.ok and res.dogbone is not None and res.dogbone.throat is not None
    assert ENTRY_WIDENED in res.warnings

    m = Model()
    m.state.primitives = list(prims)
    m.state.next_seq = 1
    stack = SnapshotStack(m)
    stack.push_load()
    stack.push()

    m.apply_corner(res)
    eids = {e.eid for e in m.state.primitives}
    db = m.state.dogbones[0]
    assert db.throat is not None
    assert db.arc.eid in eids
    assert db.throat[0].eid in eids
    assert db.throat[1].eid in eids
    assert db.arc.eid.startswith("n")
    assert all(t.eid.startswith("n") for t in db.throat)
    # three new entities minted (arc + 2 throat)
    assert m.state.next_seq == 4

    assert stack.undo()
    assert m.state.dogbones == []
    assert not any(
        isinstance(e, Seg) and e.eid.startswith("n") for e in m.state.primitives
    )
