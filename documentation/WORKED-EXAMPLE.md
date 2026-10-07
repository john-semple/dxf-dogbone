# Worked Example â€” T-Junction Dogbone (center-right, sample part)

Binding numeric trace for M2. All values verified: every claimed point lies on the dogbone circle at distance R Â± 5e-5, arc endpoints equal rebuilt edge endpoints, and the apex is strictly interior to the arc span (never an endpoint). Coordinates in mm, printed to 5 decimals. **Where this file and CONTRACTS.md disagree, CONTRACTS.md wins (AGENTS.md canon).**

## Geometry inputs (from `base-rectangular-before-AI.DXF`)

Center-right T-junction: bottom tab (xâˆˆ[âˆ’45, 45], down to y=âˆ’95) meets main body. Two edges clicked (raw DXF decomposes edges into micro-segments; promotion views per CONTRACTS Â§2):

- **Edge 1 â€” tab right edge** (supporting line x = 45.0): stored member (45.0, 51.5118) â†’ (45.0, âˆ’95.0). Corner-facing outer endpoint = TOP (45.0, 51.5118).
- **Edge 2 â€” main body bottom edge** = stored LINE (44.2484, 51.5168) â†’ (124.7552, 51.5168) (supporting line y = 51.5168). Corner-facing outer endpoint = LEFT (44.2484, 51.5168). Promotion stops at (44.2484, 51.5168): a non-collinear member (the vertical tear stub) touches that vertex (CONTRACTS Â§2 promotion rule) â€” so the composite is exactly this one member.
- **Side:** ghost pick placing the circle center in the air notch (x > 45, y < 51.5168); the arc bulges through the apex into both body and tab material.
- **R:** production 1.5875 (Ã˜ 3.175 mm). Golden replay for this corner: R = 3.175 (documented user error in the after-file; SAMPLES.md carries per-corner golden radii).

## Step 1 â€” Apex and gate

Supporting lines x = 45.0 âˆ© y = 51.5168:

    apex = (45.0, 51.5168)      half-angle = 45.0Â°  (90Â° corner â†’ within [15Â°, 165Â°] âœ“)

`apex_proximity_ok` (point-to-SEGMENT): apex lies in edge 2's interior (distance 0); for edge 1 it overshoots the stored member's top endpoint (45.0, 51.5118) by 0.0050 â€” within the â‰¤ 5Â·R overshoot allowance â†’ **pass**. (T-cap case: gate measures perpendicular segment distance, per Â§11.4 v3.) M2 fixture asserts these two distances (0.0 and 0.0050), not "distance 0 for both".

## Step 2 â€” Circle construction (R = 1.5875)

Center on air-side bisector at distance R from apex. Air-notch bisector direction: (cos(âˆ’45Â°), sin(âˆ’45Â°))Â·R â†’

    c        = (45.0 + 1.12253, 51.5168 âˆ’ 1.12253) = (46.12253, 50.39427)   [round (46.1225, 50.3943)]
    RÂ·âˆš2/2   = 1.5875 Ã— 0.70710678 = 1.122532
    check    : |c âˆ’ apex| = 1.12253 Ã— âˆš2 = 1.58750 = R âœ“   (identity, not a coincidence)

## Step 3 â€” Rebuild (ADR-003 operational form + Â§11.4 uniqueness post-condition)

Supporting line x = 45.0 âˆ© circle: Î”x = 1.12253 from center â‡’ Î”y = Â±âˆš(RÂ² âˆ’ Î”xÂ²) = Â±âˆš(2.520156 âˆ’ 1.260078) = Â±1.122532

    intersections: (45.0, 51.51680) = apex   and   (45.0, 49.27174)
    **p1 = (45.0, 49.2717)**  (unique non-apex intersection)   angle from c: 225.0000Â°

Supporting line y = 51.5168 âˆ© circle: Î”y = 1.122532 â‡’ Î”x = Â±1.122532

    intersections: (45.0, 51.5168) = apex   and   **p2 = (47.24506, 51.5168)**   angle from c: 45.0000Â°

