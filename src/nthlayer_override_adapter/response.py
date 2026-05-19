"""Response body shapes for the override-adapter HTTP endpoints.

Plain dicts on the wire. Dataclasses internally so the batch builder
can carry typed state through the route handler without touching JSON
until the final return.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BatchResult:
    """Per-batch accumulator threaded through the batch route handler."""

    accepted: list[str] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    duplicates: list[dict[str, Any]] = field(default_factory=list)
    # Reserved for jmy.18 follow-up; currently always empty.
    errors: list[dict[str, Any]] = field(default_factory=list)


def accepted_single(decision_id: str) -> dict[str, Any]:
    """Body for a successful single-override POST."""
    return {"decision_id": decision_id, "emitted_to_otel": True}


def build_batch_response(result: BatchResult) -> dict[str, Any]:
    """Final JSON body for a batch POST. Always populated keys."""
    return {
        "accepted": list(result.accepted),
        "rejected": list(result.rejected),
        "duplicates": list(result.duplicates),
        "errors": list(result.errors),
    }
