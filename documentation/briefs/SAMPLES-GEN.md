# Brief — SAMPLES-GEN: Synthetic DXF Test Set (agent-executable)

**Role:** generate deterministic synthetic DXF test files. Implement the exact geometry below; do NOT redesign it.
**Files you own:** `tools/gen_samples.py`, `samples/` (synthetic files only), `documentation/SAMPLES-SYN.md` (manifest auto-generated from reload output — never hand-typed numbers).
**Forbidden:** touching the user-provided SolidWorks golden pair, app code, `tests/`, any other doc.
**All values below have been pre-derived and machine-verified** (every "assert" is a computed check you reproduce in the script — if your drawn geometry disagrees, the script fails and you STOP; do not adjust targets).

## Tooling

- Python 3.11 + `ezdxf`, pinned per `requirements.txt` (M0's pin; if absent, write `ezdxf==1.4.2` and the M0-brief pytest pin, then proceed).
- ONE script, `tools/gen_samples.py`: builds every file below into `samples/`, reloads each with ezdxf, asserts DXF version / `$INSUNITS` / census / layers / the specific geometry assertions listed per file (including half-angle recomputation from drawn entities — self-catching construction errors), prints a per-file PASS table, exits non-zero on any mismatch. Assertions ignore header timestamps (CONTRACTS §4 exclusion list).

## Global requirements

- DXF `R2000` (AC1015) except `neg-r12.dxf` (R12 deliberately); `$INSUNITS = 4` (mm) everywhere except `neg-inch.dxf`.
- Entity types: LINE, ARC, CIRCLE, POINT, MTEXT only, layer `0` unless stated. No LWPOLYLINE/SPLINE/ELLIPSE (except `neg-spline.dxf`'s one SPLINE).
- Outlines = closed CCW loops of SEGs, endpoint gaps ≤ 0.0001. Units mm. Tool R = 1.5875 (Ø 3.175).

**Angle convention (LOCKED, used by every file + M2):**
- A *site* = any loop vertex with cross(prev,cur,nxt) < 0 (right turn on the CCW loop), turn-based interior angle ∈ (0°, 180°); the script DETECTS sites this way (never from a hand list) and asserts the count per file.
- Dogbone center = apex + R · air-side bisector unit (air = away from material; for notch bottoms the air is the notch void, for material corners the air is outside the plate). Same formula everywhere.
- The tool band [15°, 165°] applies to that turn-based interior angle. Exactly one construction — mirrors WORKED-EXAMPLE.
- The script prints each site's vertex, arm vectors, interior angle, computed center, and expected outcome; the manifest carries these printed values.

## Positive samples

### 1. `syn-L-bracket.dxf` — minimal clean reflex corner
Outline (CCW): (0,0) → (80,0) → (80,80) → (30,80) → (30,30) → (0,30) → close.
Site **(30,30)** — material-reflex corner (interior 90°, half 45.0°), air NE; dogbone center = apex + R·(+1,+1)/√2 = (31.1225, 31.1225). Assert 45.0 ± 0.01, |center−apex| = R.

### 2. `syn-angled-notch.dxf` — variable arc span (≠ 180°)
Plate (CCW): (0,0) → (120,0) → (120,100) → (94.641,100) → (60,60) → (25.359,100) → (0,100) → close.
Site **(60,60)** — machine-derived: arms from apex to entries are (∓34.641, +40) ⇒ turn-based interior = **81.787°, half 40.893°**; air = +y (notch void); dogbone center = (60.0, **61.5875**). Script asserts 40.89 ± 0.05 and center distance = R. Note: the notch air-V (81.79°) within band ⇒ placeable; arc span ≠ 180°.

### 3. `syn-tight-notch.dxf` — inside angle band, near edge
Plate (CCW): (0,0) → (120,0) → (120,40) → (90,50) → (120,60) → (120,100) → (0,100) → close.
Site **(90,50)**: arms (30,−10)/(30,+10) ⇒ turn-based interior (notch air-V) = **36.870°, half 18.435°** — inside [15°,165°], near the edge; air = +x (notch void); dogbone center = apex + R·(+1,0) = (91.5875, 50.0); assert |center−apex| = R. Purpose: non-right-angle geometry, placeable; arc-span math is M2's to verify from the corner angle (script asserts only center placement and half-angle).

### 4. `syn-shallow-refuse.dxf` — below-band refusal case
Plate (CCW): (0,0) → (120,0) → (120,46.5) → (78,50) → (120,53.5) → (120,100) → (0,100) → close.
Site **(78,50)**: arms (42,∓3.5) ⇒ turn-based interior = **9.527°, half 4.764°** < 15° ⇒ **must refuse** (shallow-angle message class, SPEC §11.4). Script asserts 9.527 ± 0.05 from drawn geometry; the refusal itself is M2's fixture consuming this geometry.

### 5. `syn-double-tabs.dxf` — T-junctions + re-promotion (ADR-012(c))
Outline (CCW): (0,57) → (20,57) → (20,0) → (60,0) → (60,57) → (80,57) → (80,0) → (120,0) → (120,57) → (200,57) → (200,140) → (0,140) → close. Shape: top bar y∈[57,140] with two tabs hanging to y=0 (x∈[20,60] and x∈[80,120]); voids: x<20 below bar, x∈(60,80) between tabs, x>120 below bar.
Sites (4, machine-detected, half 45° each): **(20,57)** air SW (center 18.8775, 55.8775); **(60,57)** air SE (center 61.1225, 55.8775); **(80,57)** air SW (center 78.8775, 55.8775); **(120,57)** air SE (center 121.1225, 55.8775).
Key property: slot-mouth dogbones at (60,57) and (80,57) both consume the shared bar segment (60,57)-(80,57) ⇒ ADR-012(c) re-promotion. Center gap = **17.755 > 2R**; overlap silent.
Plus one fold, layer `BEND_UP`: LINE (10,100) → (190,100). Distance from fold to nearest dogbone center = **44.12 > 12.7** window ⇒ untouched. (`BEND_UP` matches auto-detect `bend`.)

### 6. `syn-near-hole.dxf` — flagged-CIRCLE flow (ADR-009/013)
Plate with top slot (CCW): (0,0) → (100,0) → (100,100) → (60,100) → (60,60) → (40,60) → (40,100) → (0,100) → close.
Sites (2, machine-detected): slot-floor corners **(60,60)** air NW (center 58.8775, 61.1225) and **(40,60)** air NE (center 41.1225, 61.1225) — half 45° each. Rim vertices (60,100)/(40,100) are convex (turn +90°) — NOT sites; script asserts site count exactly 2.
Extras: CIRCLE center (50,54) r=1.25; MTEXT "NOTES" at (42,58) height 2.
Distances (assert): hole center → site (40,60) = **11.662** < 12.7 (4× Ø) window ⇒ flag triggers at that corner; 11.662 > 1.5875 + 1.25 = 2.84 ⇒ kept hole cannot intersect the dogbone circle. MTEXT (42,58) → (40,60) = **2.828** < 12.7 ⇒ flagged; ≥ R ⇒ intersect-safe keep. Center gap between the two dogbones = **17.755 > 2R** ⇒ overlap silent.

### 7. `syn-fold-heavy.dxf` — auto-detect + §11.3 case-5 collinear warning
Plate (CCW): (0,0) → (180,0) → (180,90) → (20,90) → (20,60) → (0,60) → close.
Site **(20,60)** — material-reflex (interior 90°, half 45°), air SW; center = apex + R·(−1,−1)/√2 = (18.8775, 58.8775).
Folds (all straight LINEs):
- layer `BEND_UP`: (10,80) → (170,80); (30,40) → (170,40)  [distances to center 21.12 / 18.88 mm — clear of the 12.7 window; auto-detect]
- layer `FOLD_LINES`: (40,20) → (160,20)  [also matches auto-detect]
- layer `0`: (50,70) → (150,70); (50,30) → (150,30)  [manual designation, no auto-hit]
- layer `0`: LINE (0,60) → (20,60) — **exactly overlays contour edge (20,60)→(0,60)** ⇒ §11.3 case-5: loader must WARN (not refuse); manifest notes the expected warning.

### 8. `syn-arc-tears.dxf` — ARC truth-table rows (§11.5)
Plate (CCW): (0,0) → (120,0) → (120,30) → (95,30) → (95,55) → (120,55) → (120,100) → (0,100) → close. Right-edge notch, void x∈[95,120], y∈[30,55].
Sites (2, machine-detected): **(95,30)** air NE (center **96.1225, 31.1225**); **(95,55)** air SE (center **96.12253, 53.87747**); half 45° each.
All tear entities target the **(95,55) dogbone circle**; corner (95,55) dogbone at R=1.5875 bisector (+1,−1)/√2 ⇒ center **c8 = (96.12253, 53.87747)** — mirrors WORKED-EXAMPLE construction.
Tears (script recomputes every distance from reloaded geometry and asserts the classification):
- **ARC A1** center (97.0,53.0), r=2.0, span 140°→230°. Endpoints (95.4679,54.2856) dist→c8 = **0.7714 < R** (in); (95.7144,51.4679) dist = **2.4439 > R**. Row: endpoint-in ⇒ **DELETE + FLAG**.
- **ARC A2** center (96.25,53.8775), r=2.75, span 180°→360°. Endpoints (93.5,53.8775) dist = **2.6225 > R**, (99.0,53.8775) dist = **2.8775 > R**; min distance of arc set to c8 = **0.1275 < R** ⇒ chord-crosser ⇒ **FLAG with delete|trim options** (ADR-013).
- **LINE L1** (94.9,55.2) → (98.0,52.8): endpoint dists **1.8010 / 2.1647** (both > R); min segment distance to c8 = **0.2974 < R** ⇒ chord-crosser ⇒ **FLAG**.
- **LINE L2** (95.2,54.8) → (98.0,54.8): endpoint (95.2,54.8) dist = **1.3047 < R** ⇒ endpoint-in ⇒ **DELETE**.

### 9. `syn-multicorner.dxf` — four corners → one Apply All
Plate (CCW): (0,0) → (200,0) → (200,100) → (180,100) → (180,80) → (160,80) → (160,100) → (140,100) → (140,80) → (120,80) → (120,100) → (0,100) → close. Three 20×20 U-slots cut INTO the top edge (voids x∈[160,180], [140,160], [120,140], each y∈[80,100]).
Sites (4, machine-detected — the slot-floor corners; rim vertices (180,100)/(160,100)/(140,100)/(120,100) are convex, NOT sites): **(180,80)** air NW (center 178.8775, 81.1225); **(160,80)** air NE (center 161.1225, 81.1225); **(140,80)** air NW (center 138.8775, 81.1225); **(120,80)** air NE (center 121.1225, 81.1225). Half 45° ± 0.01 each (script asserts all four, site count exactly 4).
Adjacent-center gaps within each slot = **17.755 > 2R** ⇒ overlap silent.
Plus: CIRCLEs Ø5 at (60,50) & (100,50) — ≥ 64 mm from every site ⇒ immune. Fold layer `BEND_DOWN`: (30,15) → (170,15) — ≥ 65 mm from every site ⇒ untouched (auto-detected).
Purpose: chain 4 dogbones → single Apply All; one auto-fired fold; clean census.

## Negative files (loader gates per SPEC §11.3)

- `neg-inch.dxf`: geometry of #1, `$INSUNITS = 1` ⇒ loader REFUSES (case 1).
- `neg-r12.dxf`: ezdxf `new('R12')`, geometry of #1 ⇒ WARN (case 2), then process (manifest records the agreed behavior).
- `neg-spline.dxf`: geometry of #1 + one SPLINE ⇒ REFUSE (case 3 census).

## Manifest — `documentation/SAMPLES-SYN.md` (script-generated)

Per file: purpose; census table (reload output); layer list; concave-site table (vertex / edge dirs / computed half-angle / expected outcome: placeable | refused+reason-class | flagged-entity roles); negative files: exact loader gate expectation. Global note: **synthetic — the golden M6 whole-file gate uses only the user's SolidWorks pair.** All numbers printed from reloaded geometry.

## DoD

- `python tools/gen_samples.py` runs clean: **11 files** (8 positive + 3 negative); every construction + reload assertion PASSes; single truth per site (no alternative-reading notes survive in the brief after this rewrite — if the script disagrees with a listed number, STOP and report the discrepancy rather than "fixing" either side).
- `samples/` ends with exactly 11 synthetic + 2 user golden DXFs, nothing else.

**Cite:** CONTRACTS §1–§4; SPEC §4, §6, §11.3, §11.5, §11.4; WORKED-EXAMPLE.md (construction + center placement math); ADR-012/013. Manifest numbers are DERIVED (script-printed), never hand-typed.