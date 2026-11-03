"""OTel emission for override events — ``nthlayer.reversal`` log records.

Each override is one OpenTelemetry log record (OpenSRM Addendum A1 §4.0,
opensrm-a829 / opensrm-quqo), emitted through nthlayer-common's
``emit_event``: ``event_name`` ``nthlayer.reversal``, A1 §4.2's
``nthlayer.reversal.*`` attributes, no body, severity INFO, and a Timestamp
of when the override happened (``OverrideEvent.timestamp``; ruling Q2).
Until 0.4.0 it was an unparented span; collectors that counted it with the
spanmetrics connector count the log record with the count connector
instead (docs/upgrading-0.4.md).

Privacy is applied ONCE at the route level (spec § 7): the sidecar is
the single privacy boundary. Routes call ``apply_privacy`` to produce
a masked copy of the event, then pass the masked event to both
``emit_override`` (OTel) and ``bind_to_core`` (HTTP POST to core). This
ensures the OTel pipeline and core storage always receive the same
redacted payload.

Redaction (hashing, ``exclude_reason``) happens only in ``apply_privacy``.
``emit_override`` expects a pre-masked event and applies one OTel-only
filter: it leaves ``reason`` off the record unless ``emit_reason`` is set.
That filter decides what goes to OTel, not what is redacted; core is
unaffected.

The record is never parented to a trace: an override is an operator
decision not bound to any service trace, so it is emitted under an empty
context. Do not "fix" this to inherit the request's trace context. A1 §4.0 then requires §5's
provenance attributes, but §5 (P1) defines them for ``nthlayer.decision``
events only; a reversal's link to its decision is
``nthlayer.reversal.decision_id``, which it always carries.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog
from nthlayer_common.overrides import (
    REVERSAL_EVENT_NAME,
    OverrideEvent,
    OverridePrivacyConfig,
    hash_reviewer,
)
from nthlayer_common.telemetry import emit_event
from opentelemetry import context as otel_context

from nthlayer_override_adapter.metrics import (
    binding_total,
    emission_total,
    emit_duration_seconds,
)
from nthlayer_override_adapter.response import BindingResult

logger = structlog.get_logger(__name__)


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


def emit_override(
    event: OverrideEvent, *, exporting: bool, emit_reason: bool = False,
) -> bool:
    """Emit one ``nthlayer.reversal`` log record for this override.

    ``reason`` is free text, and A1 §4.2 makes it Opt-in: it is left off the
    record unless ``emit_reason`` is set (config ``privacy.emit_reason``;
    ruling R3). This governs OTel only; core still receives the reason
    through ``bind_to_core``. ``exclude_reason`` removes it from both, upstream.

    Expects a pre-masked event — callers must call ``apply_privacy`` upstream
    and pass the masked result here. This function emits the event's reviewer
    string as-is; it does NOT redact (see ``emit_reason`` above).

    ``exporting`` is the ``TelemetryStatus.exporting`` init_telemetry
    returned at startup. Emitting never raises (``emit_event`` is fail-open),
    and an export failure surfaces later, on the batch thread, so the only
    honest per-request signal is whether the record can leave the process at
    all (ruling Q7).

    Returns:
        ``exporting``: True when the record was handed to an exporting
        provider, False when telemetry is off (no endpoint, or the SDK is
        missing) and the record is dropped. Callers use it to populate
        ``BindingResult.otel`` (spec § 5.3, § 10).
    """
    started = time.perf_counter()
    attributes = event.to_otel_attributes()
    if not emit_reason:
        attributes.pop(f"{REVERSAL_EVENT_NAME}.reason", None)
    # Emit under an empty context: the logs SDK stamps a record with the
    # current span's trace and span ids, and an override must not be
    # parented to whatever request trace an instrumented server is in.
    token = otel_context.attach(otel_context.Context())
    try:
        emit_event(REVERSAL_EVENT_NAME, attributes, timestamp=event.timestamp)
    finally:
        otel_context.detach(token)
    emission_total.labels(result="emitted" if exporting else "failed").inc()
    emit_duration_seconds.observe(time.perf_counter() - started)
    return exporting


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
    except TimeoutError:
        binding_total.labels(result="failed", reason="core_timeout").inc()
        return BindingResult(core="failed", reason="core_timeout")

    if api_result.ok:
        binding_total.labels(result="success", reason="ok").inc()
        return BindingResult(core="ok", reason=None)

    reason = _STATUS_TO_REASON.get(api_result.status_code, "other")
    binding_total.labels(result="failed", reason=reason).inc()
    return BindingResult(core="failed", reason=reason)
