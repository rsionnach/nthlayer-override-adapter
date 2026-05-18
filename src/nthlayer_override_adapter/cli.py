"""nthlayer-override-adapter — CLI entry."""
from __future__ import annotations

import argparse
import os
import sys

import structlog
import uvicorn
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from starlette.applications import Starlette

from nthlayer_override_adapter.app import build_app
from nthlayer_override_adapter.config import AdapterConfig, ConfigError, load_config

logger = structlog.get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nthlayer-override-adapter")
    subs = parser.add_subparsers(dest="command", required=True)

    serve = subs.add_parser("serve", help="run the override-adapter HTTP server")
    serve.add_argument(
        "--config",
        default=None,
        help="path to override-adapter-config.yaml "
             "(default: $NTHLAYER_OVERRIDE_ADAPTER_CONFIG)",
    )
    serve.add_argument("--host", default="0.0.0.0")  # noqa: S104
    serve.add_argument("--port", type=int, default=8090)
    return parser


def load_app(config_path: str | None) -> tuple[Starlette, AdapterConfig]:
    """Load config from path (or env) and build the Starlette app.

    Exits via ``SystemExit`` on config-not-found / config-invalid so
    the process fails loudly at startup rather than serving with an
    incomplete adapter set.

    Returns both the app and the resolved config so the caller can
    initialise OTel before serving.
    """
    resolved = config_path or os.environ.get("NTHLAYER_OVERRIDE_ADAPTER_CONFIG")
    if resolved is None:
        sys.stderr.write(
            "error: --config or $NTHLAYER_OVERRIDE_ADAPTER_CONFIG required\n",
        )
        raise SystemExit(2)
    try:
        cfg = load_config(resolved)
    except ConfigError as exc:
        sys.stderr.write(f"error: {exc}\n")
        raise SystemExit(2) from exc
    return build_app(cfg), cfg


def _init_otel(otel_endpoint: str | None) -> None:
    """Initialise the OTel SDK so emitted spans reach the configured collector.

    Resolves the OTLP endpoint from the explicit ``otel_endpoint`` config
    value first, falling back to ``$OTEL_EXPORTER_OTLP_ENDPOINT``. When
    neither is set, the SDK is not initialised — ``trace.get_tracer()``
    in emission.py returns the no-op tracer and spans are silently dropped.
    Log loudly so operators know the adapter is running blind.
    """
    endpoint = otel_endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        logger.warning(
            "otel_sdk_not_initialised",
            reason="no_endpoint_configured",
            hint="set otel.endpoint in the adapter config or "
                 "OTEL_EXPORTER_OTLP_ENDPOINT env var to export spans",
        )
        return

    resource = Resource.create(
        {
            "service.name": os.environ.get(
                "OTEL_SERVICE_NAME", "nthlayer-override-adapter",
            ),
        },
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    logger.info(
        "otel_sdk_initialised",
        endpoint=endpoint,
        service_name=resource.attributes.get("service.name"),
    )


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "serve":
        app, cfg = load_app(args.config)
        # Initialise OTel SDK with the resolved endpoint from config.
        _init_otel(cfg.otel_endpoint)
        logger.info(
            "override_adapter_serving",
            host=args.host,
            port=args.port,
            config=args.config,
        )
        uvicorn.run(app, host=args.host, port=args.port, log_config=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
