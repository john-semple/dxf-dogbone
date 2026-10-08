"""dxf_io/export.py fold stage — CONTRACTS §3 (ADR-004 purity; SPEC §11.6).

Gates (M5a DoD):
  - export moves designated fold eids to FOLD_LINES with color 7 on the
    deep copy; non-fold entities keep their layer/color.
  - purity: working ModelState bit-identical before/after export.
  - re-export idempotency: export → export the result again → no double
    trim (ADR-004's whole point).
  - trimmed endpoints lie ON the engine arc within 0.001 (ISSUE-012(d)).
"""
from pathlib import Path

import ezdxf
import pytest

from dxf_io import FOLD_COLOR_CONST, export
from geometry.entities import Arc, Dogbone, Pt, Seg, Side
from model.state import ModelState


def _db(center, r, span=(45.0, 225.0)):
    arc = Arc(eid="arc1", center=center, r=r, start_deg=span[0], end_deg=span[1])
    return Dogbone(
        db_id="db1",
        apex=Pt(45.0, 51.5168),
        center=center,
        r=r,
        side=Side(-1),
        edge1_eid="e1",
        edge2_eid="e2",
        arc=arc,
    )


def _state_with_fold(fold, db, fold_eids=None):
    return ModelState(
        primitives=[fold],
        dogbones=[db],
        fold_eids=fold_eids if fold_eids is not None else {fold.eid},
        next_seq=1,
    )


def test_dxf_io_export_fold_moves_to_fold_lines_layer_with_color_7(tmp_path):
    """Designated fold eids move to FOLD_LINES with color 7 (FOLD_COLOR_CONST);
    non-fold entities keep layer 0 / no explicit color."""
    db = _db(Pt(46.12253, 50.39427), 1.5875)
    fold = Seg(eid="F1", a=Pt(40.0, 51.2634), b=Pt(0.0, 51.2634))
    contour = Seg(eid="C1", a=Pt(0.0, 80.0), b=Pt(100.0, 80.0))  # non-fold, far
    state = ModelState(
        primitives=[fold, contour],
        dogbones=[db],
        fold_eids={"F1"},
        next_seq=1,
    )
    out = tmp_path / "out.dxf"
    r = export(state, {"$ACADVER": "AC1015", "$INSUNITS": 4}, out)
    assert r.audit_summary == "clean"
    assert out.exists()
    doc = ezdxf.readfile(str(out))
    msp = doc.modelspace()
    lines = list(msp.query("LINE"))
    by_layer = {}
    for ln in lines:
        by_layer.setdefault(ln.dxf.layer, []).append(ln)
    # the fold is on FOLD_LINES with color 7
    assert "FOLD_LINES" in by_layer
    fold_lines = by_layer["FOLD_LINES"]
    assert len(fold_lines) == 1
    assert fold_lines[0].dxf.color == FOLD_COLOR_CONST
    # the contour is on layer 0 (not FOLD_LINES)
    assert "0" in by_layer
    assert len(by_layer["0"]) == 1


def test_dxf_io_export_purity_working_model_unchanged(tmp_path):
    """ADR-004: the working ModelState is bit-identical before/after export
    (deep copy; no mutation of the input state)."""
    import copy

    db = _db(Pt(46.12253, 50.39427), 1.5875)
    fold = Seg(eid="F1", a=Pt(40.0, 51.2634), b=Pt(0.0, 51.2634))
    state = _state_with_fold(fold, db)
    before = copy.deepcopy(state)
    out = tmp_path / "out.dxf"
    export(state, {"$ACADVER": "AC1015", "$INSUNITS": 4}, out)
    # bit-identical: primitives, dogbones, fold_eids, flag_decisions, next_seq
    assert state.primitives == before.primitives
    assert state.dogbones == before.dogbones
    assert state.fold_eids == before.fold_eids
    assert state.flag_decisions == before.flag_decisions
    assert state.next_seq == before.next_seq
    # the fold endpoint was NOT moved in the working model
    assert state.primitives[0].a == Pt(40.0, 51.2634)


