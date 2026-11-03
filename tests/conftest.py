from collections.abc import Callable, Iterator

import pytest
from nthlayer_common.overrides import OverridePrivacyConfig
from nthlayer_common.telemetry import CapturedEvent, EventCapture, TelemetryStatus, capture_events

from nthlayer_override_adapter.config import AdapterConfig, CoreConfig, WebhookAdapter

REVERSAL = "nthlayer.reversal"


@pytest.fixture(autouse=True)
def event_capture() -> Iterator[EventCapture]:
    """Capture every emit_event for the duration of each test (ruling Q5).

    Autouse, so emit_event never reaches the global provider, and each test
    sees only its own records: a fresh capture per test.
    """
    with capture_events() as cap:
        yield cap


@pytest.fixture
def reversals(event_capture: EventCapture) -> Callable[[], list[CapturedEvent]]:
    """Zero-arg callable: the ``nthlayer.reversal`` records emitted so far."""
    return lambda: event_capture.named(REVERSAL)


@pytest.fixture
def adapter_config() -> AdapterConfig:
    """Minimal valid AdapterConfig for use in C4+ fixtures.

    Provides a core: block so handlers can read adapter_config.core.timeout_seconds.
    Includes a jira webhook adapter at /webhook/jira so the app_with_fake_core
    factory registers the webhook route for C6 tests.
    """
    return AdapterConfig(
        adapters=[
            WebhookAdapter(
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
        ],
        privacy=OverridePrivacyConfig(),
        core=CoreConfig(url="http://localhost:8100", timeout_seconds=5.0),
    )


@pytest.fixture
def app_with_fake_core(adapter_config: AdapterConfig):
    """Returns a factory that builds the adapter app with a stubbed CoreAPIClient.

    Usage: app = app_with_fake_core(fake_status=200)
    (``telemetry`` defaults to INSTALLED, the normal deployed case.)

    Builds the app via build_app, then injects a fake core_client and
    adapter_config onto app.state so the canonical single handler can call
    bind_to_core without a real nthlayer-core instance.
    """
    from unittest.mock import MagicMock

    from nthlayer_common.api_client import APIResult

    from nthlayer_override_adapter.app import build_app

    def _factory(
        fake_status: int = 200,
        telemetry: TelemetryStatus = TelemetryStatus.INSTALLED,
    ):
        app = build_app(adapter_config, telemetry=telemetry)

        fake_client = MagicMock()

        async def _fake_apply(vid, payload):
            return APIResult(
                ok=(fake_status == 200),
                status_code=fake_status,
                data={"id": vid, "status": "overridden"} if fake_status == 200 else None,
                error=None if fake_status == 200 else "err",
                detail=None,
            )

        fake_client.apply_override = _fake_apply
        app.state.core_client = fake_client
        # Ensure adapter_config is reachable from app.state for the handler
        # to read cfg.core.timeout_seconds. Idempotent if build_app already sets it.
        app.state.adapter_config = adapter_config
        return app

    return _factory
