"""rules/manual_edit.py — ADR-025 trim_to_closest engine tests.

Pinned spec order (ADR-025(b) + user ruling): the STRAY check fires
FIRST — a run with zero external attachments proposes deletion INSTEAD
of trimming. Trim/extend therefore applies to runs attached at least
somewhere; fixtures below give subjects a far-end attachment.

Covers: plain trim (overshoot), extend (falls short), moving-end
authority (click-near-end), promoted-run subject, stray rule (zero
external attachments → whole-run deletion; one-end-attached trims; run
members never count as each other's attachments; POINT counts as an
attachment), supporting-geometry targets (LINE supporting line, ARC
supporting circle span-filtered, CIRCLE, POINT), refusal strings
verbatim (UNKNOWN_EDGE / NO_TARGET), own-member exclusion, folds allowed
both ways, degenerate-candidate guard.
"""
from __future__ import annotations

import math

from geometry.entities import Arc, Circ, EditResult, PointEnt, Pt, Seg, TextEnt
from rules.manual_edit import (
    REFUSAL_NO_TARGET,
    REFUSAL_UNKNOWN,
    SPAN_DELETE_WARNING,
    trim_to_closest,
)

TOL = 1e-9


# -- fixtures ----------------------------------------------------------------

def _seg(eid, ax, ay, bx, by):
    return Seg(eid=eid, a=Pt(ax, ay), b=Pt(bx, by))


# A far-end attachment: keeps the subject line OUT of the stray
# rule so the trim/extend path is exercised (pinned spec order).
# Attachment = SHARED ENDPOINT (adjacency is endpoint-keyed; a wall
# merely CROSSING the line does not attach).
def _attached(l1: Seg) -> list:
    wall = _seg("W", l1.a.x, l1.a.y, l1.a.x, l1.a.y + 5)
    return [l1, wall]


# -- basic trim / extend -----------------------------------------------------

def test_manual_edit_trim_overshoot_to_line():
    """L1 attached at (0,0); overshoots target T x=10; click near b →
    b trims back to (10,0)."""
    l1 = _seg("L1", 0, 0, 20, 0)
    ents = _attached(l1) + [_seg("T", 10, -5, 10, 5)]
    res = trim_to_closest(ents, Pt(19.9, 0.05), "L1")
    assert res.ok and not res.deletions and len(res.trims) == 1
    t = res.trims[0]
    assert t.eid == "promoted-L1"
    new_a, new_b = t.new
    assert abs(new_b.x - 10.0) < TOL and abs(new_b.y) < TOL
    assert new_a == Pt(0.0, 0.0)  # far end unchanged


def test_manual_edit_extend_short_to_line():
    """L1 attached at (0,0); falls short of target T x=10 → extends b."""
    l1 = _seg("L1", 0, 0, 8, 0)
    ents = _attached(l1) + [_seg("T", 10, -5, 10, 5)]
    res = trim_to_closest(ents, Pt(7.9, 0.05), "L1")
    assert res.ok and len(res.trims) == 1
    new_a, new_b = res.trims[0].new
    assert abs(new_b.x - 10.0) < TOL and abs(new_b.y) < TOL
    assert new_a == Pt(0.0, 0.0)


def test_manual_edit_click_near_end_authority():
    """Click near the a end moves a, not b (user answer 1). a is the
    attached end; b has the target."""
    l1 = _seg("L1", 5, 0, 20, 0)
    wall = _seg("W", 20, 0, 20, 5)  # ends at b (20,0) = shared endpoint
    target = _seg("T", 8, -5, 8, 5)
    res = trim_to_closest([l1, wall, target], Pt(5.1, 0.05), "L1")
    assert res.ok and len(res.trims) == 1
    new_a, new_b = res.trims[0].new
    assert abs(new_a.x - 8.0) < TOL  # a moved to the target
    assert new_b == Pt(20.0, 0.0)    # b untouched


def test_manual_edit_supporting_line_counts_target_short():
    """Target T does not REACH the intersection (segment-reach not
    required; the supporting line counts — user answer 3)."""
    l1 = _seg("L1", 0, 0, 20, 0)
    short_target = _seg("T", 10, -5, 10, -1)  # ends below y=0; never touches
    ents = _attached(l1) + [short_target]
    res = trim_to_closest(ents, Pt(19.9, 0.05), "L1")
    assert res.ok and len(res.trims) == 1
    new_a, new_b = res.trims[0].new
    assert abs(new_b.x - 10.0) < TOL and abs(new_b.y) < TOL


