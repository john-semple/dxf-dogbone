"""ui.transform — pure screen<->world math (tkinter-free, headless-testable)."""
from __future__ import annotations

import pytest

from geometry.entities import Pt
from ui.transform import MAX_SCALE, MIN_SCALE, ViewTransform


def test_ui_transform_screen_world_round_trip():
    t = ViewTransform(scale=4.0, ox=100.0, oy=200.0)
    for p in (Pt(0, 0), Pt(12.5, -3.75), Pt(-40, 88)):
        sx, sy = t.to_screen(p)
        w = t.to_world(sx, sy)
        assert w.x == pytest.approx(p.x, abs=1e-12)
        assert w.y == pytest.approx(p.y, abs=1e-12)


def test_ui_transform_y_axis_flips():
    t = ViewTransform(scale=2.0, ox=0.0, oy=0.0)
    assert t.to_screen(Pt(0, 5)) == (0.0, -10.0)
    assert t.to_world(0.0, -10.0) == Pt(0.0, 5.0)


def test_ui_transform_zoomed_at_keeps_world_point_under_cursor():
    t = ViewTransform(scale=1.0, ox=50.0, oy=50.0)
    sx, sy = 123.0, 77.0
    w = t.to_world(sx, sy)
    t2 = t.zoomed_at(sx, sy, 2.5)
    w2 = t2.to_world(sx, sy)
    assert w2.x == pytest.approx(w.x, abs=1e-9)
    assert w2.y == pytest.approx(w.y, abs=1e-9)
    assert t2.scale == pytest.approx(2.5)


def test_ui_transform_zoom_clamps_at_bounds():
    t = ViewTransform(scale=1.0, ox=0.0, oy=0.0)
    t_max = t.zoomed_at(10, 10, 1e12)
    assert t_max.scale == MAX_SCALE
    t_min = t.zoomed_at(10, 10, 1e-12)
    assert t_min.scale == MIN_SCALE


def test_ui_transform_zoomed_at_rejects_bad_factor():
    t = ViewTransform(scale=1.0, ox=0.0, oy=0.0)
    with pytest.raises(ValueError):
        t.zoomed_at(0, 0, 0.0)
    with pytest.raises(ValueError):
        t.zoomed_at(0, 0, -2.0)


def test_ui_transform_panned_by_shifts_origin():
    t = ViewTransform(scale=2.0, ox=10.0, oy=20.0)
    t2 = t.panned_by(30.0, -5.0)
    assert (t2.ox, t2.oy) == (40.0, 15.0)
    assert t2.scale == 2.0
    w = t.to_world(50.0, 40.0)
    w2 = t2.to_world(50.0 + 30.0, 40.0 - 5.0)  # content moved by (+30, -5) px
    assert (w.x, w.y) == (w2.x, w2.y)
