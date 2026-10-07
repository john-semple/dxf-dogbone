"""SAMPLES-GEN generator — synthetic DXF test set (ISSUE-011).

Builds the 8 positive + 3 negative synthetic DXFs into `samples/`, reloads each
with ezdxf, re-derives every site + classification INDEPENDENTLY of the writer,
asserts DXF version / $INSUNITS / census / layers / the per-file geometry
assertions from documentation/briefs/SAMPLES-GEN.md, prints a per-file PASS
table, and regenerates the manifest `documentation/SAMPLES-SYN.md` from the
reload output (never hand-typed numbers).

Run:  .venv\\Scripts\\python.exe tools\\gen_samples.py
Exit: non-zero on any mismatch.

Angle convention (resolved, see session blocker note):
  site   = loop vertex with cross(prev, apex, nxt) < 0  (right turn, CCW loop)
  material = reflex interior angle (> 180°)
  air-V  = 360° − material        ∈ (0°, 180°)
  half   = air-V / 2              band [15°, 165°]
  air bisector = unit( unit(apex→prev) + unit(apex→nxt) )
  center = apex + R · air_bisector  (R = 1.5875 mm, Ø 3.175)
  syn-L-bracket is the corrected outlier: air side is SW void
  (bisector (−1,+1)/√2·) → center (28.87747, 31.12253); the brief text's
  "NE / (31.1225, 31.1225)" is superseded per the user's choice.
"""
from __future__ import annotations

import math
from pathlib import Path

import ezdxf

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
MANIFEST = ROOT / "documentation" / "SAMPLES-SYN.md"

R = 1.5875                    # tool radius, Ø 3.175 mm
ANG_ATOL = 0.01               # site-angle asserts, degrees
C_ATOL = 5e-5                 # center-coordinate asserts, mm (SAMPLES-GEN tol)

# ----------------------------------------------------------------------------
# headless math (verify path only — stdlib, no ezdxf)
# ----------------------------------------------------------------------------

def _cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _unit(v):
    n = math.hypot(*v)
    return (v[0] / n, v[1] / n)


def find_sites(pts):
    """Reflex (cross<0) CCW-loop vertices, in loop order."""
    n = len(pts)
    return [pts[i] for i in range(n) if _cross(pts[(i - 1) % n], pts[i], pts[(i + 1) % n]) < 0]


def _material_deg(prev, v, nxt):
    """Reflex 'interior' angle on the material side of a site vertex, >180°."""
    ui = _unit((prev[0] - v[0], prev[1] - v[1]))   # arm from apex back to prev
    uo = _unit((nxt[0] - v[0], nxt[1] - v[1]))     # arm from apex out to nxt
    sweep = (math.degrees(math.atan2(uo[1], uo[0])) - math.degrees(math.atan2(ui[1], ui[0]))) % 360.0
    return 360.0 - sweep


def _air_deg(prev, v, nxt):        # the brief's (0°,180°) notch angle
    return 360.0 - _material_deg(prev, v, nxt)


def _air_bis(prev, v, nxt):
    """Air-side bisector unit: unit( unit(apex→prev) + unit(apex→nxt) )."""
    ui = _unit((prev[0] - v[0], prev[1] - v[1]))
    uo = _unit((nxt[0] - v[0], nxt[1] - v[1]))
    return _unit((ui[0] + uo[0], ui[1] + uo[1]))


def _center(prev, v, nxt):
    b = _air_bis(prev, v, nxt)
    return (round(v[0] + R * b[0], 6), round(v[1] + R * b[1], 6))


def _d(p, q):
    return math.hypot(p[0] - q[0], p[1] - q[1])


def _seg_min_dist(a, b, p):
    (ax, ay), (bx, by), (px, py) = a, b, p
    L2 = (bx - ax) ** 2 + (by - ay) ** 2
    t = max(0.0, min(1.0, ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / L2)) if L2 else 0.0
    return _d((ax + t * (bx - ax), ay + t * (by - ay)), p)


def _arc_pt(c, r, deg):
    t = math.radians(deg)
    return (c[0] + r * math.cos(t), c[1] + r * math.sin(t))


def _ang_in_span(ang, s, e):
    a, s, e = ang % 360.0, s % 360.0, e % 360.0
    return s <= a <= e if s <= e else (a >= s or a <= e)


