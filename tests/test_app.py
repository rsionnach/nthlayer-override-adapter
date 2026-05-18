import pytest
from nthlayer_common.overrides import OverridePrivacyConfig
from starlette.testclient import TestClient

from nthlayer_override_adapter.app import build_app
from nthlayer_override_adapter.config import AdapterConfig, WebhookAdapter


@pytest.fixture
def cfg() -> AdapterConfig:
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
    )


@pytest.fixture
def client(span_exporter, cfg) -> TestClient:
    return TestClient(build_app(cfg))


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
