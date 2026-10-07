"""rules.filters: EPS_PICK derivation, pick, and collinear promotion (CONTRACTS 2;
ADR-012(c) re-promotion; SPEC 11.8.1 "longest collinear run through the click")."""
from __future__ import annotations

import math

import pytest

from geometry.entities import Circ, Pt, Seg
from rules.filters import eps_pick_from_scale, promoted_edge_at


def seg(eid: str, ax: float, ay: float, bx: float, by: float, **kw) -> Seg:
    return Seg(eid=eid, a=Pt(ax, ay), b=Pt(bx, by), **kw)


class TestEpsPick:
    def test_rules_filters_eps_pick_from_scale_formula(self):
        assert eps_pick_from_scale(4.0) == pytest.approx(0.75)
        assert eps_pick_from_scale(2.0, pick_px=3.0) == pytest.approx(1.5)
        assert eps_pick_from_scale(10.0, pick_px=1.0) == pytest.approx(0.1)

    def test_rules_filters_eps_pick_rejects_bad_scale(self):
        with pytest.raises(ValueError):
            eps_pick_from_scale(0.0)


class TestPick:
    def test_rules_filters_single_segment_pick_and_promote(self):
        s = seg("A", 0, 0, 10, 0)
        p = promoted_edge_at([s], Pt(5, 0.5), eps_pick=1.0)
        assert p is not None
        assert p.eid == "promoted-A"
        assert p.members == ("A",) and p.pick_eid == "A"
        assert (p.a.x, p.a.y) == (0, 0) and (p.b.x, p.b.y) == (10, 0)

    def test_rules_filters_nearest_segment_within_eps_pick_wins(self):
        near = seg("NEAR", 0, 1, 10, 1)
        far = seg("FAR", 0, 0, 10, 0)
        p = promoted_edge_at([far, near], Pt(5, 0.6), eps_pick=1.0)
        assert p is not None and p.pick_eid == "NEAR"

    def test_rules_filters_miss_returns_none(self):
        s = seg("A", 0, 0, 10, 0)
        assert promoted_edge_at([s], Pt(5, 5), eps_pick=1.0) is None

    def test_rules_filters_non_seg_entities_are_not_edge_candidates(self):
        c = Circ(eid="C", center=Pt(5, 0), r=1.0)
        assert promoted_edge_at([c], Pt(5, 0), eps_pick=1.0) is None


class TestPromotion:
    def test_rules_filters_collinear_chain_merges_both_directions(self):
        a = seg("A", 0, 0, 10, 0)
        b = seg("B", 10, 0, 20, 0)
        c = seg("C", 20, 0, 30, 0)
        for click in (Pt(5, 0), Pt(15, 0), Pt(25, 0)):
            p = promoted_edge_at([a, b, c], click, eps_pick=0.5)
            assert p is not None
            assert p.members == ("A", "B", "C")
            assert p.eid == "promoted-A"  # anchored on run-first member
            assert (p.a.x, p.b.x) == (0.0, 30.0)

    def test_rules_filters_reversed_orientation_neighbor_joins(self):
        a = seg("A", 0, 0, 10, 0)
        b = seg("B", 20, 0, 10, 0)  # reversed: b.b meets a.b
        p = promoted_edge_at([a, b], Pt(5, 0), eps_pick=0.5)
        assert p is not None
        assert set(p.members) == {"A", "B"}
        assert (p.a.x, p.b.x) == (0.0, 20.0)

    def test_rules_filters_gap_beyond_eps_coincide_stops_promotion(self):
        a = seg("A", 0, 0, 10, 0)
        b = seg("B", 11, 0, 20, 0)  # 1mm gap >> EPS_COINCIDE
        p = promoted_edge_at([a, b], Pt(5, 0), eps_pick=0.5)
        assert p is not None and p.members == ("A",)

    def test_rules_filters_non_collinear_neighbor_stops_promotion(self):
        a = seg("A", 0, 0, 10, 0)
        b = seg("B", 10, 0, 20, 10)  # 45 degrees
        p = promoted_edge_at([a, b], Pt(5, 0), eps_pick=0.5)
        assert p is not None and p.members == ("A",)

    def test_rules_filters_parallel_offset_neighbor_stops_promotion(self):
        a = seg("A", 0, 0, 10, 0)
        b = seg("B", 10, 5, 20, 5)  # parallel but 5mm offset
        p = promoted_edge_at([a, b], Pt(5, 0), eps_pick=0.5)
        assert p is not None and p.members == ("A",)

    def test_rules_filters_repromotion_flattens_and_prefixes(self):
        comp = seg("promoted-A", 0, 0, 20, 0, members=("A", "B"), pick_eid="A")
        c = seg("C", 20, 0, 30, 0)
        p = promoted_edge_at([comp, c], Pt(25, 0), eps_pick=0.5)
        assert p is not None
        # ADR-016(f): re-promotion KEEPS the composite's own eid
        # (ADR-012(c) intent: never mint a second id for the same line;
        # supersedes M1's promoted-promoted-* prefixing)
        assert p.eid == "promoted-A"
        assert p.members == ("A", "B", "C")
        assert p.pick_eid == "C"
        assert (p.a.x, p.b.x) == (0.0, 30.0)

    def test_rules_filters_pick_first_wins_ties(self):
        # ADR-016(f): FIRST wins equidistant picks (docstring semantics)
        first = seg("FIRST", 0, 0, 10, 0)
        second = seg("SECOND", 0, 1, 10, 1)
        p = promoted_edge_at([first, second], Pt(5, 0.5), eps_pick=1.0)
        assert p is not None and p.pick_eid == "FIRST"

    def test_rules_filters_micro_segment_chain_to_fixed_point(self):
        segs = [seg(f"s{i}", i, 0, i + 1, 0) for i in range(10)]
        for i in range(10):
            p = promoted_edge_at(segs, Pt(i + 0.5, 0), eps_pick=0.5)
            assert p is not None
            assert p.members == tuple(f"s{i}" for i in range(10))
            assert p.eid == "promoted-s0"
            assert (p.a.x, p.b.x) == (0.0, 10.0)

    def test_rules_filters_degenerate_zero_length_segment(self):
        s = seg("Z", 5, 5, 5, 5)
        p = promoted_edge_at([s], Pt(5, 5), eps_pick=0.5)
        assert p is not None
        assert p.members == ("Z",) and p.eid == "promoted-Z"
        assert p.a == Pt(5, 5) and p.b == Pt(5, 5)

    def test_rules_filters_promoted_geometry_is_collinear_regardless_of_click(self):
        a = seg("A", 0, 0, 10, 0)
        b = seg("B", 10, 0, 20, 0)
        p1 = promoted_edge_at([a, b], Pt(1, 0.2), eps_pick=0.5)
        p2 = promoted_edge_at([b, a], Pt(19, 0.2), eps_pick=0.5)
        assert p1 is not None and p2 is not None
        assert (p1.a.x, p1.b.x) == (p2.a.x, p2.b.x) == (0.0, 20.0)
        assert math.isclose(p1.a.y, 0.0, abs_tol=1e-12)