def _norm(a): return a % 360.0

def _arc_min_dist(c, r, s, e, p):
    """point min distance to ARC set; analytic closest + both endpoints."""
    best = min(_d(_arc_pt(c, r, s), p), _d(_arc_pt(c, r, e), p))
    # projection of p on the supporting circle falls at angle atan2
    th = math.degrees(math.atan2(p[1] - c[1], p[0] - c[0]))
    if _ang_in_span(th, s, e):
        best = min(best, abs(_d(p, c) - r))
    return best


class Fail(Exception):
    pass

def _close(a, b, tol, label):
    if abs(a - b) > tol:
        raise Fail(f"{label}: {a!r} != {b!r} (tol {tol})")

# ----------------------------------------------------------------------------
# file builders
# ----------------------------------------------------------------------------

def _doc(dxfver="R2000", insunits=4):
    doc = ezdxf.new(dxfver)
    doc.header["$INSUNITS"] = insunits
    return doc


def _layer(doc, name):
    if name not in doc.layers:
        doc.layers.add(name)
    return doc


def _add_outline(msp, pts):
    n = len(pts)
    for i in range(n):
        msp.add_line(pts[i], pts[(i + 1) % n], dxfattribs={"layer": "0"})


def _build_L_bracket():
    pts = [(0, 0), (80, 0), (80, 80), (30, 80), (30, 30), (0, 30)]
    doc = _doc(); _add_outline(doc.modelspace(), pts); return doc, "0"


def _build_angled_notch():
    pts = [(0, 0), (120, 0), (120, 100), (94.641, 100), (60, 60), (25.359, 100), (0, 100)]
    doc = _doc(); _add_outline(doc.modelspace(), pts); return doc, "0"


def _build_tight_notch():
    pts = [(0, 0), (120, 0), (120, 40), (90, 50), (120, 60), (120, 100), (0, 100)]
    doc = _doc(); _add_outline(doc.modelspace(), pts); return doc, "0"


def _build_shallow_refuse():
    pts = [(0, 0), (120, 0), (120, 46.5), (78, 50), (120, 53.5), (120, 100), (0, 100)]
    doc = _doc(); _add_outline(doc.modelspace(), pts); return doc, "0"


def _build_double_tabs():
    pts = [(0, 57), (20, 57), (20, 0), (60, 0), (60, 57), (80, 57), (80, 0),
           (120, 0), (120, 57), (200, 57), (200, 140), (0, 140)]
    doc = _doc(); _layer(doc, "BEND_UP")
    _add_outline(doc.modelspace(), pts)
    doc.modelspace().add_line((10, 100), (190, 100), dxfattribs={"layer": "BEND_UP"})
    return doc, "0,BEND_UP"


def _build_near_hole():
    pts = [(0, 0), (100, 0), (100, 100), (60, 100), (60, 60), (40, 60), (40, 100), (0, 100)]
    doc = _doc(); msp = doc.modelspace()
    _add_outline(msp, pts)
    msp.add_circle((50, 54), 1.25, dxfattribs={"layer": "0"})
    msp.add_mtext("NOTES", dxfattribs={"insert": (42, 58), "char_height": 2.0, "layer": "0"})
    return doc, "0"


def _build_fold_heavy():
    pts = [(0, 0), (180, 0), (180, 90), (20, 90), (20, 60), (0, 60)]
    doc = _doc(); _layer(doc, "BEND_UP"); _layer(doc, "FOLD_LINES")
    msp = doc.modelspace()
    _add_outline(msp, pts)
    msp.add_line((10, 80), (170, 80), dxfattribs={"layer": "BEND_UP"})
    msp.add_line((30, 40), (170, 40), dxfattribs={"layer": "BEND_UP"})
    msp.add_line((40, 20), (160, 20), dxfattribs={"layer": "FOLD_LINES"})
    msp.add_line((50, 61), (150, 61), dxfattribs={"layer": "0"})
    msp.add_line((50, 30), (150, 30), dxfattribs={"layer": "0"})
    # §11.3 case-5 overlay: this LINE exactly covers contour edge (20,60)->(0,60)
    # (same geometry, reversed direction) on layer "FOLD_LINES", not "0" — placing it on
    # "0" would make the outline chain non-manifold.  The loader must therefore detect the
    # overlay by geometry (not layer) and WARN (never silently accept §4.5's rule).
    msp.add_line((0, 60), (20, 60), dxfattribs={"layer": "FOLD_LINES"})
    return doc, "0,BEND_UP,FOLD_LINES"


