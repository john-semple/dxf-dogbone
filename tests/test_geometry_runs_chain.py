"""geometry.runs.chain_run — the single promotion walk (ADR-016(f)) and the
filters/runs twin-sync guarantee (the twins diverged once; these tests pin
them together over a corpus).
"""
from __future__ import annotations

import pytest

from geometry.entities import Pt, Seg
from geometry.runs import chain_run, collinear_run_through
from rules.filters import promoted_edge_at


def seg(eid, ax, ay, bx, by, **kw) -> Seg:
    return Seg(eid=eid, a=Pt(ax, ay), b=Pt(bx, by), **kw)


def test_geometry_runs_mixed_direction_symmetric_extent():
    # Round-2 defect: the old filters walk (min of a-proj / max of b-proj)
    # truncated mixed-direction runs; chain_run is symmetric over both.
    a = seg("a", 0, 0, 10, 0)
    b = seg("b", 0, 0, -10, 0)      # stored reversed
    c = seg("c", -10, 0, -20, 0)   # continues west
    result = chain_run([a, b, c], a)
    assert result is not None
    run, ent = result
    assert set(ent) == {"a", "b", "c"}
    # ordered by min projection along the CLICKED seed's direction (a: (1,0),
    # anchored at a.a): c <-20, b <-10, a <0
    assert run.members == ("c", "b", "a")
    assert run.eid == "promoted-c"  # first entity in anchor order
    assert (run.a.x, run.b.x) == (-20.0, 10.0)  # full extent both ways


def test_geometry_runs_keep_seed_eid_for_composite_first():
    comp = seg("promoted-A", 0, 0, 20, 0, members=("A", "B"), pick_eid="A")
    c = seg("C", 20, 0, 30, 0)
    result = chain_run([comp, c], c)
    assert result is not None
    run, ent = result
    # ADR-016(f): the run's first entity is the composite -> its eid is KEPT
    assert run.eid == "promoted-A"
    assert run.members == ("A", "B", "C")
    assert ent == ("promoted-A", "C")


def test_geometry_runs_plain_run_eid_prefixed():
    a = seg("A", 0, 0, 10, 0)
    b = seg("B", 10, 0, 20, 0)
    result = chain_run([a, b], a)
    assert result is not None
    run, ent = result
    assert run.eid == "promoted-A"
    assert ent == ("A", "B")


def test_geometry_runs_degenerate_seed():
    z = seg("Z", 5, 5, 5, 5)
    result = chain_run([z], z)
    assert result is not None
    run, ent = result
    assert run.eid == "promoted-Z" and ent == ("Z",)
    assert run.a == Pt(5, 5) and run.b == Pt(5, 5)


def test_geometry_runs_collinear_run_through_wrapper():
    a = seg("A", 0, 0, 10, 0)
    b = seg("B", 10, 0, 20, 0)
    run = collinear_run_through([a, b], "B")
    assert run is not None
    assert run.eid == "promoted-A" and run.members == ("A", "B")
    assert collinear_run_through([a, b], "nope") is None


# --- twin-sync corpus: filters.promoted_edge_at and the runs walk must agree
# on (eid, extent, members) for every case (ADR-016(e) regression) ---


def _corpus():
    cases = []
    # mixed directions (the round-2 divergence)
    cases.append(("mixed", [
        seg("a", 0, 0, 10, 0), seg("b", 0, 0, -10, 0), seg("c", -10, 0, -20, 0)
    ], Pt(5, 0)))
    # reversed join
    cases.append(("reversed", [seg("A", 0, 0, 10, 0), seg("B", 20, 0, 10, 0)], Pt(5, 0)))
    # chain both directions
    cases.append(("chain", [seg("A", 0, 0, 10, 0), seg("B", 10, 0, 20, 0),
                            seg("C", 20, 0, 30, 0)], Pt(15, 0)))
    # composite + plain continuation (re-promotion)
    cases.append(("repromote", [
        seg("promoted-A", 0, 0, 20, 0, members=("A", "B"), pick_eid="A"),
        seg("C", 20, 0, 30, 0),
    ], Pt(25, 0)))
    # gap stops promotion
    cases.append(("gap", [seg("A", 0, 0, 10, 0), seg("B", 11, 0, 20, 0)], Pt(5, 0)))
    # non-collinear stops promotion
    cases.append(("bend", [seg("A", 0, 0, 10, 0), seg("B", 10, 0, 20, 10)], Pt(5, 0)))
    return cases


@pytest.mark.parametrize("name,prims,click", [c for c in _corpus()])
def test_geometry_runs_twin_sync_corpus(name, prims, click):
    via_filters = promoted_edge_at(prims, click, eps_pick=1.0)
    seed = next(s for s in prims
                if abs(click.x - (s.a.x + s.b.x) / 2) <= 15.0
                and go_dist(click, s) <= 1.0)
    via_runs = collinear_run_through(prims, seed.eid)
    assert (via_filters is None) == (via_runs is None)
    if via_filters is None:
        return
    assert via_filters.eid == via_runs.eid
    assert via_filters.members == via_runs.members
    assert abs(via_filters.a.x - via_runs.a.x) < 1e-9
    assert abs(via_filters.b.x - via_runs.b.x) < 1e-9


def go_dist(p, s):
    import math

    dx, dy = s.b.x - s.a.x, s.b.y - s.a.y
    n2 = dx * dx + dy * dy
    t = max(0.0, min(1.0, ((p.x - s.a.x) * dx + (p.y - s.a.y) * dy) / n2))
    return math.hypot(p.x - (s.a.x + t * dx), p.y - (s.a.y + t * dy))