def test_dxf_io_export_re_export_idempotency_no_double_trim(tmp_path):
    """ADR-004's whole point: export → reload the result → export again →
    no double trim. The trimmed endpoint is already on the arc; the second
    export's resolve_folds returns no Trim for it."""
    db = _db(Pt(46.12253, 50.39427), 1.5875)
    fold = Seg(eid="F1", a=Pt(40.0, 51.2634), b=Pt(0.0, 51.2634))
    state = _state_with_fold(fold, db)
    out1 = tmp_path / "out1.dxf"
    export(state, {"$ACADVER": "AC1015", "$INSUNITS": 4}, out1)

    # reload out1 — the fold's near endpoint should be on the arc
    doc1 = ezdxf.readfile(str(out1))
    msp1 = doc1.modelspace()
    fold_lines = [ln for ln in msp1.query("LINE") if ln.dxf.layer == "FOLD_LINES"]
    assert len(fold_lines) == 1
    starts = [fold_lines[0].dxf.start, fold_lines[0].dxf.end]
    # one endpoint is (44.7941, 51.2634) — on the arc
    on_arc = [s for s in starts if abs((s.x - db.center.x) ** 2 + (s.y - db.center.y) ** 2 - db.r ** 2) < 1e-6]
    assert len(on_arc) == 1

    # build a new state from the exported geometry, RE-DESIGNATE the fold
    # (the loader sets fold_eids=set(); M5b's auto-preselect would re-pick
    # the FOLD_LINES layer — here we designate manually to test the engine
    # idempotency), and export AGAIN
    from dxf_io import load
    r2 = load(out1)
    # the fold eid in out1 is the DXF handle of the FOLD_LINES line; find it
    fold_eid2 = next(
        e.eid for e in r2.model_state.primitives
        if isinstance(e, Seg) and e.eid  # the fold line
    )
    r2.model_state.fold_eids = {fold_eid2}
    # carry the dogbone so resolve_folds has a circle to resolve against
    r2.model_state.dogbones = [db]
    out2 = tmp_path / "out2.dxf"
    export(r2.model_state, {"$ACADVER": "AC1015", "$INSUNITS": 4}, out2)
    # the second export should not double-trim: the fold endpoints in out2
    # match out1's endpoints (the on-arc endpoint is unchanged)
    doc2 = ezdxf.readfile(str(out2))
    msp2 = doc2.modelspace()
    fold_lines2 = [ln for ln in msp2.query("LINE") if ln.dxf.layer == "FOLD_LINES"]
    assert len(fold_lines2) == 1
    s2 = {fold_lines2[0].dxf.start, fold_lines2[0].dxf.end}
    s1 = {fold_lines[0].dxf.start, fold_lines[0].dxf.end}
    # endpoints match (allowing for ezdxf's Vec3 equality)
    assert {(round(p.x, 6), round(p.y, 6)) for p in s1} == {
        (round(p.x, 6), round(p.y, 6)) for p in s2
    }


