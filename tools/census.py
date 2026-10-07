"""Entity census for a DXF file (M0 checkpoint tool).

Usage: python tools/census.py <path-to-dxf>

Prints per-type entity counts, layer names, $INSUNITS, $ACADVER.
Loads with ezdxf.readfile, falling back to ezdxf.recover.readfile
(damaged-file path, SPEC §11.3; §11.9-M0).
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import ezdxf
import ezdxf.recover

# Entity types named in the ISSUES.md census contract; everything else → "other"
TRACKED = ("LINE", "ARC", "CIRCLE", "POINT", "MTEXT")


def load(path: Path):
    """readfile with recover fallback (SPEC §11.3)."""
    try:
        return ezdxf.readfile(path)
    except Exception:
        doc, auditor = ezdxf.recover.readfile(path)
        print(f"note: ezdxf.readfile failed; used ezdxf.recover "
              f"(recoverable errors: {len(auditor.errors)})")
        return doc


def census(path: str) -> None:
    doc = load(Path(path))
    msp = doc.modelspace()

    counts: Counter[str] = Counter()
    layers: set[str] = set()
    for e in msp:
        t = e.dxftype()
        counts[t if t in TRACKED else "other"] += 1
        if e.dxf.hasattr("layer"):
            layers.add(e.dxf.layer)

    print(f"file: {Path(path).name}")
    for t in TRACKED:
        print(f"  {t}: {counts[t]}")
    if counts["other"]:
        detail = {t: n for t, n in counts.items() if t not in TRACKED and t != "other"}
        print(f"  other: {counts['other']}  {detail}")
    print("layers:", ", ".join(sorted(layers)) or "(none)")
    print(f"$INSUNITS: {doc.header.get('$INSUNITS', '(unset)')}")
    print(f"$ACADVER:  {doc.header.get('$ACADVER', '(unset)')}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python tools/census.py <path-to-dxf>")
        sys.exit(2)
    census(sys.argv[1])
