"""Canonical POST /api/v1/overrides and /batch route handlers."""
from __future__ import annotations

import json
from datetime import datetime

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
from nthlayer_override_adapter.response import accepted_single


def register_canonical_routes(
    app: Starlette, *, privacy: OverridePrivacyConfig,
) -> None:
    """Mount /api/v1/overrides on the given Starlette app."""

    async def post_single(request: Request) -> JSONResponse:
        try:
            payload = await request.json()
        except json.JSONDecodeError as exc:
            return _validation_response("malformed_json", str(exc))

        try:
            event = _event_from_payload(payload)
        except (ValueError, TypeError) as exc:
            return _validation_response("invalid_body", str(exc))

        emit_override(event, privacy)
        requests_total.labels(endpoint="canonical", status="accepted").inc()
        return JSONResponse(accepted_single(event.decision_id), status_code=201)

    app.routes.append(Route("/api/v1/overrides", post_single, methods=["POST"]))


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


def _validation_response(reason: str, detail: str) -> JSONResponse:
    validation_errors_total.labels(reason=reason).inc()
    requests_total.labels(endpoint="canonical", status="rejected").inc()
    return JSONResponse({"detail": detail}, status_code=400)