def _build_arc_tears():
    pts = [(0, 0), (120, 0), (120, 30), (95, 30), (95, 55), (120, 55), (120, 100), (0, 100)]
    doc = _doc(); msp = doc.modelspace()
    _add_outline(msp, pts)
    msp.add_arc((97.0, 53.0), 2.0, 140.0, 230.0, dxfattribs={"layer": "0"})       # A1 DELETE+FLAG
    msp.add_arc((99.122533, 53.8775), 2.75, 90.0, 270.0, dxfattribs={"layer": "0"})  # A2 FLAG (chord-crosser; corrected — see session log)
    msp.add_line((94.9, 55.2), (98.0, 52.8), dxfattribs={"layer": "0"})          # L1 FLAG
    msp.add_line((95.2, 54.8), (98.0, 54.8), dxfattribs={"layer": "0"})          # L2 DELETE
    return doc, "0"


def _build_multicorner():
    # Three 20×20 U-slots cut INTO a y=100 top edge (voids x=[160,180],[140,160],[120,140],
    # y=[80,100]). Reflex slot-floor corners ⇒ the four dogboneable sites:
    #   (180,80) air NW, (160,80) air NE, (140,80) air NW, (120,80) air NE.
    # Adjacent-centre gaps 17.755 / 22.245 / 17.755 > 2R ⇒ overlap silent.
    pts = [(0, 0), (200, 0), (200, 100), (180, 100), (180, 80), (160, 80),
           (160, 100), (140, 100), (140, 80), (120, 80), (120, 100), (0, 100)]
    doc = _doc(); _layer(doc, "BEND_DOWN"); msp = doc.modelspace()
    _add_outline(msp, pts)
    msp.add_circle((60, 50), 2.5, dxfattribs={"layer": "0"})
    msp.add_circle((100, 50), 2.5, dxfattribs={"layer": "0"})
    msp.add_line((30, 15), (170, 15), dxfattribs={"layer": "BEND_DOWN"})
    return doc, "0,BEND_DOWN"


def _neg_from(builder):
    """reuse geometry of file #1 for the negative cases"""
    doc, _ = builder()
    return doc


def _build_neg_inch():
    doc = _neg_from(_build_L_bracket)
    doc.header["$INSUNITS"] = 1
    return doc, "0"


def _build_neg_r12():
    doc = ezdxf.new("R12")
    _add_outline(doc.modelspace(), [(0, 0), (80, 0), (80, 80), (30, 80), (30, 30), (0, 30)])
    return doc, "0"


def _build_neg_spline():
    doc = _neg_from(_build_L_bracket)
    doc.modelspace().add_spline([(0, 0, 0), (40, 40, 0), (80, 0, 0)], dxfattribs={"layer": "0"})
    return doc, "0"


BUILDERS = {
    "syn-L-bracket.dxf": _build_L_bracket,
    "syn-angled-notch.dxf": _build_angled_notch,
    "syn-tight-notch.dxf": _build_tight_notch,
    "syn-shallow-refuse.dxf": _build_shallow_refuse,
    "syn-double-tabs.dxf": _build_double_tabs,
    "syn-near-hole.dxf": _build_near_hole,
    "syn-fold-heavy.dxf": _build_fold_heavy,
    "syn-arc-tears.dxf": _build_arc_tears,
    "syn-multicorner.dxf": _build_multicorner,
    "neg-inch.dxf": _build_neg_inch,
    "neg-r12.dxf": _build_neg_r12,
    "neg-spline.dxf": _build_neg_spline,
}

EXPECTED_SITES = {
    "syn-L-bracket.dxf": 1,
    "syn-angled-notch.dxf": 1,
    "syn-tight-notch.dxf": 1,
    "syn-shallow-refuse.dxf": 1,
    "syn-double-tabs.dxf": 4,
    "syn-near-hole.dxf": 2,
    "syn-fold-heavy.dxf": 1,
    "syn-arc-tears.dxf": 2,
    "syn-multicorner.dxf": 4,
}

