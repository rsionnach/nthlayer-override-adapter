"""Starlette app factory — wires canonical + webhook routes + health + metrics."""
from __future__ import annotations

from nthlayer_common.api_client import CoreAPIClient
from nthlayer_common.metrics import metrics_content_type, render_metrics
from nthlayer_common.telemetry import TelemetryStatus
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from nthlayer_override_adapter.config import AdapterConfig
from nthlayer_override_adapter.routes.canonical import register_canonical_routes
from nthlayer_override_adapter.routes.webhook import register_webhook_routes


def build_app(config: AdapterConfig, *, telemetry: TelemetryStatus) -> Starlette:
    """Construct the Starlette app from a loaded ``AdapterConfig``.

    ``telemetry`` is what ``init_telemetry`` returned at startup. Its
    ``exporting`` decides each response's ``otel`` binding and the
    ``override_emission_total`` result (ruling Q7). Required, so no caller
    can report ``otel: ok`` without having initialised telemetry.
    """
    app = Starlette()
    app.routes.append(Route("/healthz", _healthz, methods=["GET"]))
    app.routes.append(Route("/metrics", _metrics, methods=["GET"]))
    register_canonical_routes(
        app, privacy=config.privacy, max_batch_size=config.max_batch_size,
        exporting=telemetry.exporting, emit_reason=config.emit_reason,
    )
    register_webhook_routes(
        app, adapters=config.adapters, privacy=config.privacy,
        exporting=telemetry.exporting, emit_reason=config.emit_reason,
    )
    app.state.adapter_config = config
    app.state.core_client = CoreAPIClient(base_url=config.core.url)
    return app


async def _healthz(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


async def _metrics(request: Request) -> Response:
    return Response(render_metrics(), media_type=metrics_content_type())
