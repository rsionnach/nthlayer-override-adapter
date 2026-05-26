"""Canonical POST /api/v1/overrides and /api/v1/overrides/batch route handlers."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import structlog
from nthlayer_common.overrides import OverrideEvent, OverridePrivacyConfig
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from nthlayer_override_adapter.emission import apply_privacy, bind_to_core, emit_override
from nthlayer_override_adapter.metrics import (
    binding_total,
    requests_total,
    validation_errors_total,
)
from nthlayer_override_adapter.response import (
    BatchResult,
    BindingResult,
    accepted_single,
    build_batch_response,
)

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class _Winner:
    index: int
    event: OverrideEvent


def register_canonical_routes(
    app: Starlette, *, privacy: OverridePrivacyConfig, max_batch_size: int = 1000,
) -> None:
    """Mount /api/v1/overrides and /api/v1/overrides/batch on the app."""

    async def post_single(request: Request) -> JSONResponse:
        try:
            payload = await request.json()
        except json.JSONDecodeError as exc:
            return _validation_response(
                endpoint="canonical", reason="malformed_json", detail=str(exc)
            )

        try:
            event = _event_from_payload(payload)
        except (ValueError, TypeError) as exc:
            return _validation_response(
                endpoint="canonical", reason="invalid_body", detail=str(exc)
            )

        # Spec § 7: apply privacy ONCE at the sidecar boundary.
        # The masked event is passed to both emit_override (OTel) and
        # bind_to_core (HTTP POST) so both sides of the boundary receive
        # identical redacted data. Core trusts pre_redacted=True and stores
        # the reviewer string as-is, so plaintext must never reach core.
        masked = apply_privacy(event, privacy)
        otel_ok = emit_override(masked)
        requests_total.labels(endpoint="canonical", status="accepted").inc()

        # C4 (opensrm-jmy.18): bind to core after OTel emission.
        # core_client and adapter_config are set on app.state by the app
        # factory (C7) or by test fixtures. When core_client is absent
        # (e.g. legacy fixture path) skip binding so existing tests still pass.
        core_client = getattr(request.app.state, "core_client", None)
        if core_client is not None:
            adapter_cfg = request.app.state.adapter_config
            binding = await bind_to_core(
                core_client,
                masked,
                timeout_seconds=adapter_cfg.core.timeout_seconds,
            )
            # Reflect actual OTel status in the response (spec § 5.3).
            binding = BindingResult(
                otel="ok" if otel_ok else "failed",
                core=binding.core,
                reason=binding.reason,
            )
        else:
            logger.warning(
                "core_client_absent",
                endpoint="canonical_single",
                decision_id=event.decision_id,
            )
            binding_total.labels(result="skipped", reason="no_client").inc()
            binding = None

        return JSONResponse(accepted_single(event.decision_id, bindings=binding), status_code=201)

    async def post_batch(request: Request) -> JSONResponse:
        try:
            payload = await request.json()
        except json.JSONDecodeError as exc:
            return _validation_response(endpoint="batch", reason="malformed_json", detail=str(exc))

        if not isinstance(payload, dict) or "overrides" not in payload:
            return _validation_response(
                endpoint="batch",
                reason="invalid_body",
                detail="batch body must be a JSON object with an 'overrides' array",
            )
        entries = payload["overrides"]
        if not isinstance(entries, list):
            return _validation_response(
                endpoint="batch", reason="invalid_body", detail="'overrides' must be an array",
            )

        if len(entries) > max_batch_size:
            validation_errors_total.labels(reason="batch_too_large").inc()
            requests_total.labels(endpoint="batch", status="rejected").inc()
            detail = (
                f"batch exceeds max_batch_size "
                f"({len(entries)} entries, limit {max_batch_size})"
            )
            return JSONResponse(
                {"detail": detail},
                status_code=413,
            )

        winners, result = _process_batch(entries)

        # C5 (opensrm-jmy.18): emit-pass — one span per winner, then bind to core.
        # core_client and adapter_config are set on app.state by the app factory (C7)
        # or by test fixtures. When core_client is absent, skip binding (backward-compat).
        core_client = getattr(request.app.state, "core_client", None)
        if core_client is None:
            logger.warning(
                "core_client_absent",
                endpoint="canonical_batch",
                entry_count=len(entries),
            )
            binding_total.labels(result="skipped", reason="no_client").inc()
            # don't compute timeout — bind_to_core won't be called
        else:
            timeout_seconds = request.app.state.adapter_config.core.timeout_seconds

        bindings: dict[str, BindingResult] = {}
        for decision_id, winner in winners.items():
            # Spec § 7: apply privacy once per winner; pass masked event to
            # both emit_override (OTel) and bind_to_core (HTTP POST to core).
            masked = apply_privacy(winner.event, privacy)
            otel_ok = emit_override(masked)
            result.accepted.append(decision_id)
            if core_client is not None:
                core_binding = await bind_to_core(
                    core_client, masked, timeout_seconds=timeout_seconds,
                )
                # Reflect actual OTel status per winner (spec § 5.3).
                bindings[decision_id] = BindingResult(
                    otel="ok" if otel_ok else "failed",
                    core=core_binding.core,
                    reason=core_binding.reason,
                )

        status = "accepted" if result.accepted else "rejected"
        requests_total.labels(endpoint="batch", status=status).inc()
        return JSONResponse(
            build_batch_response(result, bindings=bindings if core_client is not None else None),
            status_code=201,
        )

    app.routes.append(Route("/api/v1/overrides", post_single, methods=["POST"]))
    app.routes.append(
        Route("/api/v1/overrides/batch", post_batch, methods=["POST"]),
    )


def _process_batch(
    entries: list[Any],
) -> tuple[dict[str, _Winner], BatchResult]:
    """Walk entries in array order. Last-in-array wins on duplicate decision_id.

    Dedup-pass only: resolves the winning entry per decision_id and populates
    rejected/duplicates in BatchResult, but does NOT emit spans or append to
    accepted. The caller (async post_batch) owns the emit-pass so it can
    await bind_to_core per winner.

    Returns (winners, result) where:
      - winners: decision_id → _Winner (the entry that will be emitted)
      - result: BatchResult with rejected and duplicates populated; accepted is empty
    """
    result = BatchResult()
    winners: dict[str, _Winner] = {}
    superseded: dict[str, list[int]] = {}

    for idx, entry in enumerate(entries):
        try:
            event = _event_from_payload(entry)
        except (ValueError, TypeError) as exc:
            result.rejected.append({"index": idx, "reason": str(exc)})
            continue

        prev = winners.get(event.decision_id)
        if prev is not None:
            superseded.setdefault(event.decision_id, []).append(prev.index)
        winners[event.decision_id] = _Winner(index=idx, event=event)

    for decision_id, winner in winners.items():
        if decision_id in superseded:
            result.duplicates.append(
                {
                    "decision_id": decision_id,
                    "applied_at_index": winner.index,
                    "discarded_indices": sorted(superseded[decision_id]),
                }
            )

    return winners, result


def _event_from_payload(payload: object) -> OverrideEvent:
    if not isinstance(payload, dict):
        raise ValueError(f"override body must be a JSON object, got {type(payload).__name__}")
    kwargs = dict(payload)
    if "timestamp" in kwargs:
        ts = kwargs["timestamp"]
        if isinstance(ts, str):
            kwargs["timestamp"] = _parse_iso_timestamp(ts)
        elif isinstance(ts, datetime):
            if ts.tzinfo is None:
                raise ValueError(
                    f"timestamp must be tz-aware; got naive datetime {ts!r}"
                )
        else:
            raise ValueError(
                f"timestamp must be an ISO 8601 string or datetime; got {type(ts).__name__}"
            )
    return OverrideEvent(**kwargs)


def _parse_iso_timestamp(value: str) -> datetime:
    raw = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        raise ValueError(
            f"timestamp must be tz-aware (got naive: {value!r}); "
            "include a 'Z' or '+HH:MM' offset"
        )
    return parsed


def _validation_response(*, endpoint: str, reason: str, detail: str) -> JSONResponse:
    validation_errors_total.labels(reason=reason).inc()
    requests_total.labels(endpoint=endpoint, status="rejected").inc()
    return JSONResponse({"detail": detail}, status_code=400)
