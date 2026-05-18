"""Starlette app factory — wires canonical + webhook routes + health + metrics."""
from __future__ import annotations

from nthlayer_common.metrics import metrics_content_type, render_metrics
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from nthlayer_override_adapter.config import AdapterConfig
from nthlayer_override_adapter.routes.canonical import register_canonical_routes
from nthlayer_override_adapter.routes.webhook import register_webhook_routes


def build_app(config: AdapterConfig) -> Starlette:
    """Construct the Starlette app from a loaded ``AdapterConfig``."""
    app = Starlette()
    app.routes.append(Route("/healthz", _healthz, methods=["GET"]))
    app.routes.append(Route("/metrics", _metrics, methods=["GET"]))
    register_canonical_routes(app, privacy=config.privacy)
    register_webhook_routes(
        app, adapters=config.adapters, privacy=config.privacy,
    )
    return app


async def _healthz(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


async def _metrics(request: Request) -> Response:
    return Response(render_metrics(), media_type=metrics_content_type())
