from pathlib import Path

import pytest
from nthlayer_common.overrides import OverridePrivacyConfig

from nthlayer_override_adapter.config import ConfigError, load_config

FIXTURES = Path(__file__).parent / "fixtures"


class TestLoadMinimal:
    def test_empty_adapters_is_legal(self) -> None:
        cfg = load_config(FIXTURES / "adapter_config_minimal.yaml")
        assert cfg.adapters == []

    def test_defaults_when_privacy_absent(self, tmp_path: Path) -> None:
        target = tmp_path / "cfg.yaml"
        target.write_text("adapters: []\n")
        cfg = load_config(target)
        assert cfg.privacy.plaintext_reviewer is False
        assert cfg.privacy.exclude_reason is False

    def test_otel_endpoint_optional(self, tmp_path: Path) -> None:
        target = tmp_path / "cfg.yaml"
        target.write_text("adapters: []\n")
        cfg = load_config(target)
        assert cfg.otel_endpoint is None


class TestLoadJira:
    def test_full_jira_adapter_parses(self) -> None:
        cfg = load_config(FIXTURES / "adapter_config_jira.yaml")
        assert len(cfg.adapters) == 1
        jira = cfg.adapters[0]
        assert jira.source == "jira"
        assert jira.webhook_path == "/webhook/jira"
        assert jira.field_mapping["reviewer"] == "issue.assignee.emailAddress"
        assert jira.defaults["source_system"] == "jira"

    def test_privacy_round_trips(self) -> None:
        cfg = load_config(FIXTURES / "adapter_config_jira.yaml")
        assert isinstance(cfg.privacy, OverridePrivacyConfig)
        assert cfg.privacy.plaintext_reviewer is False

    def test_otel_endpoint_round_trips(self) -> None:
        cfg = load_config(FIXTURES / "adapter_config_jira.yaml")
        assert cfg.otel_endpoint == "http://localhost:4317"


class TestValidation:
    def test_missing_source_raises(self, tmp_path: Path) -> None:
        target = tmp_path / "bad.yaml"
        target.write_text(
            "adapters:\n"
            "  - webhook_path: /x\n"
            "    field_mapping: {decision_id: a, corrected_action: b, reviewer: c}\n"
        )
        with pytest.raises(ConfigError, match="source"):
            load_config(target)

    def test_missing_webhook_path_raises(self, tmp_path: Path) -> None:
        target = tmp_path / "bad.yaml"
        target.write_text(
            "adapters:\n"
            "  - source: x\n"
            "    field_mapping: {decision_id: a, corrected_action: b, reviewer: c}\n"
        )
        with pytest.raises(ConfigError, match="webhook_path"):
            load_config(target)

    def test_duplicate_webhook_paths_raise(self, tmp_path: Path) -> None:
        target = tmp_path / "bad.yaml"
        target.write_text(
            "adapters:\n"
            "  - source: a\n"
            "    webhook_path: /webhook/x\n"
            "    field_mapping: {decision_id: i, corrected_action: c, reviewer: r}\n"
            "  - source: b\n"
            "    webhook_path: /webhook/x\n"
            "    field_mapping: {decision_id: i, corrected_action: c, reviewer: r}\n"
        )
        with pytest.raises(ConfigError, match="duplicate webhook_path"):
            load_config(target)

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="not found"):
            load_config(tmp_path / "absent.yaml")


class TestTypeGuards:
    def test_adapters_non_list_raises(self, tmp_path: Path) -> None:
        target = tmp_path / "bad.yaml"
        target.write_text("adapters: not-a-list\n")
        with pytest.raises(ConfigError, match=r"'adapters' must be a list"):
            load_config(target)

    def test_field_mapping_non_dict_raises(self, tmp_path: Path) -> None:
        target = tmp_path / "bad.yaml"
        target.write_text(
            "adapters:\n"
            "  - source: x\n"
            "    webhook_path: /webhook/x\n"
            "    field_mapping: not-a-mapping\n"
        )
        with pytest.raises(ConfigError, match="field_mapping must be a mapping"):
            load_config(target)

    def test_defaults_non_dict_raises(self, tmp_path: Path) -> None:
        target = tmp_path / "bad.yaml"
        target.write_text(
            "adapters:\n"
            "  - source: x\n"
            "    webhook_path: /webhook/x\n"
            "    field_mapping: {decision_id: a, corrected_action: b, reviewer: c}\n"
            "    defaults: not-a-mapping\n"
        )
        with pytest.raises(ConfigError, match="defaults must be a mapping"):
            load_config(target)

    def test_privacy_non_dict_raises(self, tmp_path: Path) -> None:
        target = tmp_path / "bad.yaml"
        target.write_text("adapters: []\nprivacy: not-a-mapping\n")
        with pytest.raises(ConfigError, match=r"'privacy' must be a mapping"):
            load_config(target)

    def test_otel_non_dict_raises(self, tmp_path: Path) -> None:
        target = tmp_path / "bad.yaml"
        target.write_text("adapters: []\notel: not-a-mapping\n")
        with pytest.raises(ConfigError, match=r"'otel' must be a mapping"):
            load_config(target)
