from collections.abc import Iterator

import pytest
from nthlayer_common.overrides import OverridePrivacyConfig
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from nthlayer_override_adapter.config import AdapterConfig, CoreConfig, WebhookAdapter

# Module-level exporter and provider, set once.
_exporter: InMemorySpanExporter | None = None
_provider: TracerProvider | None = None


def _init_otel() -> InMemorySpanExporter:
    """Initialize OTel SDK with in-memory exporter, once per session."""
    global _exporter, _provider
    if _exporter is None:
        _exporter = InMemorySpanExporter()
        _provider = TracerProvider()
        _provider.add_span_processor(SimpleSpanProcessor(_exporter))
        trace.set_tracer_provider(_provider)
    return _exporter


@pytest.fixture(autouse=True)
def _reset_exporter_before_each_test() -> Iterator[None]:
    """Clear the in-memory exporter's span buffer before each test.

    Called automatically before every test. Ensures each test sees only
    its own spans.
    """
    _init_otel()
    if _exporter is not None:
        _exporter.clear()
    yield


@pytest.fixture
def span_exporter() -> InMemorySpanExporter:
    """In-memory exporter for assertion in the current test.

    Wired to a shared TracerProvider. Each test's spans are isolated
    via the autouse _reset_exporter_before_each_test fixture.
    """
    return _init_otel()


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

    Builds the app via build_app, then injects a fake core_client and
    adapter_config onto app.state so the canonical single handler can call
    bind_to_core without a real nthlayer-core instance.
    """
    from unittest.mock import MagicMock

    from nthlayer_common.api_client import APIResult

    from nthlayer_override_adapter.app import build_app

    def _factory(fake_status: int = 200):
        app = build_app(adapter_config)

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
