from datetime import UTC, datetime

import pytest
from nthlayer_common.overrides import (
    OverrideEvent,
    OverridePrivacyConfig,
    hash_reviewer,
)
from opentelemetry._logs import SeverityNumber
from opentelemetry.sdk.trace import TracerProvider
from prometheus_client import REGISTRY

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


def _emit(event: OverrideEvent, **kwargs: object) -> bool:
    """emit_override as the deployed app calls it: telemetry exporting."""
    kwargs.setdefault("exporting", True)
    return emit_override(event, **kwargs)


class TestEmissionShape:
    def test_emits_one_log_record_named_nthlayer_reversal(self, reversals, event_capture) -> None:
        privacy = OverridePrivacyConfig()
        _emit(apply_privacy(_make_event(), privacy))
        # Exactly one record overall, and it is the reversal.
        assert [e.name for e in event_capture.events] == ["nthlayer.reversal"]
        assert len(reversals()) == 1

    def test_severity_is_info(self, reversals) -> None:
        _emit(apply_privacy(_make_event(), OverridePrivacyConfig()))
        (event,) = reversals()
        assert event.severity_number == SeverityNumber.INFO.value == 9

    def test_timestamp_is_the_overrides_own_time(self, reversals) -> None:
        # A time clearly not "now", with sub-second precision, so a record
        # stamped at emission (or truncated to seconds) cannot match.
        when = datetime(2026, 1, 2, 3, 4, 5, 678000, tzinfo=UTC)
        _emit(apply_privacy(_make_event(timestamp=when), OverridePrivacyConfig()))
        (event,) = reversals()
        # 2026-01-02T03:04:05.678Z in unix nanoseconds, computed independently.
        assert event.timestamp == 1_767_323_045_678_000_000

    def test_record_carries_required_attributes(self, reversals) -> None:
        privacy = OverridePrivacyConfig()
        _emit(apply_privacy(_make_event(), privacy))
        attrs = reversals()[0].attributes
        # OpenSRM Addendum A1 §4.2's attributes.
        assert attrs["nthlayer.reversal.decision_id"] == "vrd-001"
        assert attrs["nthlayer.reversal.new_value"] == "escalate"
        # A1 §4.2: an override is a human's reversal.
        assert attrs["nthlayer.reversal.type"] == "human_override"
        assert attrs["nthlayer.reversal.actor_type"] == "human"
        assert not [k for k in attrs if k.startswith("gen_ai.")]

    def test_record_carries_the_service_extension(self, reversals) -> None:
        """Not an A1 §4.2 attribute: an implementation extension under the
        same prefix (opensrm-1dua ruling R2), which the count connector in
        docs/upgrading-0.4.md labels by."""
        _emit(apply_privacy(_make_event(), OverridePrivacyConfig()))
        assert reversals()[0].attributes["nthlayer.reversal.service"] == "fraud-detect"

    def test_record_is_unparented_inside_an_active_span(self, event_capture) -> None:
        # A private provider, never set globally: the global TracerProvider
        # can be set only once per process, and this test must not change
        # what any other test sees. Its tracer still makes the span current
        # in the OTel context, which is what the logs SDK stamps a record from.
        tracer = TracerProvider().get_tracer("test-unparented")
        with tracer.start_as_current_span("request") as span:
            assert span.get_span_context().trace_id != 0  # the span is real
            _emit(apply_privacy(_make_event(), OverridePrivacyConfig()))
        # Private read: CapturedEvent does not expose the record's trace
        # context, so read the SDK record through the capture's exporter.
        # Exposing trace_id/span_id on CapturedEvent is a nthlayer-common change.
        (data,) = event_capture._exporter.get_finished_logs()
        assert data.log_record.trace_id == 0
        assert data.log_record.span_id == 0


class TestReturnValueAndMetric:
    """emit_override returns ``exporting`` and counts it (ruling Q7)."""

    @staticmethod
    def _count(result: str) -> float:
        return REGISTRY.get_sample_value(
            "override_emission_total", {"result": result},
        ) or 0.0

    @pytest.mark.parametrize(
        ("exporting", "counted", "not_counted"),
        [(True, "emitted", "failed"), (False, "failed", "emitted")],
        ids=["exporting", "not-exporting"],
    )
    def test_returns_exporting_and_counts_result(
        self, reversals, exporting: bool, counted: str, not_counted: str,
    ) -> None:
        before = {r: self._count(r) for r in ("emitted", "failed")}
        result = emit_override(
            apply_privacy(_make_event(), OverridePrivacyConfig()), exporting=exporting,
        )
        assert result is exporting
        assert self._count(counted) == before[counted] + 1
        assert self._count(not_counted) == before[not_counted]
        # The record is handed to the logs API either way; whether it leaves
        # the process is the provider's business, not emit_override's.
        assert len(reversals()) == 1


