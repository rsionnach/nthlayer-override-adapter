from nthlayer_override_adapter.metrics import (
    collector_errors_total,
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

    def test_collector_errors_unlabelled(self) -> None:
        collector_errors_total.inc()

    def test_emit_duration_is_histogram(self) -> None:
        emit_duration_seconds.observe(0.001)
