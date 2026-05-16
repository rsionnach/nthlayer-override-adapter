"""Prometheus self-observability metrics for the override-adapter sidecar.

Mirrors ``nthlayer_common.metrics`` conventions: stable label sets, low
cardinality, scrape-friendly names. Exposed via ``GET /metrics`` in the
Starlette app.
"""
from __future__ import annotations

from prometheus_client import Counter, Histogram

requests_total = Counter(
    "override_requests_total",
    "Override HTTP requests received, by endpoint and outcome.",
    ["endpoint", "status"],
)

emission_total = Counter(
    "override_emission_total",
    "Override events emitted to OTel collector.",
    ["result"],
)

validation_errors_total = Counter(
    "override_validation_errors_total",
    "Input validation failures, by canonical reason.",
    ["reason"],
)

collector_errors_total = Counter(
    "override_collector_errors_total",
    "OTel exporter failures observed by the adapter.",
)

emit_duration_seconds = Histogram(
    "override_emit_duration_seconds",
    "Time from HTTP receipt to OTel span emitted, seconds.",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)
