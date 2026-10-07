"""M2.2 brief item 1 — tolerance constants pin (the mutation blind spot:
EPS_COINCIDE 1e-3 -> 5e-3 passed all 114 pre-M2.2 tests; the golden gate
must not PASS under constants drift).

Reads geometry/tolerances.py values and asserts the SPEC §11.2 defaults:
EPS_COINCIDE == 1e-3, EPS_CONSTRUCTION == 1e-9, PICK_PX == 3.
"""
from geometry.tolerances import EPS_COINCIDE, EPS_CONSTRUCTION, PICK_PX


def test_tolerances_pin_eps_coincide():
    assert EPS_COINCIDE == 1e-3, f"EPS_COINCIDE drifted: {EPS_COINCIDE!r} != 1e-3"


def test_tolerances_pin_eps_construction():
    assert EPS_CONSTRUCTION == 1e-9, f"EPS_CONSTRUCTION drifted: {EPS_CONSTRUCTION!r} != 1e-9"


def test_tolerances_pin_pick_px():
    assert PICK_PX == 3.0, f"PICK_PX drifted: {PICK_PX!r} != 3"