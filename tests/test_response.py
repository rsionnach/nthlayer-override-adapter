from nthlayer_override_adapter.response import (
    BatchResult,
    accepted_single,
    build_batch_response,
)


class TestSingleResponse:
    def test_accepted_single_shape_no_bindings(self) -> None:
        body = accepted_single("dec_001")
        assert body == {
            "accepted": ["dec_001"],
            "rejected": [],
            "duplicates": [],
            "errors": [],
        }
        assert "bindings" not in body

    def test_accepted_single_shape_with_bindings_ok(self) -> None:
        from nthlayer_override_adapter.response import BindingResult
        br = BindingResult(otel="ok", core="ok", reason=None)
        body = accepted_single("dec_001", bindings=br)
        assert body["accepted"] == ["dec_001"]
        assert body["bindings"] == {"dec_001": {"otel": "ok", "core": "ok"}}
        assert "reason" not in body["bindings"]["dec_001"]

    def test_accepted_single_shape_with_bindings_failed(self) -> None:
        from nthlayer_override_adapter.response import BindingResult
        br = BindingResult(otel="ok", core="failed", reason="verdict_not_found")
        body = accepted_single("dec_001", bindings=br)
        assert body["bindings"]["dec_001"]["core"] == "failed"
        assert body["bindings"]["dec_001"]["reason"] == "verdict_not_found"


class TestBatchResponse:
    def test_all_accepted_no_duplicates(self) -> None:
        result = BatchResult(
            accepted=["dec_001", "dec_002"],
            rejected=[],
            duplicates=[],
            errors=[],
        )
        body = build_batch_response(result)
        assert body == {
            "accepted": ["dec_001", "dec_002"],
            "rejected": [],
            "duplicates": [],
            "errors": [],
        }

    def test_rejected_entries_carry_index_and_reason(self) -> None:
        result = BatchResult(
            accepted=[],
            rejected=[{"index": 3, "reason": "missing field 'reviewer'"}],
            duplicates=[],
            errors=[],
        )
        body = build_batch_response(result)
        assert body["rejected"] == [{"index": 3, "reason": "missing field 'reviewer'"}]

    def test_duplicates_carry_decision_id_and_indices(self) -> None:
        result = BatchResult(
            accepted=["dec_002"],
            rejected=[],
            duplicates=[
                {"decision_id": "dec_002", "applied_at_index": 5, "discarded_indices": [1, 3]}
            ],
            errors=[],
        )
        body = build_batch_response(result)
        dup = body["duplicates"][0]
        assert dup["decision_id"] == "dec_002"
        assert dup["applied_at_index"] == 5
        assert dup["discarded_indices"] == [1, 3]