EXPECTED_COUNTS = {
    "syn-L-bracket.dxf": ("LINE", 6),
    "syn-angled-notch.dxf": ("LINE", 7),
    "syn-tight-notch.dxf": ("LINE", 7),
    "syn-shallow-refuse.dxf": ("LINE", 7),
    "syn-double-tabs.dxf": ("LINE", 13),
    "syn-near-hole.dxf": ("LINE/CIRCLE/MTEXT", (8, 1, 1)),
    "syn-fold-heavy.dxf": ("LINE", 12),
    "syn-arc-tears.dxf": ("LINE/ARC", (10, 2)),
    "syn-multicorner.dxf": ("LINE/CIRCLE", (13, 2)),
    "neg-inch.dxf": ("LINE", 6),
    "neg-r12.dxf": ("LINE", 6),
    "neg-spline.dxf": ("LINE/SPLINE", (6, 1)),
}

# ----------------------------------------------------------------------------
# reload + verify (independent of the writer)
# ----------------------------------------------------------------------------

def _outline_points(doc):
    """Chain the layer-0 LINE outline by nearest-neighbour endpoint matching.

    Interior strays/folds stub off no outline vertex → never chained; syn-fold-heavy's
    §11.3 case-5 overlay lives on FOLD_LINES, so it stays out of layer-0 here.
    """
    msp = doc.modelspace()
    segs = [((e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y))
            for e in msp if e.dxftype() == "LINE" and e.dxf.layer == "0"]
    if not segs:
        raise Fail("no layer-0 LINEs to chain")
    unused = segs[:]
    tol = 1e-3
    a, b = unused.pop(0)
    loop = [a, b]
    guard = len(segs) * 20 + 20
    while unused and guard:
        guard -= 1
        tail = loop[-1]
        best_i, best_d, best_q = -1, float("inf"), None
        for i, (p, q) in enumerate(unused):
            for cand_end, nxt_pt in ((p, q), (q, p)):
                dd = _d(cand_end, tail)
                if dd < best_d:
                    best_i, best_d, best_q = i, dd, nxt_pt
        if best_d > tol:
            break
        loop.append(best_q); unused.pop(best_i)
    if unused:
        # Interior strays / folds never share an outline vertex, so they cannot chain.
        # Count them and continue — the loader is responsible for gating them
        # (§11.3 case-5, delete-preview), not the generator.
        strays = len(unused)
    else:
        strays = 0
    # cut a repeated vertex out of the cycle, if any (defensive)
    cut = None
    for i in range(1, len(loop)):
        for j in range(i):
            if _d(loop[i], loop[j]) < tol and i - j > 1:
                cut = (j, i); break
        if cut:
            break
    if cut:
        loop = loop[cut[0]:cut[1]]
    if _d(loop[0], loop[-1]) < tol:
        loop.pop()

    # rotate so the leftmost-bottom vertex is first: keeps sites in the
    # "machine-verified" order that SAMPLES-GEN lists them.
    k = min(range(len(loop)), key=lambda i: (loop[i][0], loop[i][1]))
    loop = loop[k:] + loop[:k]

    area = 0.5 * sum(loop[i][0] * loop[(i + 1) % len(loop)][1] - loop[(i + 1) % len(loop)][0] * loop[i][1] for i in range(len(loop)))
    if area < 0:
        loop.reverse()
        k = min(range(len(loop)), key=lambda i: (loop[i][0], loop[i][1]))
        loop = loop[k:] + loop[:k]
    return loop, strays


