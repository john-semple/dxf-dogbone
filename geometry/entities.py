"""Core entity dataclasses — CONTRACTS.md §1 (binding; changes need an ADR).

stdlib-only (ADR-008). Every primitive carries an immutable ``eid`` (DXF handle
at load; minted as ``n<seq>`` for new entities; promoted composites as
``promoted-<first member eid>``). Rules reference ``eid``, never object refs or
raw coordinates (ADR-010; AGENTS.md hard invariant 3).

ADR-014 amendments implemented here:
  * ``Seg.members`` / ``Seg.pick_eid`` — the promoted-Seg fields CONTRACTS §2
    requires, in frozen-safe form (tuple instead of list; ``""`` pick_eid
    cannot collide with handle / ``n<seq>`` / ``promoted-*`` eids).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final


@dataclass(frozen=True)
class Pt:
    x: float
    y: float


@dataclass(frozen=True)
class Seg:  # LINE primitive
    eid: str
    a: Pt  # endpoint in world coords
    b: Pt
    # ADR-014: promoted-Seg fields (CONTRACTS §2 note). Empty members ⇒ a plain,
    # non-promoted segment. Non-empty ⇒ this Seg is a promoted composite whose
    # ``eid`` is "promoted-<first member eid>" (ADR-012; re-promotion prefixes
    # the existing composite eid — ADR-012(c)).
    members: tuple[str, ...] = ()
    pick_eid: str = ""


@dataclass(frozen=True)
class Arc:  # ARC primitive (CCW from start_deg to end_deg, degrees)
    eid: str
    center: Pt
    r: float
    start_deg: float
    end_deg: float


@dataclass(frozen=True)
class Circ:
    eid: str
    center: Pt
    r: float


@dataclass(frozen=True)
class PointEnt:  # POINT primitive
    eid: str
    p: Pt


@dataclass(frozen=True)
class TextEnt:  # MTEXT — render as text at insertion point; ignore formatting
    eid: str
    p: Pt
    text: str


Primitive = Seg | Arc | Circ | PointEnt | TextEnt


@dataclass(frozen=True)
class PassThrough:
    """Unsupported entity kept untouched (SPEC §6): eid + raw DXF kind string."""

    eid: str
    kind: str


Entity = Primitive | PassThrough


@dataclass(frozen=True)
class Side:
    """Which bisector construction the ghost-pick selected (CONTRACTS §1).

    ``sign`` is +1 | -1; the engine computes both and tags them; the UI
    forwards the picked Side object. The LEFT_OF_EDGE1_AB /
    RIGHT_OF_EDGE1_AB naming from CONTRACTS §1's Dogbone comment belongs to
    the engine's semantic map (M2) — M1 does not pin numeric meanings.
    """

    sign: int


@dataclass(frozen=True)
class Dogbone:
    db_id: str  # minted per placement
    apex: Pt
    center: Pt
    r: float
    side: Side
    edge1_eid: str
    edge2_eid: str
    arc: Arc  # replacement arc; endpoints == rebuilt edge endpoints


@dataclass(frozen=True)
class Rebuild:  # one edge endpoint moved by a placement (ADR-003; member eids per ADR-012)
    eid: str  # member (or composite) eid whose endpoint moved
    old: Pt
    new: Pt  # == arc endpoint after rebuild


@dataclass(frozen=True)
class Trim:  # endpoint repositioned without deletion (strays, folds, flag-trim)
    eid: str
    old: tuple  # Seg: (Pt, Pt) endpoints; Arc: (start_deg, end_deg) — ADR-015(d)
    new: tuple  # same per-kind semantics as old


@dataclass(frozen=True)
class Flag:  # ADR-009/013: explicit-user-decision entity
    eid: str
    reason: str  # "CIRCLE_IN_WINDOW" | "MTEXT_IN_WINDOW" | "ARC_ENDPOINT_IN" | "CHORD_CROSSER" | "CASCADE_DANGLING"
    options: frozenset  # subset of {"delete","keep","trim"}
    decision: str | None  # None while pending; else "delete"|"keep"|"trim"


@dataclass(frozen=True)
class Refusal:  # ADR-015(a): CONTRACTS §2 references this type but never defined it
    reason: str  # human-readable, ASCII, deterministic formatting


@dataclass
class CornerResult:
    ok: bool
    dogbone: Dogbone | None
    deletions: list[str]  # member eids to delete (promoted edges carry member lists, ADR-012)
    trims: list[Trim]
    rebuilt: list[Rebuild]
    refusals: list[str]  # human-readable refusal reasons
    flags: list[Flag]
    # ADR-016(b): non-blocking warnings; ADR-009 keep-warning carrier
    # (KEPT_CROSSER / KEPT_INTERSECTS / FLAG_DECISION ...)
    warnings: list[str] = field(default_factory=list)


# Flag option vocabulary (ADR-013). Kept adjacent to Flag for M2/M4; the
# frozenset fields carry these exact strings.
FLAG_OPTIONS: Final = frozenset({"delete", "keep", "trim"})


@dataclass
class EditResult:
    """ADR-025: manual-edit result (trim-to-closest / stray-delete).

    ``ok=False`` carries the refusal verbatim in ``reason``; on stray-delete
    ``deletions`` lists the run's entity-level eids; a trim proposes at most
    one Trim whose ``eid`` is the promoted-run eid (Seg (Pt, Pt) semantics).
    """

    ok: bool
    reason: str | None
    deletions: list[str]
    trims: list[Trim]
    warnings: list[str] = field(default_factory=list)
