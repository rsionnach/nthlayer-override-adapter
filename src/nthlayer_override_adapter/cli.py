"""nthlayer-override-adapter — CLI entry."""
from __future__ import annotations

import argparse
import os
import sys

import structlog
import uvicorn
from starlette.applications import Starlette

from nthlayer_override_adapter.app import build_app
from nthlayer_override_adapter.config import ConfigError, load_config

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


def load_app(config_path: str | None) -> Starlette:
    """Load config from path (or env) and build the Starlette app.

    Exits via ``SystemExit`` on config-not-found / config-invalid so
    the process fails loudly at startup rather than serving with an
    incomplete adapter set.
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
    return build_app(cfg)


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "serve":
        app = load_app(args.config)
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
