"""DXF load with upfront validation - CONTRACTS 3 + SPEC 11.3 (refuse upfront, with reason).

Gates, in SPEC 11.3 order (first refusal wins):
  1. ``$INSUNITS`` must be exactly 4 (mm) - missing or any other value refuses
     (also guards the 25.4x radius error class, ADR-005).
  2. ``$ACADVER``: accept R2000+ (numeric tag >= AC1015); AC1009 (R12) loads
     with a warning; anything older or unset refuses. Output version ==
     input version (M6 export copies the header).
  3. Entity census: V1 processes LINE/ARC/CIRCLE/POINT/MTEXT. Unsupported
     entities are REFUSED as "contour-scale" when their bbox diagonal is
     >= 20 pct of the supported-model bbox diagonal (ADR-014(e); SPEC's
     "contour-scale" wording is not machine-decidable on its own); smaller
     ones pass through untouched as PassThrough + warning (SPEC 6). An
     entity ezdxf cannot size passes through with an "unsized" warning
     (refuse only on *known* contour scale). Any unsupported entity in a
     file with no supported geometry refuses. Known V1 limitation: many
     small splines that collectively form a contour pass individually.
  4. Duplicates (same type, geometry coincident within EPS_COINCIDE) merge -
     the first occurrence in document order is kept, later ones are dropped,
     count logged in warnings. Per-type semantics pinned here (11.3 case 4
     says only "same type, endpoints within EPS_COINCIDE"):
       LINE   both endpoints coincide, either order
       ARC    center + radius + both endpoint points coincide (either order)
       CIRCLE center + radius coincide
       POINT  location coincides
       MTEXT  insertion point coincides AND text is identical
       PassThrough exempt ("never modified", CONTRACTS 1)
  5. Fold lines: STUB - no folds are designated at load (M5 owns
     designation), so the per-fold contour-distance warning list is empty
     by construction.

Other pins: modelspace entities only (paperspace ignored); eids are DXF
handles; MTEXT text is stripped to plain text via ezdxf's own extractor
(``ezdxf.tools.text.plain_mtext``); entities' raw OCS/extrusion is not
projected (flat-pattern assumption, SPEC 1); ``next_seq`` starts at 1.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import ezdxf
import ezdxf.recover
from ezdxf import bbox as _ezbbox
from ezdxf.tools.text import plain_mtext

from geometry.entities import (
    Arc,
    Circ,
    Entity,
    PassThrough,
    PointEnt,
    Pt,
    Seg,
    TextEnt,
)
from geometry.tolerances import EPS_COINCIDE
from model.state import ModelState

SUPPORTED_TYPES = frozenset({"LINE", "ARC", "CIRCLE", "POINT", "MTEXT"})

# ADR-014(e): unsupported entity is "contour-scale" when its bbox diagonal is
# >= this fraction of the supported-model bbox diagonal.
CONTOUR_SCALE_RATIO = 0.20


class LoadRefused(Exception):
    """Raised for SPEC 11.3 refusal cases; ``reason`` is user-presentable."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class LoadResult:
    model_state: ModelState
    header: dict = field(default_factory=dict)  # $INSUNITS, $ACADVER
    warnings: list[str] = field(default_factory=list)
    # M5b auto-preselect: eid -> DXF layer name. Entities don't carry layer
    # (CONTRACTS §1), so the layer map travels in LoadResult for the UI's
    # auto-preselect-on-load (case-insensitive contains bend|fold|centerline).
    layer_of: dict[str, str] = field(default_factory=dict)


def _read_doc(path: Path, warnings: list[str]):
    """ezdxf.readfile with recover fallback (SPEC 11.3 damaged-file path)."""
    try:
        return ezdxf.readfile(path)
    except OSError as exc:
        raise LoadRefused(f"cannot read file: {exc}") from exc
    except Exception:
        doc, auditor = ezdxf.recover.readfile(path)
        warnings.append(
            f"loaded via ezdxf.recover ({len(auditor.errors)} recoverable errors)"
        )
        return doc


def _check_units(doc) -> None:
    units = doc.header.get("$INSUNITS", None)
    if units != 4:
        shown = "unset" if units is None else repr(units)
        raise LoadRefused(
            f"$INSUNITS is {shown}, must be 4 (mm) - refusing "
            "(radius values would be mis-scaled; ADR-005)"
        )


def _check_version(doc, warnings: list[str]) -> str:
    ver = doc.header.get("$ACADVER", "")
    if ver == "AC1009":  # R12: warn + proceed (SPEC 11.3 case 2)
        warnings.append("DXF version R12 (AC1009) is older than R2000 - loaded anyway")
        return ver
    num = "".join(ch for ch in str(ver) if ch.isdigit())
    if num < "1015":
        raise LoadRefused(
            f"DXF version '{ver or '(unset)'}' not supported - accept R2000+, warn on R12, refuse older"
        )
    return ver


