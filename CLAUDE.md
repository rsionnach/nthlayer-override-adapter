# nthlayer-override-adapter

Standalone HTTP sidecar — accepts override events via canonical JSON, batch JSON, or generic webhook payloads; emits each as one unparented `gen_ai.override` OTel span. Implements `opensrm-jmy.7` (Wave A). Slack adapter (`opensrm-jmy.17`) and verdict-binding OTel consumer in `nthlayer-workers/measure` (`opensrm-jmy.18`) are separate beads.

## Architecture

```
src/nthlayer_override_adapter/
  __init__.py     # Package marker
  config.py       # AdapterConfig + WebhookAdapter dataclasses; load_config() reads YAML; ConfigError raised on missing required fields, duplicate webhook_paths, or non-dict sections (privacy/otel/field_mapping/defaults/adapters list-shape); AdapterConfig.max_batch_size (default 1000, set via YAML batch.max_size; ConfigError on non-int or ≤0)
  metrics.py      # Prometheus counters: requests_total{endpoint, status}, emission_total{result}, validation_errors_total{reason}, collector_errors_total; emit_duration_seconds histogram
  response.py     # BatchResult dataclass + accepted_single / build_batch_response helpers; response shape per design doc § 3 (decision_ids in accepted, indexed rejected/duplicates)
  emission.py     # emit_override(event, privacy) — opens unparented gen_ai.override span via empty otel_context.Context(); applies hash_reviewer (default) / drops reason when exclude_reason; fail-open on exporter errors (logged + counted, never raised)
  app.py          # build_app(config) — Starlette factory; wires /healthz + /metrics + canonical + dynamic webhook routes
  cli.py          # nthlayer-override-adapter serve [--config <path>] [--host <h>] [--port <p>]; argparse-driven; exits SystemExit(2) on config-not-found or invalid YAML; --config falls back to $NTHLAYER_OVERRIDE_ADAPTER_CONFIG env var; calls _init_otel(cfg.otel_endpoint) after build_app() to initialise the OTel SDK (Wave A behaviour); registers atexit hook to force_flush(5000ms) + shutdown TracerProvider on SIGTERM/exit; logs resolved config_path so env-var users see the actual path
  routes/
    canonical.py  # POST /api/v1/overrides + POST /api/v1/overrides/batch (last-in-array-wins on dup decision_id; two-pass _process_batch uses frozen _Winner(index, event) dataclass to compute winners then emits exactly one span per unique accepted decision_id; 413 on batch_too_large; _event_from_payload validates timestamp type — str or tz-aware datetime only, other types → 400)
    webhook.py    # Dynamic POST {webhook_path} per WebhookAdapter; handler runs map_webhook_to_override (from nthlayer-common) + emits via shared emit_override; mapper ValueError → 400
```

## Conventions

- **Privacy at emission**, not consumer: hash_reviewer applied before `OverrideEvent.to_otel_attributes()` so plaintext reviewers never enter the OTel pipeline.
- **Unparented spans**: `gen_ai.override` is emitted with an empty OTel `Context()` — overrides are operator decisions not bound to any service trace. Do not "fix" this to inherit a current trace context.
- **Cardinality-match invariant**: response `accepted` set always equals the set of emitted-span `gen_ai.override.decision_id` values. Tests assert this explicitly in `tests/test_routes_canonical_batch.py::TestCardinalityInvariant`.
- **Fail-open on OTel export errors**: HTTP request still returns 201 even if export is degraded; the OTel SDK retries / buffers. `override_collector_errors_total` increments.
- **No auth in v1.5**: matches `nthlayer-core` posture. File a follow-up bead if a real deployment needs it.
- **Per-endpoint metric labels**: `_validation_response(*, endpoint, reason, detail)` is keyword-only in both `canonical.py` and `webhook.py` so rejection counters are correctly attributed per endpoint.
- **`_Winner` dataclass**: `_process_batch` tracks per-decision winners as a frozen `_Winner(index, event)` dataclass — not a tuple — for clarity and type-safety. Do not revert to a tuple.
- **Batch cap enforcement**: `/api/v1/overrides/batch` returns 413 when `len(entries) > max_batch_size`; increments both `validation_errors_total{reason="batch_too_large"}` and `requests_total{endpoint="batch", status="rejected"}`.
- **Timestamp validation**: `_event_from_payload` accepts ISO 8601 strings (parsed to tz-aware `datetime`) or already-tz-aware `datetime` objects; any other type raises `ValueError` → HTTP 400, not 500.
- **OTel shutdown**: atexit hook in `cli.py` calls `provider.force_flush(timeout_millis=5000)` then `provider.shutdown()` so in-flight spans are flushed on SIGTERM/clean process exit.
- **`BatchResult.errors` reserved**: field exists on the dataclass but is intentionally unpopulated by the adapter; reserved for jmy.18 (verdict-binding OTel consumer in `nthlayer-workers/measure`). Do not populate it here.
- **OTel SDK no-op fallback**: `_init_otel()` resolves the OTLP endpoint from `otel.endpoint` in config, then from `$OTEL_EXPORTER_OTLP_ENDPOINT`. When neither is set the SDK is not initialised — `emission.py` gets the no-op tracer and spans are silently dropped. The adapter logs `otel_sdk_not_initialised` at WARNING so operators know it is running blind.

## Commands

```bash
uv sync --extra dev
uv run pytest -q                   # full suite (70 tests)
uv run ruff check src/ tests/
uv run nthlayer-override-adapter serve --config <path>
# example config at repo root:
cp override-adapter-config.yaml.example override-adapter-config.yaml
```

CI runs `ruff` then `pytest` against Python 3.11, 3.12, and 3.13 (matrix in `.github/workflows/test.yml`). Local dev uses 3.11+.

## Dependencies

- `nthlayer-common>=1.5.0,<2.0.0` — overrides foundation (`OverrideEvent`, `OverridePrivacyConfig`, `map_webhook_to_override`, `hash_reviewer`), `metrics_content_type` / `render_metrics`
- `starlette>=0.40`, `uvicorn>=0.30` — ASGI stack, mirrors core / workers/respond
- `opentelemetry-api>=1.28`, `opentelemetry-sdk>=1.28`, `opentelemetry-exporter-otlp>=1.28` — span emission + OTLP export
- `pyyaml>=6.0` — adapter config loading
- `structlog>=24.1.0` — logging
- `prometheus-client>=0.21` — `/metrics`

Dev: `pytest>=8.2`, `pytest-asyncio>=0.23`, `httpx>=0.27` (Starlette TestClient), `ruff>=0.8`.

## Spec + plan references

- Design spec: `nthlayer/docs/superpowers/specs/2026-05-15-jmy7-override-adapter-sidecar-design.md`
- Implementation plan: `nthlayer/docs/superpowers/plans/2026-05-15-jmy7-override-adapter-sidecar.md`
- Capability spec source: `nthlayer/docs/roadmap/NTHLAYER_MISSING_CAPABILITIES_SPEC.md` § 4
