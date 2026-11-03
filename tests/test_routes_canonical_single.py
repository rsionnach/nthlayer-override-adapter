import pytest
from nthlayer_common.overrides import OverridePrivacyConfig
from nthlayer_common.telemetry import TelemetryStatus
from starlette.applications import Starlette
from starlette.testclient import TestClient

from nthlayer_override_adapter.routes.canonical import register_canonical_routes


@pytest.fixture
def client() -> TestClient:
    app = Starlette()
    register_canonical_routes(
        app, privacy=OverridePrivacyConfig(), max_batch_size=1000, exporting=True,
    )
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
    def test_happy_path_201(self, client, reversals) -> None:
        resp = client.post("/api/v1/overrides", json=_valid_body())
        assert resp.status_code == 201
        data = resp.json()
        # No core_client on app.state → bindings key absent; otel emission
        # confirmed by the log record.
        assert data["accepted"] == ["vrd-001"]
        assert data["rejected"] == []
        assert "bindings" not in data
        (event,) = reversals()
        assert event.attributes["nthlayer.reversal.decision_id"] == "vrd-001"

    def test_cardinality_one_response_one_record(self, client, reversals) -> None:
        client.post("/api/v1/overrides", json=_valid_body(decision_id="dec-a"))
        client.post("/api/v1/overrides", json=_valid_body(decision_id="dec-b"))
        assert [e.attributes["nthlayer.reversal.decision_id"] for e in reversals()] == [
            "dec-a", "dec-b",
        ]

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


class TestSingleNoCoreClient:
    def test_single_no_core_client_returns_201_without_bindings(self, client):
        """opensrm-jmy.18 edge-case: absent core_client skips binding silently."""
        # client fixture has no core_client on app.state — exercises the absent-guard.
        resp = client.post("/api/v1/overrides", json={
            "decision_id": "dec-no-core",
            "service": "s",
            "corrected_action": "approve",
            "reviewer": "h",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["accepted"] == ["dec-no-core"]
        # No core_client → bindings key must be absent entirely.
        assert "bindings" not in data


class TestCanonicalSingleBindings:
    """opensrm-jmy.18: single-override response carries bindings field."""

    def test_single_success_response_includes_bindings(self, app_with_fake_core) -> None:
        """app_with_fake_core fixture wires a fake CoreAPIClient that returns 200."""
        app = app_with_fake_core(fake_status=200)
        client = TestClient(app)
        body = {
            "decision_id": "dec-1",
            "service": "fraud-detect",
            "corrected_action": "approve",
            "reviewer": "reviewer-hash",
        }
        resp = client.post("/api/v1/overrides", json=body)
        assert resp.status_code == 201
        data = resp.json()
        assert data["accepted"] == ["dec-1"]
        assert data["bindings"]["dec-1"]["otel"] == "ok"
        assert data["bindings"]["dec-1"]["core"] == "ok"
        assert "reason" not in data["bindings"]["dec-1"]  # core==ok → no reason

    def test_single_core_failure_surfaces_in_response(self, app_with_fake_core) -> None:
        app = app_with_fake_core(fake_status=404)
        client = TestClient(app)
        body = {
            "decision_id": "dec-missing",
            "service": "fraud-detect",
            "corrected_action": "approve",
            "reviewer": "reviewer-hash",
        }
        resp = client.post("/api/v1/overrides", json=body)
        assert resp.status_code == 201  # unchanged HTTP status — body is truth
        data = resp.json()
        assert data["accepted"] == ["dec-missing"]
        assert data["bindings"]["dec-missing"]["core"] == "failed"
        assert data["bindings"]["dec-missing"]["reason"] == "verdict_not_found"

    def test_otel_not_exporting_still_reports_to_core(
        self, app_with_fake_core, reversals,
    ) -> None:
        """Spec § 10 OTel-fails-core-still-runs: when telemetry is not
        exporting (no endpoint configured), the response envelope shows
        {"otel": "failed", "core": "ok"}. The HTTP 201 is unchanged —
        fail-open posture is preserved (ruling Q7).
        """
        app = app_with_fake_core(fake_status=200, telemetry=TelemetryStatus.NO_ENDPOINT)
        client = TestClient(app)
        body = {
            "decision_id": "dec-otel-fail",
            "service": "fraud-detect",
            "corrected_action": "approve",
            "reviewer": "reviewer-hash",
        }
        resp = client.post("/api/v1/overrides", json=body)
        assert resp.status_code == 201  # fail-open — HTTP status unchanged
        data = resp.json()
        assert data["accepted"] == ["dec-otel-fail"]
        assert data["bindings"]["dec-otel-fail"]["otel"] == "failed"
        assert data["bindings"]["dec-otel-fail"]["core"] == "ok"
        assert "reason" not in data["bindings"]["dec-otel-fail"]
