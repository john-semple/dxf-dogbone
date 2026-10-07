"""Tolerance constants — SPEC §11.2 (single source; raw ``==`` on coordinates is banned).

Every geometric predicate takes an explicit tolerance parameter with a
documented default drawn from here (AGENTS.md hard invariant 2). EPS_PICK is
NOT a constant: it is world-units ~= 3 screen px, derived from the current zoom
by ``rules.filters.eps_pick_from_scale`` (CONTRACTS §5 ownership).
"""
from __future__ import annotations

# Analytic construction (apex, circle centers) — mm.
EPS_CONSTRUCTION: float = 1e-9

# Point/endpoint coincide decisions — mm. DXF rounds to 4 decimals.
EPS_COINCIDE: float = 1e-3

# GUI picking: nominal pick radius in screen pixels before world conversion.
PICK_PX: float = 3.0
