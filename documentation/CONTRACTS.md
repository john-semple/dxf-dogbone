# Interface Contracts

> **Status: Mostly completed**

Single source of truth for module boundaries and function signatures. Agents implement these; they do not redesign them. All signatures use Python type hints; all tolerances are explicit parameters with defaults from `geometry/tolerances.py`.

**Ownership:** changes to this file require a new ADR entry in DECISIONS.md.

---

## 1. Core dataclasses (`geometry/entities.py`, stdlib-only)

Primitive entity dataclasses live in `geometry/` (NOT `model/` — see ADR-008, not ADR-006). Every primitive carries an immutable `eid: str` (DXF handle at load; minted as `n<seq>` for new entities). IDs are stable across Apply/Undo/Revert; all rules reference `eid`, never object references or raw coordinates.

```python
@dataclass(frozen=True)
class Pt:
    x: float
    y: float

@dataclass(frozen=True)
class Seg:            # LINE primitive
    eid: str
    a: Pt             # endpoint in world coords
    b: Pt

@dataclass(frozen=True)
class Arc:            # ARC primitive (CCW from start_angle to end_angle)
    eid: str
    center: Pt
    r: float
    start_deg: float  # CCW, degrees
    end_deg: float

@dataclass(frozen=True)
class Circ:
    eid: str
    center: Pt
    r: float

@dataclass(frozen=True)
class PointEnt:       # POINT primitive
    eid: str
    p: Pt

@dataclass(frozen=True)
class TextEnt:        # MTEXT (render as text at insertion point; ignore formatting)
    eid: str
    p: Pt
    text: str

Primitive = Seg | Arc | Circ | PointEnt | TextEnt
Entity = union of Primitive and PassThrough   # PassThrough: eid + raw kind string, never modified

@dataclass(frozen=True)
class Dogbone:
    db_id: str        # minted per placement
    apex: Pt
    center: Pt
    r: float
    side: Side        # enum: LEFT_OF_EDGE1_AB | RIGHT_OF_EDGE1_AB (ghost-pick result)
    edge1_eid: str
    edge2_eid: str
    arc: Arc          # the replacement arc; endpoints == rebuilt edge endpoints

@dataclass(frozen=True)
class Side:
    sign: int             # +1 | -1 — which of the two bisector constructions (ghost-pick result);
                          # engine computes both and tags them; UI forwards the picked Side object

@dataclass(frozen=True)
class Rebuild:            # one edge endpoint moved by a placement (ADR-003 ops; member eids per ADR-012)
    eid: str              # member (or composite) eid whose endpoint moved
    old: Pt
    new: Pt               # == arc endpoint after rebuild

@dataclass(frozen=True)
class Trim:               # endpoint repositioned without deletion (strays, folds, flag-trim)
    eid: str
    old: tuple            # (a, b) before — Seg: (Pt, Pt); Arc: (start_deg, end_deg) per ADR-015(d)
    new: tuple            # (a, b) after — Seg: (Pt, Pt); Arc: (start_deg, end_deg) per ADR-015(d)

@dataclass(frozen=True)
class Refusal:            # ADR-015(a): the type CONTRACTS §2 references but never defined
    reason: str

@dataclass(frozen=True)
class Flag:               # ADR-009/013: explicit-user-decision entity
    eid: str
    reason: str           # "CIRCLE_IN_WINDOW" | "MTEXT_IN_WINDOW" | "ARC_ENDPOINT_IN" | "CHORD_CROSSER" | "CASCADE_DANGLING"
    options: frozenset    # subset of {"delete","keep","trim"} — allowed outcomes for this case
    decision: str | None  # None while pending; else "delete"|"keep"|"trim"; sticky per session

@dataclass
class CornerResult:
    ok: bool
    dogbone: Dogbone | None
    deletions: list[str]      # member eids to delete (promoted edges carry member lists, ADR-012)
    trims: list[Trim]         # from strays / folds / flag-trims
    rebuilt: list[Rebuild]    # per-endpoint, member eids; ADR-003 ops:
                              # rebuilt endpoint = UNIQUE NON-APEX intersection of the edge's
                              # supporting line with the dogbone circle; endpoint-moved uniqueness
                              # proven by §11.4 post-condition (kept segment interior misses circle)
    refusals: list[str]       # human-readable refusal reasons (shallow angle, tangent line, overlap...)
    flags: list[Flag]         # flagged entities awaiting/holding user decisions
    warnings: list[str] = field(default_factory=list)
                              # ADR-016(b): non-blocking, human-readable; ADR-009 keep-warning
                              # carrier (KEPT_CROSSER / KEPT_INTERSECTS / FLAG_DECISION ...)

@dataclass
class EditResult:            # ADR-025: manual-edit result (trim-to-closest / stray-delete)
    ok: bool                  # False => reason carries the refusal verbatim
    reason: str | None         # "NO_TARGET: ..." | "UNKNOWN_EDGE: ..." | None on ok
    deletions: list[str]      # stray-delete: the run's ENTITY-level eids (members + composites)
    trims: list[Trim]         # at most one; trims[0].eid = the promoted-run eid; Seg (Pt,Pt)
    warnings: list[str] = field(default_factory=list)
```

