"""ModelState — CONTRACTS §1 (binding), scaffolded per ADR-014(d).

Data container only: no snapshot/undo logic here (Model class is M2/M4 scope).
``primitives`` is the ordered entity list in document order, including
PassThrough entries; ``fold_eids``/``flag_decisions`` start empty at load and
are owned by M5/M4 respectively. ``next_seq`` mints ``n<seq>`` eids for new
entities (starts at 1 after load; all loaded eids are DXF handles).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from geometry.entities import Dogbone, Entity


@dataclass
class ModelState:
    primitives: list[Entity] = field(default_factory=list)
    dogbones: list[Dogbone] = field(default_factory=list)
    fold_eids: set[str] = field(default_factory=set)
    flag_decisions: dict[str, str] = field(default_factory=dict)  # eid -> "keep"|"delete"|"trim" (ADR-009/013)
    next_seq: int = 1
