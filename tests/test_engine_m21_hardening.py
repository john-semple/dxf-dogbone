"""M2.1 hardening: radius validation, unified UNKNOWN_EDGE, flag-decision
validation + warnings (ADR-016(b)/(c)/(e)), flag dedup (ADR-016(d))."""
from __future__ import annotations

from geometry import geomops as go
from geometry.entities import Arc, Circ, PointEnt, Pt, Refusal, Seg, Side, TextEnt
from geometry.tolerances import EPS_COINCIDE
from rules.engine import ghost_candidates, place_corner


def base_prims(extra):
    prims = [
        Seg("e1", Pt(0.0, 0.0), Pt(0.0, -10.0)),
        Seg("e2", Pt(0.0, 0.0), Pt(10.0, 0.0)),
    ]
    prims.extend(extra)
    return prims


def place(prims, r=1.5875, **kw):
    return place_corner(
        prims, "e1", "e2", Side(+1), r, kw.pop("folds", set()), kw.pop("dbs", []),
        side_flip=+1, **kw,
    )


def test_engine_m21_radius_validation_refuses():
    prims = base_prims([])
    for r in (0.0, -1.5875, EPS_COINCIDE / 2.0):
        res = place(prims, r=r)
        assert not res.ok
        assert res.refusals == [
            f"RADIUS: tool radius must exceed EPS_COINCIDE (got {r:.6f})"
        ]


def test_engine_m21_unknown_edge_string_unified():
    # place_corner and ghost_candidates use the SAME refusal string (ADR-016(a))
    g = ghost_candidates(base_prims([]), "e1", "nope", 1.5875)
    assert isinstance(g, Refusal)
    assert g.reason == "UNKNOWN_EDGE: nope is not resolvable in primitives"
    res = place_corner(
        base_prims([]), "e1", "nope", Side(+1), 1.5875, set(), [], side_flip=+1
    )
    assert not res.ok
    assert res.refusals == ["UNKNOWN_EDGE: nope is not resolvable in primitives"]


def test_engine_m21_invalid_trim_on_line_chord_crosser_pending_and_alive():
    chord = Seg("chord", Pt(-4.0, -1.122532), Pt(6.0, -1.122532))
    res = place(base_prims([chord]), flag_decisions={"chord": "trim"})
    assert res.ok
    # ADR-016(c): "trim" is not in the LINE chord-crosser's options -> ignored
    assert "chord" not in res.deletions
    fl = {f.eid: f for f in res.flags}["chord"]
    assert fl.decision is None  # pending, never a bogus 'trim'
    assert res.warnings == [
        "FLAG_DECISION: ignoring invalid decision 'trim' for chord "
        "(allowed: delete|keep)"
    ]


def test_engine_m21_invalid_trim_on_arc_endpoint_in_not_deleted():
    aep = Arc("aep", Pt(2.0, -1.122532), 0.8, 90.0, 270.0)  # endpoints inside
    res = place(base_prims([aep]), flag_decisions={"aep": "trim"})
    assert res.ok
    # ADR-016(c): invalid decision never auto-deletes (round-2 defect: it did)
    assert "aep" not in res.deletions
    fl = {f.eid: f for f in res.flags}["aep"]
    assert fl.reason == "ARC_ENDPOINT_IN" and fl.decision is None
    assert any(w.startswith("FLAG_DECISION: ignoring invalid decision 'trim'") for w in res.warnings)


def test_engine_m21_invalid_cascade_decision_not_deleted():
    # WE-shaped junction: BA dangles; an invalid decision must not delete it
    prims = [
        Seg("B8", Pt(45.0, 51.5118), Pt(45.0, -95.0)),
        Seg("63", Pt(124.7552, 51.5168), Pt(44.2484, 51.5168)),
        Seg("B9", Pt(44.2484, 51.5118), Pt(45.0, 51.5118)),
        Seg("BA", Pt(44.2484, 51.5118), Pt(44.2484, 51.5168)),
    ]
    res = place_corner(
        prims, "B8", "63", Side(-1), 1.5875, set(), [],
        side_flip=+1, flag_decisions={"BA": "trim"},
    )
    assert res.ok
    # B9 (truth-table delete) goes; BA dangles but the invalid decision is
    # ignored -> pending, NOT deleted
    assert res.deletions == ["B9"]
    fl = {f.eid: f for f in res.flags}["BA"]
    assert fl.reason == "CASCADE_DANGLING" and fl.decision is None
    assert any("ignoring invalid decision 'trim' for BA" in w for w in res.warnings)


def test_engine_m21_flag_dedup_one_flag_per_eid():
    # An ARC_ENDPOINT_IN entity with decision "keep" that also dangles must
    # carry exactly ONE flag (round-2 defect: two).
    aep = Arc("aep", Pt(0.5, -1.0), 1.0, 90.0, 270.0)
    # endpoints (0.5, 0.0) and (0.5, -2.0); (0.5, 0.0) is inside the circle
    # AND lies on edge-2's removed portion with no other neighbors -> dangles
    prims = base_prims([aep])
    res = place(prims, flag_decisions={"aep": "keep"})
    assert res.ok
    aep_flags = [f for f in res.flags if f.eid == "aep"]
    assert len(aep_flags) == 1
    assert aep_flags[0].reason == "ARC_ENDPOINT_IN"
    assert aep_flags[0].decision == "keep"
    assert "aep" not in res.deletions
    # kept + still crossing -> the ADR-009 keep-warning carrier fires
    assert any("KEPT_CROSSER" in w and "aep" in w for w in res.warnings)


def test_engine_m21_kept_circle_intersects_warning():
    hole = Circ("hole", Pt(2.0, -2.0), 0.5)  # overlaps the dogbone circle
    res = place(base_prims([hole]), flag_decisions={"hole": "keep"})
    assert res.ok
    assert "hole" not in res.deletions
    assert res.warnings == [
        "KEPT_INTERSECTS: kept CIRCLE hole intersects the dogbone circle"
    ]
    assert {f.eid: f for f in res.flags}["hole"].decision == "keep"