Model state (owned by `model/`, stdlib + geometry imports allowed per SPEC §11.1 amendment ADR-008):

```python
@dataclass
class ModelState:
    primitives: list[Entity]          # ordered; includes PassThrough; promoted composites registered
    dogbones: list[Dogbone]
    fold_eids: set[str]               # designated fold lines
    flag_decisions: dict[str, str]    # eid -> "keep"|"delete"|"trim"; sticky per session; ADR-009/013 amendment
    next_seq: int                     # for minting eids

class Model:
    def snapshot(self) -> ModelState          # deep copy
    def restore(self, s: ModelState) -> None  # swap; ID↔entity mapping preserved
    def get(self, eid: str) -> Entity | None
    def apply_corner(self, res: CornerResult) -> None  # mutate per result
    def apply_edit(self, res: EditResult) -> None      # ADR-025: manual edits (trim/stray-delete);
                                                        # deletions scrubbed from primitives AND
                                                        # fold_eids AND flag_decisions; trims are
                                                        # Seg-only; every referenced eid must exist
```

**Adjacency (ADR-012, loop-2 amendment):** the model maintains an endpoint-keyed adjacency map (each eid → set of member eids sharing an endpoint within EPS_COINCIDE), built at load, traveling inside snapshots. *(ADR-015(e): the map is a pure derived function `geometry/adjacency.py: build_adjacency(entities, eps_coincide)` of the snapshot's primitives — "maintained/traveling" is satisfied by derivation; no ModelState field is added.)* Cascade trigger: attachment endpoint in a rebuilt edge's removed portion AND no remaining attached neighbor after that portion is removed — **a surviving entity's contact at a vertex inside the removed portion does NOT count as a remaining attached neighbor; the cascade is evaluated transitively (truth-table deletions first, then iterate to fixed-point).** Both criteria required.

---

## 2. Engine API (`rules/engine.py` — headless; may import geometry only)

```python
TOL = tolerances  # single source; predicates never roll their own

def compute_apex(seg1: Seg, seg2: Seg, eps_construction: float) -> tuple[Pt, float] | Refusal
    # returns (apex, half_angle_deg) or Refusal for parallel/collinear/half-angle outside [15,165]

def apex_proximity_ok(apex: Pt, seg1: Seg, seg2: Seg, k: float, r: float) -> bool
    # point-to-SEGMENT distance (perpendicular; interior apex passes at 0, T-cap apex passes);
    # overshoot past segment end allowed if ≤ k*r (tear-truncated edges)

def resolve_edge(primitives: list[Entity], eid: str,
                 eps_coincide: float = EPS_COINCIDE) -> tuple[Seg, Seg] | None
    # ADR-016(a)/(g): (promoted run Seg, seed Seg) | None. The seed is the
    # deepest eid present in primitives (member pre-apply, registered
    # composite post-apply). M2.2: the run is re-derived by walking
    # geometry/runs.chain_run FROM THE SEED — never a proximity pick at the
    # seed's midpoint (X-crossing defect); keeps the seed-membership guard.

def ghost_candidates(primitives: list[Entity], edge1_eid: str, edge2_eid: str, r: float,
                     eps_construction: float = EPS_CONSTRUCTION,
                     eps_coincide: float = EPS_COINCIDE) -> list[tuple[Side, int, Pt]] | Refusal
    # ADR-015(m)/016(a): the four (Side, side_flip, center) ghost rays for a
    # picked edge pair; refusal propagates the apex/band gate.

def place_corner(primitives: list[Entity], edge1_eid: str, edge2_eid: str, side: Side,
                 r: float, fold_eids: set[str], dogbones: list[Dogbone]) -> CornerResult
                 # ADR-015(b): + kw-only eps_construction=EPS_CONSTRUCTION, eps_coincide=EPS_COINCIDE,
                 # flag_decisions: dict[str, str] = {}, db_id: str | None = None (deterministic default
                 # "db-<edge1>+<edge2>"). ADR-015(c): placed arc eid = "arc-pending-<db_id>";
                 # Model.apply_corner mints the real n<seq> eid. ADR-015(g): compute_apex returns half
                 # of the smaller angle; per-side half/bisector/span derived inside.
                 # ADR-016(b): CornerResult.warnings carries the ADR-009 keep-warnings
                 # (KEPT_CROSSER / KEPT_INTERSECTS / FLAG_DECISION) — see the §1 dataclass.
                 # ADR-016: + kw-only side_flip: int = +1 (one sign bit cannot address all four
                 # ghost rays); radius validation refusal "RADIUS: ..." pinned; UNKNOWN_EDGE string
                 # unified as "UNKNOWN_EDGE: <eid> is not resolvable in primitives"; flag_decisions
                 # validated per-case against Flag.options (invalid -> pending/default + warning).
                 # M2.2 (decomposition, no signature change): pipeline stages are
                 # _validate_inputs -> _truth_table -> _rebuild_and_arc over an internal
                 # _Ctx dataclass (radius/edges/gate/bisector; rows+flags+warnings+flagged;
                 # rebuild uniqueness/cascade/span identity/assembly) — public API and all
                 # refusal/warning strings byte-identical.
                 # full rule pipeline, in order: radius validation -> apex gate -> overlap vs existing dogbones ->
                 # circle construction → deletion truth table (SPEC §11.5) → edge rebuild (ADR-003 ops:
                 # rebuilt endpoint = UNIQUE NON-APEX intersection of the edge's supporting line with the
                 # dogbone circle; refusals: line tangent to circle; post-rebuild opposite endpoint not
                 # on the far side of the rebuilt point (segment no longer spans)) → fold interaction stubs
                 # (extend/trim runs at export; here only compute fold-vs-circle intersections for preview)

def promoted_edge_at(primitives: list[Entity], p_world: Pt, eps_pick: float,
                     eps_coincide: float) -> Seg | None
    # pick: clicked entity = nearest segment within eps_pick; promotion: extend along
    # collinear neighbors (endpoint gaps ≤ eps_coincide, direction dot ≥ 0.999 same dir
    # or ≥ -0.999 reversed) until non-collinear neighbor; returns the promoted Seg (eid
    # per geometry/runs.chain_run: promoted-<first entity eid>, composite's own eid kept
    # on re-promotion — ADR-016(f); M2.2: canonical direction derives from the run
                  # EXTENT, snapped to the dominant axis) — Seg carries fields members: list[str]
                  # (ordered member eids merged, ADR-012) and pick_eid (the clicked member eid)

def trim_to_closest(primitives: list[Entity], p_world: Pt, eid: str,
                    eps_construction: float = EPS_CONSTRUCTION,
                    eps_coincide: float = EPS_COINCIDE) -> EditResult
                  # ADR-025 manual trim-to-closest. ``eid`` is a promoted_edge_at Seg's eid
                  # (plain member or promoted-* composite); the run is re-derived via
                  # chain_run from the seed (X-crossing discipline, ADR-016(f)). The moving
                  # endpoint = the run-extent endpoint nearest the click (within EPS_COINCIDE
                  # of the clicked entity's own end when the click lands interior). It snaps
                  # to its CLOSEST supporting-geometry intersection among candidate targets
                  # (LINE supporting line; ARC/CIRCLE supporting circle, arc-span-filtered
                  # via span_contains when the arc actually spans the crossing; POINT
                  # location) — candidates exclude the run's own member eids; extend-when-
                  # short, trim-when-past. Zero EXTERNAL attachments (build_adjacency minus
                  # run members, EPS_COINCIDE) => stray => propose deleting the run's
                  # entity-level eids (deletions, no trims). ADR-028: when the click
                  # sits in a collinear span with an intersection on both sides
                  # (external attachment at a piece endpoint, or a finite crossing
                  # through the piece interior), remove that span instead of
                  # rotating onto a perpendicular foot. Members wholly inside are
                  # a deletion carrying SPAN_DELETE. A member that runs past both
                  # bounds is deleted whole; collinear geometry past either
                  # intersection is kept. A member that runs past exactly one
                  # bound is one on-axis Trim of the surviving stub. One open
                  # side keeps the foot path above. Refusals (verbatim, pinned):
                  # "UNKNOWN_EDGE: <eid> is not resolvable in primitives" /
                  # "NO_TARGET: no supporting-geometry intersection found". Pure engine:
                  # imports geometry only.
```

**Promotion/reconciliation rules (ADR-012):** every `Rebuild/Trim/Deletion` references member eids; `Model.apply_corner` replaces the member run with the rebuilt composite (registered under the promoted eid), migrates protected-set references from members to the composite, and asserts no member eid is referenced twice. Entities whose attachment endpoint lands on a rebuilt edge's removed portion (± EPS_COINCIDE) are deleted by the attachment-cascade rule and flagged (editable, sticky).

## 3. IO API (`dxf_io/` — headless; may import ezdxf, geometry)

```python
def load(path: Path) -> LoadResult            # raises LoadRefused(reason) for §11.3 cases
class LoadResult:
    model_state: ModelState                   # primitives with DXF handles as eids
    header: dict                              # $INSUNITS, $ACADVER (for version-matched export)
    warnings: list[str]                       # census passthrough list, duplicate-merge count, fold-on-contour warnings

def export(state: ModelState, header: dict, out_path: Path, fold_layer: str = "FOLD_LINES",
           fold_color: int = FOLD_COLOR_CONST, *, eps: float = EPS_COINCIDE,
           remove_watermark: bool = True, original: ModelState | None = None) -> ExportResult
    # PURE: operates on a deep copy (ADR-004). Pipeline: fold extend/trim (idempotent:
    # skip if endpoint on arc within eps_coincide; extend to FIRST circle intersection,
    # max 2× deletion-window reach else unchanged+warn) → watermark filter (ADR-017:
    # exact WATERMARK_TEXTS match on the copy only; default on) → move folds to
    # FOLD_LINES layer → ezdxf.audit pre-check (must be clean, else export aborts
    # with a human-readable report and writes neither the DXF nor the log) → save
    # → write <out>.export_log.md. `original` is the load-time drawing, used only
    # for the log's deletion list. ExportResult: warnings, audit_summary,
    # deleted_entity_count (watermark notes removed by this call), written.
```

## 4. Verification API (`tools/verify_*.py`)

```python
# M2 golden, corner-local (per revised M2 gate): for each sample corner with the
# documented golden radii (2× R=3.175, 1× R=1.5875 — see SAMPLES.md):
def verify_corner(out: list[Entity], expected_corner_block: list[tuple]) -> bool
# normalization recipe (SPEC §11.9 amendment): compare only tuples
#   (type, layer, color, round(coord,3)) for LINE/ARC/CIRCLE/POINT,
#   sorted by (type, rounded sortpoint, rounded end) where sortpoint =
#   start Pt for Seg/PointEnt, center for Arc/Circ; exclude header, tables,
#   handles, timestamps, MTEXT styling. Whole-file normalized diff deferred to M6.

# GUI harness (no human eyes): drive tkinter canvas with synthetic events
def run_corner_workflow_clicks(canvas, click_seq: list[tuple[float, float]]) -> ModelState
# asserts on MODEL state after synthetic clicks (edge picks → ghosts → side → preview →
# confirm); human then does 2-min visual checklist per GUI milestone (briefs cite it)
```

**Test runner:** pytest (pinned in requirements.txt per M0 brief; SPEC §11.9).

## 5. Ownership matrix (supplements SPEC §11.1)

| Concern | Module | Note |
|---|---|---|
| hit-testing, EPS_PICK derivation, edge promotion | `rules/` | headless-testable; UI only converts screen→world |
| snapshot/undo/redo/revert, flag-decision persistence | `model/` | flags travel in snapshots (sticky per session; Revert-to-Original clears). Redo (ADR-027) keeps the state undo leaves; a new push, revert, fold designation, or sticky flag decision clears it. The pending queue is not in the snapshot |
| pending-corner undo | `ui/` | ADR-016(j) record, ADR-029 history: confirm depth, Apply All batch restore, newest-first removal. Revert keeps the queue and drops that history |
| zoom transform (px↔world) | `ui/` | but EPS_PICK derivation (px→world formula) lives in `rules/filters.py` |

Rule: `geometry/` + `rules/` + `model/` are tkinter-free and ezdxf-free; `dxf_io/` + `ui/` may import their respective libraries.