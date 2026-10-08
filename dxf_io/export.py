"""DXF export — CONTRACTS §3 (headless; ezdxf allowed).

Pipeline (CONTRACTS §3, ADR-004, ADR-017):
  1. deep copy the working ModelState (the working model is immutable
     under export; re-export after undo cannot double-trim).
  2. fold extend/trim (``rules.folds.resolve_folds`` on the copy).
  3. watermark filter (ADR-017): exact plain-text match against
     ``WATERMARK_TEXTS``, on the copy only, when ``remove_watermark``
     is true (the dialog default).
  4. build an ezdxf document; designated fold eids move to the
     ``FOLD_LINES`` layer with ``FOLD_COLOR_CONST`` (ACI 7). Every
     entity is written ACI 7 — load does not keep per-entity color,
     and the sample files are uniformly ACI 7, so BYLAYER 256 would
     fail the M6 color component of the normalized diff.
  5. ``ezdxf.audit`` pre-check. Errors abort: no DXF and no export log.
  6. save (``$ACADVER`` from the header) and write ``<out>.export_log.md``.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from pathlib import Path

import ezdxf

from geometry import geomops as go
from geometry.entities import (
    Arc,
    Circ,
    Entity,
    PointEnt,
    Seg,
    TextEnt,
)
from geometry.tolerances import EPS_COINCIDE, EPS_CONSTRUCTION
from model.state import ModelState
from rules.folds import out_of_reach_warnings, resolve_folds

FOLD_COLOR_CONST: int = 7  # SAMPLES.md: ACI 7, Continuous, layer 0
FOLD_LINETYPE: str = "Continuous"

# ADR-017. Exact plain-text match only — never a substring search.
WATERMARK_TEXTS: tuple[str, ...] = (
    "SOLIDWORKS Educational Product.",
    "For Instructional Use Only.",
)


@dataclass
class ExportResult:
    warnings: list[str] = field(default_factory=list)
    audit_summary: str = ""
    deleted_entity_count: int = 0
    written: bool = False


@dataclass
class PreparedExport:
    """Post-export geometry on a deep copy, before the file is written.

    The preview dialog renders ``state`` so the picture matches the file.
    """

    state: ModelState
    warnings: list[str] = field(default_factory=list)
    fold_trims: list = field(default_factory=list)
    watermark_removed: list[tuple[str, str]] = field(default_factory=list)


def export_log_path(out_path: Path) -> Path:
    """``<out>.export_log.md`` beside the DXF (``foo.dxf.export_log.md``)."""
    return Path(str(out_path) + ".export_log.md")


def _kind(entity: Entity) -> str:
    if isinstance(entity, Seg):
        return "LINE"
    if isinstance(entity, Arc):
        return "ARC"
    if isinstance(entity, Circ):
        return "CIRCLE"
    if isinstance(entity, PointEnt):
        return "POINT"
    if isinstance(entity, TextEnt):
        return "MTEXT"
    return type(entity).__name__


def _fmt_pt(p) -> str:
    return f"({p.x:.4f}, {p.y:.4f})"


def _apply_trims(primitives: list[Entity], trims) -> None:
    """Apply ``resolve_folds`` Trims to the deep-copied primitives in place
    (Seg endpoint repositioning per ADR-015(d))."""
    by_eid = {e.eid: i for i, e in enumerate(primitives) if isinstance(e, Seg)}
    for t in trims:
        idx = by_eid.get(t.eid)
        if idx is None:
            continue
        old = primitives[idx]
        new_a, new_b = t.new
        primitives[idx] = replace(old, a=new_a, b=new_b)


def _strip_watermark(primitives: list[Entity], enabled: bool) -> tuple[list[Entity], list[tuple[str, str]]]:
    """Drop notes whose text is exactly one of ``WATERMARK_TEXTS``.

    Any other note stays. ``enabled`` False keeps the watermark too.
    """
    if not enabled:
        return list(primitives), []
    kept: list[Entity] = []
    removed: list[tuple[str, str]] = []
    for entity in primitives:
        if isinstance(entity, TextEnt) and entity.text in WATERMARK_TEXTS:
            removed.append((entity.eid, entity.text))
            continue
        kept.append(entity)
    return kept, removed


def prepare_export(
    state: ModelState,
    *,
    remove_watermark: bool = True,
    eps: float = EPS_COINCIDE,
) -> PreparedExport:
    """Run the export pipeline on a deep copy and return that copy.

    Does not write a file and does not mutate ``state``.
    """
    working = copy.deepcopy(state)
    warnings = list(
        out_of_reach_warnings(working.primitives, working.dogbones, working.fold_eids, eps)
    )
    trims = resolve_folds(working.primitives, working.dogbones, working.fold_eids, eps)
    _apply_trims(working.primitives, trims)
    kept, removed = _strip_watermark(working.primitives, remove_watermark)
    working.primitives = kept
    return PreparedExport(
        state=working,
        warnings=warnings,
        fold_trims=list(trims),
        watermark_removed=removed,
    )


def _build_doc(state: ModelState, header: dict, fold_layer: str, fold_color: int) -> "ezdxf.Document":
    """Build an ezdxf document from the prepared entities."""
    doc = ezdxf.new(header.get("$ACADVER", "AC1015"))
    # SPEC §11.3 case 1: $INSUNITS must be 4 (mm) on output.
    doc.header["$INSUNITS"] = header.get("$INSUNITS", 4)
    msp = doc.modelspace()
    folds = set(state.fold_eids)
    for entity in state.primitives:
        is_fold = entity.eid in folds
        layer = fold_layer if is_fold else "0"
        color = fold_color if is_fold else FOLD_COLOR_CONST
        kw = {"layer": layer, "color": color}
        if isinstance(entity, Seg):
            msp.add_line((entity.a.x, entity.a.y), (entity.b.x, entity.b.y), dxfattribs=kw)
        elif isinstance(entity, Arc):
            msp.add_arc(
                (entity.center.x, entity.center.y),
                entity.r,
                entity.start_deg,
                entity.end_deg,
                dxfattribs=kw,
            )
        elif isinstance(entity, Circ):
            msp.add_circle((entity.center.x, entity.center.y), entity.r, dxfattribs=kw)
        elif isinstance(entity, PointEnt):
            msp.add_point((entity.p.x, entity.p.y), dxfattribs=kw)
        elif isinstance(entity, TextEnt):
            kw["insert"] = (entity.p.x, entity.p.y)
            kw["char_height"] = 2.5  # styling is excluded from the M6 diff
            msp.add_mtext(entity.text, dxfattribs=kw)
    return doc


def _audit_summary(auditor) -> tuple[bool, str]:
    """Return (ok, human-readable report). Errors are a failed check."""
    errors = list(auditor.errors)
    if errors:
        lines = ["The drawing failed the DXF health check and was not saved."]
        for err in errors:
            lines.append(str(err))
        return False, "\n".join(lines)
    if auditor.fixes:
        return True, f"{len(auditor.fixes)} audit fixes applied (clean)"
    return True, "clean"


def _moved(a, b, eps: float) -> bool:
    return go.dist(a, b) > eps


def render_export_log(
    prepared: PreparedExport,
    *,
    remove_watermark: bool,
    original: ModelState | None,
    audit_summary: str,
    eps: float = EPS_CONSTRUCTION,
) -> str:
    """Markdown export log: dogbones, deletions, trims, warnings, flags, audit."""
    state = prepared.state
    lines: list[str] = ["# Export log", ""]

    lines.append("## Dogbones placed")
    if not state.dogbones:
        lines.append("- none")
    for db in state.dogbones:
        lines.append(
            f"- {db.db_id}: center {_fmt_pt(db.center)}, R={db.r:.4f}"
        )
    lines.append("")

    original_by_eid = {}
    if original is not None:
        original_by_eid = {e.eid: e for e in original.primitives}
    final_eids = {e.eid for e in state.primitives}
    lines.append("## Deletions")
    deletions: list[str] = []
    if original is None:
        for eid, text in prepared.watermark_removed:
            deletions.append(f"- {eid} MTEXT ({text})")
        if not deletions:
            lines.append("- original drawing was not supplied")
    else:
        for entity in original.primitives:
            if entity.eid not in final_eids:
                deletions.append(f"- {entity.eid} {_kind(entity)}")
    if deletions:
        lines.extend(deletions)
    elif original is not None:
        lines.append("- none")
    lines.append("")

    fold_eids = {t.eid for t in prepared.fold_trims}
    lines.append("## Fold trims")
    if not prepared.fold_trims:
        lines.append("- none")
    for trim in prepared.fold_trims:
        old_a, old_b = trim.old
        new_a, new_b = trim.new
        lines.append(
            f"- {trim.eid}: {_fmt_pt(old_a)}-{_fmt_pt(old_b)} -> "
            f"{_fmt_pt(new_a)}-{_fmt_pt(new_b)}"
        )
    lines.append("")

    lines.append("## Other endpoint moves")
    moves: list[str] = []
    if original is None:
        lines.append("- original drawing was not supplied")
    else:
        for entity in state.primitives:
            old = original_by_eid.get(entity.eid)
            if old is None or entity.eid in fold_eids:
                continue
            if isinstance(entity, Seg) and isinstance(old, Seg):
                if _moved(entity.a, old.a, eps) or _moved(entity.b, old.b, eps):
                    moves.append(
                        f"- {entity.eid} LINE: {_fmt_pt(old.a)}-{_fmt_pt(old.b)} -> "
                        f"{_fmt_pt(entity.a)}-{_fmt_pt(entity.b)}"
                    )
            elif isinstance(entity, Arc) and isinstance(old, Arc):
                if (
                    abs(entity.start_deg - old.start_deg) > eps
                    or abs(entity.end_deg - old.end_deg) > eps
                ):
                    moves.append(
                        f"- {entity.eid} ARC: {old.start_deg:.4f}-{old.end_deg:.4f} -> "
                        f"{entity.start_deg:.4f}-{entity.end_deg:.4f}"
                    )
        if moves:
            lines.extend(moves)
        else:
            lines.append("- none")
    lines.append("")

    lines.append("## Fold warnings")
    if prepared.warnings:
        for warning in prepared.warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Flag decisions")
    if state.flag_decisions:
        for eid in sorted(state.flag_decisions):
            lines.append(f"- {eid}: {state.flag_decisions[eid]}")
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Watermark")
    if not remove_watermark:
        lines.append("- kept (remove watermark is off)")
    elif prepared.watermark_removed:
        for eid, text in prepared.watermark_removed:
            lines.append(f"- removed {eid}: {text}")
    else:
        lines.append("- none present")
    lines.append("")

    lines.append("## Audit")
    lines.append(audit_summary)
    lines.append("")
    return "\n".join(lines)


def export(
    state: ModelState,
    header: dict,
    out_path: Path,
    fold_layer: str = "FOLD_LINES",
    fold_color: int = FOLD_COLOR_CONST,
    *,
    eps: float = EPS_COINCIDE,
    remove_watermark: bool = True,
    original: ModelState | None = None,
) -> ExportResult:
    """Export the working model to a DXF (CONTRACTS §3; ADR-004 pure).

    ``remove_watermark`` defaults on (ADR-017). ``original``, when given,
    is the load-time drawing used only to describe deletions in the log.
    A failed health check writes neither the DXF nor the log.
    """
    out_path = Path(out_path)
    prepared = prepare_export(state, remove_watermark=remove_watermark, eps=eps)
    doc = _build_doc(prepared.state, header, fold_layer, fold_color)
    ok, audit_summary = _audit_summary(doc.audit())
    if not ok:
        return ExportResult(
            warnings=list(prepared.warnings),
            audit_summary=audit_summary,
            deleted_entity_count=len(prepared.watermark_removed),
            written=False,
        )
    doc.saveas(str(out_path))
    log = render_export_log(
        prepared,
        remove_watermark=remove_watermark,
        original=original,
        audit_summary=audit_summary,
    )
    export_log_path(out_path).write_text(log, encoding="utf-8")
    return ExportResult(
        warnings=list(prepared.warnings),
        audit_summary=audit_summary,
        deleted_entity_count=len(prepared.watermark_removed),
        written=True,
    )
