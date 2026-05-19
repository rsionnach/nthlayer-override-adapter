"""Dynamic webhook routes — one POST endpoint per configured source.

Each configured ``WebhookAdapter`` registers ``POST {webhook_path}``.
The handler runs ``map_webhook_to_override`` with the adapter's field
mapping + defaults, then emits via the shared emission path. Required-
field failures from the mapper surface as 400.
"""
from __future__ import annotations

import json

from nthlayer_common.overrides import (
    OverridePrivacyConfig,
    map_webhook_to_override,
)
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from nthlayer_override_adapter.config import WebhookAdapter
from nthlayer_override_adapter.emission import emit_override
from nthlayer_override_adapter.metrics import (
    requests_total,
    validation_errors_total,
)
from nthlayer_override_adapter.response import accepted_single


def register_webhook_routes(
    app: Starlette,
    *,
    adapters: list[WebhookAdapter],
    privacy: OverridePrivacyConfig,
) -> None:
    """Mount one POST {webhook_path} route per configured adapter."""
    for adapter in adapters:
        app.routes.append(
            Route(
                adapter.webhook_path,
                _make_handler(adapter, privacy=privacy),
                methods=["POST"],
            )
        )


def _make_handler(adapter: WebhookAdapter, *, privacy: OverridePrivacyConfig):
    async def handle(request: Request) -> JSONResponse:
        try:
            payload = await request.json()
        except json.JSONDecodeError as exc:
            return _validation_response(
                endpoint="webhook", reason="malformed_json", detail=str(exc)
            )

        if not isinstance(payload, dict):
            return _validation_response(
                endpoint="webhook",
                reason="invalid_body",
                detail=f"webhook body must be a JSON object, got {type(payload).__name__}",
            )

        try:
            event = map_webhook_to_override(
                payload,
                mapping=adapter.field_mapping,
                defaults=adapter.defaults,
            )
        except ValueError as exc:
            return _validation_response(endpoint="webhook", reason="mapper_error", detail=str(exc))

        emit_override(event, privacy)
        requests_total.labels(endpoint="webhook", status="accepted").inc()
        return JSONResponse(accepted_single(event.decision_id), status_code=201)

    return handle


def _validation_response(*, endpoint: str, reason: str, detail: str) -> JSONResponse:
    validation_errors_total.labels(reason=reason).inc()
    requests_total.labels(endpoint=endpoint, status="rejected").inc()
    return JSONResponse({"detail": detail}, status_code=400)
