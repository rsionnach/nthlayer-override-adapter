# Upgrading to nthlayer-override-adapter 0.4

0.4.0 emits each override as an OpenTelemetry **log record** instead of a
span (opensrm-a829, part of opensrm-quqo). OpenSRM Addendum A1 §4.0 defines
`nthlayer.reversal` as a log-based event; until now the adapter was the one
emitter that sent it as a span. It is a breaking release because anything
that read the span stops matching. That includes a collector's spanmetrics
connector, a trace query, and a tail-sampling rule.

## What stays the same

- The event name, `nthlayer.reversal`, and every attribute
  (`nthlayer.reversal.decision_id`, `.type`, `.actor_type`, `.actor`,
  `.new_value`, `.service`, and the rest) keep their names and values.
- The event is still unparented: it never joins a request's trace.
- The HTTP API, the request and response shapes, the privacy behaviour and
  core binding are unchanged.

## Migration order

The order matters. Done the other way round, overrides are lost while every
response still says `otel: ok`, because export failures happen after the
response is sent.

1. **Collector first.** Add the count connector and a `logs` pipeline on the
   OTLP receiver (below), next to the existing spanmetrics configuration, and
   reload. A 0.4 adapter sending logs to a receiver with no logs pipeline
   loses every record.
2. **Repoint dashboards, alerts and recording rules** from your spanmetrics
   series for the `nthlayer.reversal` span to `nthlayer_reversals_total`. The
   old series stops at the cutover, so a `rate()` across it shows a gap.
3. **Deploy 0.4 with its config in the same rollout.** Rename
   `privacy.emit_reason_on_span` to `privacy.emit_reason`, and give
   `otel.endpoint` an `http://` scheme if the collector is plaintext. The two
   versions do not share a config: 0.3 ignores `emit_reason`, and 0.4 refuses
   `emit_reason_on_span`.
4. **Remove spanmetrics** for `nthlayer.reversal` once nothing reads it.

## Breaking changes

### The event is a log record

Each accepted override is one OTLP log record:

| field | value |
|---|---|
| `EventName` | `nthlayer.reversal` |
| attributes | the `nthlayer.reversal.*` keys above |
| body | none |
| `SeverityNumber` | 9 (INFO) |
| `Timestamp` | when the override happened (the event's `timestamp`), not when the adapter received it |

A collector pipeline that counted the span with the **spanmetrics**
connector must count the log record instead. The **count** connector does
this. The configuration below is an illustration, not a tested artefact: it
has not been run through `otelcol validate`, so check it against your
Collector's version.

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317

connectors:
  count:
    logs:
      nthlayer.reversals:
        description: Human reversals of NthLayer decisions (nthlayer.reversal).
        conditions:
          - 'event_name == "nthlayer.reversal"'
        attributes:
          - key: nthlayer.reversal.service
          - key: nthlayer.reversal.type

exporters:
  prometheus:
    endpoint: 0.0.0.0:8889

service:
  pipelines:
    logs:
      receivers: [otlp]
      exporters: [count]
    metrics:
      receivers: [count]
      exporters: [prometheus]
```

With its default name translation, the Prometheus exporter publishes
`nthlayer.reversals` as `nthlayer_reversals_total`, labelled by `nthlayer_reversal_service` and
`nthlayer_reversal_type`. The `event_name` path in the condition needs a
Collector whose OTTL log context exposes the record's EventName. On an older
Collector, filter on another attribute every reversal carries instead, for
example `attributes["nthlayer.reversal.type"] == "human_override"`.

Keep the counter's labels to low-cardinality attributes. `.decision_id` and
`.actor` are per-override identifiers, and A1 §4.0 bars identifiers from
low-cardinality uses.

Not covered here: nthlayer-workers' measure module still queries
`gen_ai_overrides_total{service=...}` for the `reversal_rate` judgment SLO.
Aligning that query with this series is tracked separately (opensrm-zo0o).
Until it lands, rename the metric and label in your collector, or record a
Prometheus rule, if measure must read it.

### `privacy.emit_reason_on_span` is now `privacy.emit_reason`

```yaml
privacy:
  emit_reason: true   # was: emit_reason_on_span: true
```

It means what it did before: the override's free-text `reason` goes on the
OTel event only when this is set (A1 §4.2: Opt-in). Core still stores the
reason either way, unless `exclude_reason` is set. The old key is now a
config error, so the adapter refuses to start until you rename it. Silently
ignoring it would drop your opt-in.

### Telemetry is set up by nthlayer-common, over gRPC

The adapter no longer builds its own TracerProvider. It calls
nthlayer-common's `init_telemetry`, which installs a LoggerProvider with an
OTLP **gRPC** log exporter.

- The endpoint is `otel.endpoint` in the config, then
  `$OTEL_EXPORTER_OTLP_LOGS_ENDPOINT`, then `$OTEL_EXPORTER_OTLP_ENDPOINT`.
  Point it at the collector's gRPC port (4317). `OTEL_EXPORTER_OTLP_PROTOCOL`
  is not read.
- For a plaintext collector, give the endpoint an `http://` scheme. 0.3
  always connected without TLS; 0.4 follows the OTLP exporter's own rules, so
  a bare `host:4317` can try TLS.
- `OTEL_SERVICE_NAME` still overrides `service.name`
  (default `nthlayer-override-adapter`).

### `otel` in responses reports whether telemetry is exporting

Each binding in a response carries `otel: ok | failed`. In 0.3, `ok` meant
"a span was started". With no endpoint configured the span was silently
dropped, but the response still said `ok`. In 0.4 the value comes from what
telemetry setup reported at startup:

- `ok`: an exporting provider is installed, either the adapter's or one
  already set by `opentelemetry-instrument`.
- `failed`: there is no endpoint, the OTel SDK is missing, or
  `OTEL_SDK_DISABLED=true`. The record is dropped. The adapter also logs
  `otel_not_exporting` at WARNING at startup.

Export errors happen later, on the exporter's background thread, so no
per-request field can report them.

### Buffering and shutdown

Records go through the SDK's batch processor. Its queue holds 2048 records by
default (`OTEL_BLRP_MAX_QUEUE_SIZE`), and records beyond that are dropped
while the response still says `otel: ok`. One batch request emits one record
per accepted override, up to `batch.max_size` (default 1000). If you raise
`max_size`, or send large batches faster than the collector accepts them,
raise the queue size to match.

Buffered records are flushed at exit. With the collector unreachable, the
flush waits up to `OTEL_EXPORTER_OTLP_TIMEOUT` (10s by default). 0.3 capped
its own flush at 5s. Container runtimes usually allow 10s between SIGTERM and
SIGKILL, so lower the timeout or lengthen the stop grace period if you need
the flush to finish.

### Metrics

- `override_emission_total{result}` now counts `failed` when telemetry is
  not exporting, matching the response field. Before, it counted `failed`
  only when starting the span raised, which happened only on a programming
  error.
- `override_collector_errors_total` is removed. It counted exceptions from
  starting a span. The log pipeline never raises at emit time, so the
  counter could only ever read zero.

### Dependencies

`opentelemetry-sdk` and `opentelemetry-exporter-otlp` are no longer direct
dependencies. The SDK and the OTLP gRPC log exporter come from
`nthlayer-common[otel]`, and `opentelemetry-api` stays a direct dependency.
Pin them yourself if you relied on the HTTP exporter that
`opentelemetry-exporter-otlp` pulled in.
