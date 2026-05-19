from pathlib import Path
from unittest import mock

import pytest

from nthlayer_override_adapter.cli import _init_otel, build_parser, load_app


def _write_minimal_config(tmp_path: Path) -> Path:
    p = tmp_path / "cfg.yaml"
    p.write_text("adapters: []\n")
    return p


class TestArgParse:
    def test_serve_subcommand_defaults(self) -> None:
        parser = build_parser()
        ns = parser.parse_args(["serve"])
        assert ns.command == "serve"
        assert ns.host == "0.0.0.0"  # noqa: S104 — default bind for a sidecar
        assert ns.port == 8090
        assert ns.config is None

    def test_serve_subcommand_overrides(self) -> None:
        parser = build_parser()
        ns = parser.parse_args(
            ["serve", "--host", "127.0.0.1", "--port", "9000", "--config", "/x.yaml"]
        )
        assert ns.host == "127.0.0.1"
        assert ns.port == 9000
        assert ns.config == "/x.yaml"


class TestLoadApp:
    def test_load_app_from_explicit_config(self, tmp_path: Path) -> None:
        cfg = _write_minimal_config(tmp_path)
        app, config = load_app(str(cfg))
        assert app is not None
        assert config is not None
        paths = {r.path for r in app.routes if hasattr(r, "path")}
        assert "/healthz" in paths
        assert "/api/v1/overrides" in paths

    def test_load_app_missing_config_exits(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit):
            load_app(str(tmp_path / "absent.yaml"))


class TestOtelShutdown:
    def test_atexit_hook_registered_when_endpoint_set(self) -> None:
        with mock.patch("nthlayer_override_adapter.cli.atexit.register") as mock_register:
            with mock.patch("nthlayer_override_adapter.cli.OTLPSpanExporter"):
                with mock.patch("nthlayer_override_adapter.cli.trace.set_tracer_provider"):
                    _init_otel("http://localhost:4317")

            # Verify atexit.register was called with our shutdown handler.
            # TracerProvider may also register internal handlers, so check for ours.
            assert mock_register.called
            assert mock_register.call_count >= 1
            # Our shutdown function should be the last registered handler
            # or at least one of them.
            calls = mock_register.call_args_list
            registered_callables = [call[0][0] for call in calls]
            # Find our _shutdown_otel function (it has "_shutdown_otel" in qualname).
            shutdown_fns = [
                fn for fn in registered_callables
                if callable(fn) and getattr(fn, "__qualname__", "").endswith("_shutdown_otel")
            ]
            assert len(shutdown_fns) >= 1, "Expected _shutdown_otel to be registered"
