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


def _entry(decision_id: str, **overrides: object) -> dict[str, object]:
    base = {
        "decision_id": decision_id,
        "service": "fraud-detect",
        "corrected_action": "escalate",
        "reviewer": "analyst-047",
        "timestamp": "2026-05-15T12:00:00Z",
    }
    base.update(overrides)
    return base


class TestBatchHappyPath:
    def test_scenario_3_one_hundred_overrides_all_accepted(self, client, span_exporter) -> None:
        body = {"overrides": [_entry(f"dec-{i:04d}") for i in range(100)]}
        resp = client.post("/api/v1/overrides/batch", json=body)

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["accepted"]) == 100
        assert data["accepted"][0] == "dec-0000"
        assert data["accepted"][-1] == "dec-0099"
        assert data["rejected"] == []
        assert data["duplicates"] == []
        assert data["errors"] == []
        assert len(span_exporter.get_finished_spans()) == 100


class TestBatchDuplicates:
    def test_scenario_4_last_in_array_wins(self, client, span_exporter) -> None:
        # dec-002 appears at indices 1, 3, and 5 — last wins (idx 5).
        body = {
            "overrides": [
                _entry("dec-001"),                              # 0
                _entry("dec-002", corrected_action="approve"),  # 1 — discarded
                _entry("dec-003"),                              # 2
                _entry("dec-002", corrected_action="reject"),   # 3 — discarded
                _entry("dec-004"),                              # 4
                _entry("dec-002", corrected_action="escalate"), # 5 — applied
            ],
        }
        resp = client.post("/api/v1/overrides/batch", json=body)
        data = resp.json()

        assert set(data["accepted"]) == {"dec-001", "dec-002", "dec-003", "dec-004"}
        assert data["duplicates"] == [
            {"decision_id": "dec-002", "applied_at_index": 5, "discarded_indices": [1, 3]}
        ]
        # Cardinality: 4 unique accepted decision_ids → 4 spans, NOT 6.
        spans = span_exporter.get_finished_spans()
        assert len(spans) == 4
        # The dec-002 span carries the LAST corrected_action ("escalate").
        dec_002 = [s for s in spans if s.attributes["gen_ai.override.decision_id"] == "dec-002"]
        assert len(dec_002) == 1
        assert dec_002[0].attributes["gen_ai.override.corrected_action"] == "escalate"


class TestBatchRejected:
    def test_invalid_entry_recorded_other_entries_accepted(self, client, span_exporter) -> None:
        bad = _entry("dec-002")
        del bad["reviewer"]
        body = {"overrides": [_entry("dec-001"), bad, _entry("dec-003")]}

        resp = client.post("/api/v1/overrides/batch", json=body)
        data = resp.json()

        assert data["accepted"] == ["dec-001", "dec-003"]
        # The reason is the message raised by Python's dataclass __init__ for
        # a missing required keyword argument. Accept any reason that mentions
        # 'reviewer' — exact text varies across Python versions.
        assert len(data["rejected"]) == 1
        assert data["rejected"][0]["index"] == 1
        assert "reviewer" in data["rejected"][0]["reason"]
        assert len(span_exporter.get_finished_spans()) == 2


class TestCardinalityInvariant:
    def test_response_counts_match_emission_cardinality(self, client, span_exporter) -> None:
        body = {
            "overrides": [
                _entry("dec-a"),                          # 0 — accepted
                _entry("dec-b"),                          # 1 — accepted
                _entry("dec-a", corrected_action="r2"),   # 2 — dup of 0
                _entry("dec-c"),                          # 3 — accepted
            ],
        }
        resp = client.post("/api/v1/overrides/batch", json=body)
        data = resp.json()

        emitted_ids = {
            s.attributes["gen_ai.override.decision_id"]
            for s in span_exporter.get_finished_spans()
        }

        # Response claims about cardinality:
        assert set(data["accepted"]) == emitted_ids
        assert len(span_exporter.get_finished_spans()) == len(data["accepted"])


class TestBatchMalformed:
    def test_top_level_not_a_dict_400(self, client) -> None:
        resp = client.post("/api/v1/overrides/batch", json=[1, 2, 3])
        assert resp.status_code == 400

    def test_overrides_key_missing_400(self, client) -> None:
        resp = client.post("/api/v1/overrides/batch", json={"foo": []})
        assert resp.status_code == 400


class TestBatchSizeCap:
    def test_413_above_cap(self, span_exporter) -> None:
        app = Starlette()
        register_canonical_routes(app, privacy=OverridePrivacyConfig(), max_batch_size=3)
        client = TestClient(app)

        # Post 4 valid entries, cap is 3.
        body = {"overrides": [_entry(f"dec-{i:03d}") for i in range(4)]}
        resp = client.post("/api/v1/overrides/batch", json=body)

        assert resp.status_code == 413
        data = resp.json()
        assert "batch exceeds" in data["detail"]
        assert "4 entries" in data["detail"]
        assert "limit 3" in data["detail"]
        # No spans should be emitted.
        assert len(span_exporter.get_finished_spans()) == 0

    def test_status_rejected_when_all_entries_invalid(self, span_exporter) -> None:
        app = Starlette()
        register_canonical_routes(app, privacy=OverridePrivacyConfig(), max_batch_size=1000)
        client = TestClient(app)

        # Post 2 entries, each missing 'reviewer' (invalid).
        body = {
            "overrides": [
                {
                    "decision_id": "dec-001",
                    "service": "svc",
                    "corrected_action": "act",
                    "timestamp": "2026-05-15T12:00:00Z",
                },
                {
                    "decision_id": "dec-002",
                    "service": "svc",
                    "corrected_action": "act",
                    "timestamp": "2026-05-15T12:00:00Z",
                },
            ]
        }
        resp = client.post("/api/v1/overrides/batch", json=body)

        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted"] == []
        assert len(data["rejected"]) == 2
