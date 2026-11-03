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


def test_the_log_export_stack_is_installed() -> None:
    """What nthlayer-common's init_telemetry imports to export the
    nthlayer.reversal record. Run in the release container, where deps come
    from the built wheel, this fails if the [otel] extra stops reaching it."""
    importlib.import_module("opentelemetry.sdk._logs")
    importlib.import_module("opentelemetry.exporter.otlp.proto.grpc._log_exporter")
