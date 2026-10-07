"""ui/ — thin tkinter shell ONLY: screen<->world transform, events, rendering.

Per AGENTS.md stack map, the UI never computes geometry; picking math lives in
rules/filters.py. ``transform.py`` is deliberately tkinter-free (pure math) so
it is headless-testable by pytest.
"""
