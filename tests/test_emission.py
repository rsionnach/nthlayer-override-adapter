import pytest
from datetime import UTC, datetime

from nthlayer_common.overrides import (
    OverrideEvent,
    OverridePrivacyConfig,
    hash_reviewer,
)

from nthlayer_override_adapter.emission import apply_privacy, emit_override


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
        privacy = OverridePrivacyConfig()
        emit_override(apply_privacy(_make_event(), privacy))
        spans = span_exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "gen_ai.override"

    def test_span_carries_required_attributes(self, span_exporter) -> None:
        privacy = OverridePrivacyConfig()
        emit_override(apply_privacy(_make_event(), privacy))
        attrs = span_exporter.get_finished_spans()[0].attributes
        assert attrs["gen_ai.override.decision_id"] == "vrd-001"
        assert attrs["gen_ai.override.service"] == "fraud-detect"
        assert attrs["gen_ai.override.corrected_action"] == "escalate"

    def test_span_is_unparented(self, span_exporter) -> None:
        privacy = OverridePrivacyConfig()
        emit_override(apply_privacy(_make_event(), privacy))
        span = span_exporter.get_finished_spans()[0]
        assert span.parent is None


class TestPrivacy:
    def test_reviewer_hashed_by_default(self, span_exporter) -> None:
        privacy = OverridePrivacyConfig()
        emit_override(apply_privacy(_make_event(reviewer="analyst-047"), privacy))
        attrs = span_exporter.get_finished_spans()[0].attributes
        assert attrs["gen_ai.override.reviewer"] == hash_reviewer("analyst-047")

    def test_reviewer_plaintext_when_opted_in(self, span_exporter) -> None:
        privacy = OverridePrivacyConfig(plaintext_reviewer=True)
        emit_override(apply_privacy(_make_event(reviewer="analyst-047"), privacy))
        attrs = span_exporter.get_finished_spans()[0].attributes
        assert attrs["gen_ai.override.reviewer"] == "analyst-047"

    def test_reviewer_plaintext_when_pre_redacted(self, span_exporter) -> None:
        """pre_redacted=True (preferred per spec § 7) also suppresses hashing."""
        privacy = OverridePrivacyConfig(pre_redacted=True)
        emit_override(apply_privacy(_make_event(reviewer="analyst-047"), privacy))
        attrs = span_exporter.get_finished_spans()[0].attributes
        assert attrs["gen_ai.override.reviewer"] == "analyst-047"

    def test_reason_dropped_when_excluded(self, span_exporter) -> None:
        privacy = OverridePrivacyConfig(exclude_reason=True)
        emit_override(apply_privacy(_make_event(reason="sensitive"), privacy))
        attrs = span_exporter.get_finished_spans()[0].attributes
        assert "gen_ai.override.reason" not in attrs


class TestOptionalFields:
    def test_none_fields_dropped(self, span_exporter) -> None:
        privacy = OverridePrivacyConfig()
        emit_override(apply_privacy(
            _make_event(reason=None, original_action=None, source_system=None),
            privacy,
        ))
        attrs = span_exporter.get_finished_spans()[0].attributes
        assert "gen_ai.override.reason" not in attrs
        assert "gen_ai.override.original_action" not in attrs
        assert "gen_ai.override.source_system" not in attrs


class TestBindToCore:
    """opensrm-jmy.18: bind_to_core maps APIResult → BindingResult."""

    @pytest.mark.asyncio
    async def test_bind_to_core_success_returns_ok(self):
        from nthlayer_override_adapter.emission import bind_to_core
        from nthlayer_common.api_client import APIResult

        class _FakeClient:
            async def apply_override(self, vid, payload):
                return APIResult(ok=True, status_code=200, data={"id": vid}, error=None, detail=None)

        event = OverrideEvent(
            decision_id="dec-1", service="s", corrected_action="approve",
            reviewer="h",
        )
        result = await bind_to_core(_FakeClient(), event, timeout_seconds=5.0)
        assert result.core == "ok"
        assert result.reason is None  # spec § 5.3: reason absent when core == "ok"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status,expected_reason", [
        (404, "verdict_not_found"),
        (409, "validation_error"),
        (422, "validation_error"),
        (500, "other"),
        (503, "other"),  # opensrm-jmy.18 edge-case: unmapped status falls through to "other"
    ])
    async def test_bind_to_core_status_mapping(self, status, expected_reason):
        from nthlayer_override_adapter.emission import bind_to_core
        from nthlayer_common.api_client import APIResult

        class _FakeClient:
            async def apply_override(self, vid, payload):
                return APIResult(ok=False, status_code=status, data=None,
                                 error="err", detail=None)

        event = OverrideEvent(decision_id="d", service="s",
                              corrected_action="approve", reviewer="h")
        result = await bind_to_core(_FakeClient(), event, timeout_seconds=5.0)
        assert result.core == "failed"
        assert result.reason == expected_reason

    @pytest.mark.asyncio
    async def test_bind_to_core_connection_failed_returns_core_unreachable(self):
        from nthlayer_override_adapter.emission import bind_to_core
        from nthlayer_common.api_client import APIResult

        class _FakeClient:
            async def apply_override(self, vid, payload):
                return APIResult(ok=False, status_code=0, data=None,
                                 error="connection_failed", detail=None)

        event = OverrideEvent(decision_id="d", service="s",
                              corrected_action="approve", reviewer="h")
        result = await bind_to_core(_FakeClient(), event, timeout_seconds=5.0)
        assert result.core == "failed"
        assert result.reason == "core_unreachable"

    @pytest.mark.asyncio
    async def test_bind_to_core_timeout_returns_core_timeout(self):
        from nthlayer_override_adapter.emission import bind_to_core
        import asyncio

        class _SlowClient:
            async def apply_override(self, vid, payload):
                await asyncio.sleep(10)  # exceeds 0.05s timeout below

        event = OverrideEvent(decision_id="d", service="s",
                              corrected_action="approve", reviewer="h")
        result = await bind_to_core(_SlowClient(), event, timeout_seconds=0.05)
        assert result.core == "failed"
        assert result.reason == "core_timeout"
