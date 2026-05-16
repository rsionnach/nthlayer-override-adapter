from datetime import UTC, datetime

from nthlayer_common.overrides import (
    OverrideEvent,
    OverridePrivacyConfig,
    hash_reviewer,
)

from nthlayer_override_adapter.emission import emit_override


def _make_event(**overrides: object) -> OverrideEvent:
    base = {
        "decision_id": "vrd-001",
        "service": "fraud-detect",
        "corrected_action": "escalate",
        "reviewer": "analyst-047",
        "reason": "model regression",
        "confidence_at_decision": 0.71,
        "source_system": "internal-ui",
        "timestamp": datetime(2026, 5, 15, 12, 0, tzinfo=UTC),
    }
    base.update(overrides)
    return OverrideEvent(**base)


class TestEmissionShape:
    def test_emits_one_span_named_gen_ai_override(self, span_exporter) -> None:
        emit_override(_make_event(), OverridePrivacyConfig())
        spans = span_exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "gen_ai.override"

    def test_span_carries_required_attributes(self, span_exporter) -> None:
        emit_override(_make_event(), OverridePrivacyConfig())
        attrs = span_exporter.get_finished_spans()[0].attributes
        assert attrs["gen_ai.override.decision_id"] == "vrd-001"
        assert attrs["gen_ai.override.service"] == "fraud-detect"
        assert attrs["gen_ai.override.corrected_action"] == "escalate"

    def test_span_is_unparented(self, span_exporter) -> None:
        emit_override(_make_event(), OverridePrivacyConfig())
        span = span_exporter.get_finished_spans()[0]
        assert span.parent is None


class TestPrivacy:
    def test_reviewer_hashed_by_default(self, span_exporter) -> None:
        emit_override(_make_event(reviewer="analyst-047"), OverridePrivacyConfig())
        attrs = span_exporter.get_finished_spans()[0].attributes
        assert attrs["gen_ai.override.reviewer"] == hash_reviewer("analyst-047")

    def test_reviewer_plaintext_when_opted_in(self, span_exporter) -> None:
        privacy = OverridePrivacyConfig(plaintext_reviewer=True)
        emit_override(_make_event(reviewer="analyst-047"), privacy)
        attrs = span_exporter.get_finished_spans()[0].attributes
        assert attrs["gen_ai.override.reviewer"] == "analyst-047"

    def test_reason_dropped_when_excluded(self, span_exporter) -> None:
        privacy = OverridePrivacyConfig(exclude_reason=True)
        emit_override(_make_event(reason="sensitive"), privacy)
        attrs = span_exporter.get_finished_spans()[0].attributes
        assert "gen_ai.override.reason" not in attrs


class TestOptionalFields:
    def test_none_fields_dropped(self, span_exporter) -> None:
        emit_override(
            _make_event(reason=None, original_action=None, source_system=None),
            OverridePrivacyConfig(),
        )
        attrs = span_exporter.get_finished_spans()[0].attributes
        assert "gen_ai.override.reason" not in attrs
        assert "gen_ai.override.original_action" not in attrs
        assert "gen_ai.override.source_system" not in attrs