class TestPrivacy:
    def test_reviewer_hashed_by_default(self, reversals) -> None:
        privacy = OverridePrivacyConfig()
        _emit(apply_privacy(_make_event(reviewer="analyst-047"), privacy))
        attrs = reversals()[0].attributes
        assert attrs["nthlayer.reversal.actor"] == hash_reviewer("analyst-047")

    def test_reviewer_plaintext_when_opted_in(self, reversals) -> None:
        privacy = OverridePrivacyConfig(plaintext_reviewer=True)
        _emit(apply_privacy(_make_event(reviewer="analyst-047"), privacy))
        attrs = reversals()[0].attributes
        assert attrs["nthlayer.reversal.actor"] == "analyst-047"

    def test_reviewer_plaintext_when_pre_redacted(self, reversals) -> None:
        """pre_redacted=True (preferred per spec § 7) also suppresses hashing."""
        privacy = OverridePrivacyConfig(pre_redacted=True)
        _emit(apply_privacy(_make_event(reviewer="analyst-047"), privacy))
        attrs = reversals()[0].attributes
        assert attrs["nthlayer.reversal.actor"] == "analyst-047"


class TestReasonIsOptIn:
    """A1 §4.2 marks reason Opt-in: off the record unless enabled (ruling R3)."""

    def test_reason_not_on_record_by_default(self, reversals) -> None:
        privacy = OverridePrivacyConfig()
        _emit(apply_privacy(_make_event(reason="model regression"), privacy))
        attrs = reversals()[0].attributes
        assert "nthlayer.reversal.reason" not in attrs

    def test_reason_on_record_when_opted_in(self, reversals) -> None:
        _emit(
            apply_privacy(_make_event(reason="model regression"), OverridePrivacyConfig()),
            emit_reason=True,
        )
        attrs = reversals()[0].attributes
        assert attrs["nthlayer.reversal.reason"] == "model regression"

    def test_exclude_reason_wins_over_opt_in(self, reversals) -> None:
        privacy = OverridePrivacyConfig(exclude_reason=True)
        _emit(apply_privacy(_make_event(reason="sensitive"), privacy), emit_reason=True)
        attrs = reversals()[0].attributes
        assert "nthlayer.reversal.reason" not in attrs


class TestOptionalFields:
    def test_none_fields_dropped(self, reversals) -> None:
        privacy = OverridePrivacyConfig()
        _emit(apply_privacy(
            _make_event(reason=None, original_action=None, source_system=None),
            privacy,
        ), emit_reason=True)
        attrs = reversals()[0].attributes
        assert "nthlayer.reversal.reason" not in attrs
        assert "nthlayer.reversal.original_action" not in attrs
        assert "nthlayer.reversal.source_system" not in attrs


class TestBindToCore:
    """opensrm-jmy.18: bind_to_core maps APIResult → BindingResult."""

    @pytest.mark.asyncio
    async def test_bind_to_core_success_returns_ok(self):
        from nthlayer_common.api_client import APIResult

        from nthlayer_override_adapter.emission import bind_to_core

        class _FakeClient:
            async def apply_override(self, vid, payload):
                return APIResult(
                    ok=True, status_code=200, data={"id": vid}, error=None, detail=None
                )

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
        from nthlayer_common.api_client import APIResult

        from nthlayer_override_adapter.emission import bind_to_core

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
        from nthlayer_common.api_client import APIResult

        from nthlayer_override_adapter.emission import bind_to_core

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
        import asyncio

        from nthlayer_override_adapter.emission import bind_to_core

        class _SlowClient:
            async def apply_override(self, vid, payload):
                await asyncio.sleep(10)  # exceeds 0.05s timeout below

        event = OverrideEvent(decision_id="d", service="s",
                              corrected_action="approve", reviewer="h")
        result = await bind_to_core(_SlowClient(), event, timeout_seconds=0.05)
        assert result.core == "failed"
        assert result.reason == "core_timeout"
