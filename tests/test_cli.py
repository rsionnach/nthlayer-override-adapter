from pathlib import Path

import pytest

from nthlayer_override_adapter.cli import build_parser, load_app


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