def verify(name, path, doc_expected_layers, expected_ver, expected_insunits):
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()

    # --- header gate (SPEC §11.3) ---
    ver = doc.header.get("$ACADVER", "?")
    ins = doc.header.get("$INSUNITS", "?")
    if ver != expected_ver:
        raise Fail(f"$ACADVER {ver} != expected {expected_ver}")
    if ins != expected_insunits:
        raise Fail(f"$INSUNITS {ins} != expected {expected_insunits}")

    # --- census ---
    from collections import Counter
    cnt = Counter(e.dxftype() for e in msp)
    layers = sorted({e.dxf.layer for e in msp if e.dxf.hasattr("layer")})
    if ",".join(layers) != doc_expected_layers:
        raise Fail(f"layers {layers} != expected {doc_expected_layers}")

    # --- outline reconstruction + site detection on reloaded geometry ---
    pts, stray_count = _outline_points(doc)
    sited = find_sites(pts)
    if name.startswith("syn-"):
        n_exp = EXPECTED_SITES[name]
        if len(sited) != n_exp:
            raise Fail(f"site count {len(sited)} != expected {n_exp}")

    # --- per-file geometry assertions ---
    def at(v):
        i = pts.index(v); return pts[(i - 1) % len(pts)], v, pts[(i + 1) % len(pts)]

    recs = []   # rows for the manifest: (vertex, air_deg, center, outcome)
    for v in sited:
        prev, _, nxt = at(v)
        adeg = _air_deg(prev, v, nxt)
        c = _center(prev, v, nxt)
        _close(_d(c, v), R, 1e-6, f"{name} {v} |c-apex|")
        recs.append((v, round(adeg, 3), c))

    if name == "syn-L-bracket.dxf":
        (vdeg, vc), = [(r[1], r[2]) for r in recs]
        _close(vdeg, 90.0, ANG_ATOL, "L-bracket half implies air=90")
        _close(vc[0], 28.8775, C_ATOL, "L-bracket cx"); _close(vc[1], 31.1225, C_ATOL, "L-bracket cy")
        # corrected outlier: center must lie SW of the notch void, NOT the brief text's NE
        if vc[0] > 30.0: raise Fail("L-bracket center must be SW-side (void side), per session blocker")
    elif name == "syn-angled-notch.dxf":
        (vdeg, vc), = [(r[1], r[2]) for r in recs]
        _close(vdeg, 81.787, 0.05, "angled-notch air-V"); _close(vdeg / 2, 40.8935, 0.05, "angled-notch half")
        _close(vc[0], 60.0, C_ATOL, "angled cx"); _close(vc[1], 61.5875, C_ATOL, "angled cy")
    elif name == "syn-tight-notch.dxf":
        (vdeg, vc), = [(r[1], r[2]) for r in recs]
        _close(vdeg, 36.870, 0.05, "tight air-V"); _close(vc[0], 91.5875, C_ATOL, "tight cx"); _close(vc[1], 50.0, C_ATOL, "tight cy")
    elif name == "syn-shallow-refuse.dxf":
        (vdeg, _), = [(r[1], r[2]) for r in recs]
        _close(vdeg, 9.527, 0.05, "shallow air-V"); _close(vdeg / 2, 4.7635, 0.005, "shallow half")
        if vdeg >= 15: raise Fail("shallow-refuse air-V must be < 15")
    elif name == "syn-double-tabs.dxf":
        exp = {(20, 57): (18.8775, 55.8775), (60, 57): (61.1225, 55.8775), (80, 57): (78.8775, 55.8775), (120, 57): (121.1225, 55.8775)}
        for v, want in exp.items():
            r0 = next(r for r in recs if _d(r[0], v) < 1e-6)
            vd, vc = r0[1], r0[2]
            _close(vd, 90.0, ANG_ATOL, f"DT {v} air"); _close(vc[0], want[0], C_ATOL, f"DT {v} cx"); _close(vc[1], want[1], C_ATOL, f"DT {v} cy")
        g = _d(exp[(60, 57)], exp[(80, 57)]); _close(g, 17.755, 1e-3, "DT centre gap")
        if g <= 2 * R: raise Fail("DT centre gap must exceed 2R (silent overlap)")
        fold = ((10, 100), (190, 100))
        mind = min(_seg_min_dist(*fold, exp[s]) for s in exp); _close(mind, 44.1225, 1e-3, "DT fold dist")
    elif name == "syn-near-hole.dxf":
        exp = {(60, 60): (58.8775, 61.1225), (40, 60): (41.1225, 61.1225)}
        for v, want in exp.items():
            vd, vc = next((r[1], r[2]) for r in recs if _d(r[0], v) < 1e-6)
            _close(vd, 90.0, ANG_ATOL, f"NH {v} air"); _close(vc[0], want[0], C_ATOL, f"NH {v} cx"); _close(vc[1], want[1], C_ATOL, f"NH {v} cy")
        _close(_d((50, 54), (40, 60)), 11.662, 1e-3, "NH hole→site"); _close(_d((42, 58), (40, 60)), 2.828, 1e-3, "NH mtext→site")
        if not (_d((50, 54), exp[(40, 60)]) > R + 1.25): raise Fail("NH hole keep-safe fail")
        _close(_d(exp[(60, 60)], exp[(40, 60)]), 17.755, 1e-3, "NH centre gap")
    elif name == "syn-fold-heavy.dxf":
        (vdeg, vc), = [(r[1], r[2]) for r in recs]
        _close(vdeg, 90.0, ANG_ATOL, "FH site air")
        # corrected outlier (same fix as syn-L-bracket): the void of the step is NW of
        # (20,60), so the dogbone center is NW, not the brief text's SW.
        _close(vc[0], 18.8775, C_ATOL, "FH cx"); _close(vc[1], 61.1225, C_ATOL, "FH cy")
        if vc[1] < 60.0: raise Fail("FH center must be NW-side (air / step void)")
        _close(_seg_min_dist((10, 80), (170, 80), vc), 18.8775, 1e-3, "FH fold dist a")
        _close(_seg_min_dist((30, 40), (170, 40), vc), 23.872, 1e-3, "FH fold dist b")
        _close(_seg_min_dist((40, 20), (160, 20), vc), 46.2301, 1e-3, "FH fold dist c")
        _close(_seg_min_dist((50, 61), (150, 61), vc), 31.1228, 1e-3, "FH manual fold warn dist")
        _close(_seg_min_dist((50, 30), (150, 30), vc), 44.0139, 1e-3, "FH manual fold b")
        # §11.3 case-5 overlay: duplicate contour edge (20,60)→(0,60), drawn as the
        # layer-FOLD_LINES stray. Detected by geometry (NOT by layer), per the spec's
        # "each designated fold's distance to every contour edge … warn" rule.
        over = [e for e in msp if e.dxftype() == "LINE" and e.dxf.layer == "FOLD_LINES"
                and { (round(e.dxf.start.x, 3), round(e.dxf.start.y, 3)), (round(e.dxf.end.x, 3), round(e.dxf.end.y, 3)) }
                == {(0.0, 60.0), (20.0, 60.0)}]
        if len(over) != 1:
            raise Fail("FH §11.3 case-5 overlay (0,60)-(20,60) on FOLD_LINES not found")
    elif name == "syn-arc-tears.dxf":
        exp = {(95, 30): (96.1225, 31.1225), (95, 55): (96.12253, 53.87747)}
        for v, want in exp.items():
            vd, vc = next((r[1], r[2]) for r in recs if _d(r[0], v) < 1e-6)
            _close(vd, 90.0, ANG_ATOL, f"AT {v} air"); _close(vc[0], want[0], 1e-4, f"AT {v} cx"); _close(vc[1], want[1], 1e-4, f"AT {v} cy")
        c8 = (96.12253, 53.87747)
        A1 = [e for e in msp if e.dxftype() == "ARC" and abs(e.dxf.center.x - 97.0) < 1e-6]
        if not A1: raise Fail("AT A1 ARC not found")
        A1 = A1[0]
        e1 = _arc_pt((A1.dxf.center.x, A1.dxf.center.y), A1.dxf.radius, A1.dxf.start_angle)
        e2 = _arc_pt((A1.dxf.center.x, A1.dxf.center.y), A1.dxf.radius, A1.dxf.end_angle)
        _close(e1[0], 95.4679, 1e-3, "A1 e1x"); _close(e1[1], 54.2856, 1e-3, "A1 e1y")
        _close(e2[0], 95.7144, 1e-3, "A1 e2x"); _close(e2[1], 51.4679, 1e-3, "A1 e2y")
        if not (_d(e1, c8) < R): raise Fail("A1 endpoint-in fail")
        if not (_d(e2, c8) > R): raise Fail("A1 e2 must be out")
        A2 = [e for e in msp if e.dxftype() == "ARC" and abs(e.dxf.center.x - 99.122533) < 1e-4][0]
        a1 = _arc_pt((A2.dxf.center.x, A2.dxf.center.y), A2.dxf.radius, A2.dxf.start_angle)
        a2 = _arc_pt((A2.dxf.center.x, A2.dxf.center.y), A2.dxf.radius, A2.dxf.end_angle)
        _close(_d(a1, c8), 4.0697, 1e-3, "A2 e1 dist"); _close(_d(a2, c8), 4.0697, 1e-3, "A2 e2 dist")
        if not (_d(a1, c8) > R and _d(a2, c8) > R): raise Fail("A2 endpoints must be outside")
        mA2 = _arc_min_dist((A2.dxf.center.x, A2.dxf.center.y), A2.dxf.radius, A2.dxf.start_angle, A2.dxf.end_angle, c8)
        _close(mA2, 0.25, 1e-3, "A2 min-dist")
        if mA2 >= R: raise Fail("A2 must be chord-crosser (min-dist < R)")
        L1 = next(e for e in msp if e.dxftype() == "LINE" and abs(e.dxf.start.x - 94.9) < 1e-6)
        if _seg_min_dist((L1.dxf.start.x, L1.dxf.start.y), (L1.dxf.end.x, L1.dxf.end.y), c8) >= R: raise Fail("L1 chord-crosser fail")
        L2 = next(e for e in msp if e.dxftype() == "LINE" and abs(e.dxf.start.x - 95.2) < 1e-6)
        if not (_d((L2.dxf.start.x, L2.dxf.start.y), c8) < R): raise Fail("L2 endpoint-in fail")
    elif name == "syn-multicorner.dxf":
        exp = {(180, 80): (178.8775, 81.1225), (160, 80): (161.1225, 81.1225), (140, 80): (138.8775, 81.1225), (120, 80): (121.1225, 81.1225)}
        for v, want in exp.items():
            vd, vc = next((r[1], r[2]) for r in recs if _d(r[0], v) < 1e-6)
            _close(vd, 90.0, ANG_ATOL, f"MC {v} air"); _close(vc[0], want[0], C_ATOL, f"MC {v} cx"); _close(vc[1], want[1], C_ATOL, f"MC {v} cy")
        for a, b in (((180, 80), (160, 80)), ((160, 80), (140, 80)), ((140, 80), (120, 80))):
            g = _d(exp[a], exp[b])
            _close(g, {((180, 80), (160, 80)): 17.755, ((160, 80), (140, 80)): 22.245, ((140, 80), (120, 80)): 17.755}[(a, b)], 1e-3, f"MC gap {a}")
            if g <= 2 * R: raise Fail("MC centre gap must exceed 2R")
        for h in ((60, 50), (100, 50)):
            if not (min(_d(h, exp[s]) for s in exp) >= 30): raise Fail(f"MC hole {h} immunity fail")
        fold = ((30, 15), (170, 15))
        if not (min(_seg_min_dist(*fold, exp[s]) for s in exp) >= 60): raise Fail("MC fold immunity fail")

    # --- census assertion ---
    kind, want = EXPECTED_COUNTS[name]
    if "/" in kind:
        names = kind.split("/")
        for nm, w in zip(names, want):
            if cnt[nm] != w: raise Fail(f"{name} census {nm}={cnt[nm]} != {w}")
    else:
        if cnt[kind] != want: raise Fail(f"{name} census {kind}={cnt[kind]} != {want}")
        if sum(cnt.values()) != want: raise Fail(f"{name} total census {sum(cnt.values())} != {want}")

    return recs, cnt, layers


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------

