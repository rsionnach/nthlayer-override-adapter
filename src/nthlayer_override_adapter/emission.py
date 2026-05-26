"""OTel emission for override events — unparented gen_ai.override spans.

Privacy is applied ONCE at the route level (spec § 7): the sidecar is
the single privacy boundary. Routes call ``apply_privacy`` to produce
a masked copy of the event, then pass the masked event to both
``emit_override`` (OTel span) and ``bind_to_core`` (HTTP POST to
core). This ensures the OTel pipeline and core storage always receive
the same redacted payload.

``emit_override`` expects a pre-masked event and does NOT apply any
further privacy transformation.

Rationale for unparented spans: overrides are operator decisions not
bound to any service trace. Treating each as a standalone span
preserves the semantic that 'an override is its own thing'; collectors
route span → metric via spanmetricsconnector following standard OTel
patterns. Do not "fix" this to inherit a trace context.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog
from nthlayer_common.overrides import (
    OverrideEvent,
    OverridePrivacyConfig,
    hash_reviewer,
)
from opentelemetry import context as otel_context
from opentelemetry import trace

from nthlayer_override_adapter.metrics import (
    binding_total,
    collector_errors_total,
    emission_total,
    emit_duration_seconds,
)
from nthlayer_override_adapter.response import BindingResult

logger = structlog.get_logger(__name__)

_SPAN_NAME = "gen_ai.override"
_TRACER_NAME = "nthlayer-override-adapter"


def apply_privacy(
    event: OverrideEvent, privacy: OverridePrivacyConfig,
) -> OverrideEvent:
    """Return a privacy-masked copy of *event*.

    This is the single privacy application point for the sidecar (spec § 7).
    Routes must call this once and pass the returned masked event to both
    ``emit_override`` and ``bind_to_core``.

    Predicate matches ``nthlayer_common.overrides.ingestion._build_override``:
    ``plaintext_reviewer or pre_redacted`` — both flags mean "trust the
    caller's reviewer string; skip hashing". ``plaintext_reviewer`` is the
    deprecated alias; ``pre_redacted`` is the preferred flag per spec § 7.
    """
    trust_wire = privacy.plaintext_reviewer or privacy.pre_redacted
    reviewer = event.reviewer if trust_wire else hash_reviewer(event.reviewer)
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


def emit_override(event: OverrideEvent) -> bool:
    """Emit one unparented ``gen_ai.override`` span for this override.

    Expects a pre-masked event — callers must call ``apply_privacy`` upstream
    and pass the masked result here. This function emits the event's reviewer
    string as-is; it does NOT apply any privacy transformation.

    Exporter failures are logged + counted but do not raise — fail-open
    posture matches the rest of the ecosystem (caller still treats the HTTP
    request as accepted).

    Returns:
        True if the span was emitted successfully, False if the internal
        fail-open caught an exporter exception. Callers use this to populate
        ``BindingResult.otel`` honestly (spec § 5.3, § 10).
    """
    started = time.perf_counter()
    tracer = trace.get_tracer(_TRACER_NAME)
    unparented_context = otel_context.Context()
    try:
        with tracer.start_as_current_span(_SPAN_NAME, context=unparented_context) as span:
            for key, value in event.to_otel_attributes().items():
                span.set_attribute(key, value)
        emission_total.labels(result="emitted").inc()
        return True
    except Exception as exc:  # noqa: BLE001 — fail-open is intentional
        emission_total.labels(result="failed").inc()
        collector_errors_total.inc()
        logger.warning(
            "override_emission_failed",
            decision_id=event.decision_id,
            error=str(exc),
        )
        return False
    finally:
        emit_duration_seconds.observe(time.perf_counter() - started)


_STATUS_TO_REASON: dict[int, str] = {
    200: "ok",
    404: "verdict_not_found",
    # 409 is "conflict" at the HTTP layer (existing override differs OR CAS
    # miss) but the spec § 5.3 bounded reason set has no "conflict". Collapsed
    # to validation_error; structured logs (override_conflicts_with_existing,
    # override_lost_race_to_concurrent_writer) distinguish the cause.
    409: "validation_error",
    422: "validation_error",
    0:   "core_unreachable",
}


async def bind_to_core(
    client: Any,  # nthlayer_common.api_client.CoreAPIClient
    event: OverrideEvent,
    timeout_seconds: float,
) -> BindingResult:
    """Apply the override to core via HTTP POST; map result → BindingResult.

    Wraps the CoreAPIClient call in asyncio.wait_for so the sidecar enforces
    its own timeout regardless of CoreAPIClient's internal retry semantics.
    Always increments nthlayer_override_binding_total.
    """
    payload = event.to_dict()
    try:
        api_result = await asyncio.wait_for(
            client.apply_override(event.decision_id, payload),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        binding_total.labels(result="failed", reason="core_timeout").inc()
        return BindingResult(core="failed", reason="core_timeout")

    if api_result.ok:
        binding_total.labels(result="success", reason="ok").inc()
        return BindingResult(core="ok", reason=None)

    reason = _STATUS_TO_REASON.get(api_result.status_code, "other")
    binding_total.labels(result="failed", reason=reason).inc()
    return BindingResult(core="failed", reason=reason)