# -- promoted-run subject ----------------------------------------------------

def test_manual_edit_promoted_run_moves_as_one():
    """A 2-member collinear chain attached at its far end trims as the
    whole run: click near the chain's b end → the RUN's b endpoint moves."""
    m1 = _seg("M1", 0, 0, 10, 0)
    m2 = _seg("M2", 10, 0, 20, 0)
    wall = _seg("W", 0, 0, 0, 5)  # ends at (0,0) = shared endpoint
    target = _seg("T", 15, -5, 15, 5)
    res = trim_to_closest([m1, m2, wall, target], Pt(19.5, 0.05), "M2")
    assert res.ok and len(res.trims) == 1
    t = res.trims[0]
    # run eid is promoted-<first member eid> per chain_run
    assert t.eid == "promoted-M1"
    old_a, old_b = t.old
    new_a, new_b = t.new
    assert old_a == Pt(0.0, 0.0) and old_b == Pt(20.0, 0.0)  # extent
    assert abs(new_b.x - 15.0) < TOL
    assert new_a == Pt(0.0, 0.0)


def test_manual_edit_own_members_never_targets():
    """The run's own members are excluded from candidate targets — the
    run cannot trim to itself (perpendicular foot on a member)."""
    m1 = _seg("M1", 0, 0, 10, 0)
    m2 = _seg("M2", 10, 0, 20, 0)
    wall = _seg("W", 0, 0, 0, 5)  # ends at (0,0): not a stray
    res = trim_to_closest([m1, m2, wall], Pt(19.9, 0.05), "M2")
    assert not res.ok
    assert res.reason == REFUSAL_NO_TARGET


# -- stray rule ---------------------------------------------------------------

def test_manual_edit_stray_zero_attachments_proposes_deletion():
    """Isolated line: no external attachments → stray → delete the run."""
    stray = _seg("S1", 0, 0, 20, 0)
    far = _seg("FAR", 0, 50, 20, 50)  # exists but never touches
    res = trim_to_closest([stray, far], Pt(10.0, 0.0), "S1")
    assert res.ok and not res.trims
    assert res.deletions == ["S1"]


def test_manual_edit_stray_ignores_nearby_targets():
    """Stray rule fires BEFORE the trim proposal (pinned spec: zero
    attachments → delete INSTEAD of trimming, even when a target
    exists)."""
    stray = _seg("S1", 0, 0, 20, 0)
    target = _seg("T", 10, -5, 10, 5)  # a crossing target exists
    res = trim_to_closest([stray, target], Pt(19.9, 0.05), "S1")
    assert res.ok and not res.trims
    assert res.deletions == ["S1"]


def test_manual_edit_one_end_attached_trims_not_deletes():
    """Line touching a T at one end trims normally (stray rule needs
    ZERO external attachments)."""
    l1 = _seg("L1", 0, 0, 20, 0)
    wall = _seg("W", 20, 0, 20, 5)  # ends at (20, 0) = shared endpoint
    target = _seg("T", 10, -5, 10, 5)
    res = trim_to_closest([l1, wall, target], Pt(0.1, 0.05), "L1")
    assert res.ok and len(res.trims) == 1
    new_a, _new_b = res.trims[0].new
    assert abs(new_a.x - 10.0) < TOL


def test_manual_edit_run_members_do_not_count_as_attachments():
    """A 2-member chain in the middle of nowhere: members attach to each
    OTHER but that's internal — still a stray."""
    m1 = _seg("M1", 0, 0, 10, 0)
    m2 = _seg("M2", 10, 0, 20, 0)
    res = trim_to_closest([m1, m2], Pt(10.0, 0.0), "M2")
    assert res.ok and not res.trims
    assert set(res.deletions) == {"M1", "M2"}


def test_manual_edit_point_attachment_prevents_stray():
    """A POINT sitting on the line's endpoint counts as an external
    attachment (user answer: POINT counts) — not a stray."""
    l1 = _seg("L1", 0, 0, 20, 0)
    pt = PointEnt(eid="P1", p=Pt(0, 0))
    target = _seg("T", 10, -5, 10, 5)
    res = trim_to_closest([l1, pt, target], Pt(19.9, 0.05), "L1")
    assert res.ok and len(res.trims) == 1  # trimmed, not deleted


