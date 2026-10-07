"""M2.2 brief item 7 (optional, executed) — resolve_edge prefix unrolling is
bounded to ONE level, and the KEPT_CROSSER predicate is uniform across
truth-table rows (kept LINE crossers and kept ARC_ENDPOINT_IN both warn iff
the entity actually crosses the circle interior).
"""
import pytest

from geometry.entities import Pt, Seg, Side
from rules.engine import place_corner, resolve_edge

EPS = 1e-3


def seg(eid, a, b):
    return Seg(eid, Pt(*a), Pt(*b))


def test_resolve_edge_strips_one_prefix_level():
    # plain member present -> one-level strip resolves it
    prims = [seg("A", (0.0, 0.0), (10.0, 0.0))]
    out = resolve_edge(prims, "promoted-A", EPS)
    assert out is not None
    assert out[1].eid == "A"


def test_resolve_edge_raises_on_double_prefix():
    # promoted-promoted-* labels are not mintable (ADR-016(f)) — resolving one
    # must fail LOUD (developer's probe: it used to resolve silently through
    # the unbounded strip loop).
    prims = [seg("e1", (0.0, 0.0), (10.0, 0.0))]
    with pytest.raises(ValueError, match="corrupt edge eid"):
        resolve_edge(prims, "promoted-promoted-e1", EPS)


def test_kept_crosser_warning_uniform_across_rows():
    # kept LINE chord-crosser warns (crosses the circle interior). Geometry:
    # BAR x VERT 90-deg corner, apex (10, 0) interior to both edges; dogbone
    # center (10.7071, 0.7071), r=1. CHORD spans the circle interior with
    # both endpoints outside -> CHORD_CROSSER row; "keep" -> KEPT_CROSSER.
    prims = [
        seg("BAR", (0.0, 0.0), (20.0, 0.0)),
        seg("VERT", (10.0, -4.0), (10.0, 8.0)),
        seg("CHORD", (9.0, 0.5), (12.5, 0.5)),
    ]
    res = place_corner(
        prims, "BAR", "VERT", Side(+1), 1.0, set(), [], side_flip=+1,
        flag_decisions={"CHORD": "keep"},
    )
    assert res.ok, res.refusals
    assert "CHORD" not in res.deletions
    assert any(w == "KEPT_CROSSER: kept entity CHORD will cross the relief cut"
               for w in res.warnings)


def test_kept_arc_endpoint_in_warns_iff_crossing():
    # kept ARC with an endpoint inside the circle and the body passing
    # through the interior warns KEPT_CROSSER (same predicate as the LINE
    # row — M2.2 item 7 symmetry fix; previously conditional inline).
    from geometry.entities import Arc

    prims = [
        seg("BAR", (0.0, 0.0), (20.0, 0.0)),
        seg("VERT", (10.0, -4.0), (10.0, 8.0)),
        Arc("AEP", Pt(11.7, 0.7), 1.0, 0.0, 180.0),  # endpoint in circle; body through C
    ]
    res = place_corner(
        prims, "BAR", "VERT", Side(+1), 1.0, set(), [], side_flip=+1,
        flag_decisions={"AEP": "keep"},
    )
    assert res.ok, res.refusals
    assert "AEP" not in res.deletions
    flags = {f.eid: f for f in res.flags}
    assert flags["AEP"].reason == "ARC_ENDPOINT_IN"
    assert flags["AEP"].decision == "keep"
    # arc passes through the dogbone circle interior -> the warning fires
    assert any(w.startswith("KEPT_CROSSER: kept entity AEP") for w in res.warnings)