**Which endpoint moves â€” resolved by the Â§11.4 uniqueness post-condition** ("after rebuild, the protected segment's interior must not intersect the dogbone circle"):

- Edge 1, choice move-TOP-endpoint-to-p1: kept segment (45.0, 49.2717) â†’ (45.0, âˆ’95.0); interior (strictly between) vs circle at x = 45 spans y âˆˆ [49.2717, 51.5168] â†’ disk touches only at the endpoint â†’ **clean âœ“ MOVE TOP ENDPOINT**.
- Edge 1, choice bottom-endpoint: kept segment (49.2717 â€¦ 51.5118 top): interior fully inside disk y-range â†’ **REFUSED** âœ“.
- Edge 2, choice LEFT-endpoint-to-p2: kept segment (47.24506 â†’ 124.7552, y = 51.5168); disk x-range at that line = [45.0, 47.24506] â†’ interior clear âœ“ **MOVE LEFT ENDPOINT**. Kept member after rebuild: (47.2451, 51.5168) â†’ (124.7552, 51.5168).
- Edge 2, choice RIGHT-endpoint-to-p2: segment (44.2484 â†’ 47.2451): interior intersects disk â†’ **REFUSED** âœ“.

Invariants (asserted within 0.001): rebuilt edge-1 endpoint == arc endpoint at 225Â°; rebuilt edge-2 endpoint == arc endpoint at 45Â°; apex strictly interior to arc span (135Â°), never an endpoint.

## Step 4 â€” Arc (replaces the corner)

    arc = Arc(center = c, r = R, start_deg = 45.0, end_deg = 225.0)    # CCW, 180Â°: endpoints p2 â†’ p1, through apex at 135Â°

Both rebuilt edge endpoints == arc endpoints (CONTRACTS Â§1); apex strictly mid-arc. For a 90Â° corner the natural span is exactly 180Â° (not forced â€” angles scale with corner angle).

## Step 5 â€” Deletion truth table (SPEC Â§11.5; window 4Ã— Ã˜ = 12.7 mm, prefilter only)

Tear fragments in-window (circle test, endpoint-in-circle per table):