def test_manual_edit_arc_endpoint_attachment_prevents_stray():
    """An ARC sharing the line's endpoint counts as an external
    attachment (arc endpoint == line endpoint within EPS_COINCIDE)."""
    l1 = _seg("L1", 0, 0, 20, 0)
    arc = Arc(eid="A1", center=Pt(0, 3), r=3.0, start_deg=270.0, end_deg=0.0)
    # arc start point = (0, 0) — attached to L1's a end
    target = _seg("T", 10, -5, 10, 5)
    res = trim_to_closest([l1, arc, target], Pt(19.9, 0.05), "L1")
    assert res.ok and len(res.trims) == 1


# -- target kinds -------------------------------------------------------------

def test_manual_edit_trim_to_arc_supporting_circle():
    """Falls-short line extends to the ARC's supporting circle (span
    covers the candidate angle)."""
    arc = Arc(eid="A1", center=Pt(15, 0), r=3.0, start_deg=90.0, end_deg=270.0)
    l1 = _seg("L1", 0, 0, 10, 0)  # ends 2 short of the circle at x=12
    ents = _attached(l1) + [arc]
    res = trim_to_closest(ents, Pt(9.9, 0.05), "L1")
    assert res.ok and len(res.trims) == 1
    new_a, new_b = res.trims[0].new
    # circle x=12 (left entry; arc spans 90..270 = the left half)
    assert abs(new_b.x - 12.0) < TOL and abs(new_b.y) < TOL


def test_manual_edit_trim_to_circle():
    l1 = _seg("L1", 0, 0, 10, 0)
    ents = _attached(l1) + [Circ(eid="C1", center=Pt(15, 0), r=3.0)]
    res = trim_to_closest(ents, Pt(9.9, 0.05), "L1")
    assert res.ok and len(res.trims) == 1
    new_a, new_b = res.trims[0].new
    assert abs(new_b.x - 12.0) < TOL


def test_manual_edit_trim_to_point():
    l1 = _seg("L1", 0, 0, 10, 0)
    ents = _attached(l1) + [PointEnt(eid="P1", p=Pt(12, 0))]
    res = trim_to_closest(ents, Pt(9.9, 0.05), "L1")
    assert res.ok and len(res.trims) == 1
    new_a, new_b = res.trims[0].new
    assert new_b == Pt(12.0, 0.0)


def test_manual_edit_arc_span_filters_far_side():
    """The arc's supporting-circle candidate on the NON-spanned side is
    rejected (span filter) — no reachable spanned crossing → NO_TARGET.
    (Superseded by test_manual_edit_arc_unspanned_entry_refuses, kept for
    the radial-only assertion path.)"""
    # arc covering the RIGHT half of the circle (270..90 = right half)
    arc = Arc(eid="A1", center=Pt(15, 0), r=3.0, start_deg=270.0, end_deg=90.0)
    # line from the LEFT along y=+4 (ABOVE the circle): radial candidate
    # at angle ~143 not spanned; the supporting line y=4 never crosses
    # the r=3 circle -> no reach crossing either -> NO_TARGET
    l1 = _seg("L1", 0, 4, 10, 4)
    ents = _attached(l1) + [arc]
    res = trim_to_closest(ents, Pt(9.9, 4.05), "L1")
    assert not res.ok and res.reason == REFUSAL_NO_TARGET


def test_manual_edit_arc_true_crossing_reaches_span():
    """When the radial candidate IS spanned, the run snaps to it even
    though the arc's NEAREST point along the supporting line (the true
    crossing) is a different point — radial projection wins (supporting
    geometry authority, ADR-025(b))."""
    # half arc spanning 90..270 (LEFT half of circle at (15,0))
    arc = Arc(eid="A1", center=Pt(15, 0), r=3.0, start_deg=90.0, end_deg=270.0)
    # line approaching from the left along y=+2: radial projection of the
    # moving endpoint (11,2) onto the circle = angle ~153 (spanned)
    l1 = _seg("L1", 0, 2, 11, 2)
    ents = _attached(l1) + [arc]
    res = trim_to_closest(ents, Pt(10.9, 2.05), "L1")
    assert res.ok and len(res.trims) == 1
    new_a, new_b = res.trims[0].new
    # radial point: center + r * unit(moving - center)
    dx, dy = 11.0 - 15.0, 2.0 - 0.0
    dn = math.hypot(dx, dy)
    want = Pt(15 + 3.0 * dx / dn, 3.0 * dy / dn)
    assert abs(new_b.x - want.x) < TOL and abs(new_b.y - want.y) < TOL


