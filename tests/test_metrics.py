from nthlayer_override_adapter.metrics import (
    emission_total,
    emit_duration_seconds,
    requests_total,
    validation_errors_total,
)


class TestCounters:
    def test_requests_total_has_endpoint_and_status_labels(self) -> None:
        sample = requests_total.labels(endpoint="canonical", status="accepted")
        sample.inc()  # smoke — exercising the label tuple

    def test_emission_total_has_result_label(self) -> None:
        emission_total.labels(result="emitted").inc()

    def test_validation_errors_has_reason_label(self) -> None:
        validation_errors_total.labels(reason="missing_field").inc()

    def test_emit_duration_is_histogram(self) -> None:
        emit_duration_seconds.observe(0.001)


def test_binding_total_counter_exists_with_bounded_labels():
    """opensrm-jmy.18: nthlayer_override_binding_total{result, reason}."""
    from nthlayer_override_adapter.metrics import binding_total

    binding_total.labels(result="success", reason="ok").inc()
    for reason in ("core_unreachable", "verdict_not_found",
                   "validation_error", "core_timeout", "other"):
        binding_total.labels(result="failed", reason=reason).inc()

    samples = list(binding_total.collect())
    metric_names = {s.name for s in samples}
    assert any("nthlayer_override_binding" in n for n in metric_names)


def test_collector_errors_total_removed():
    """opensrm-a829: emission no longer observes exporter failures, so the
    counter that claimed to count them is gone rather than stuck at zero."""
    from prometheus_client import REGISTRY

    import nthlayer_override_adapter.metrics as metrics_mod

    assert not hasattr(metrics_mod, "collector_errors_total")
    assert REGISTRY.get_sample_value("override_collector_errors_total") is None
