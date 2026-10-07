"""CONTRACTS 1 dataclass shapes are pinned here so M2/M3 cannot drift (ADR-008/014)."""
from __future__ import annotations

import dataclasses

import pytest

from geometry.entities import (
    Arc,
    Circ,
    CornerResult,
    Dogbone,
    Flag,
    PassThrough,
    PointEnt,
    Primitive,
    Pt,
    Rebuild,
    Seg,
    Side,
    TextEnt,
    Trim,
)


def test_geometry_entities_pt_and_seg_frozen_with_adr014_defaults():
    p = Pt(1.0, 2.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.x = 3.0  # type: ignore[misc]
    s = Seg(eid="h1", a=p, b=Pt(3.0, 2.0))
    assert s.members == () and s.pick_eid == ""
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.eid = "h2"  # type: ignore[misc]


def test_geometry_entities_primitive_union_covers_all_types():
    prims = [
        Seg(eid="1", a=Pt(0, 0), b=Pt(1, 1)),
        Arc(eid="2", center=Pt(0, 0), r=1.0, start_deg=0.0, end_deg=90.0),
        Circ(eid="3", center=Pt(0, 0), r=1.0),
        PointEnt(eid="4", p=Pt(0, 0)),
        TextEnt(eid="5", p=Pt(0, 0), text="hello"),
    ]
    for x in prims:
        assert isinstance(x, Primitive)
    assert not isinstance(PassThrough(eid="6", kind="ELLIPSE"), Primitive)


def test_geometry_entities_result_types_constructible():
    arc = Arc(eid="a", center=Pt(0, 0), r=1.0, start_deg=0.0, end_deg=180.0)
    db = Dogbone(db_id="d1", apex=Pt(0, 0), center=Pt(1, 1), r=1.5,
                 side=Side(sign=1), edge1_eid="e1", edge2_eid="e2", arc=arc)
    res = CornerResult(ok=True, dogbone=db, deletions=["x"], trims=[
        Trim(eid="t", old=(Pt(0, 0), Pt(1, 1)), new=(Pt(0, 0), Pt(2, 2)))
    ], rebuilt=[Rebuild(eid="r", old=Pt(0, 0), new=Pt(1, 0))], refusals=[],
    flags=[Flag(eid="f", reason="CHORD_CROSSER",
                options=frozenset({"delete", "keep", "trim"}), decision=None)])
    assert res.ok and res.flags[0].decision is None
    assert res.flags[0].options == frozenset({"delete", "keep", "trim"})


def test_geometry_entities_promoted_seg_carries_members():
    s = Seg(eid="promoted-h1", a=Pt(0, 0), b=Pt(3, 0),
            members=("h1", "h2"), pick_eid="h2")
    assert s.members == ("h1", "h2") and s.pick_eid == "h2"