def main():
    SAMPLES.mkdir(exist_ok=True)
    MANIFEST.parent.mkdir(exist_ok=True)

    results = []
    failures = []
    for name, builder in BUILDERS.items():
        doc, expected_layers = builder()
        path = SAMPLES / name
        doc.saveas(path)
        if name == "neg-r12.dxf":
            # ezdxf never emits a DXF-R12 $INSUNITS group; patch it in by hand so
            # the §11.3 case-2 loader gate is exercised exactly (geometry is L-bracket).
            txt = path.read_text(encoding="ascii", errors="replace")
            marker = "  2\nHEADER\n"
            assert marker in txt, "R12 HEADER marker not found"
            txt = txt.replace(marker, marker + "  9\n$ACADVER\n  1\nAC1009\n  9\n$INSUNITS\n 70\n     4\n", 1)
            path.write_text(txt, encoding="ascii")
        # expected header version / units
        exp_ver = {"neg-r12.dxf": "AC1009"}.get(name, "AC1015")
        exp_ins = 1 if name == "neg-inch.dxf" else 4
        try:
            recs, cnt, layers = verify(name, path, expected_layers, exp_ver, exp_ins)
            results.append((name, "PASS", recs, cnt, layers))
        except Fail as e:
            failures.append((name, str(e)))
            results.append((name, "FAIL: " + str(e), [], {}, []))

    # per-file PASS table
    print(f"{'file':24s} result")
    print("-" * 60)
    for name, status, *_ in results:
        print(f"{name:24s} {status}")

    # manifest (regenerated from reload output — never hand-typed)
    lines = ["# SAMPLES-SYN — synthetic test set manifest",
             "",
             "Generated by `tools/gen_samples.py` from reload output. Numbers below are",
             "script-printed (never hand-typed). Tool radius R = 1.5875 mm (Ø 3.175).",
             "",
             "Angle convention: site = loop vertex with cross(prev,apex,nxt) < 0 (CW turn on the",
             "CCW loop); air-V = 360° − material-interior ∈ (0°,180°); half = air-V/2; band",
             "[15°,165°]. Center = apex + R·unit( unit(apex→prev) + unit(apex→nxt) ).",
             "syn-L-bracket and syn-fold-heavy are the documented outliers: both sites' air side is",
             "the notch void (NW of the apex), centers (28.8775, 31.1225) and (18.8775, 61.1225);",
             "the SAMPLES-GEN text's NE / SW notes are superseded. See session log 2026-09-29-M0.",
             "",
             "**Synthetic — the golden M6 whole-file gate uses only the user's SolidWorks pair.**",
             ""]
    for name, builder in BUILDERS.items():
        path = SAMPLES / name
        doc = ezdxf.readfile(path); msp = doc.modelspace()
        from collections import Counter
        cnt = Counter(e.dxftype() for e in msp)
        layers = sorted({e.dxf.layer for e in msp if e.dxf.hasattr("layer")})
        recs = next((r for n, s, r, c, l in results if n == name and s == "PASS"), [])
        lines.append(f"## {name}")
        lines.append("")
        lines.append(f"`$ACADVER` = {doc.header.get('$ACADVER')}; `$INSUNITS` = {doc.header.get('$INSUNITS')}; layers: {', '.join(layers)}")
        lines.append("")
        lines.append("Census: " + ", ".join(f"{k}={v}" for k, v in sorted(cnt.items())))
        lines.append("")
        if name.startswith("syn-"):
            lines.append("| site | air-V° | center | outcome |")
            lines.append("|---|---|---|---|")
            exp_out = {
                "syn-shallow-refuse.dxf": "refused (shallow-angle)",
                "syn-near-hole.dxf": "placeable; CIRCLE+MTEXT flagged",
                "syn-arc-tears.dxf": "placeable; A1 DELETE+FLAG, A2 FLAG(trim), L1 FLAG, L2 DELETE",
            }.get(name, "placeable")
            for (v, adeg, c) in recs:
                lines.append(f"| {v} | {adeg} | ({c[0]}, {c[1]}) | {exp_out} |")
        else:
            gates = {"neg-inch.dxf": "$INSUNITS = 1 → loader REFUSES (§11.3 case 1)",
                     "neg-r12.dxf": "$ACADVER = AC1009 → WARN (§11.3 case 2), then process",
                     "neg-spline.dxf": "1 SPLINE at contour scale → loader REFUSES (§11.3 case 3)"}
            lines.append("Loader gate: " + gates[name])
        lines.append("")
    MANIFEST.write_text("\n".join(lines), encoding="utf-8")

    if failures:
        raise SystemExit(1)
    # DoD: samples/ ends with exactly the 11 synthetic DXFs this script wrote plus
    # the user's two SolidWorks golden files (nothing else).
    synth = {n for n in BUILDERS}
    extra = {p.name for p in SAMPLES.glob("*.dxf")} - synth
    unexpected = extra - {"base-rectangular-before-AI.DXF",
                          "base-rectangular - partially radiused.DXF"}
    if unexpected:
        raise SystemExit(f"unexpected files in samples/: {sorted(unexpected)}")
    print(f"\n{len(BUILDERS) - len(failures)}/{len(BUILDERS)} PASS; samples/ contains {len(list(SAMPLES.glob('*.dxf')))} DXFs")

if __name__ == "__main__":
    main()
