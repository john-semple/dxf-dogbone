"""M6 whole-file golden gate (CONTRACTS §4; SPEC §11.9).

``python tools/verify_m6.py <out_path>``

Replays the before-file with three scripted corner placements (two at
R=3.175, one at R=1.5875), exports, and checks:

  - ezdxf audit is clean
  - output $ACADVER matches the before-file
  - the before-file's SHA256 is unchanged
  - normalized geometry matches the after-file once the agreed residuals
    are removed

Bend lines are ignored (user decision 2026-10-08): the before-file has
none, so the replay does not designate folds. Fold trim stays covered by
the M5a tests.

Residuals (user decision 2026-10-08, plus the hand edits the comparison
actually showed — same rule, pinned here so a surprise fails the gate):

  after-file only:
    - bend lines at y=51.263 and y=120.770, including the short stubs
    - point markers at (±45, 51.517)
    - rib walls at x=±45.253 and the extra walls at x=±185.760
    - the hand-drawn line at y=45.253
    - the user's corner-1 arc and the ramp pieces that meet it
  export only:
    - every circle that was already in the before-file (the after-file
      has none; the three corners do not delete the rest)
    - the bottom-tab slot and its two r=2.5 arcs
    - the engine's corner-1 arc and the two ramp edges it rebuilds

Exit 0 on success, 1 on a failed check, 2 on bad usage.
"""
from __future__ import annotations

import hashlib
import sys
from collections import Counter
from pathlib import Path

import ezdxf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dxf_io import load as dxf_load  # noqa: E402
from dxf_io.export import export  # noqa: E402
from geometry import geomops as go  # noqa: E402
from geometry.entities import Pt  # noqa: E402
from model.model import Model  # noqa: E402
from rules.engine import ghost_candidates, place_corner  # noqa: E402

BEFORE = ROOT / "samples" / "base-rectangular-before-AI.DXF"
AFTER = ROOT / "samples" / "base-rectangular - partially radiused.DXF"

