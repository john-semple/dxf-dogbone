"""ui.canvas_view.flatten_arc — CCW start->end direction and full-circle handling."""
from __future__ import annotations

import math

import pytest

from geometry.entities import Arc, Pt
from ui.canvas_view import flatten_arc


def test_ui_canvas_view_flatten_arc_respects_ccw_direction():
    a = Arc(eid="x", center=Pt(0, 0), r=2.0, start_deg=0.0, end_deg=90.0)
    pts = flatten_arc(a, min_seg=4)
    assert pts[0].x == pytest.approx(2.0) and pts[0].y == pytest.approx(0.0, abs=1e-12)
    assert pts[-1].x == pytest.approx(0.0, abs=1e-12) and pts[-1].y == pytest.approx(2.0)
    for p in pts:  # every sample on the circle
        assert math.hypot(p.x, p.y) == pytest.approx(2.0, abs=1e-9)


def test_ui_canvas_view_flatten_arc_wraps_past_360():
    a = Arc(eid="x", center=Pt(1, 1), r=0.5, start_deg=350.0, end_deg=10.0)
    pts = flatten_arc(a, min_seg=4)
    assert pts[0].x == pytest.approx(1 + 0.5 * math.cos(math.radians(350.0)))
    assert pts[-1].x == pytest.approx(1 + 0.5 * math.cos(math.radians(10.0)))
    assert len(pts) >= 5


def test_ui_canvas_view_flatten_arc_full_circle_when_start_equals_end():
    a = Arc(eid="x", center=Pt(0, 0), r=1.0, start_deg=90.0, end_deg=90.0)
    pts = flatten_arc(a)
    assert pts[0] == pytest.approx(pts[-1]) or (pts[0].x == pytest.approx(pts[-1].x)
                                                and pts[0].y == pytest.approx(pts[-1].y))
    xs = [p.x for p in pts]
    assert min(xs) <= -0.9999  # extreme only sampled exactly at lucky angles
    assert max(xs) >= 0.9999
