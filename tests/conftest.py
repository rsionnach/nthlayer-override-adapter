from collections.abc import Iterator

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

# Module-level exporter and provider, set once.
_exporter: InMemorySpanExporter | None = None
_provider: TracerProvider | None = None


def _init_otel() -> InMemorySpanExporter:
    """Initialize OTel SDK with in-memory exporter, once per session."""
    global _exporter, _provider
    if _exporter is None:
        _exporter = InMemorySpanExporter()
        _provider = TracerProvider()
        _provider.add_span_processor(SimpleSpanProcessor(_exporter))
        trace.set_tracer_provider(_provider)
    return _exporter


@pytest.fixture(autouse=True)
def _reset_exporter_before_each_test() -> Iterator[None]:
    """Clear the in-memory exporter's span buffer before each test.

    Called automatically before every test. Ensures each test sees only
    its own spans.
    """
    _init_otel()
    if _exporter is not None:
        _exporter.clear()
    yield


@pytest.fixture
def span_exporter() -> InMemorySpanExporter:
    """In-memory exporter for assertion in the current test.

    Wired to a shared TracerProvider. Each test's spans are isolated
    via the autouse _reset_exporter_before_each_test fixture.
    """
    return _init_otel()
