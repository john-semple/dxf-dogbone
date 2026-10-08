"""DXF export — CONTRACTS §3 fold stage (headless; ezdxf allowed).

Pipeline (CONTRACTS §3 order):
  1. deep copy the working ModelState (ADR-004 purity — the working model
     is immutable under export; re-export after undo cannot double-trim).
  2. fold extend/trim (``rules.folds.resolve_folds`` applied to the copy's
     primitives; idempotent by construction — endpoints already on a
     relief arc are the nearest valid candidate to themselves).
  3. build an ezdxf document from the (possibly trimmed) entities; move
     designated fold eids to the ``FOLD_LINES`` layer with
     ``FOLD_COLOR_CONST`` (ACI 7) and Continuous linetype (SAMPLES.md).
  4. ezdxf.audit pre-check (M6 owns the strict refuse gate; M5a runs the
     audit and reports — ``audit_summary``).
  5. save to ``out_path`` (output version == input version per SPEC §11.3
     case 2; the M6 dialog supplies the real path; tests use ``tmp_path``).

``ExportResult`` per CONTRACTS §3: ``warnings`` (out-of-reach fold
warnings + any audit notes), ``audit_summary`` (``"clean"`` or a
report), ``deleted_entity_count`` (always 0 in M5a — the fold stage
trims/extends, never deletes).
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from pathlib import Path

import ezdxf
from ezdxf.audit import Auditor

from geometry.entities import (
    Arc,
    Circ,
    Entity,
    PointEnt,
    Pt,
    Seg,
    TextEnt,
)
from geometry.tolerances import EPS_COINCIDE
from model.state import ModelState
from rules.folds import out_of_reach_warnings, resolve_folds

FOLD_COLOR_CONST: int = 7  # SAMPLES.md: ACI 7, Continuous, layer 0
FOLD_LINETYPE: str = "Continuous"


@dataclass
class ExportResult:
    warnings: list[str] = field(default_factory=list)
    audit_summary: str = ""
    deleted_entity_count: int = 0


def _apply_trims(primitives: list[Entity], trims) -> None:
    """Apply ``resolve_folds`` Trims to the deep-copied primitives in place
    (Seg endpoint repositioning per ADR-015(d))."""
    by_eid = {e.eid: i for i, e in enumerate(primitives) if isinstance(e, Seg)}
    from dataclasses import replace
    for t in trims:
        idx = by_eid.get(t.eid)
        if idx is None:
            continue
        old = primitives[idx]
        new_a, new_b = t.new
        primitives[idx] = replace(old, a=new_a, b=new_b)


def _build_doc(state: ModelState, header: dict, fold_layer: str, fold_color: int) -> "ezdxf.Document":
    """Build an ezdxf document from the ModelState entities. Designated
    fold eids go to ``fold_layer`` with ``fold_color``; everything else
    keeps its original layer (layer 0 by default — the load path does not
    preserve layer names into entities, so non-fold entities land on
    layer 0, matching the SAMPLES.md fold-constants observation that the
    after-file's fold lines move to a distinct layer/color while the rest
    stays on layer 0)."""
    doc = ezdxf.new(header.get("$ACADVER", "AC1015"))
    # SPEC §11.3 case 1: $INSUNITS must be 4 (mm) on output (the loader
    # refuses anything else; round-trip must stay in mm).
    doc.header["$INSUNITS"] = header.get("$INSUNITS", 4)
    msp = doc.modelspace()
    folds = set(state.fold_eids)
    for e in state.primitives:
        is_fold = e.eid in folds
        layer = fold_layer if is_fold else "0"
        color = fold_color if is_fold else None
        if isinstance(e, Seg):
            kw = {"layer": layer}
            if color is not None:
                kw["color"] = color
            msp.add_line((e.a.x, e.a.y), (e.b.x, e.b.y), dxfattribs=kw)
        elif isinstance(e, Arc):
            kw = {"layer": layer, "center": (e.center.x, e.center.y), "radius": e.r,
                  "start_angle": e.start_deg, "end_angle": e.end_deg}
            if color is not None:
                kw["color"] = color
            msp.add_arc(dxfattribs=kw)
        elif isinstance(e, Circ):
            kw = {"layer": layer, "center": (e.center.x, e.center.y), "radius": e.r}
            if color is not None:
                kw["color"] = color
            msp.add_circle(dxfattribs=kw)
        elif isinstance(e, PointEnt):
            kw = {"layer": layer}
            if color is not None:
                kw["color"] = color
            msp.add_point((e.p.x, e.p.y), dxfattribs=kw)
        elif isinstance(e, TextEnt):
            kw = {"layer": layer}
            if color is not None:
                kw["color"] = color
            msp.add_mtext((e.p.x, e.p.y), e.text, dxfattribs=kw)
    return doc


def export(
    state: ModelState,
    header: dict,
    out_path: Path,
    fold_layer: str = "FOLD_LINES",
    fold_color: int = FOLD_COLOR_CONST,
    *,
    eps: float = EPS_COINCIDE,
) -> ExportResult:
    """Export the working model to a DXF (CONTRACTS §3; ADR-004 pure)."""
    out_path = Path(out_path)
    working = copy.deepcopy(state)
    # Compute out-of-reach warnings on the ORIGINAL endpoints (before any
    # trim/extend is applied) — a fold whose near endpoint is within reach
    # but whose far endpoint is beyond the cap must warn about the far
    # endpoint's original position, not the post-trim position.
    warnings = list(
        out_of_reach_warnings(working.primitives, working.dogbones, working.fold_eids, eps)
    )
    trims = resolve_folds(working.primitives, working.dogbones, working.fold_eids, eps)
    _apply_trims(working.primitives, trims)
    doc = _build_doc(working, header, fold_layer, fold_color)
    auditor = doc.audit()
    if auditor.errors:
        audit_summary = f"{len(auditor.errors)} audit errors"
    elif auditor.fixes:
        audit_summary = f"{len(auditor.fixes)} audit fixes applied (clean)"
    else:
        audit_summary = "clean"
    doc.saveas(str(out_path))
    return ExportResult(
        warnings=warnings,
        audit_summary=audit_summary,
        deleted_entity_count=0,
    )