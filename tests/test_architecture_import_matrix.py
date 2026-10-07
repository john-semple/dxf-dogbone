"""AGENTS.md hard invariant 1: geometry/, rules/, model/ import neither
tkinter nor ezdxf. Enforced via AST (no false positives from docstrings)."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BANNED = {"ezdxf", "tkinter", "numpy"}


def _imports_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                found.add(node.module.split(".")[0])
    return found


def test_architecture_geometry_rules_model_are_pure():
    offenders = []
    for pkg in ("geometry", "rules", "model"):
        for py in sorted((ROOT / pkg).glob("*.py")):
            bad = _imports_of(py) & BANNED
            if bad:
                offenders.append(f"{py.relative_to(ROOT)}: {sorted(bad)}")
    assert not offenders, f"banned imports found: {offenders}"


def test_architecture_scaffold_modules_import_clean():
    import geometry.entities  # noqa: F401
    import geometry.tolerances  # noqa: F401
    import model.state  # noqa: F401
    import rules.filters  # noqa: F401