def test_manual_edit_arc_unspanned_entry_refuses():
    """Reach path with a DISK-CROSSING spanned crossing refuses: the
    spanned portion of the arc is unreachable from the moving end without
    passing through unspanned circle (far-side authority)."""
    # arc covering the RIGHT half (270..90); line from the LEFT along y=0
    arc = Arc(eid="A1", center=Pt(15, 0), r=3.0, start_deg=270.0, end_deg=90.0)
    # radial candidate (12,0)@180 not spanned; the only spanned crossing
    # (18,0)@0 lies past the unspanned entry (12,0)@180 -> refuse
    l1 = _seg("L1", 0, 0, 10, 0)
    ents = _attached(l1) + [arc]
    res = trim_to_closest(ents, Pt(9.9, 0.05), "L1")
    assert not res.ok and res.reason == REFUSAL_NO_TARGET


def test_manual_edit_closest_wins_multiple_targets():
    """Two candidate targets: the nearest to the moving endpoint wins."""
    l1 = _seg("L1", 0, 0, 30, 0)
    near = _seg("NEAR", 10, -5, 10, 5)
    far = _seg("FAR", 25, -5, 25, 5)
    ents = _attached(l1) + [near, far]
    res = trim_to_closest(ents, Pt(29.9, 0.05), "L1")
    assert res.ok and len(res.trims) == 1
    new_a, new_b = res.trims[0].new
    assert abs(new_b.x - 25.0) < TOL  # far line is the closest to b=30


def test_manual_edit_text_is_never_a_target():
    l1 = _seg("L1", 0, 0, 10, 0)
    ents = _attached(l1) + [TextEnt(eid="TX", p=Pt(12, 0), text="note")]
    res = trim_to_closest(ents, Pt(9.9, 0.05), "L1")
    assert not res.ok and res.reason == REFUSAL_NO_TARGET


# -- folds --------------------------------------------------------------------

def test_manual_edit_fold_subject_and_target_allowed():
    """Folds are ordinary Segs to the engine (user answer 8): a fold can
    be the subject AND the target."""
    fold1 = _seg("F1", 0, 0, 20, 0)    # designated fold, the subject
    wall = _seg("W", 0, 0, 0, 5)       # ends at (0,0): not a stray
    fold2 = _seg("F2", 10, -5, 10, 5)  # designated fold, the target
    res = trim_to_closest([fold1, wall, fold2], Pt(19.9, 0.05), "F1")
    assert res.ok and len(res.trims) == 1
    new_a, new_b = res.trims[0].new
    assert abs(new_b.x - 10.0) < TOL


# -- refusals -----------------------------------------------------------------

def test_manual_edit_unknown_edge_refusal_verbatim():
    res = trim_to_closest([_seg("L1", 0, 0, 10, 0)], Pt(5, 0), "GHOST")
    assert not res.ok
    assert res.reason == REFUSAL_UNKNOWN.format(eid="GHOST")
    assert res.reason == "UNKNOWN_EDGE: GHOST is not resolvable in primitives"


def test_manual_edit_no_target_refusal_verbatim():
    """Attached at one end (not a stray) but nothing to trim TO on the
    moving side → NO_TARGET verbatim."""
    l1 = _seg("L1", 0, 0, 20, 0)
    wall = _seg("W", 0, 0, 0, 5)  # ends at (0,0): not a stray
    res = trim_to_closest([l1, wall], Pt(19.9, 0.05), "L1")
    assert not res.ok
    assert res.reason == REFUSAL_NO_TARGET
    assert res.reason == "NO_TARGET: no supporting-geometry intersection found"


# -- both-sides span (ADR-028) ------------------------------------------------

