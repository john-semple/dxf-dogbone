"""M2.2 brief item 3 — resolve_edge walks the chain from the seed, not the
seed's midpoint (mathematician's X-crossing defect, probe-confirmed).

Old behavior: after the iterative seed lookup, resolve_edge re-derived the
run via promoted_edge_at(seed MIDPOINT) — a proximity PICK. If a
non-collinear entity passes within eps_pick of that midpoint, the pick
returns the WRONG entity and the engine falsely refuses UNKNOWN_EDGE.

Fix (brief, binding): call chain_run(primitives, seed, eps_coincide)
directly after the seed lookup and drop the pick step; keep the
seed-membership guard.

Regressions: (1) an X-crossing entity passing through the seed's midpoint;
(2) a stub crossing a bar at the bar's midpoint (both directions).
"""
from geometry.entities import Pt, Seg, Side
from rules.engine import place_corner, resolve_edge

EPS = 1e-3


def seg(eid, a, b):
    return Seg(eid, Pt(*a), Pt(*b))


def test_resolve_edge_x_crossing_at_seed_midpoint():
    # BAR (0,0)->(20,0); CROSS passes exactly through BAR's midpoint (10,0)
    # within any eps_pick — the old midpoint re-pick could latch onto CROSS.
    prims = [
        seg("BAR", (0.0, 0.0), (20.0, 0.0)),
        seg("CROSS", (10.0, -5.0), (10.0, 5.0)),
    ]
    out = resolve_edge(prims, "BAR", EPS)
    assert out is not None, "X-crossing at the seed midpoint must not break resolution"
    run, seed = out
    assert run.eid in ("BAR", "promoted-BAR")
    assert seed.eid == "BAR"
    assert (run.members or (run.eid,)) == ("BAR",)
    # the crossing entity must never be absorbed into the run
    assert "CROSS" not in (run.members or ())
    # mirror direction: resolving CROSS from ITS midpoint (BAR crosses it)
    out2 = resolve_edge(prims, "CROSS", EPS)
    assert out2 is not None
    assert "BAR" not in (out2[0].members or ())


def test_resolve_edge_stub_crossing_bar_at_bar_midpoint():
    # STUB's midpoint lies ON BAR (a T-pair): resolving BAR must not latch
    # onto STUB and resolving STUB must not latch onto BAR.
    prims = [
        seg("BAR", (0.0, 0.0), (20.0, 0.0)),
        seg("STUB", (10.0, 0.0), (10.0, 8.0)),
    ]
    out_bar = resolve_edge(prims, "BAR", EPS)
    assert out_bar is not None
    assert out_bar[1].eid == "BAR"
    assert "STUB" not in (out_bar[0].members or ())
    out_stub = resolve_edge(prims, "STUB", EPS)
    assert out_stub is not None
    assert out_stub[1].eid == "STUB"
    assert "BAR" not in (out_stub[0].members or ())


def test_place_corner_unknown_edge_false_refusal_gone():
    # End-to-end: place_corner must NOT refuse UNKNOWN_EDGE when a
    # non-collinear X crosses the seed's midpoint. Mechanism (old code):
    # the midpoint re-pick is first-wins on ties — X comes FIRST in
    # primitives and passes exactly through BAR's midpoint (10, 0), so the
    # pick latches X; the membership guard then fails and the engine
    # falsely refuses UNKNOWN_EDGE: BAR.
    prims = [
        seg("X", (5.0, -5.0), (15.0, 5.0)),      # crosses (10, 0) = BAR mid
        seg("BAR", (0.0, 0.0), (20.0, 0.0)),
        seg("VERT", (10.0, -4.0), (10.0, 8.0)),  # apex interior (T-cap)
    ]
    res = place_corner(
        prims, "BAR", "VERT", Side(-1), 1.0, set(), [], side_flip=+1
    )
    assert res.ok, res.refusals
    assert res.refusals == []
    # X is tangent to the dogbone circle -> truth-table no-op row
    assert "X" not in res.deletions
    assert not any(f.eid == "X" for f in res.flags)


def test_place_corner_unknown_edge_still_fires_for_missing_eid():
    prims = [seg("BAR", (0.0, 0.0), (20.0, 0.0))]
    res = place_corner(
        prims, "BAR", "NOPE", Side(-1), 1.0, set(), [], side_flip=+1
    )
    assert not res.ok
    assert res.refusals == ["UNKNOWN_EDGE: NOPE is not resolvable in primitives"]