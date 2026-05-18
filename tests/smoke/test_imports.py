"""Smoke test: every public module imports without error.

Mirrors nthlayer_common/tests/smoke/test_imports.py. Catches stale
__all__ entries and broken imports before the wheel reaches PyPI.
"""
from __future__ import annotations

import importlib
import pkgutil

import nthlayer_override_adapter


def test_all_submodules_import() -> None:
    pkg = nthlayer_override_adapter
    for info in pkgutil.walk_packages(pkg.__path__, prefix=f"{pkg.__name__}."):
        mod = importlib.import_module(info.name)
        for name in getattr(mod, "__all__", ()):
            assert getattr(mod, name) is not None, (
                f"{info.name}.{name} declared in __all__ but unresolved"
            )