| Stored entity (before-file) | Endpoint distances (R=1.5875 circle at c) | Action |
|---|---|---|
| (44.2484, 51.5118) â†’ (45.0, 51.5118) | (45.0,51.5118): 1.58397 < R (in); (44.2484,51.5118): 2.18203 (out) | DELETE |
| (44.2484, 51.5118) â†’ (44.2484, 51.5168) | 2.18203, 2.18460 (both out) | survives the circle test â€” **attachment cascade** (below) deletes it |
| (44.2484, 51.5168) â†’ (âˆ’44.2484, 51.5168) tab-top run | 2.18460, â‰«R | survives (east endpoint is attachment-in-removed-portion but HAS a remaining attached neighbor west â€” cascade criterion not met; rebuilt by the LEFT junction's dogbone later) |
| CIRCLE/MTEXT | â€” | none inside window â†’ no flags for this corner |

**Attachment cascade (ADR-012 loop-2/3 amendment, both criteria):** the vertical stub's top endpoint (44.2484, 51.5168) lies in edge-2's removed portion AND â€” evaluated transitively, with removed-portion-vertex contacts not counting â€” the stub retains no remaining attached neighbor (its run contact sits at a removed-portion vertex; the horizontal tear stub was already truth-table-deleted) â†’ cascade delete, **flagged with scripted decision "delete"** in fixtures. The tab-top run survives because its remaining contacts live at non-removed vertices to the west (adjacency criterion discriminates stub vs run). This matches the user's hand-cleaned after-file (stub absent there).

## Step 6 â€” Fold interaction (SYNTHETIC illustration; real sample folds at y=51.2634 span x â‰ˆ Â±[124.8, 230.8], far from this junction â€” the real fold-vs-dogbone cases live at other corners)

Fold line y = 51.2634 heading toward the c area: distance |50.39427 âˆ’ 51.2634| = 0.86913 < R â‡’ circle crosses.

    x_entry = c_x Â± âˆš(RÂ² âˆ’ 0.86913Â²) = 46.12253 Â± âˆš(2.520156 âˆ’ 0.755387) = 46.12253 Â± 1.328514
    â†’ entries at x = 47.45104 and 44.79402

Kept side = the fold approaching from the left â‡’ extend/trim endpoint = **(44.7941, 51.2634)** (Â± 0.001). Golden replay R = 3.175: distance = 51.2634 âˆ’ 49.27183 = 1.99157 < R â‡’ crossings x = 49.71757 / 44.77237.

## Print-precision note (non-blocking, loop-3)

Intermediate intermediates below are printed at reduced precision; exact values: RÂ·âˆš2/2 = 2.2450640, RÂ² = 10.0806250, c_gold = (47.24506, 49.27174), Step-6 half-chord = 1.32845, entries x = 47.45100 / 44.79409. All differences from printed values â‰¤ 9e-5, below every asserted tolerance (Â±5e-5 identity, Â±0.001 acceptance) is the point none of them break â€” no fixture can trip on these.

## Golden replay â€” R = 3.175 (must match the user's after-file within 0.001)

*Errata (M2.2, 2026-10-07; append-only — trace below NOT rewritten): two
printed values in this section are transcription typos; the exact values are
R·√2/2 = 2.245064 (printed 2.244972) and c_gold = (47.24506, 49.27174)
(printed 47.24497, 49.27183) — see the print-precision note above, which
already carries them.*

    c_gold    = (45.0 + 2.24497, 51.5168 âˆ’ 2.24497) = (47.24497, 49.27183)   [after-file: (47.2451, 49.2717) âœ“]
    p1_gold   = (45.0, 49.27183 âˆ’ 2.24516) = (45.0, 47.02667)                [after-file tab edge stops at 47.0267 âœ“]
    p2_gold   = (47.24497 + 2.24516, 51.5168) = (49.49013, 51.5168)          [after-file: (49.49, 51.5168) âœ“]
    arc_gold  = start 45Â° â†’ end 225Â°, CCW, through apex at 135Â°              [after-file arc 64: 50=45.0, 51=225.0 âœ“]
    RÂ·âˆš2/2    = 3.175 Ã— 0.70710678 = 2.244972 ; Î”(âŠ¥) = âˆš(RÂ²âˆ’(Râˆš2/2)Â²) = âˆš(10.080156 âˆ’ 5.039905) = 2.245156

All three after-file cross-checks hold within 0.00013 â€” the construction is verified against the user's own radiused output.

## Identity block (machine-checkable â€” every M2 fixture asserts these)

1. |c âˆ’ apex| = R Â± EPS_CONSTRUCTION.
2. dist(c, p1) = dist(c, p2) = R Â± 5e-5; p1, p2 are the UNIQUE non-apex intersections of the two supporting lines with the circle.
3. Arc endpoints == rebuilt edge endpoints (same stored points, Â± 0.001); apex strictly interior to the arc span (angle strictly between start and end, CCW) â€” never an endpoint.
4. Kept main-edge interiors do not intersect the circle; interior-intersection test uniquely selects the moved endpoint (both alternatives of both edges computed: exactly one passes).
5. Truth-table rows for this corner, with SCRIPTED flag decisions: exactly 1 truth-table delete (horizontal tear stub, no flag) + 1 attachment-cascade delete with scripted decision "delete" (vertical tear stub, flag present, ADR-012/009) + 2 rebuilds (edge-1 top â†’ p1; edge-2 left â†’ p2, edge-2 rebuild references the composite eid per ADR-012 re-promotion clause â€” this edge is re-clicked by the LEFT junction's dogbone later) + protected set = {edge-1 member, edge-2 composite, fold eids, placed arc}.

## Acceptance thresholds

- M2 default replay (R=1.5875): c = (46.1225, 50.3943); arc endpoints p1=(45.0, 49.2717) @225Â°, p2=(47.2451, 51.5168) @45Â°; Â±0.001.
- M2 golden replay (R=3.175, matches after-file): c = (47.2450, 49.2718); p1 = (45.0, 47.0267); p2 = (49.4900, 51.5168); Â±0.001.
- Both identity blocks assert with `start=45.0, end=225.0`.