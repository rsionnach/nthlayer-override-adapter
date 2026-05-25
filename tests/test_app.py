import pytest
from nthlayer_common.overrides import OverridePrivacyConfig
from starlette.testclient import TestClient

from nthlayer_override_adapter.app import build_app
from nthlayer_override_adapter.config import AdapterConfig, CoreConfig, WebhookAdapter


@pytest.fixture
def adapter_config() -> AdapterConfig:
    return AdapterConfig(
        adapters=[
            WebhookAdapter(
                source="jira",
                webhook_path="/webhook/jira",
                field_mapping={
                    "decision_id": "issue.id",
                    "corrected_action": "issue.action",
                    "reviewer": "issue.who",
                },
                defaults={"service": "fraud-detect"},
            ),
        ],
        privacy=OverridePrivacyConfig(),
        core=CoreConfig(url="http://core:8000"),
    )


@pytest.fixture
def client(span_exporter, adapter_config) -> TestClient:
    return TestClient(build_app(adapter_config))


class TestHealthAndMetrics:
    def test_healthz_returns_200(self, client) -> None:
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_metrics_returns_prometheus_text(self, client) -> None:
        resp = client.get("/metrics")
        assert resp.status_code == 200
        assert "override_requests_total" in resp.text
        assert resp.headers["content-type"].startswith("text/plain")


class TestAllRoutesWired:
    def test_canonical_single_present(self, client) -> None:
        resp = client.post("/api/v1/overrides", json={"bad": "body"})
        # 400 means route exists and reached validation; 404 would mean
        # the route wasn't registered.
        assert resp.status_code == 400

    def test_canonical_batch_present(self, client) -> None:
        resp = client.post("/api/v1/overrides/batch", json={"bad": "body"})
        assert resp.status_code == 400

    def test_webhook_present(self, client) -> None:
        resp = client.post("/webhook/jira", json={"bad": "body"})
        assert resp.status_code == 400


class TestBuildAppCoreClientLifecycle:
    """opensrm-jmy.18 C7: build_app wires CoreAPIClient onto app.state."""

    def test_build_app_attaches_core_client_to_state(self, adapter_config) -> None:
        """build_app instantiates CoreAPIClient and attaches it to app.state."""
        from nthlayer_common.api_client import CoreAPIClient

        from nthlayer_override_adapter.app import build_app

        app = build_app(adapter_config)
        assert app.state.core_client is not None
        assert isinstance(app.state.core_client, CoreAPIClient)
        # adapter_config must also be reachable from state for handlers
        assert app.state.adapter_config is adapter_config

    def test_build_app_core_client_base_url_matches_config(
        self, adapter_config
    ) -> None:
        """CoreAPIClient.base_url reflects adapter_config.core.url."""
        from nthlayer_override_adapter.app import build_app

        app = build_app(adapter_config)
        client = app.state.core_client
        # CoreAPIClient stores base_url directly on the dataclass field;
        # __post_init__ strips a trailing slash, so compare without one.
        expected = adapter_config.core.url.rstrip("/")
        actual = getattr(client, "base_url", None)
        assert actual == expected