# Rounded (CONTRACTS §4) identities for the corner-1 hand edit and the
# engine construction that replaces it.
_USER_ARC_CENTER = (45.253, 122.104)
_ENGINE_ARC_CENTER = (45.253, 121.651)
_MARKER_POINTS = {(-45.0, 51.517), (45.0, 51.517)}
_WALL_X = {-45.253, 45.253, -185.76, 185.76}
_BEND_Y = {51.263, 120.77}
_USER_ADDED_LINE = frozenset({(-45.0, 45.253), (45.0, 45.253)})
_USER_CORNER1_LINES = {
    frozenset({(43.546, 121.77), (43.765, 121.551)}),
    frozenset({(46.741, 121.551), (46.961, 121.77)}),
    frozenset({(46.961, 121.77), (62.214, 137.024)}),
    frozenset({(28.293, 137.024), (43.546, 121.77)}),
}
_ENGINE_CORNER1_LINES = {
    frozenset({(46.841, 121.651), (62.214, 137.024)}),
    frozenset({(28.293, 137.024), (43.666, 121.651)}),
}
_T_JUNCTION_ARCS = (
    ((47.245, 49.272), 3.175),
    ((-47.245, 49.272), 3.175),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _round3(value: float) -> float:
    return round(value, 3)


def normalize_dxf(path: Path) -> list[tuple]:
    """CONTRACTS §4 tuples. Segment direction is canonical (SAMPLES.md:
    the M6 recipe is direction-insensitive). MTEXT is excluded."""
    doc = ezdxf.readfile(str(path))
    rows: list[tuple] = []
    for entity in doc.modelspace():
        kind = entity.dxftype()
        if kind not in {"LINE", "ARC", "CIRCLE", "POINT"}:
            continue
        layer = str(entity.dxf.layer)
        color = int(entity.dxf.color)
        if kind == "LINE":
            a = (_round3(entity.dxf.start.x), _round3(entity.dxf.start.y))
            b = (_round3(entity.dxf.end.x), _round3(entity.dxf.end.y))
            if b < a:
                a, b = b, a
            rows.append((kind, layer, color, a, b))
        elif kind == "ARC":
            center = (_round3(entity.dxf.center.x), _round3(entity.dxf.center.y))
            rows.append(
                (
                    kind,
                    layer,
                    color,
                    center,
                    _round3(entity.dxf.radius),
                    _round3(entity.dxf.start_angle),
                    _round3(entity.dxf.end_angle),
                )
            )
        elif kind == "CIRCLE":
            center = (_round3(entity.dxf.center.x), _round3(entity.dxf.center.y))
            rows.append((kind, layer, color, center, _round3(entity.dxf.radius)))
        else:
            point = (_round3(entity.dxf.location.x), _round3(entity.dxf.location.y))
            rows.append((kind, layer, color, point))
    rows.sort()
    return rows


def _line_ends(row: tuple) -> frozenset:
    return frozenset({row[3], row[4]})


def _is_after_residual(row: tuple) -> bool:
    kind = row[0]
    if kind == "POINT" and row[3] in _MARKER_POINTS:
        return True
    if kind == "ARC" and row[3] == _USER_ARC_CENTER:
        return True
    if kind != "LINE":
        return False
    a, b = row[3], row[4]
    if a[1] == b[1] and a[1] in _BEND_Y:
        return True
    if a[0] == b[0] and a[0] in _WALL_X:
        return True
    if _line_ends(row) == _USER_ADDED_LINE:
        return True
    if _line_ends(row) in _USER_CORNER1_LINES:
        return True
    return False


def _is_export_residual(row: tuple, before_circles: set[tuple]) -> bool:
    kind = row[0]
    if kind == "CIRCLE" and (row[3], row[4]) in before_circles:
        return True
    if kind == "ARC" and row[3] == _ENGINE_ARC_CENTER:
        return True
    if kind == "ARC" and row[4] == 2.5 and row[3][1] == -47.0:
        return True
    if kind == "LINE":
        a, b = row[3], row[4]
        if a[1] == b[1] and a[1] in (-49.5, -44.5):
            return True
        if _line_ends(row) in _ENGINE_CORNER1_LINES:
            return True
    return False


def _pick_side(prims, edge1, edge2, radius, target):
    ghosts = ghost_candidates(prims, edge1, edge2, radius)
    best = None
    for side, flip, center in ghosts:
        distance = go.dist(center, Pt(*target))
        if best is None or distance < best[0]:
            best = (distance, side, flip)
    if best is None:
        raise RuntimeError(f"no ghost for {edge1}/{edge2}")
    return best[1], best[2]


def _replay(loaded) -> Model:
    """Three placements on the original drawing, then apply (M2 script)."""
    prims = loaded.model_state.primitives
    jobs = [
        ("B8", "63", 3.175, (47.2451, 49.2717), {}),
        ("B6", "B3", 3.175, (-47.2451, 49.2717), {}),
        ("8A", "84", 1.5875, (45.2534, 121.6506), {"85": "delete", "89": "delete"}),
    ]
    results = []
    for edge1, edge2, radius, target, flags in jobs:
        side, flip = _pick_side(prims, edge1, edge2, radius, target)
        result = place_corner(
            prims, edge1, edge2, side, radius, set(), [],
            side_flip=flip, flag_decisions=flags,
        )
        if not result.ok:
            raise RuntimeError(f"{edge1}/{edge2} refused: {result.refusals}")
        results.append(result)
    model = Model(loaded.model_state)
    for result in results:
        model.apply_corner(result)
    return model


def _has_arc(rows: list[tuple], center: tuple, radius: float) -> bool:
    return any(
        row[0] == "ARC" and row[3] == center and row[4] == radius for row in rows
    )


def verify(out_path: Path) -> int:
    lines: list[str] = []
    failed = False

    def check(ok: bool, message: str) -> None:
        nonlocal failed
        lines.append(("PASS " if ok else "FAIL ") + message)
        if not ok:
            failed = True

    if not BEFORE.is_file() or not AFTER.is_file():
        print("sample DXFs are missing from /samples")
        return 1

    before_hash = _sha256(BEFORE)
    loaded = dxf_load(BEFORE)
    model = _replay(loaded)
    # No fold designation: bend lines exist only in the after-file.
    result = export(model.state, loaded.header, out_path, original=loaded.model_state)
    check(result.written, "export wrote the file")
    check(result.audit_summary == "clean", f"audit summary: {result.audit_summary}")
    check(_sha256(BEFORE) == before_hash, "before-file SHA256 unchanged")

    if out_path.is_file():
        doc = ezdxf.readfile(str(out_path))
        auditor = doc.audit()
        check(not list(auditor.errors), "re-read audit has no errors")
        got = str(doc.header.get("$ACADVER", ""))
        want = str(loaded.header.get("$ACADVER", ""))
        check(got == want, f"version {got} matches {want}")
        log_path = Path(str(out_path) + ".export_log.md")
        check(log_path.is_file(), "export log present")

        exported = normalize_dxf(out_path)
        after = normalize_dxf(AFTER)
        before_rows = normalize_dxf(BEFORE)
        before_circles = {(row[3], row[4]) for row in before_rows if row[0] == "CIRCLE"}

        for center, radius in _T_JUNCTION_ARCS:
            check(
                _has_arc(exported, center, radius) and _has_arc(after, center, radius),
                f"T-junction arc {center} R={radius} in both files",
            )

        exp_counts = Counter(exported)
        aft_counts = Counter(after)
        only_export = list((exp_counts - aft_counts).elements())
        only_after = list((aft_counts - exp_counts).elements())
        leftover_export = [row for row in only_export if not _is_export_residual(row, before_circles)]
        leftover_after = [row for row in only_after if not _is_after_residual(row)]
        check(
            not leftover_export and not leftover_after,
            f"normalized diff (export-only {len(leftover_export)}, "
            f"after-only {len(leftover_after)})",
        )
        for row in leftover_export:
            lines.append(f"  export only: {row}")
        for row in leftover_after:
            lines.append(f"  after only: {row}")

    print("M6 whole-file golden gate")
    for line in lines:
        print("  " + line)
    if failed:
        print("FAILED")
        return 1
    print("ALL PASS")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python tools/verify_m6.py <out_path>")
        return 2
    return verify(Path(argv[1]))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
