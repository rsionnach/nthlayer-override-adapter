"""Response body shapes for the override-adapter HTTP endpoints.

Plain dicts on the wire. Dataclasses internally so the batch builder
can carry typed state through the route handler without touching JSON
until the final return.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BindingResult:
    """Per-decision binding outcome (opensrm-jmy.18).

    otel and core each ∈ {"ok", "failed"}.
    reason is core-specific: present iff core == "failed",
    None when core == "ok". Values match the bounded set in the
    spec: ok | core_unreachable | verdict_not_found |
    validation_error | core_timeout | other.
    """
    otel: str = "ok"
    core: str = "ok"
    reason: str | None = None

    def to_dict(self) -> dict:
        out: dict = {"otel": self.otel, "core": self.core}
        if self.reason is not None and self.core == "failed":
            out["reason"] = self.reason
        return out


@dataclass
class BatchResult:
    """Per-batch accumulator threaded through the batch route handler."""

    accepted: list[str] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    duplicates: list[dict[str, Any]] = field(default_factory=list)
    # Reserved for jmy.18 follow-up; currently always empty.
    errors: list[dict[str, Any]] = field(default_factory=list)


def accepted_single(
    decision_id: str,
    bindings: BindingResult | None = None,
) -> dict[str, Any]:
    """Body for a successful single-override POST.

    Backward-compatible: bindings defaults to None and is omitted from the
    response when not provided (e.g. in tests that don't wire a core client).
    When provided, the bindings key is a mapping from decision_id to the
    serialised BindingResult dict.
    """
    out: dict[str, Any] = {
        "accepted": [decision_id],
        "rejected": [],
        "duplicates": [],
        "errors": [],
    }
    if bindings is not None:
        out["bindings"] = {decision_id: bindings.to_dict()}
    return out


def build_batch_response(
    result: BatchResult,
    bindings: dict[str, BindingResult] | None = None,
) -> dict[str, Any]:
    """Final JSON body for a batch POST. Always populated keys.

    Backward-compatible: if bindings is None (e.g. no core_client wired),
    the 'bindings' key is omitted from the response.
    When provided, bindings is keyed by decision_id (winners only; losers
    of dedup never appear here).
    """
    out: dict[str, Any] = {
        "accepted": list(result.accepted),
        "rejected": list(result.rejected),
        "duplicates": list(result.duplicates),
        "errors": list(result.errors),
    }
    if bindings is not None:
        out["bindings"] = {k: v.to_dict() for k, v in bindings.items()}
    return out
