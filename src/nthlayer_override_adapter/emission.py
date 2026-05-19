"""OTel emission for override events — unparented gen_ai.override spans.

Privacy is applied here, at the emission boundary, not at the consumer
side: once the payload reaches the OTel pipeline it's observable
downstream, so reviewer hashing must happen before ``to_otel_attributes``.

Rationale for unparented spans: overrides are operator decisions not
bound to any service trace. Treating each as a standalone span
preserves the semantic that 'an override is its own thing'; collectors
route span → metric via spanmetricsconnector following standard OTel
patterns. Do not "fix" this to inherit a trace context.
"""
from __future__ import annotations

import time

import structlog
from nthlayer_common.overrides import (
    OverrideEvent,
    OverridePrivacyConfig,
    hash_reviewer,
)
from opentelemetry import context as otel_context
from opentelemetry import trace

from nthlayer_override_adapter.metrics import (
    collector_errors_total,
    emission_total,
    emit_duration_seconds,
)

logger = structlog.get_logger(__name__)

_SPAN_NAME = "gen_ai.override"
_TRACER_NAME = "nthlayer-override-adapter"


def emit_override(event: OverrideEvent, privacy: OverridePrivacyConfig) -> None:
    """Emit one unparented ``gen_ai.override`` span for this override.

    Privacy is applied to a shallow copy of the event so the caller's
    instance is not mutated. Exporter failures are logged + counted but
    do not raise — fail-open posture matches the rest of the ecosystem
    (caller still treats the HTTP request as accepted).
    """
    started = time.perf_counter()
    masked = _apply_privacy(event, privacy)
    tracer = trace.get_tracer(_TRACER_NAME)
    unparented_context = otel_context.Context()
    try:
        with tracer.start_as_current_span(_SPAN_NAME, context=unparented_context) as span:
            for key, value in masked.to_otel_attributes().items():
                span.set_attribute(key, value)
        emission_total.labels(result="emitted").inc()
    except Exception as exc:  # noqa: BLE001 — fail-open is intentional
        emission_total.labels(result="failed").inc()
        collector_errors_total.inc()
        logger.warning(
            "override_emission_failed",
            decision_id=event.decision_id,
            error=str(exc),
        )
    finally:
        emit_duration_seconds.observe(time.perf_counter() - started)


def _apply_privacy(
    event: OverrideEvent, privacy: OverridePrivacyConfig,
) -> OverrideEvent:
    reviewer = (
        event.reviewer
        if privacy.plaintext_reviewer
        else hash_reviewer(event.reviewer)
    )
    reason = None if privacy.exclude_reason else event.reason
    return OverrideEvent(
        decision_id=event.decision_id,
        service=event.service,
        corrected_action=event.corrected_action,
        reviewer=reviewer,
        original_action=event.original_action,
        reason=reason,
        confidence_at_decision=event.confidence_at_decision,
        source_system=event.source_system,
        timestamp=event.timestamp,
    )