def test_manual_edit_both_ends_attached_deletes_span_not_rotates():
    """Walls at both ends, plus an off-axis line whose perpendicular foot
    would rotate the segment. The span between the walls is deleted."""
    l1 = _seg("L1", 0, 0, 10, 0)
    wall_a = _seg("WA", 0, 0, 0, 5)
    wall_b = _seg("WB", 10, 0, 10, 5)
    off = _seg("OFF", 0, 4, 6, 8)  # infinite-line foot is off y=0
    res = trim_to_closest([l1, wall_a, wall_b, off], Pt(5.0, 0.0), "L1")
    assert res.ok and not res.trims
    assert res.deletions == ["L1"]
    assert SPAN_DELETE_WARNING in res.warnings


def test_manual_edit_span_stops_at_joint_attachment():
    """Two collinear segments, a third line only at the shared endpoint,
    and a wall at the far end of the clicked segment. The shared endpoint
    is the first intersection; the second segment is not deleted."""
    m1 = _seg("M1", 0, 0, 10, 0)
    m2 = _seg("M2", 10, 0, 20, 0)
    third = _seg("T", 10, 0, 10, 5)
    wall = _seg("W", 0, 0, 0, 5)
    res = trim_to_closest([m1, m2, third, wall], Pt(4.0, 0.0), "M1")
    assert res.ok and not res.trims
    assert res.deletions == ["M1"]
    assert "M2" not in res.deletions
    assert SPAN_DELETE_WARNING in res.warnings


def test_manual_edit_span_keeps_collinear_gap_in_the_piece():
    """No other geometry at the joint: both collinear segments are one
    span and both are deleted."""
    m1 = _seg("M1", 0, 0, 10, 0)
    m2 = _seg("M2", 10, 0, 20, 0)
    wall_a = _seg("WA", 0, 0, 0, 5)
    wall_b = _seg("WB", 20, 0, 20, 5)
    res = trim_to_closest([m1, m2, wall_a, wall_b], Pt(5.0, 0.0), "M1")
    assert res.ok and not res.trims
    assert set(res.deletions) == {"M1", "M2"}
    assert SPAN_DELETE_WARNING in res.warnings


def test_manual_edit_span_deletes_segment_past_both_crossings():
    """The clicked segment continues past the nearest crossing on each
    side. Delete that whole segment. The collinear neighbor past the
    far end is not deleted."""
    subject = _seg("S", 0, 0, 20, 0)
    wall = _seg("W", 0, 0, 0, 5)
    left = _seg("C1", 6, -5, 6, 5)
    right = _seg("C2", 14, -5, 14, 5)
    neighbor = _seg("N", 20, 0, 30, 0)
    res = trim_to_closest(
        [subject, wall, left, right, neighbor], Pt(10.0, 0.0), "S")
    assert res.ok and not res.trims
    assert res.deletions == ["S"]
    assert "N" not in res.deletions
    assert SPAN_DELETE_WARNING in res.warnings


def test_manual_edit_span_shortens_member_past_one_crossing():
    """Walls at both ends and one interior crossing. The member continues
    past that crossing only, so the surviving stub is an on-axis trim."""
    l1 = _seg("L1", 0, 0, 20, 0)
    wall_a = _seg("WA", 0, 0, 0, 5)
    wall_b = _seg("WB", 20, 0, 20, 5)
    cross = _seg("C", 8, -5, 8, 5)
    res = trim_to_closest(
        [l1, wall_a, wall_b, cross], Pt(4.0, 0.0), "L1")
    assert res.ok and not res.deletions and len(res.trims) == 1
    new_a, new_b = res.trims[0].new
    assert abs(new_a.x - 8.0) < TOL and abs(new_a.y) < TOL
    assert abs(new_b.x - 20.0) < TOL and abs(new_b.y) < TOL
    assert res.warnings == []


def test_manual_edit_degenerate_candidate_at_moving_point_rejected():
    """A target whose closest point IS the moving endpoint (zero move)
    is not a candidate (guard against no-op trims)."""
    l1 = _seg("L1", 0, 0, 10, 0)
    wall = _seg("W", 0, 0, 0, 5)  # ends at (0,0): not a stray
    # target passing exactly through L1's b end (10,0):
    through = _seg("TH", 10, -5, 10, 5)
    res = trim_to_closest([l1, wall, through], Pt(9.9, 0.05), "L1")
    # candidate (10,0) == moving point → skipped → NO_TARGET
    assert not res.ok and res.reason == REFUSAL_NO_TARGET