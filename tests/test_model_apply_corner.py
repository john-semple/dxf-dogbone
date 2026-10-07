"""Model.apply_corner — ADR-012 reconciliation + ADR-015(c)/(k) (M2)."""
from geometry.entities import Pt, Seg, Side
from model.model import Model
from model.state import ModelState
from rules.engine import place_corner
from rules.filters import promoted_edge_at


def test_model_apply_corner_composite_after_apply():
    # ADR-012 test clause: member eids in results; composite after apply.
    prims = [
        Seg("B8", Pt(45.0, 51.5118), Pt(45.0, -95.0)),
        Seg("63", Pt(124.7552, 51.5168), Pt(44.2484, 51.5168)),
        Seg("B9", Pt(44.2484, 51.5118), Pt(45.0, 51.5118)),
        Seg("BA", Pt(44.2484, 51.5118), Pt(44.2484, 51.5168)),
    ]
    res = place_corner(prims, "B8", "63", Side(-1), 1.5875, set(), [], side_flip=+1)
    assert res.ok
    # results reference member eids (not the composite id)
    assert {rb.eid for rb in res.rebuilt} == {"B8", "63"}

    st = ModelState(primitives=list(prims), next_seq=1)
    m = Model(st)
    m.apply_corner(res)

    got = {e.eid: e for e in m.state.primitives}
    # members replaced by composites; tear stubs deleted
    assert set(got) == {"promoted-B8", "promoted-63", "n1"}
    c1 = got["promoted-B8"]
    assert (round(c1.a.x, 6), round(c1.a.y, 6)) == (45.0, 49.271736)
    assert (round(c1.b.x, 4), round(c1.b.y, 4)) == (45.0, -95.0)
    assert c1.members == ("B8",)
    c2 = got["promoted-63"]
    assert (round(c2.a.x, 4), round(c2.a.y, 4)) == (124.7552, 51.5168)
    assert (round(c2.b.x, 6), round(c2.b.y, 4)) == (47.245064, 51.5168)
    assert c2.members == ("63",)
    # placed arc minted via next_seq; dogbone re-recorded with the minted eid
    arc = got["n1"]
    assert arc.eid == "n1" and abs(arc.r - 1.5875) < 1e-12
    assert m.state.next_seq == 2
    assert len(m.state.dogbones) == 1
    assert m.state.dogbones[0].arc.eid == "n1"
    assert m.state.dogbones[0].db_id == "db-B8+63"


def test_model_apply_corner_flag_decisions_persist():
    prims = [
        Seg("B8", Pt(45.0, 51.5118), Pt(45.0, -95.0)),
        Seg("63", Pt(124.7552, 51.5168), Pt(44.2484, 51.5168)),
        Seg("B9", Pt(44.2484, 51.5118), Pt(45.0, 51.5118)),
        Seg("BA", Pt(44.2484, 51.5118), Pt(44.2484, 51.5168)),
    ]
    res = place_corner(
        prims, "B8", "63", Side(-1), 1.5875, set(), [],
        side_flip=+1, flag_decisions={"BA": "delete"},
    )
    m = Model(ModelState(primitives=list(prims), next_seq=1))
    m.apply_corner(res)
    assert m.state.flag_decisions == {"BA": "delete"}  # ADR-009 sticky


def test_model_snapshot_restore_roundtrip():
    prims = [
        Seg("B8", Pt(45.0, 51.5118), Pt(45.0, -95.0)),
        Seg("63", Pt(124.7552, 51.5168), Pt(44.2484, 51.5168)),
        Seg("B9", Pt(44.2484, 51.5118), Pt(45.0, 51.5118)),
        Seg("BA", Pt(44.2484, 51.5118), Pt(44.2484, 51.5168)),
    ]
    m = Model(ModelState(primitives=list(prims), next_seq=1))
    snap = m.snapshot()
    res = place_corner(prims, "B8", "63", Side(-1), 1.5875, set(), [], side_flip=+1)
    m.apply_corner(res)
    assert len(m.state.primitives) == 3  # 2 composites + arc
    m.restore(snap)
    # deep equality with the original state; ID<->entity mapping preserved
    assert m.state.primitives == prims
    assert m.state.dogbones == []
    assert m.state.next_seq == 1
    # snapshot is a deep copy: mutating after restore does not touch snap
    assert snap is not m.state


def test_model_apply_corner_microsegmented_run_and_repromotion():
    # ADR-012: multi-member run -> one composite; ADR-012(c)/(ADR-016(f)):
    # re-promotion keeps the composite eid and flattens members. The run's
    # canonical eid comes from promoted_edge_at (vertical-down run orders
    # bottom-up -> promoted-m2; ADR-016(g) canonical-eid rule).
    prims = [
        Seg("m1", Pt(0.0, 0.0), Pt(0.0, -5.0)),
        Seg("m2", Pt(0.0, -5.0), Pt(0.0, -10.0)),
        Seg("e2", Pt(0.0, 0.0), Pt(10.0, 0.0)),
    ]
    run = promoted_edge_at(prims, Pt(0.0, -2.5), 1.0)
    assert run is not None and run.eid == "promoted-m2"
    assert run.members == ("m2", "m1")

    res = place_corner(prims, run.eid, "e2", Side(+1), 1.5875, set(), [], side_flip=+1)
    assert res.ok
    rb = {x.eid: x for x in res.rebuilt}
    assert set(rb) == {"m1", "e2"}
    assert abs(rb["m1"].new.y - (-2.245064)) < 1e-6  # x=0 chord depth

    m = Model(ModelState(primitives=list(prims), next_seq=1))
    m.apply_corner(res)
    got = {e.eid: e for e in m.state.primitives}
    assert set(got) == {"promoted-m2", "promoted-e2", "n1"}
    comp = got["promoted-m2"]
    assert comp.members == ("m2", "m1")
    assert (round(comp.a.x, 6), round(comp.a.y, 6)) == (0.0, -2.245064)
    assert (comp.b.x, comp.b.y) == (0.0, -10.0)

    # re-pick the registered composite: ADR-016(f) keep-seed-eid + flattening
    reseg = promoted_edge_at(m.state.primitives, Pt(0.0, -6.0), 1.0)
    assert reseg is not None
    assert reseg.eid == "promoted-m2"  # composite eid kept, never re-prefixed
    assert reseg.members == ("m2", "m1")


def test_model_apply_corner_rejects_noncanonical_edge_label():
    # ADR-016(g): a caller forwarding a label that disagrees with the
    # canonical run eid fails loudly (never two ids for one line)
    prims = [
        Seg("m1", Pt(0.0, 0.0), Pt(0.0, -5.0)),
        Seg("m2", Pt(0.0, -5.0), Pt(0.0, -10.0)),
        Seg("e2", Pt(0.0, 0.0), Pt(10.0, 0.0)),
    ]
    res = place_corner(prims, "m1", "e2", Side(+1), 1.5875, set(), [], side_flip=+1)
    assert res.ok
    m = Model(ModelState(primitives=list(prims), next_seq=1))
    try:
        m.apply_corner(res)  # res.dogbone.edge1_eid == "m1" (non-canonical)
        raise AssertionError("expected ValueError")
    except ValueError as e:
        assert "canonical run eid" in str(e)


def test_model_apply_corner_rejects_bad_results():
    from geometry.entities import CornerResult

    m = Model(ModelState(next_seq=1))
    bad = CornerResult(ok=False, dogbone=None, deletions=[], trims=[], rebuilt=[], refusals=["x"], flags=[])
    try:
        m.apply_corner(bad)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
