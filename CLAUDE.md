# nthlayer-override-adapter

Standalone HTTP sidecar. Accepts override events (canonical JSON, batch
JSON, or generic webhook payloads), emits each as one unparented
`gen_ai.override` OTel span, and binds each accepted override to the
verdict store via HTTP POST to nthlayer-core.

Implements `opensrm-jmy.7` (Wave A) and `opensrm-jmy.18` (verdict-binding).

## Stack

Python ≥3.11, `uv`-managed. Starlette + Uvicorn ASGI runtime.

## Build / test / lint / run commands

→ See `AGENTS.md`.

## Hard rules (conventions)

These are load-bearing — wrong-side mistakes either leak plaintext PII,
break the cardinality-match invariant, or silently drop spans.

1. **`apply_privacy` is the single privacy boundary (spec §7).**
   Routes call it once to produce a masked event, then pass that same
   masked event to both `emit_override` (OTel) and `bind_to_core`
   (HTTP). Never apply privacy twice. Never apply it inside
   `emit_override`.

2. **`pre_redacted` vs `plaintext_reviewer`.**
   `OverridePrivacyConfig.pre_redacted` is the preferred flag to skip
   hashing; `plaintext_reviewer` is the deprecated alias. Both are
   honoured by `apply_privacy` via
   `trust_wire = privacy.plaintext_reviewer or privacy.pre_redacted`.

3. **Privacy at emission, not consumer.** `hash_reviewer` is applied
   before `OverrideEvent.to_otel_attributes()` so plaintext reviewers
   never enter the OTel pipeline.

4. **Unparented spans.** `gen_ai.override` is emitted with an empty
   OTel `Context()` — overrides are operator decisions, not bound to
   any service trace. Do **not** "fix" this to inherit a current trace
   context.

5. **Cardinality-match invariant.** Response `accepted` set always
   equals the set of emitted-span `gen_ai.override.decision_id`
   values. Pinned by `tests/test_routes_canonical_batch.py::TestCardinalityInvariant`.

6. **Fail-open on OTel export errors.** HTTP request still returns 201
   even if export is degraded; the OTel SDK retries/buffers.
   `override_collector_errors_total` increments. Same posture for
   `bind_to_core` failures (core unreachable, timeout, 4xx): the
   `binding_total{result="failed"}` counter increments and the
   `BindingResult(core="failed")` is reported back, but the HTTP 201
   to the caller is unchanged. `asyncio.wait_for(timeout_seconds)`
   enforces the sidecar's own timeout independently of CoreAPIClient.

7. **`core_client` absent guard.** All three route modules check
   `getattr(request.app.state, "core_client", None)`. When absent
   they log `core_client_absent` at WARNING, increment
   `binding_total{result="skipped", reason="no_client"}`, and skip
   binding. This preserves backward-compat with tests that don't wire
   a core client.

8. **No auth in v1.5.** Matches `nthlayer-core` posture. File a
   follow-up bead if a real deployment needs it; don't add auth
   ad-hoc.

9. **Per-endpoint metric labels.** `_validation_response(*, endpoint,
   reason, detail)` is keyword-only in both `canonical.py` and
   `webhook.py` so rejection counters are correctly attributed per
   endpoint. Do not collapse this to positional args.

10. **`_Winner` is a frozen dataclass, not a tuple.** `_process_batch`
    tracks per-decision winners as `_Winner(index, event)` for
    clarity and type-safety. Do not revert to a tuple.

11. **Batch cap enforcement.** `/api/v1/overrides/batch` returns 413
    when `len(entries) > max_batch_size`; increments both
    `validation_errors_total{reason="batch_too_large"}` and
    `requests_total{endpoint="batch", status="rejected"}`.

12. **Timestamp validation.** `_event_from_payload` accepts ISO 8601
    strings (parsed to tz-aware `datetime`) or already-tz-aware
    `datetime` objects only; any other type raises `ValueError` →
    HTTP 400, not 500.

13. **OTel shutdown.** atexit hook in `cli.py` calls
    `provider.force_flush(timeout_millis=5000)` then
    `provider.shutdown()` so in-flight spans are flushed on SIGTERM
    or clean process exit. Do not remove.

14. **`BatchResult.errors` is reserved.** Field exists on the
    dataclass but is intentionally unpopulated; reserved for future
    error classification. Do not populate it here without a spec
    change.

15. **OTel SDK no-op fallback.** `_init_otel()` resolves the OTLP
    endpoint from `otel.endpoint` in config, then from
    `$OTEL_EXPORTER_OTLP_ENDPOINT`. When neither is set the SDK is
    not initialised — `emission.py` gets the no-op tracer and spans
    are silently dropped. The adapter logs
    `otel_sdk_not_initialised` at WARNING so operators know it is
    running blind.

## Where to find detail

- Source layout, transport dependencies, spec/plan references:
  `docs/architecture.md`.
- nthlayer-common public API the adapter consumes:
  `nthlayer-common/docs/architecture.md`.
- Design spec:
  `nthlayer/docs/superpowers/specs/2026-05-15-jmy7-override-adapter-sidecar-design.md`.
- Beads: `cd opensrm && bd ready --json`.