def _pt_dist(p: Pt, q: Pt) -> float:
    return math.hypot(p.x - q.x, p.y - q.y)


def _arc_endpoints(a: Arc) -> tuple[Pt, Pt]:
    s = Pt(a.center.x + a.r * math.cos(math.radians(a.start_deg)),
           a.center.y + a.r * math.sin(math.radians(a.start_deg)))
    e = Pt(a.center.x + a.r * math.cos(math.radians(a.end_deg)),
           a.center.y + a.r * math.sin(math.radians(a.end_deg)))
    return s, e


def _is_dup(x: Entity, y: Entity, eps: float) -> bool:
    """Per-type duplicate semantics (module docstring, 11.3 case 4)."""
    if type(x) is not type(y):
        return False
    if isinstance(x, Seg):
        return ((_pt_dist(x.a, y.a) <= eps and _pt_dist(x.b, y.b) <= eps)
                or (_pt_dist(x.a, y.b) <= eps and _pt_dist(x.b, y.a) <= eps))
    if isinstance(x, Arc):
        if _pt_dist(x.center, y.center) > eps or abs(x.r - y.r) > eps:
            return False
        xs, xe = _arc_endpoints(x)
        ys, ye = _arc_endpoints(y)
        return ((_pt_dist(xs, ys) <= eps and _pt_dist(xe, ye) <= eps)
                or (_pt_dist(xs, ye) <= eps and _pt_dist(xe, ys) <= eps))
    if isinstance(x, Circ):
        return _pt_dist(x.center, y.center) <= eps and abs(x.r - y.r) <= eps
    if isinstance(x, PointEnt):
        return _pt_dist(x.p, y.p) <= eps
    if isinstance(x, TextEnt):
        return _pt_dist(x.p, y.p) <= eps and x.text == y.text
    return False  # PassThrough exempt ("never modified")


def _supported_bbox(primitives: list[Entity]) -> tuple[float, float, float, float] | None:
    """(minx, miny, maxx, maxy) over supported primitives; None when empty."""
    lo: list[float] = []
    hi: list[float] = []
    for e in primitives:
        if isinstance(e, Seg):
            lo += [min(e.a.x, e.b.x), min(e.a.y, e.b.y)]
            hi += [max(e.a.x, e.b.x), max(e.a.y, e.b.y)]
        elif isinstance(e, (Arc, Circ)):
            c, r = e.center, e.r
            lo += [c.x - r, c.y - r]
            hi += [c.x + r, c.y + r]
        elif isinstance(e, (PointEnt, TextEnt)):
            lo += [e.p.x, e.p.y]
            hi += [e.p.x, e.p.y]
    if not lo:
        return None
    return min(lo[0::2]), min(lo[1::2]), max(hi[0::2]), max(hi[1::2])


def _unsupported_diag(entity) -> tuple[float, str | None]:
    """(bbox diagonal mm, note) of a raw ezdxf entity; note set when unsizable."""
    try:
        ext = _ezbbox.extents([entity])
        if ext.has_data:
            return (math.hypot(ext.extmax.x - ext.extmin.x,
                               ext.extmax.y - ext.extmin.y), None)
        return 0.0, "unsized"
    except Exception as exc:  # unsizable -> passthrough + warning (ADR-014(e))
        return 0.0, f"unsized ({type(exc).__name__})"


def _fold_contour_warnings(primitives: list[Entity], fold_eids: set[str], eps: float) -> list[str]:
    """SPEC 11.3 case 5 stub: no folds are designated at load (M5 owns it)."""
    if not fold_eids:
        return []
    segs = [e for e in primitives if isinstance(e, Seg)]
    by_id = {e.eid: e for e in segs}
    out: list[str] = []
    for eid in sorted(fold_eids):
        f = by_id.get(eid)
        if f is None:
            continue
        for e in segs:
            if e.eid == eid:
                continue
            if (min(_pt_dist(f.a, e.a), _pt_dist(f.a, e.b),
                    _pt_dist(f.b, e.a), _pt_dist(f.b, e.b)) <= eps):
                out.append(f"fold {eid} runs within {eps} mm of contour edge {e.eid}")
    return out


