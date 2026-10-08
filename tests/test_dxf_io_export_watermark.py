"""Export watermark filter, audit abort, and the export log (ADR-017, M6)."""
from __future__ import annotations

from pathlib import Path

import ezdxf
import pytest

from dxf_io import load
from dxf_io.export import WATERMARK_TEXTS, export, prepare_export
from geometry.entities import Pt, Seg, TextEnt
from model.state import ModelState

ROOT = Path(__file__).resolve().parent.parent
BEFORE = ROOT / "samples" / "base-rectangular-before-AI.DXF"
AFTER = ROOT / "samples" / "base-rectangular - partially radiused.DXF"
HEADER = {"$ACADVER": "AC1015", "$INSUNITS": 4}
SHOP_NOTE = "Keep this note."


def _state_with_notes() -> ModelState:
    notes = [
        TextEnt(eid="W1", p=Pt(0, 0), text=WATERMARK_TEXTS[0]),
        TextEnt(eid="W2", p=Pt(0, -5), text=WATERMARK_TEXTS[1]),
        TextEnt(eid="N1", p=Pt(10, 10), text=SHOP_NOTE),
        Seg(eid="L1", a=Pt(0, 0), b=Pt(5, 0)),
    ]
    return ModelState(primitives=notes, next_seq=1)


def _texts(path: Path) -> list[str]:
    doc = ezdxf.readfile(str(path))
    found = []
    for entity in doc.modelspace():
        if entity.dxftype() == "MTEXT":
            found.append(entity.text)
    return found


def test_dxf_io_export_watermark_on_drops_exact_texts_keeps_other_notes(tmp_path):
    state = _state_with_notes()
    out = tmp_path / "on.dxf"
    result = export(state, HEADER, out, remove_watermark=True)
    assert result.written
    assert result.deleted_entity_count == 2
    texts = _texts(out)
    assert texts == [SHOP_NOTE]
    # the working model still shows the watermark
    assert [e.text for e in state.primitives if isinstance(e, TextEnt)] == [
        WATERMARK_TEXTS[0],
        WATERMARK_TEXTS[1],
        SHOP_NOTE,
    ]


def test_dxf_io_export_watermark_off_keeps_both_lines(tmp_path):
    state = _state_with_notes()
    out = tmp_path / "off.dxf"
    result = export(state, HEADER, out, remove_watermark=False)
    assert result.written
    assert result.deleted_entity_count == 0
    assert _texts(out) == [WATERMARK_TEXTS[0], WATERMARK_TEXTS[1], SHOP_NOTE]


def test_dxf_io_export_watermark_default_is_on(tmp_path):
    state = _state_with_notes()
    out = tmp_path / "default.dxf"
    export(state, HEADER, out)
    assert _texts(out) == [SHOP_NOTE]


def test_dxf_io_export_watermark_ignores_substring(tmp_path):
    """A note that merely contains the watermark words is not removed."""
    state = ModelState(
        primitives=[
            TextEnt(eid="N", p=Pt(0, 0), text="See SOLIDWORKS Educational Product. today"),
        ],
        next_seq=1,
    )
    out = tmp_path / "substr.dxf"
    export(state, HEADER, out)
    assert _texts(out) == ["See SOLIDWORKS Educational Product. today"]


def test_dxf_io_export_watermark_idempotent(tmp_path):
    state = _state_with_notes()
    first = tmp_path / "first.dxf"
    export(state, HEADER, first, remove_watermark=True)
    reloaded = load(first)
    second = tmp_path / "second.dxf"
    export(reloaded.model_state, HEADER, second, remove_watermark=True)
    assert _texts(first) == _texts(second) == [SHOP_NOTE]


@pytest.mark.parametrize("path", [BEFORE, AFTER])
def test_dxf_io_export_watermark_golden_files(tmp_path, path):
    loaded = load(path)
    on_path = tmp_path / "on.dxf"
    off_path = tmp_path / "off.dxf"
    export(loaded.model_state, loaded.header, on_path, remove_watermark=True)
    export(loaded.model_state, loaded.header, off_path, remove_watermark=False)
    on_texts = _texts(on_path)
    off_texts = _texts(off_path)
    assert not any(text in WATERMARK_TEXTS for text in on_texts)
    for expected in WATERMARK_TEXTS:
        assert expected in off_texts
    # both golden files contain only the two watermark notes
    assert on_texts == []
    assert off_texts == list(WATERMARK_TEXTS)


def test_dxf_io_export_prepare_does_not_mutate_and_hides_watermark():
    state = _state_with_notes()
    before = [e.text for e in state.primitives if isinstance(e, TextEnt)]
    prepared = prepare_export(state, remove_watermark=True)
    assert [e.text for e in state.primitives if isinstance(e, TextEnt)] == before
    preview = [e.text for e in prepared.state.primitives if isinstance(e, TextEnt)]
    assert preview == [SHOP_NOTE]
    kept = prepare_export(state, remove_watermark=False)
    assert [e.text for e in kept.state.primitives if isinstance(e, TextEnt)] == before


def test_dxf_io_export_audit_failure_writes_nothing(tmp_path, monkeypatch):
    class _Bad:
        errors = ["broken handle on entity 1"]
        fixes = []

    monkeypatch.setattr(ezdxf.document.Drawing, "audit", lambda self: _Bad())
    state = _state_with_notes()
    out = tmp_path / "bad.dxf"
    result = export(state, HEADER, out, original=state)
    assert result.written is False
    assert "was not saved" in result.audit_summary
    assert "broken handle" in result.audit_summary
    assert not out.exists()
    assert not Path(str(out) + ".export_log.md").exists()


def test_dxf_io_export_log_lists_dogbone_deletion_and_flag(tmp_path):
    from geometry.entities import Arc, Dogbone, Side

    arc = Arc(eid="A", center=Pt(1, 2), r=1.5875, start_deg=0, end_deg=180)
    db = Dogbone(
        db_id="db-test",
        apex=Pt(0, 0),
        center=Pt(1, 2),
        r=1.5875,
        side=Side(1),
        edge1_eid="L1",
        edge2_eid="L2",
        arc=arc,
    )
    original = ModelState(
        primitives=[
            Seg(eid="GONE", a=Pt(0, 0), b=Pt(1, 0)),
            Seg(eid="L1", a=Pt(0, 0), b=Pt(3, 0)),
            TextEnt(eid="W1", p=Pt(0, 5), text=WATERMARK_TEXTS[0]),
        ],
        next_seq=1,
    )
    current = ModelState(
        primitives=[
            Seg(eid="L1", a=Pt(0, 0), b=Pt(3, 0)),
            TextEnt(eid="W1", p=Pt(0, 5), text=WATERMARK_TEXTS[0]),
            arc,
        ],
        dogbones=[db],
        flag_decisions={"GONE": "delete"},
        next_seq=2,
    )
    out = tmp_path / "part_dogbone.dxf"
    result = export(current, HEADER, out, original=original)
    assert result.written
    log = Path(str(out) + ".export_log.md").read_text(encoding="utf-8")
    assert "center (1.0000, 2.0000), R=1.5875" in log
    assert "GONE LINE" in log
    assert "W1 MTEXT" in log
    assert "GONE: delete" in log
    assert "clean" in log
