"""nthlayer-override-adapter — CLI entry."""
from __future__ import annotations

import argparse
import asyncio
import atexit
import os
import sys

import structlog
import uvicorn
from nthlayer_common.telemetry import TelemetryStatus, init_telemetry
from starlette.applications import Starlette

from nthlayer_override_adapter.app import build_app, telemetry_exporting
from nthlayer_override_adapter.config import AdapterConfig, ConfigError, load_config

logger = structlog.get_logger(__name__)

# The OTel service.name, unless OTEL_SERVICE_NAME overrides it.
TELEMETRY_SERVICE_NAME = "nthlayer-override-adapter"


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
    """Load config from path (or env), initialise telemetry, build the app.

    Exits via ``SystemExit`` on config-not-found / config-invalid so
    the process fails loudly at startup rather than serving with an
    incomplete adapter set.

    Telemetry is initialised here, before the app is built, because the app
    needs its status: whether events export decides each response's ``otel``
    binding (ruling Q7). The config is returned too, for callers that log or
    inspect what was loaded.
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
    return build_app(cfg, telemetry=_init_telemetry(cfg.otel_endpoint)), cfg


def _init_telemetry(otel_endpoint: str | None) -> TelemetryStatus:
    """Install nthlayer-common's OTLP log exporter for ``nthlayer.reversal``.

    The endpoint is ``otel.endpoint`` from the config, else
    ``$OTEL_EXPORTER_OTLP_LOGS_ENDPOINT``, else ``$OTEL_EXPORTER_OTLP_ENDPOINT``.
    The provider flushes at exit (nthlayer-common registers the hook). When
    events will not export, log loudly so operators know the adapter is
    running blind: every response will then say ``otel: failed``.
    """
    status = init_telemetry(TELEMETRY_SERVICE_NAME, endpoint=otel_endpoint)
    if telemetry_exporting(status):
        logger.info("otel_initialised", status=status.value)
    else:
        logger.warning(
            "otel_not_exporting",
            status=status.value,
            sdk_disabled=os.environ.get("OTEL_SDK_DISABLED"),
            hint="set otel.endpoint in the adapter config or "
                 "OTEL_EXPORTER_OTLP_ENDPOINT to a collector's OTLP gRPC "
                 "port (4317) to export nthlayer.reversal events",
        )
    return status


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "serve":
        config_path = args.config or os.environ.get("NTHLAYER_OVERRIDE_ADAPTER_CONFIG")
        app, cfg = load_app(args.config)

        # Register atexit hook for CoreAPIClient shutdown.
        def _shutdown_core_client() -> None:
            client = getattr(app.state, "core_client", None)
            if client is None:
                return
            try:
                asyncio.run(client.close())
            except Exception:  # noqa: BLE001 — fail-soft shutdown
                logger.warning("core_client_shutdown_error")

        atexit.register(_shutdown_core_client)

        logger.info(
            "override_adapter_serving",
            host=args.host,
            port=args.port,
            config_path=config_path,
        )
        uvicorn.run(app, host=args.host, port=args.port, log_config=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