def test_dxf_io_export_trimmed_endpoints_on_engine_arc(tmp_path):
    """ISSUE-012(d): trimmed endpoints lie ON the ENGINE corner-1 arc
    (center (45.2534, 121.6506)) within 0.001. The SAMPLES.md
    (44.3930/46.1138) values were measured on the USER's hand-made arc and
    are M6 residuals."""
    from rules.engine import ghost_candidates, place_corner

    prims = [
        Seg("84", Pt(62.2139, 137.0236), Pt(46.9605, 121.7702)),
        Seg("85", Pt(46.2534, 119.7702), Pt(46.9605, 121.7702)),
        Seg("86", Pt(46.2534, 120.5168), Pt(46.2534, 119.7702)),
        Seg("87", Pt(44.2534, 120.5168), Pt(46.2534, 120.5168)),
        Seg("88", Pt(44.2534, 119.7702), Pt(44.2534, 120.5168)),
        Seg("89", Pt(43.5463, 121.7702), Pt(44.2534, 119.7702)),
        Seg("8A", Pt(43.5463, 121.7702), Pt(28.2929, 137.0236)),
    ]
    target = Pt(45.2534, 121.6506)
    gcs = ghost_candidates(prims, "8A", "84", 1.5875)
    side, flip = None, None
    for s, f, c in gcs:
        if abs(c.x - target.x) < 1e-4 and abs(c.y - target.y) < 1e-4:
            side, flip = s, f
            break
    res = place_corner(prims, "8A", "84", side, 1.5875, set(), [], side_flip=flip)
    assert res.ok
    db = res.dogbone
    # right-side fold portion near the engine arc
    fold = Seg(eid="FR", a=Pt(46.607, 120.7702), b=Pt(184.4066, 120.7702))
    state = ModelState(
        primitives=[fold, *prims],
        dogbones=[db],
        fold_eids={"FR"},
        next_seq=1,
    )
    out = tmp_path / "corner1.dxf"
    r = export(state, {"$ACADVER": "AC1015", "$INSUNITS": 4}, out)
    assert r.audit_summary == "clean"
    doc = ezdxf.readfile(str(out))
    msp = doc.modelspace()
    fold_lines = [ln for ln in msp.query("LINE") if ln.dxf.layer == "FOLD_LINES"]
    assert len(fold_lines) == 1
    s, e = fold_lines[0].dxf.start, fold_lines[0].dxf.end
    # one endpoint is on the engine arc within 0.001
    ds = abs((s.x - db.center.x) ** 2 + (s.y - db.center.y) ** 2 - db.r ** 2)
    de = abs((e.x - db.center.x) ** 2 + (e.y - db.center.y) ** 2 - db.r ** 2)
    assert min(ds, de) < 1e-6  # one endpoint on the arc within ~0.001
    # the on-arc endpoint is the engine-arc right entry x ≈ 46.5744
    on_arc_pt = s if ds < de else e
    assert abs(on_arc_pt.x - 46.5744) < 0.001


def test_dxf_io_export_no_folds_still_works(tmp_path):
    """Export with zero designated folds → no fold layer, no trims, clean."""
    db = _db(Pt(46.12253, 50.39427), 1.5875)
    contour = Seg(eid="C1", a=Pt(0.0, 80.0), b=Pt(100.0, 80.0))
    state = ModelState(
        primitives=[contour],
        dogbones=[db],
        fold_eids=set(),
        next_seq=1,
    )
    out = tmp_path / "nofolds.dxf"
    r = export(state, {"$ACADVER": "AC1015", "$INSUNITS": 4}, out)
    assert r.audit_summary == "clean"
    assert r.warnings == []
    doc = ezdxf.readfile(str(out))
    msp = doc.modelspace()
    # no FOLD_LINES layer content
    assert not any(ln.dxf.layer == "FOLD_LINES" for ln in msp.query("LINE"))


def test_dxf_io_export_fold_color_constant_is_7():
    """SAMPLES.md: FOLD_COLOR_CONST = 7 (ACI), enforced in export and tests."""
    assert FOLD_COLOR_CONST == 7


def test_dxf_io_export_result_has_contracted_fields(tmp_path):
    """ExportResult carries warnings, audit_summary, deleted_entity_count
    (CONTRACTS §3)."""
    db = _db(Pt(46.12253, 50.39427), 1.5875)
    fold = Seg(eid="F1", a=Pt(40.0, 51.2634), b=Pt(0.0, 51.2634))
    state = _state_with_fold(fold, db)
    out = tmp_path / "out.dxf"
    r = export(state, {"$ACADVER": "AC1015", "$INSUNITS": 4}, out)
    assert isinstance(r.warnings, list)
    assert isinstance(r.audit_summary, str) and r.audit_summary
    assert isinstance(r.deleted_entity_count, int) and r.deleted_entity_count == 0