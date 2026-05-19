"""Adapter configuration — YAML-shaped, dataclass-backed.

Loaded once at process start by ``cli.py``. Hot-reload is intentionally
out of scope for v1.5 (see design doc § 10).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from nthlayer_common.overrides import OverridePrivacyConfig


class ConfigError(ValueError):
    """Adapter configuration is malformed or unreadable."""


@dataclass(frozen=True)
class WebhookAdapter:
    """One configured webhook source — registered as ``POST {webhook_path}``."""

    source: str
    webhook_path: str
    field_mapping: dict[str, str]
    defaults: dict[str, Any] = field(default_factory=dict)


@dataclass
class AdapterConfig:
    """Top-level adapter config — adapters, privacy posture, OTel target, batch limits."""

    adapters: list[WebhookAdapter]
    privacy: OverridePrivacyConfig
    otel_endpoint: str | None = None
    max_batch_size: int = 1000


def load_config(path: str | Path) -> AdapterConfig:
    """Parse a YAML config file into an ``AdapterConfig``.

    Raises ``ConfigError`` on any structural problem — missing required
    fields, duplicate webhook_paths, file-not-found. Empty ``adapters``
    is legal (canonical endpoints still register).
    """
    cfg_path = Path(path)
    if not cfg_path.is_file():
        raise ConfigError(f"config file not found: {cfg_path}")

    try:
        raw = yaml.safe_load(cfg_path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"YAML parse error in {cfg_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"top-level config must be a mapping, got {type(raw).__name__}")

    adapters_raw = raw.get("adapters") or []
    if not isinstance(adapters_raw, list):
        raise ConfigError(
            f"'adapters' must be a list, got {type(adapters_raw).__name__}"
        )
    adapters = _parse_adapters(adapters_raw)
    privacy = _parse_privacy(raw.get("privacy") or {})
    otel_raw = raw.get("otel") or {}
    if not isinstance(otel_raw, dict):
        raise ConfigError(
            f"'otel' must be a mapping, got {type(otel_raw).__name__}"
        )
    otel_endpoint = otel_raw.get("endpoint")
    batch_raw = raw.get("batch") or {}
    if not isinstance(batch_raw, dict):
        raise ConfigError(
            f"'batch' must be a mapping, got {type(batch_raw).__name__}"
        )
    max_batch_size = batch_raw.get("max_size", 1000)
    if not isinstance(max_batch_size, int):
        raise ConfigError(
            f"batch.max_size must be an integer, got {type(max_batch_size).__name__}"
        )
    if max_batch_size <= 0:
        raise ConfigError(
            f"batch.max_size must be positive, got {max_batch_size}"
        )

    return AdapterConfig(
        adapters=adapters,
        privacy=privacy,
        otel_endpoint=otel_endpoint,
        max_batch_size=max_batch_size,
    )


def _parse_adapters(raw_adapters: list[Any]) -> list[WebhookAdapter]:
    seen_paths: set[str] = set()
    adapters: list[WebhookAdapter] = []
    for idx, entry in enumerate(raw_adapters):
        if not isinstance(entry, dict):
            raise ConfigError(f"adapter[{idx}] must be a mapping, got {type(entry).__name__}")
        for required in ("source", "webhook_path", "field_mapping"):
            if required not in entry:
                raise ConfigError(f"adapter[{idx}] missing required field '{required}'")
        path = entry["webhook_path"]
        if path in seen_paths:
            raise ConfigError(f"adapter[{idx}] duplicate webhook_path: {path}")
        seen_paths.add(path)
        field_mapping_raw = entry["field_mapping"]
        if not isinstance(field_mapping_raw, dict):
            raise ConfigError(
                f"adapter[{idx}] field_mapping must be a mapping, "
                f"got {type(field_mapping_raw).__name__}"
            )
        defaults_raw = entry.get("defaults") or {}
        if not isinstance(defaults_raw, dict):
            raise ConfigError(
                f"adapter[{idx}] defaults must be a mapping, "
                f"got {type(defaults_raw).__name__}"
            )
        adapters.append(
            WebhookAdapter(
                source=entry["source"],
                webhook_path=path,
                field_mapping=dict(field_mapping_raw),
                defaults=dict(defaults_raw),
            )
        )
    return adapters


def _parse_privacy(raw_privacy: Any) -> OverridePrivacyConfig:
    if not isinstance(raw_privacy, dict):
        raise ConfigError(
            f"'privacy' must be a mapping, got {type(raw_privacy).__name__}"
        )
    return OverridePrivacyConfig(
        plaintext_reviewer=bool(raw_privacy.get("plaintext_reviewer", False)),
        exclude_reason=bool(raw_privacy.get("exclude_reason", False)),
    )
