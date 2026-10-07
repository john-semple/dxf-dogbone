"""M2.1 flow regressions (ADR-016(b)/(c)/(e)/(g)/(h)) — the flows the review
loop proved broken: composite re-apply, applied-edge protection (resolve-at-use
via canonical eids), mixed-direction place->apply, T-cap shared-edge chain.
"""
from __future__ import annotations

from geometry import geomops as go
from geometry.entities import Pt, Seg, Side
from model.model import Model
from model.state import ModelState
from rules.engine import ghost_candidates, place_corner
from rules.filters import promoted_edge_at


def seg(eid, ax, ay, bx, by, **kw) -> Seg:
    return Seg(eid=eid, a=Pt(ax, ay), b=Pt(bx, by), **kw)


def pick(prims, x, y, eps_pick=1.0):
    p = promoted_edge_at(prims, Pt(x, y), eps_pick)
    assert p is not None, f"pick at ({x},{y}) missed"
    return p


def side_for(prims, e1, e2, r, target):
    gcs = ghost_candidates(prims, e1, e2, r)
    assert not hasattr(gcs, "reason")
    for s, f, c in gcs:
        if go.dist(c, Pt(*target)) < 1e-4:
            return s, f
    raise AssertionError(f"ghost not found near {target}")


def test_model_m21_tcap_shared_edge_reapply():
    # syn-double-tabs style slot mouth: two dogbones consume the shared bar
    # edge (the WE's mandated T-cap flow). Canonical eids throughout.
    prims = [
        seg("t1", 60, 57, 60, 0),      # tab edge at x=60 (down)
        seg("cap", 60, 57, 80, 57),   # shared bar edge
        seg("t2", 80, 57, 80, 0),     # tab edge at x=80 (down)
    ]
    e_t1 = pick(prims, 60, 30).eid    # promoted-t1
    e_cap = pick(prims, 70, 57).eid   # promoted-cap
    assert e_t1 == "promoted-t1" and e_cap == "promoted-cap"

    side, flip = side_for(prims, e_t1, e_cap, 1.5875, (61.122532, 55.877468))
    res_a = place_corner(
        prims, e_t1, e_cap, side, 1.5875, set(), [], side_flip=flip
    )
    assert res_a.ok, res_a.refusals
    m = Model(ModelState(primitives=list(prims), next_seq=1))
    m.apply_corner(res_a)

    got = {e.eid: e for e in m.state.primitives}
    # t2 is untouched by corner A and stays in the model
    assert set(got) == {"promoted-t1", "promoted-cap", "t2", "n1"}
    cap_a = got["promoted-cap"]
    assert (round(cap_a.a.x, 6), round(cap_a.a.y, 4)) == (62.245064, 57.0)
    assert (cap_a.b.x, cap_a.b.y) == (80.0, 57.0)
    assert cap_a.members == ("cap",)

    # re-pick the registered composite: ADR-016(f) keep-seed-eid
    e_cap2 = pick(m.state.primitives, 70, 57).eid
    assert e_cap2 == "promoted-cap"

    e_t2 = pick(m.state.primitives, 80, 30).eid
    assert e_t2 == "promoted-t2"
    side_b, flip_b = side_for(
        m.state.primitives, e_t2, e_cap2, 1.5875, (78.877468, 55.877468)
    )
    res_b = place_corner(
        list(m.state.primitives), e_t2, e_cap2, side_b, 1.5875, set(),
        [m.state.dogbones[0]], side_flip=flip_b,
    )
    assert res_b.ok, res_b.refusals
    assert res_b.deletions == [] and res_b.flags == []  # nothing of A's touched
    # the composite's OWN endpoint moves (owner = the composite eid,
    # ADR-012(c) re-promotion clause)
    assert {rb.eid for rb in res_b.rebuilt} == {"t2", "promoted-cap"}

    m.apply_corner(res_b)
    got = {e.eid: e for e in m.state.primitives}
    # both dogbones consumed the shared edge; the cap eid is KEPT across
    # generations; no "run first member missing" crash
    assert set(got) == {"promoted-t1", "promoted-cap", "promoted-t2", "n1", "n2"}
    cap_b = got["promoted-cap"]
    assert (round(cap_b.a.x, 6), cap_b.a.y) == (62.245064, 57.0)
    assert (round(cap_b.b.x, 6), cap_b.b.y) == (77.754936, 57.0)
    assert cap_b.members == ("cap",)  # members preserved across generations
    assert len(m.state.dogbones) == 2


