# nthlayer-override-adapter

Standalone HTTP sidecar that accepts human-override events and emits them as `gen_ai.override` OTel spans. Part of the [NthLayer](https://github.com/rsionnach/nthlayer) ecosystem; implements [`opensrm-jmy.7`](https://github.com/rsionnach/opensrm) — § 4 of `NTHLAYER_MISSING_CAPABILITIES_SPEC.md`.

## Why

`nthlayer-measure` computes judgment SLOs from override metrics consumed via OTel. Operators reviewing AI decisions live in heterogeneous tools (Slack, Jira, internal review UIs, email). The override-adapter is the translation layer: HTTP in, canonical OTel `gen_ai.override` events out.

## Endpoints

- `POST /api/v1/overrides` — canonical OverrideEvent JSON in.
- `POST /api/v1/overrides/batch` — `{overrides: [...]}` with last-in-array-wins on duplicate `decision_id`.
- `POST /webhook/{source}` — one route per configured adapter; runs a YAML-declared field mapping on the inbound webhook payload.
- `GET /healthz` — liveness probe.
- `GET /metrics` — Prometheus self-observability.

## Run locally

```bash
uv sync --extra dev
uv run nthlayer-override-adapter serve --config override-adapter-config.yaml
```

See `override-adapter-config.yaml.example` for a Jira-shaped adapter declaration.

## Tests

```bash
uv run pytest -q
uv run ruff check src/ tests/
```

## License

Apache 2.0.
