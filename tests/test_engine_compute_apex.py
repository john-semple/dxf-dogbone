"""rules.engine.compute_apex — apex + half-angle band (M2; ADR-015(g)).

Fixtures per the M2 brief: 90/60/120 deg, shallow-refusal [15,165], the
min-side convention (discriminates the M0-logged air-side convention
conflict), band boundary.
"""
import math

from geometry.entities import Pt, Refusal, Seg
from rules.engine import compute_apex


def _seg_at(deg: float, length: float = 10.0) -> Seg:
    return Seg(
        "s",
        Pt(0.0, 0.0),
        Pt(length * math.cos(math.radians(deg)), length * math.sin(math.radians(deg))),
    )


def test_engine_compute_apex_90deg_worked_example_lines():
    s1 = Seg("s1", Pt(45.0, 51.5168), Pt(45.0, -95.0))
    s2 = Seg("s2", Pt(124.7552, 51.5168), Pt(44.2484, 51.5168))
    ap = compute_apex(s1, s2)
    assert not isinstance(ap, Refusal)
    apex, half = ap
    assert abs(apex.x - 45.0) < 1e-9 and abs(apex.y - 51.5168) < 1e-9
    assert abs(half - 45.0) < 1e-9


def test_engine_compute_apex_60_and_120_min_side():
    s1 = _seg_at(0.0)
    _, h60 = compute_apex(s1, _seg_at(60.0))
    _, h120 = compute_apex(s1, _seg_at(120.0))
    assert abs(h60 - 30.0) < 1e-9
    assert abs(h120 - 30.0) < 1e-9  # min(120, 60)/2 — ADR-015(g) min-side rule


def test_engine_compute_apex_parallel_refusal_exact_string():
    r = compute_apex(Seg("a", Pt(0, 0), Pt(10, 0)), Seg("b", Pt(0, 1), Pt(10, 1)))
    assert isinstance(r, Refusal)
    assert r.reason == (
        "PARALLEL: edges are parallel or collinear (no supporting-line intersection)"
    )


def test_engine_compute_apex_shallow_refusal_exact_string():
    # syn-shallow-refuse site: arms (42, -3.5) / (42, +3.5) -> half 4.764
    s1 = Seg("s1", Pt(78.0, 50.0), Pt(120.0, 46.5))
    s2 = Seg("s2", Pt(78.0, 50.0), Pt(120.0, 53.5))
    r = compute_apex(s1, s2)
    assert isinstance(r, Refusal)
    assert r.reason == (
        "SHALLOW: corner half-angle 4.764 deg outside [15.000, 165.000] "
        "(near-collinear edges)"
    )


def test_engine_compute_apex_band_boundary():
    s1 = _seg_at(0.0)
    assert not isinstance(compute_apex(s1, _seg_at(30.0)), Refusal)  # half 15.0
    r = compute_apex(s1, _seg_at(29.0))  # half 14.5
    assert isinstance(r, Refusal) and r.reason.startswith("SHALLOW: corner half-angle 14.500")
    # near-collinear at the OTHER end (170 deg pair = 10 deg from straight)
    r2 = compute_apex(s1, _seg_at(170.0))  # min(170, 10)/2 = 5.0
    assert isinstance(r2, Refusal) and r2.reason.startswith("SHALLOW: corner half-angle 5.000")


def test_engine_compute_apex_v25_discriminator():
    # M0-logged air-side convention conflict: a 25 deg pair is refused under
    # the min-side rule even though its wide side (155 deg) is in band.
    s1 = _seg_at(0.0)
    r = compute_apex(s1, _seg_at(25.0))
    assert isinstance(r, Refusal)
    assert r.reason.startswith("SHALLOW: corner half-angle 12.500")
