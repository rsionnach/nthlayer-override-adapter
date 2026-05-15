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
    """Top-level adapter config — adapters, privacy posture, OTel target."""

    adapters: list[WebhookAdapter]
    privacy: OverridePrivacyConfig
    otel_endpoint: str | None = None


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

    adapters = _parse_adapters(raw.get("adapters") or [])
    privacy = _parse_privacy(raw.get("privacy") or {})
    otel_endpoint = (raw.get("otel") or {}).get("endpoint")

    return AdapterConfig(adapters=adapters, privacy=privacy, otel_endpoint=otel_endpoint)


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
        adapters.append(
            WebhookAdapter(
                source=entry["source"],
                webhook_path=path,
                field_mapping=dict(entry["field_mapping"]),
                defaults=dict(entry.get("defaults") or {}),
            )
        )
    return adapters


def _parse_privacy(raw_privacy: dict[str, Any]) -> OverridePrivacyConfig:
    return OverridePrivacyConfig(
        plaintext_reviewer=bool(raw_privacy.get("plaintext_reviewer", False)),
        exclude_reason=bool(raw_privacy.get("exclude_reason", False)),
    )
