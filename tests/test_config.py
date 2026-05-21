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
        target.write_text("adapters: []\ncore:\n  url: http://core:8000\n")
        cfg = load_config(target)
        assert cfg.privacy.plaintext_reviewer is False
        assert cfg.privacy.exclude_reason is False

    def test_otel_endpoint_optional(self, tmp_path: Path) -> None:
        target = tmp_path / "cfg.yaml"
        target.write_text("adapters: []\ncore:\n  url: http://core:8000\n")
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
            "core:\n  url: http://core:8000\n"
            "adapters:\n"
            "  - webhook_path: /x\n"
            "    field_mapping: {decision_id: a, corrected_action: b, reviewer: c}\n"
        )
        with pytest.raises(ConfigError, match="source"):
            load_config(target)

    def test_missing_webhook_path_raises(self, tmp_path: Path) -> None:
        target = tmp_path / "bad.yaml"
        target.write_text(
            "core:\n  url: http://core:8000\n"
            "adapters:\n"
            "  - source: x\n"
            "    field_mapping: {decision_id: a, corrected_action: b, reviewer: c}\n"
        )
        with pytest.raises(ConfigError, match="webhook_path"):
            load_config(target)

    def test_duplicate_webhook_paths_raise(self, tmp_path: Path) -> None:
        target = tmp_path / "bad.yaml"
        target.write_text(
            "core:\n  url: http://core:8000\n"
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
        target.write_text("core:\n  url: http://core:8000\nadapters: not-a-list\n")
        with pytest.raises(ConfigError, match=r"'adapters' must be a list"):
            load_config(target)

    def test_field_mapping_non_dict_raises(self, tmp_path: Path) -> None:
        target = tmp_path / "bad.yaml"
        target.write_text(
            "core:\n  url: http://core:8000\n"
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
            "core:\n  url: http://core:8000\n"
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
        target.write_text(
            "core:\n  url: http://core:8000\nadapters: []\nprivacy: not-a-mapping\n"
        )
        with pytest.raises(ConfigError, match=r"'privacy' must be a mapping"):
            load_config(target)

    def test_otel_non_dict_raises(self, tmp_path: Path) -> None:
        target = tmp_path / "bad.yaml"
        target.write_text(
            "core:\n  url: http://core:8000\nadapters: []\notel: not-a-mapping\n"
        )
        with pytest.raises(ConfigError, match=r"'otel' must be a mapping"):
            load_config(target)

    def test_batch_non_dict_raises(self, tmp_path: Path) -> None:
        target = tmp_path / "bad.yaml"
        target.write_text(
            "core:\n  url: http://core:8000\nadapters: []\nbatch: not-a-mapping\n"
        )
        with pytest.raises(ConfigError, match=r"'batch' must be a mapping"):
            load_config(target)


class TestCoreConfig:
    """opensrm-jmy.18: core: block in adapter config."""

    def test_core_block_parsed(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "cfg.yaml"
        cfg_path.write_text(
            "adapters: []\n"
            "core:\n"
            "  url: http://core:8000\n"
            "  timeout_seconds: 7.5\n"
        )
        cfg = load_config(str(cfg_path))
        assert cfg.core.url == "http://core:8000"
        assert cfg.core.timeout_seconds == 7.5

    def test_core_url_required(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "cfg.yaml"
        cfg_path.write_text("adapters: []\ncore:\n  timeout_seconds: 5.0\n")
        with pytest.raises(ConfigError, match="core.url"):
            load_config(str(cfg_path))

    def test_core_timeout_defaults_to_5(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "cfg.yaml"
        cfg_path.write_text("adapters: []\ncore:\n  url: http://core:8000\n")
        cfg = load_config(str(cfg_path))
        assert cfg.core.timeout_seconds == 5.0

    def test_core_timeout_must_be_positive(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "cfg.yaml"
        cfg_path.write_text(
            "adapters: []\ncore:\n  url: http://core:8000\n  timeout_seconds: 0\n"
        )
        with pytest.raises(ConfigError, match="timeout_seconds"):
            load_config(str(cfg_path))

    def test_core_block_required(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "cfg.yaml"
        cfg_path.write_text("# empty config\n")
        with pytest.raises(ConfigError, match="core"):
            load_config(str(cfg_path))


class TestBatchMaxSize:
    def test_default_when_absent(self, tmp_path: Path) -> None:
        target = tmp_path / "cfg.yaml"
        target.write_text("adapters: []\ncore:\n  url: http://core:8000\n")
        cfg = load_config(target)
        assert cfg.max_batch_size == 1000

    def test_explicit_value_round_trips(self, tmp_path: Path) -> None:
        target = tmp_path / "cfg.yaml"
        target.write_text(
            "adapters: []\ncore:\n  url: http://core:8000\nbatch:\n  max_size: 500\n"
        )
        cfg = load_config(target)
        assert cfg.max_batch_size == 500

    def test_zero_raises(self, tmp_path: Path) -> None:
        target = tmp_path / "cfg.yaml"
        target.write_text(
            "adapters: []\ncore:\n  url: http://core:8000\nbatch:\n  max_size: 0\n"
        )
        with pytest.raises(ConfigError, match="must be positive"):
            load_config(target)

    def test_negative_raises(self, tmp_path: Path) -> None:
        target = tmp_path / "cfg.yaml"
        target.write_text(
            "adapters: []\ncore:\n  url: http://core:8000\nbatch:\n  max_size: -1\n"
        )
        with pytest.raises(ConfigError, match="must be positive"):
            load_config(target)

    def test_non_int_raises(self, tmp_path: Path) -> None:
        target = tmp_path / "cfg.yaml"
        target.write_text(
            "adapters: []\ncore:\n  url: http://core:8000\nbatch:\n  max_size: lots\n"
        )
        with pytest.raises(ConfigError, match="must be an integer"):
            load_config(target)