def load(path: Path) -> LoadResult:
    """Load a DXF into ModelState per CONTRACTS 3; raises LoadRefused for 11.3 cases."""
    path = Path(path)
    warnings: list[str] = []

    doc = _read_doc(path, warnings)
    _check_units(doc)
    ver = _check_version(doc, warnings)

    msp = doc.modelspace()
    supported: list[Entity] = []
    passthrough: list[tuple[int, PassThrough]] = []
    unsupported_raw: list[tuple[int, object]] = []
    order: list[tuple[int, str]] = []  # (index, "prim" | "pass")
    layer_of: dict[str, str] = {}  # M5b auto-preselect: eid -> DXF layer

    for raw in msp:
        t = raw.dxftype()
        h = str(raw.dxf.handle)
        idx = len(order)
        if t == "LINE":
            s, e = raw.dxf.start, raw.dxf.end
            supported.append(Seg(eid=h, a=Pt(s.x, s.y), b=Pt(e.x, e.y)))
            order.append((idx, "prim"))
            layer_of[h] = str(raw.dxf.layer)
        elif t == "ARC":
            c = raw.dxf.center
            supported.append(Arc(eid=h, center=Pt(c.x, c.y), r=raw.dxf.radius,
                                  start_deg=raw.dxf.start_angle,
                                  end_deg=raw.dxf.end_angle))
            order.append((idx, "prim"))
            layer_of[h] = str(raw.dxf.layer)
        elif t == "CIRCLE":
            c = raw.dxf.center
            supported.append(Circ(eid=h, center=Pt(c.x, c.y), r=raw.dxf.radius))
            order.append((idx, "prim"))
            layer_of[h] = str(raw.dxf.layer)
        elif t == "POINT":
            p = raw.dxf.location
            supported.append(PointEnt(eid=h, p=Pt(p.x, p.y)))
            order.append((idx, "prim"))
            layer_of[h] = str(raw.dxf.layer)
        elif t == "MTEXT":
            p = raw.dxf.insert
            try:
                text = plain_mtext(raw.text)
            except Exception:
                text = raw.text
            supported.append(TextEnt(eid=h, p=Pt(p.x, p.y), text=text))
            order.append((idx, "prim"))
            layer_of[h] = str(raw.dxf.layer)
        else:
            unsupported_raw.append((idx, raw))
            order.append((idx, "pass"))

    # -- 11.3 case 3: contour-scale gate (ADR-014(e)) --
    if unsupported_raw:
        bbox = _supported_bbox(supported)
        model_diag = 0.0
        if bbox is not None:
            model_diag = math.hypot(bbox[2] - bbox[0], bbox[3] - bbox[1])
        for _idx, raw in unsupported_raw:
            diag, note = _unsupported_diag(raw)
            if model_diag <= 0.0:
                raise LoadRefused(
                    f"unsupported {raw.dxftype()} with no supported geometry to size it "
                    "against - V1 cannot process"
                )
            if note is None and diag >= CONTOUR_SCALE_RATIO * model_diag:
                raise LoadRefused(
                    f"contour-scale {raw.dxftype()} present - V1 cannot process "
                    f"(bbox diagonal {diag:.3f} mm >= {CONTOUR_SCALE_RATIO:.0%} "
                    f"of model {model_diag:.3f} mm)"
                )
            w = f"passthrough: unsupported {raw.dxftype()} (bbox diagonal {diag:.3f} mm)"
            warnings.append(f"{w}, {note}" if note else w)
        for idx, raw in unsupported_raw:
            passthrough.append((idx, PassThrough(eid=str(raw.dxf.handle), kind=raw.dxftype())))

    # document order: supported + passthrough interleaved
    prims_iter = iter(supported)
    pass_iter = iter(passthrough)
    combined: list[Entity] = []
    for _idx, kind in order:
        if kind == "prim":
            combined.append(next(prims_iter))
        else:
            combined.append(next(pass_iter)[1])

    # -- 11.3 case 4: duplicate merge (keep first, count) --
    kept: list[Entity] = []
    dup_count = 0
    dropped_eids: set[str] = set()
    for e in combined:
        if not isinstance(e, PassThrough) and any(
            type(e) is type(k) and _is_dup(e, k, EPS_COINCIDE) for k in kept
        ):
            dup_count += 1
            dropped_eids.add(e.eid)
        else:
            kept.append(e)
    if dup_count:
        unit = "entity" if dup_count == 1 else "entities"
        warnings.append(f"merged {dup_count} duplicate {unit} (SPEC 11.3 case 4)")
    for eid in dropped_eids:
        layer_of.pop(eid, None)

    # -- 11.3 case 5: fold stub --
    warnings.extend(_fold_contour_warnings(kept, set(), EPS_COINCIDE))

    state = ModelState(primitives=kept, dogbones=[], fold_eids=set(),
                       flag_decisions={}, next_seq=1)
    return LoadResult(
        model_state=state,
        header={"$INSUNITS": doc.header.get("$INSUNITS"), "$ACADVER": ver},
        warnings=warnings,
        layer_of=layer_of,
    )
