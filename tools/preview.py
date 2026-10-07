"""Render sample DXFs to SVG for eyeball checks (no GUI exists until M1).

Usage:  .venv\\Scripts\\python.exe tools\\preview.py [file.dxf ...]
No args → renders every samples\\*.dxf into previews\\*.svg. Uses only ezdxf +
stdlib (SVG written by hand — no Pillow/matplotlib, SPEC §11.10). Dogbone-radius
arcs (1.5875 / 3.175) are highlighted red so the golden corners pop.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import ezdxf

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
OUT = ROOT / "previews"
DOG_R = (1.5875, 3.175)
W, H = 1600, 1000
STROKE = "#1a1a1a"


def entities(path: Path):
    doc = ezdxf.readfile(path)
    out = []
    for e in doc.modelspace():
        t = e.dxftype()
        a = e.dxf
        if t == "LINE":
            out.append(("L", (a.start.x, a.start.y), (a.end.x, a.end.y)))
        elif t == "ARC":
            out.append(("A", (a.center.x, a.center.y), a.radius, a.start_angle, a.end_angle))
        elif t == "CIRCLE":
            out.append(("C", (a.center.x, a.center.y), a.radius))
        elif t == "POINT":
            out.append(("P", (a.location.x, a.location.y)))
        elif t == "MTEXT":
            out.append(("T", (a.insert.x, a.insert.y), e.text.split("\\P")[0][:80]))
    return out


def arc_pts(c, r, s, e, n=72):
    span = (e - s) % 360.0 or 360.0
    return [(c[0] + r * math.cos(math.radians(s + span * i / n)),
             c[1] + r * math.sin(math.radians(s + span * i / n))) for i in range(n + 1)]


def render(path: Path, out: Path):
    ents = entities(path)
    if not ents:
        return False
    xs, ys = [], []
    for ent in ents:
        k = ent[0]
        if k == "L":
            xs += [ent[1][0], ent[2][0]]; ys += [ent[1][1], ent[2][1]]
        elif k == "A":
            for p in arc_pts(ent[1], ent[2], ent[3], ent[4], 36):
                xs.append(p[0]); ys.append(p[1])
        elif k in ("C", "P", "T"):
            xs.append(ent[1][0]); ys.append(ent[1][1])
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    span = max(maxx - minx, 1e-9), max(maxy - miny, 1e-9)
    m = 0.05 * max(span)
    minx -= m; miny -= m; maxx += m; maxy += m
    sx = W / (maxx - minx)
    sy = H / (maxy - miny)
    s = min(sx, sy)
    ox = (W - s * (maxx - minx)) / 2
    oy = (H - s * (maxy - miny)) / 2

    def X(x): return round(ox + (x - minx) * s, 2)
    def Y(y): return round(oy + (maxy - y) * s, 2)

    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
           f'viewBox="0 0 {W} {H}" font-family="monospace">',
           f'<rect width="100%" height="100%" fill="white"/>',
           f'<text x="8" y="16" font-size="13" fill="#666">{path.name}</text>']
    for ent in ents:
        k = ent[0]
        if k == "L":
            (x1, y1), (x2, y2) = ent[1], ent[2]
            svg.append(f'<line x1="{X(x1)}" y1="{Y(y1)}" x2="{X(x2)}" y2="{Y(y2)}" '
                       f'stroke="{STROKE}" stroke-width="1" vector-effect="non-scaling-stroke"/>')
        elif k == "A":
            c, r, sa, ea = ent[1], ent[2], ent[3], ent[4]
            hot = any(abs(r - dr) < 1e-6 for dr in DOG_R)
            col = "#d00" if hot else "#e08000"
            wid = 2.5 if hot else 1
            pts = arc_pts(c, r, sa, ea)
            pl = " ".join(f"{X(p[0])},{Y(p[1])}" for p in pts)
            svg.append(f'<polyline points="{pl}" fill="none" stroke="{col}" '
                       f'stroke-width="{wid}" vector-effect="non-scaling-stroke"/>')
        elif k == "C":
            (cx, cy), r = ent[1], ent[2]
            svg.append(f'<circle cx="{X(cx)}" cy="{Y(cy)}" r="{round(r * s, 2)}" fill="none" '
                       f'stroke="#0055d0" stroke-width="1" vector-effect="non-scaling-stroke"/>')
        elif k == "P":
            (px, py) = ent[1]
            svg.append(f'<path d="M {X(px)-4} {Y(py)} H {X(px)+4} M {X(px)} {Y(py)-4} V {Y(py)+4}" '
                       f'stroke="#d00" stroke-width="1.5" vector-effect="non-scaling-stroke"/>')
        elif k == "T":
            (tx, ty), txt = ent[1], ent[2]
            esc = txt.replace("&", "&amp;").replace("<", "&lt;")
            svg.append(f'<text x="{X(tx)}" y="{Y(ty)}" font-size="11" fill="#888">{esc}</text>')
    svg.append("</svg>")
    out.write_text("\n".join(svg), encoding="utf-8")
    return True


def main():
    OUT.mkdir(exist_ok=True)
    args = sys.argv[1:]
    files = [Path(a) for a in args] if args else sorted(SAMPLES.glob("*.dxf"))
    made = []
    for f in files:
        out = OUT / (f.stem + ".svg")
        if render(f, out):
            made.append(out.name)
    print(f"rendered {len(made)} file(s) to previews\\:")
    for n in made:
        print("  previews\\" + n)


if __name__ == "__main__":
    main()
