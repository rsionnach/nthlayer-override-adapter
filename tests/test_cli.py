from pathlib import Path
from unittest import mock

import pytest
from nthlayer_common.telemetry import TelemetryStatus
from starlette.testclient import TestClient

from nthlayer_override_adapter import cli
from nthlayer_override_adapter.cli import _init_telemetry, build_parser, load_app

# Patched at the use site: cli imports init_telemetry by name.
_INIT = "nthlayer_override_adapter.cli.init_telemetry"


def _write_minimal_config(tmp_path: Path) -> Path:
    p = tmp_path / "cfg.yaml"
    p.write_text("adapters: []\ncore:\n  url: http://core:8000\n")
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
        # Patched so the test never installs a real global LoggerProvider,
        # whatever OTEL_EXPORTER_OTLP_ENDPOINT the environment carries.
        with mock.patch(_INIT, return_value=TelemetryStatus.NO_ENDPOINT):
            app, config = load_app(str(cfg))
        assert app is not None
        assert config is not None
        paths = {r.path for r in app.routes if hasattr(r, "path")}
        assert "/healthz" in paths
        assert "/api/v1/overrides" in paths

    def test_load_app_missing_config_exits(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit):
            load_app(str(tmp_path / "absent.yaml"))


class TestInitTelemetry:
    @pytest.mark.parametrize("endpoint", ["http://collector:4317", None])
    @pytest.mark.parametrize("status", list(TelemetryStatus), ids=lambda s: s.value)
    def test_passes_endpoint_and_service_name_and_returns_status(
        self, endpoint: str | None, status: TelemetryStatus,
    ) -> None:
        with mock.patch(_INIT, return_value=status) as init:
            assert _init_telemetry(endpoint) is status
        init.assert_called_once_with("nthlayer-override-adapter", endpoint=endpoint)
        assert cli.SERVICE_NAME == "nthlayer-override-adapter"


class TestLoadAppUsesTelemetryStatus:
    """load_app initialises telemetry from the config and builds the app
    with the status it returned (ruling Q7)."""

    _BODY = {
        "decision_id": "dec-1", "service": "s",
        "corrected_action": "approve", "reviewer": "h",
    }

    def _post(self, app) -> dict:
        from nthlayer_common.api_client import APIResult

        async def _apply(verdict_id, payload):
            return APIResult(ok=True, status_code=200, data={"id": verdict_id},
                             error=None, detail=None)

        fake_core = mock.MagicMock()
        fake_core.apply_override = _apply
        app.state.core_client = fake_core
        resp = TestClient(app).post("/api/v1/overrides", json=self._BODY)
        assert resp.status_code == 201, resp.text
        return resp.json()["bindings"]["dec-1"]

    def test_config_otel_endpoint_reaches_init_telemetry(self, tmp_path: Path) -> None:
        p = tmp_path / "cfg.yaml"
        p.write_text(
            "adapters: []\ncore:\n  url: http://core:8000\n"
            "otel:\n  endpoint: http://collector:4317\n"
        )
        with mock.patch(_INIT, return_value=TelemetryStatus.NO_ENDPOINT) as init:
            _, cfg = load_app(str(p))
        assert cfg.otel_endpoint == "http://collector:4317"
        init.assert_called_once_with(cli.SERVICE_NAME, endpoint="http://collector:4317")

    @pytest.mark.parametrize(
        ("status", "otel"),
        [(TelemetryStatus.NO_ENDPOINT, "failed"), (TelemetryStatus.INSTALLED, "ok")],
        ids=["no-endpoint", "installed"],
    )
    def test_app_reports_the_status_init_returned(
        self, tmp_path: Path, status: TelemetryStatus, otel: str,
    ) -> None:
        with mock.patch(_INIT, return_value=status):
            app, _ = load_app(str(_write_minimal_config(tmp_path)))
        assert self._post(app) == {"otel": otel, "core": "ok"}