def test_model_m21_applied_edges_protected_resolve_at_use():
    # Round-1/2 defect: a later placement flagged (and could delete) an
    # APPLIED corner's rebuilt main edge. ADR-016(c)/(g): the applied
    # dogbone's canonical eids are resolved at use -> its composites are
    # protected; the second corner places, applies, and A survives intact.
    prims = [
        seg("e1", 0, 0, 0, -10),
        seg("e2", 0, 0, 12, 0),
    ]
    e1 = pick(prims, 0, -5).eid
    e2 = pick(prims, 6, 0).eid
    side, flip = side_for(prims, e1, e2, 1.5875, (1.122532, -1.122532))
    res_a = place_corner(prims, e1, e2, side, 1.5875, set(), [], side_flip=flip)
    assert res_a.ok
    m = Model(ModelState(primitives=list(prims), next_seq=1))
    m.apply_corner(res_a)
    e1_geom = m.get("promoted-e1")
    assert e1_geom is not None

    # corner B: its circle crosses A's promoted-e1 composite (min dist 0.6225)
    e3 = seg("e3", -0.5, -1, -0.5, -11)
    e4 = seg("e4", -0.5, -6, 9.5, -6)
    m.state.primitives.append(e3)
    m.state.primitives.append(e4)
    prims_b = list(m.state.primitives)
    e3 = pick(prims_b, -0.5, -6).eid
    e4 = pick(prims_b, 4.0, -6).eid
    side_b, flip_b = side_for(prims_b, e3, e4, 1.5875, (0.622532, -7.122532))
    res_b = place_corner(
        prims_b, e3, e4, side_b, 1.5875, set(), [m.state.dogbones[0]],
        side_flip=flip_b,
    )
    assert res_b.ok, res_b.refusals
    # A's rebuilt main edge is protected: never flagged, never deleted
    assert not any(f.eid == "promoted-e1" for f in res_b.flags)
    assert "promoted-e1" not in res_b.deletions
    assert "promoted-e1" not in res_b.warnings if res_b.warnings else True

    m.apply_corner(res_b)
    got = {e.eid: e for e in m.state.primitives}
    assert set(got) == {
        "promoted-e1", "promoted-e2", "n1", "promoted-e3", "promoted-e4", "n2",
    }
    # A's composite geometry unchanged; its arc survives (round-2 probe N1
    # left the arc dangling with its main edge deleted)
    kept = got["promoted-e1"]
    assert (round(kept.a.x, 6), round(kept.a.y, 6)) == (0.0, -2.245064)
    assert (kept.b.x, kept.b.y) == (0.0, -10.0)
    assert m.get("n1") is not None


def test_model_m21_mixed_direction_place_apply():
    # Round-2 defect N2: place (filters) and apply (runs) disagreed on
    # mixed-direction runs -> "rebuild old point not on run extent" crash.
    # ADR-016(e): single chain walk -> place and apply agree.
    prims = [
        seg("a", 0, 0, 10, 0),
        seg("b", 0, 0, -10, 0),      # stored reversed
        seg("c", -10, 0, -20, 0),    # continues west
        seg("v", 0, 0, 0, 10),
    ]
    run = pick(prims, 5, 0)
    assert run.eid == "promoted-c"  # anchor order: c, b, a
    assert run.members == ("c", "b", "a")
    assert (run.a.x, run.b.x) == (-20.0, 10.0)  # symmetric full extent

    e_v = pick(prims, 0, 5).eid
    side, flip = side_for(prims, run.eid, e_v, 1.5875, (1.122532, 1.122532))
    res = place_corner(prims, run.eid, e_v, side, 1.5875, set(), [], side_flip=flip)
    assert res.ok, res.refusals
    rb = {x.eid: x for x in res.rebuilt}
    assert set(rb) == {"c", "v"}  # owners: c (west end), v (base)
    assert (rb["c"].old.x, rb["c"].old.y) == (-20.0, 0.0)
    assert abs(rb["c"].new.x - 2.245064) < 1e-6 and rb["c"].new.y == 0.0

    m = Model(ModelState(primitives=list(prims), next_seq=1))
    m.apply_corner(res)  # pre-fix: ValueError; post-fix: replaces all three
    got = {e.eid: e for e in m.state.primitives}
    assert set(got) == {"promoted-c", "promoted-v", "n1"}
    comp = got["promoted-c"]
    assert comp.members == ("c", "b", "a")
    # apply re-derives the run anchored at the CANONICAL-FIRST member (c,
    # stored westward) -> the composite's a is the EAST end (deterministic;
    # the endpoint SET is what the geometry rules consume)
    assert (comp.a.x, comp.a.y) == (10.0, 0.0)
    assert (round(comp.b.x, 6), comp.b.y) == (2.245064, 0.0)


def test_model_m21_canonical_eid_roundtrip():
    # ADR-016(g): the promoted Seg's eid is the ONE eid consumed by
    # UI-forward, Dogbone records, protected set, and apply seed resolution.
    prims = [seg("e1", 0, 0, 0, -10), seg("e2", 0, 0, 10, 0)]
    e1 = pick(prims, 0, -5).eid
    e2 = pick(prims, 5, 0).eid
    side, flip = side_for(prims, e1, e2, 1.5875, (1.122532, -1.122532))
    res = place_corner(prims, e1, e2, side, 1.5875, set(), [], side_flip=flip)
    assert res.ok
    db = res.dogbone
    assert db.edge1_eid == e1 and db.edge2_eid == e2  # canonical eids recorded
    assert db.db_id == f"db-{e1}+{e2}"

    m = Model(ModelState(primitives=list(prims), next_seq=1))
    m.apply_corner(res)
    # post-apply the SAME eids resolve to the composites (resolve-at-use)
    from rules.engine import resolve_edge

    r1 = resolve_edge(m.state.primitives, e1)
    assert r1 is not None and r1[1].eid == "promoted-e1"
    r2 = resolve_edge(m.state.primitives, e2)
    assert r2 is not None and r2[1].eid == "promoted-e2"
    # a second placement can re-reference them (protected via the dogbone)
    res2 = place_corner(
        list(m.state.primitives), e1, e2, side, 1.5875, set(), [m.state.dogbones[0]],
        side_flip=flip,
    )
    assert not res2.ok  # same edge pair again -> overlap refusal, not a crash
    assert res2.refusals[0].startswith("OVERLAP:")
