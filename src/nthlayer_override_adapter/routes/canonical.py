"""Canonical POST /api/v1/overrides and /api/v1/overrides/batch route handlers."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from nthlayer_common.overrides import OverrideEvent, OverridePrivacyConfig
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from nthlayer_override_adapter.emission import emit_override
from nthlayer_override_adapter.metrics import (
    requests_total,
    validation_errors_total,
)
from nthlayer_override_adapter.response import (
    BatchResult,
    accepted_single,
    build_batch_response,
)


@dataclass(frozen=True)
class _Winner:
    index: int
    event: OverrideEvent


def register_canonical_routes(
    app: Starlette, *, privacy: OverridePrivacyConfig,
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

        emit_override(event, privacy)
        requests_total.labels(endpoint="canonical", status="accepted").inc()
        return JSONResponse(accepted_single(event.decision_id), status_code=201)

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

        result = _process_batch(entries, privacy=privacy)
        requests_total.labels(endpoint="batch", status="accepted").inc()
        return JSONResponse(build_batch_response(result), status_code=200)

    app.routes.append(Route("/api/v1/overrides", post_single, methods=["POST"]))
    app.routes.append(
        Route("/api/v1/overrides/batch", post_batch, methods=["POST"]),
    )


def _process_batch(
    entries: list[Any], *, privacy: OverridePrivacyConfig,
) -> BatchResult:
    """Walk entries in array order. Last-in-array wins on duplicate decision_id.

    Two-pass: first resolve the winning entry per decision_id without
    emitting anything, then emit only the winners. This meets the
    cardinality-match invariant (one emitted span per unique accepted
    decision_id), which a one-pass emit-as-you-go approach would violate
    by emitting N spans for N occurrences of the same id.
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
        emit_override(winner.event, privacy)
        result.accepted.append(decision_id)
        if decision_id in superseded:
            result.duplicates.append(
                {
                    "decision_id": decision_id,
                    "applied_at_index": winner.index,
                    "discarded_indices": sorted(superseded[decision_id]),
                }
            )
    return result


def _event_from_payload(payload: object) -> OverrideEvent:
    if not isinstance(payload, dict):
        raise ValueError(f"override body must be a JSON object, got {type(payload).__name__}")
    kwargs = dict(payload)
    if "timestamp" in kwargs and isinstance(kwargs["timestamp"], str):
        kwargs["timestamp"] = _parse_iso_timestamp(kwargs["timestamp"])
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
