"""privacy.emit_reason through the real app, per endpoint (opensrm-1dua R3).

OpenSRM Addendum A1 §4.2 makes nthlayer.reversal.reason Opt-in. The flag is
threaded config -> build_app -> each route -> emit_override, so a dropped
kwarg anywhere on that path would leave every unit test green; these drive
the endpoints themselves. Core receives the reason whatever the flag says.
"""

from __future__ import annotations

import dataclasses
from typing import Any
from unittest.mock import MagicMock

import pytest
from nthlayer_common.api_client import APIResult
from nthlayer_common.telemetry import TelemetryStatus
from starlette.testclient import TestClient

from nthlayer_override_adapter.app import build_app
from nthlayer_override_adapter.config import AdapterConfig

REASON = "Model regression — escalate to senior analyst"
REASON_KEY = "nthlayer.reversal.reason"

_ENTRY: dict[str, object] = {
    "decision_id": "vrd-001",
    "service": "fraud-detect",
    "corrected_action": "escalate",
    "reviewer": "analyst-047",
    "reason": REASON,
    "timestamp": "2026-05-15T12:00:00Z",
}
_JIRA: dict[str, object] = {
    "issue": {
        "customfield_10042": "vrd-001",
        "resolution": {"name": "escalate", "description": REASON},
        "assignee": {"emailAddress": "analyst-047@example.com"},
        "updated": "2026-05-15T12:00:00Z",
    },
}
# (endpoint, request body)
ENDPOINTS = [
    ("/webhook/jira", _JIRA),
    ("/api/v1/overrides", _ENTRY),
    ("/api/v1/overrides/batch", {"overrides": [_ENTRY]}),
]


def _client(config: AdapterConfig, core_payloads: list[dict[str, Any]]) -> TestClient:
    app = build_app(config, telemetry=TelemetryStatus.INSTALLED)
    fake_core = MagicMock()

    async def _apply(verdict_id: str, payload: dict[str, Any]) -> APIResult:
        core_payloads.append(payload)
        return APIResult(ok=True, status_code=200, data={"id": verdict_id}, error=None, detail=None)

    fake_core.apply_override = _apply
    app.state.core_client = fake_core
    return TestClient(app)


@pytest.mark.parametrize("emit_reason", [False, True], ids=["default-off", "opted-in"])
@pytest.mark.parametrize(("path", "body"), ENDPOINTS, ids=[p for p, _ in ENDPOINTS])
def test_reason_on_record_only_when_opted_in_and_always_sent_to_core(
    adapter_config: AdapterConfig,
    reversals,
    path: str,
    body: dict[str, object],
    emit_reason: bool,
) -> None:
    config = dataclasses.replace(adapter_config, emit_reason=emit_reason)
    core_payloads: list[dict[str, Any]] = []

    resp = _client(config, core_payloads).post(path, json=body)

    assert resp.status_code == 201, resp.text
    (event,) = reversals()
    assert (REASON_KEY in event.attributes) is emit_reason
    if emit_reason:
        assert event.attributes[REASON_KEY] == REASON
    assert [p.get("reason") for p in core_payloads] == [REASON]
