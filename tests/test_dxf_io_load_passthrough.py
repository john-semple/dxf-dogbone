"""PassThrough + duplicate-merge behavior on in-memory DXFs (no committed
sample covers the passthrough branch; built with ezdxf in tmp_path)."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import ezdxf
import pytest

from dxf_io import LoadRefused, load
from geometry.entities import PassThrough


def _doc():
    doc = ezdxf.new("R2000")
    doc.header["$INSUNITS"] = 4
    return doc


def _save_load(doc, tmp_path: Path, name: str = "t.dxf"):
    p = tmp_path / name
    doc.saveas(p)
    return load(p)


def test_dxf_io_load_scattered_unsupported_passthroughs_with_warning(tmp_path):
    doc = _doc()
    msp = doc.modelspace()
    msp.add_line((0, 0), (100, 0))
    msp.add_line((0, 0), (0, 100))
    msp.add_ellipse((50, 50), major_axis=(1, 0), ratio=1)  # tiny: ~1.4% of model
    r = _save_load(doc, tmp_path)
    pts = [e for e in r.model_state.primitives if isinstance(e, PassThrough)]
    assert len(pts) == 1 and pts[0].kind == "ELLIPSE"
    assert any("passthrough: unsupported ELLIPSE" in w for w in r.warnings)
    assert Counter(type(e).__name__ for e in r.model_state.primitives)["Seg"] == 2


def test_dxf_io_load_contour_scale_unsupported_refuses(tmp_path):
    doc = _doc()
    msp = doc.modelspace()
    msp.add_line((0, 0), (100, 0))
    msp.add_line((0, 0), (0, 100))
    msp.add_ellipse((50, 50), major_axis=(30, 0), ratio=1)  # 85% of model diag
    with pytest.raises(LoadRefused) as ei:
        _save_load(doc, tmp_path)
    assert "contour-scale ELLIPSE" in ei.value.reason


def test_dxf_io_load_unsupported_without_supported_geometry_refuses(tmp_path):
    doc = _doc()
    doc.modelspace().add_ellipse((0, 0), major_axis=(1, 0), ratio=1)
    with pytest.raises(LoadRefused):
        _save_load(doc, tmp_path)


def test_dxf_io_load_duplicate_lines_merge_with_count(tmp_path):
    doc = _doc()
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0))
    msp.add_line((0, 0), (10, 0))  # exact dup
    msp.add_line((10, 0), (0, 0))  # reversed dup (within EPS_COINCIDE)
    msp.add_line((0, 5), (10, 5))  # distinct
    r = _save_load(doc, tmp_path)
    assert Counter(type(e).__name__ for e in r.model_state.primitives)["Seg"] == 2
    assert any("merged 2 duplicate" in w for w in r.warnings)


def test_dxf_io_load_duplicate_circles_and_arcs_merge(tmp_path):
    doc = _doc()
    msp = doc.modelspace()
    msp.add_circle((5, 5), 2)
    msp.add_circle((5, 5), 2)
    msp.add_arc((20, 5), 3, start_angle=0, end_angle=90)
    msp.add_arc((20, 5), 3, start_angle=0, end_angle=90)
    r = _save_load(doc, tmp_path)
    c = Counter(type(e).__name__ for e in r.model_state.primitives)
    assert c == {"Circ": 1, "Arc": 1}
    assert any("merged 2 duplicate" in w for w in r.warnings)


def test_dxf_io_load_mtext_dedup_requires_same_text(tmp_path):
    doc = _doc()
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0))
    from ezdxf.enums import TextEntityAlignment
    m1 = msp.add_mtext("note A", dxfattribs={"char_height": 2.5})
    m1.set_location((1, 1))
    m2 = msp.add_mtext("note A", dxfattribs={"char_height": 2.5})
    m2.set_location((1, 1))  # same insert + same text -> dup
    m3 = msp.add_mtext("note B", dxfattribs={"char_height": 2.5})
    m3.set_location((1, 1))  # same insert, different text -> kept
    r = _save_load(doc, tmp_path)
    c = Counter(type(e).__name__ for e in r.model_state.primitives)
    assert c["TextEnt"] == 2
    assert any("merged 1 duplicate" in w for w in r.warnings)


def test_dxf_io_load_document_order_preserved_with_passthrough(tmp_path):
    doc = _doc()
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0))
    msp.add_ellipse((50, 50), major_axis=(1, 0), ratio=1)
    msp.add_circle((20, 20), 2)
    r = _save_load(doc, tmp_path)
    kinds = [type(e).__name__ for e in r.model_state.primitives]
    assert kinds == ["Seg", "PassThrough", "Circ"]
