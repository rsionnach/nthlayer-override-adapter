import pytest
from nthlayer_common.overrides import OverridePrivacyConfig
from starlette.applications import Starlette
from starlette.testclient import TestClient

from nthlayer_override_adapter.config import WebhookAdapter
from nthlayer_override_adapter.routes.webhook import register_webhook_routes


@pytest.fixture
def jira_adapter() -> WebhookAdapter:
    return WebhookAdapter(
        source="jira",
        webhook_path="/webhook/jira",
        field_mapping={
            "decision_id": "issue.customfield_10042",
            "corrected_action": "issue.resolution.name",
            "reviewer": "issue.assignee.emailAddress",
            "timestamp": "issue.updated",
            "reason": "issue.resolution.description",
        },
        defaults={"source_system": "jira", "service": "fraud-detect"},
    )


@pytest.fixture
def client(span_exporter, jira_adapter) -> TestClient:
    app = Starlette()
    register_webhook_routes(app, adapters=[jira_adapter], privacy=OverridePrivacyConfig())
    return TestClient(app)


JIRA_PAYLOAD: dict[str, object] = {
    "issue": {
        "customfield_10042": "vrd-001",
        "resolution": {
            "name": "escalate",
            "description": "Model regression — escalate to senior analyst",
        },
        "assignee": {"emailAddress": "analyst-047@example.com"},
        "updated": "2026-05-15T12:00:00Z",
    },
}


class TestJiraWebhook:
    def test_jira_shaped_payload_produces_span(self, client, span_exporter) -> None:
        resp = client.post("/webhook/jira", json=JIRA_PAYLOAD)
        assert resp.status_code == 201
        body = resp.json()
        assert body["decision_id"] == "vrd-001"
        assert body["emitted_to_otel"] is True
        spans = span_exporter.get_finished_spans()
        assert len(spans) == 1
        attrs = spans[0].attributes
        assert attrs["gen_ai.override.decision_id"] == "vrd-001"
        assert attrs["gen_ai.override.service"] == "fraud-detect"
        assert attrs["gen_ai.override.corrected_action"] == "escalate"

    def test_missing_required_path_400(self, client) -> None:
        bad = {"issue": {"customfield_10042": "vrd-002"}}  # no reviewer / corrected_action
        resp = client.post("/webhook/jira", json=bad)
        assert resp.status_code == 400

    def test_unconfigured_path_404(self, client) -> None:
        resp = client.post("/webhook/notexist", json={})
        assert resp.status_code == 404


class TestEmptyAdaptersList:
    def test_no_routes_registered(self, span_exporter) -> None:
        app = Starlette()
        register_webhook_routes(app, adapters=[], privacy=OverridePrivacyConfig())
        client = TestClient(app)
        resp = client.post("/webhook/jira", json={})
        assert resp.status_code == 404
