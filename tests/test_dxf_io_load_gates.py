"""SPEC 11.3 load gates against the committed negative + golden samples."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from dxf_io import LoadRefused, load
from geometry.entities import PassThrough
from model.state import ModelState

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
BEFORE = SAMPLES / "base-rectangular-before-AI.DXF"
AFTER = SAMPLES / "base-rectangular - partially radiused.DXF"


def test_dxf_io_load_refuses_inch_units():
    with pytest.raises(LoadRefused) as ei:
        load(SAMPLES / "neg-inch.dxf")
    assert "$INSUNITS" in ei.value.reason and "must be 4" in ei.value.reason


def test_dxf_io_load_warns_on_r12_then_loads():
    r = load(SAMPLES / "neg-r12.dxf")
    assert r.header["$ACADVER"] == "AC1009"
    assert any("R12" in w for w in r.warnings)
    assert len(r.model_state.primitives) == 6


def test_dxf_io_load_refuses_contour_scale_spline():
    with pytest.raises(LoadRefused) as ei:
        load(SAMPLES / "neg-spline.dxf")
    assert "contour-scale SPLINE" in ei.value.reason


def test_dxf_io_load_missing_file_refused():
    with pytest.raises(LoadRefused):
        load(SAMPLES / "no-such-file.dxf")


def test_dxf_io_load_golden_before_counts_match_census():
    r = load(BEFORE)
    c = Counter(type(e).__name__ for e in r.model_state.primitives)
    assert c == {"Seg": 78, "Arc": 14, "Circ": 27, "TextEnt": 2}
    assert not any(isinstance(e, PassThrough) for e in r.model_state.primitives)
    assert r.header == {"$INSUNITS": 4, "$ACADVER": "AC1015"}
    assert r.warnings == []


def test_dxf_io_load_golden_after_counts_match_census():
    r = load(AFTER)
    c = Counter(type(e).__name__ for e in r.model_state.primitives)
    assert c == {"Seg": 85, "Arc": 15, "PointEnt": 2, "TextEnt": 2}
    assert r.warnings == []


def test_dxf_io_load_returns_contracted_model_state():
    r = load(BEFORE)
    st = r.model_state
    assert isinstance(st, ModelState)
    assert st.dogbones == [] and st.fold_eids == set()
    assert st.flag_decisions == {} and st.next_seq == 1
    eids = [e.eid for e in st.primitives]
    assert len(eids) == len(set(eids))  # unique handles


def test_dxf_io_load_synthetic_fold_overlay_merges_by_geometry():
    r = load(SAMPLES / "syn-fold-heavy.dxf")
    assert any("duplicate" in w for w in r.warnings)
    assert Counter(type(e).__name__ for e in r.model_state.primitives)["Seg"] == 11
