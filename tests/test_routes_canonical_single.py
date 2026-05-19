import pytest
from nthlayer_common.overrides import OverridePrivacyConfig
from starlette.applications import Starlette
from starlette.testclient import TestClient

from nthlayer_override_adapter.routes.canonical import register_canonical_routes


@pytest.fixture
def client(span_exporter) -> TestClient:
    app = Starlette()
    register_canonical_routes(app, privacy=OverridePrivacyConfig(), max_batch_size=1000)
    return TestClient(app)


def _valid_body(**overrides: object) -> dict[str, object]:
    base = {
        "decision_id": "vrd-001",
        "service": "fraud-detect",
        "corrected_action": "escalate",
        "reviewer": "analyst-047",
        "reason": "model regression",
        "confidence_at_decision": 0.71,
        "timestamp": "2026-05-15T12:00:00Z",
        "source_system": "internal-ui",
    }
    base.update(overrides)
    return base


class TestSingleOverride:
    def test_happy_path_201(self, client, span_exporter) -> None:
        resp = client.post("/api/v1/overrides", json=_valid_body())
        assert resp.status_code == 201
        assert resp.json() == {"decision_id": "vrd-001", "emitted_to_otel": True}
        assert len(span_exporter.get_finished_spans()) == 1

    def test_cardinality_one_response_one_span(self, client, span_exporter) -> None:
        client.post("/api/v1/overrides", json=_valid_body(decision_id="dec-a"))
        client.post("/api/v1/overrides", json=_valid_body(decision_id="dec-b"))
        assert len(span_exporter.get_finished_spans()) == 2

    def test_missing_required_field_400(self, client) -> None:
        body = _valid_body()
        del body["reviewer"]
        resp = client.post("/api/v1/overrides", json=body)
        assert resp.status_code == 400
        assert "reviewer" in resp.json()["detail"]

    def test_invalid_confidence_400(self, client) -> None:
        resp = client.post(
            "/api/v1/overrides", json=_valid_body(confidence_at_decision=1.5),
        )
        assert resp.status_code == 400
        assert "confidence" in resp.json()["detail"]

    def test_naive_timestamp_400(self, client) -> None:
        resp = client.post(
            "/api/v1/overrides", json=_valid_body(timestamp="2026-05-15T12:00:00"),
        )
        assert resp.status_code == 400
        assert "tz-aware" in resp.json()["detail"] or "timezone" in resp.json()["detail"]

    def test_malformed_json_400(self, client) -> None:
        resp = client.post(
            "/api/v1/overrides",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 400

    def test_non_string_timestamp_400(self, client) -> None:
        resp = client.post(
            "/api/v1/overrides", json=_valid_body(timestamp=12345),
        )
        assert resp.status_code == 400
        assert "timestamp" in resp.json()["detail"]

    def test_list_timestamp_400(self, client) -> None:
        resp = client.post(
            "/api/v1/overrides", json=_valid_body(timestamp=["2026-01-01"]),
        )
        assert resp.status_code == 400
        assert "timestamp" in resp.json()["detail"]
