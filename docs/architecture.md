# nthlayer-override-adapter architecture

Implementation reference: source layout, dependency surface, and spec
trace. The Conventions block in `CLAUDE.md` is canonical for every
hard rule below — this file is the "what lives where" cross-reference.

Implements `opensrm-jmy.7` (Wave A) + `opensrm-jmy.18` (verdict-binding
path). Slack adapter (`opensrm-jmy.17`) is tracked separately.

## Source layout

```
src/nthlayer_override_adapter/
  __init__.py     # Package marker
  config.py       # AdapterConfig + WebhookAdapter + CoreConfig
                  #   - CoreConfig(url, timeout_seconds=5.0)
                  #   - AdapterConfig requires `core: CoreConfig`
                  #   - load_config() reads YAML; mandatory `core: url:`
                  #     block (ConfigError if absent or malformed)
                  #   - ConfigError on missing required fields, duplicate
                  #     webhook_paths, non-dict sections, list-shape
                  #     mismatches
                  #   - AdapterConfig.max_batch_size (default 1000, via
                  #     YAML batch.max_size; ConfigError on non-int/≤0)
  metrics.py      # Prometheus counters and a histogram:
                  #   - requests_total{endpoint, status}
                  #   - emission_total{result}
                  #   - validation_errors_total{reason}
                  #   - collector_errors_total
                  #   - emit_duration_seconds (histogram)
                  #   - binding_total{result, reason}
                  #     (nthlayer_override_binding_total tracks core
                  #     binding attempts — opensrm-jmy.18)
  response.py     # BatchResult dataclass + BindingResult (frozen)
                  #   - BindingResult fields: otel, core, reason
                  #   - reason values: ok | core_unreachable |
                  #     verdict_not_found | validation_error |
                  #     core_timeout | other
                  #   - accepted_single / build_batch_response helpers
                  #   - bindings parameter optional (omitted when None
                  #     for backward-compat with tests that pre-date
                  #     opensrm-jmy.18)
  emission.py     # apply_privacy(event, privacy) -> OverrideEvent
                  #     — single privacy boundary (spec §7); handles
                  #     plaintext_reviewer (deprecated alias) and
                  #     pre_redacted (preferred). Routes call once and
                  #     pass the masked event to both emit_override and
                  #     bind_to_core.
                  # emit_override(event) -> bool
                  #     — expects pre-masked event; opens unparented
                  #     gen_ai.override span via empty
                  #     otel_context.Context(); True on success, False
                  #     on fail-open (logged + counted, never raises)
                  # bind_to_core(client, event, timeout_seconds)
                  #     -> BindingResult (async; wraps
                  #     CoreAPIClient.apply_override in
                  #     asyncio.wait_for; maps HTTP status via
                  #     _STATUS_TO_REASON lookup dict; increments
                  #     binding_total)
  app.py          # build_app(config) — Starlette factory; wires
                  #     /healthz + /metrics + canonical + dynamic
                  #     webhook routes; sets app.state.core_client =
                  #     CoreAPIClient(base_url=config.core.url) and
                  #     app.state.adapter_config = config
                  #     (opensrm-jmy.18 C7)
  cli.py          # nthlayer-override-adapter serve [--config <path>]
                  #     [--host <h>] [--port <p>]
                  # argparse-driven; SystemExit(2) on config-not-found
                  # or invalid YAML; --config falls back to
                  # $NTHLAYER_OVERRIDE_ADAPTER_CONFIG env. Calls
                  # _init_otel(cfg.otel_endpoint) after build_app() to
                  # initialise the OTel SDK (Wave A). atexit hook:
                  # force_flush(5000ms) + shutdown TracerProvider on
                  # SIGTERM/exit. Logs resolved config_path so env-var
                  # users see the actual path.
  routes/
    canonical.py  # POST /api/v1/overrides + /api/v1/overrides/batch
                  # Both call apply_privacy → emit_override →
                  # bind_to_core; reads core_client from app.state
                  # (skips binding + logs core_client_absent warning
                  # when absent). Last-in-array-wins on dup
                  # decision_id. Two-pass _process_batch uses frozen
                  # _Winner(index, event) dataclass to compute winners,
                  # then emits exactly one span per unique accepted
                  # decision_id. 413 on batch_too_large. Batch response
                  # includes bindings key (per winner) when core_client
                  # present. _event_from_payload validates timestamp
                  # type — str or tz-aware datetime only, other types
                  # → 400.
    webhook.py    # Dynamic POST {webhook_path} per WebhookAdapter
                  # Handler runs map_webhook_to_override (from
                  # nthlayer-common) → apply_privacy → emit_override →
                  # bind_to_core. core_client read from app.state
                  # (skips binding + warns when absent). Mapper
                  # ValueError → 400.
```

## Runtime + transport dependencies

- `nthlayer-common>=1.5.0,<2.0.0` — overrides foundation (`OverrideEvent`,
  `OverridePrivacyConfig`, `map_webhook_to_override`, `hash_reviewer`),
  `metrics_content_type` / `render_metrics`.
- `starlette>=0.40`, `uvicorn>=0.30` — ASGI stack; mirrors
  nthlayer-core / nthlayer-workers/respond.
- `opentelemetry-api>=1.28`, `opentelemetry-sdk>=1.28`,
  `opentelemetry-exporter-otlp>=1.28` — span emission + OTLP export.
- `pyyaml>=6.0` — adapter config loading.
- `structlog>=24.1.0` — logging.
- `prometheus-client>=0.21` — `/metrics`.

Dev: `pytest>=8.2`, `pytest-asyncio>=0.23`, `httpx>=0.27` (Starlette
TestClient), `ruff>=0.8`.

`pyproject.toml` is the authoritative source — this file can drift.

## Spec + plan references

- Design spec:
  `nthlayer/docs/superpowers/specs/2026-05-15-jmy7-override-adapter-sidecar-design.md`
- Implementation plan:
  `nthlayer/docs/superpowers/plans/2026-05-15-jmy7-override-adapter-sidecar.md`
- Capability spec source:
  `nthlayer/docs/roadmap/NTHLAYER_MISSING_CAPABILITIES_SPEC.md` §4
