import inspect
from pathlib import Path
from unittest.mock import patch

import pytest
import tomli_w

from whotalksitron.config import Config, load_config

_CONFIG_ENV_VARS = [
    "GEMINI_API_KEY",
    "GOOGLE_CLOUD_API_KEY",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_LOCATION",
    "GOOGLE_CLOUD_STORAGE_BUCKET",
    "GOOGLE_GENAI_USE_VERTEXAI",
    "WHOTALKSITRON_BACKEND",
    "WHOTALKSITRON_LOG_LEVEL",
    "WHOTALKSITRON_CONFIG",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in _CONFIG_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_default_config():
    cfg = Config()
    assert cfg.backend == "auto"
    assert cfg.log_level == "info"
    assert cfg.progress is False
    assert cfg.gemini_model == "gemini-2.5-flash"
    assert cfg.pyannote_whisper_model == "large-v3"
    assert cfg.pyannote_device == "auto"
    assert cfg.whisper_endpoint == "http://localhost:1234/v1"
    assert cfg.match_threshold == 0.7
    assert cfg.timestamp_format == "HH:MM:SS"


def test_config_from_dict():
    cfg = Config.from_dict(
        {
            "defaults": {"backend": "gemini", "log_level": "debug"},
            "gemini": {"model": "gemini-2.5-pro"},
            "speakers": {"match_threshold": 0.85},
        }
    )
    assert cfg.backend == "gemini"
    assert cfg.log_level == "debug"
    assert cfg.gemini_model == "gemini-2.5-pro"
    assert cfg.match_threshold == 0.85
    assert cfg.progress is False


def test_config_from_toml_file(tmp_path):
    config_file = tmp_path / "config.toml"
    data = {
        "defaults": {"backend": "pyannote", "progress": True},
        "gemini": {"api_key": "test-key-123"},
    }
    config_file.write_bytes(tomli_w.dumps(data).encode())

    cfg = Config.from_file(config_file)
    assert cfg.backend == "pyannote"
    assert cfg.progress is True
    assert cfg.gemini_api_key == "test-key-123"


def test_config_missing_file_returns_defaults():
    cfg = Config.from_file(Path("/nonexistent/config.toml"))
    assert cfg.backend == "auto"


def test_config_env_override(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "env-key-456")
    monkeypatch.setenv("WHOTALKSITRON_BACKEND", "whisper")
    monkeypatch.setenv("WHOTALKSITRON_LOG_LEVEL", "error")

    cfg = load_config(config_path=None, cli_overrides={})
    assert cfg.gemini_api_key == "env-key-456"
    assert cfg.backend == "whisper"
    assert cfg.log_level == "error"


def test_config_cli_overrides_beat_env(monkeypatch):
    monkeypatch.setenv("WHOTALKSITRON_BACKEND", "whisper")
    cfg = load_config(
        config_path=None,
        cli_overrides={"backend": "gemini"},
    )
    assert cfg.backend == "gemini"


def test_config_full_precedence(tmp_path, monkeypatch):
    config_file = tmp_path / "config.toml"
    data = {"defaults": {"backend": "pyannote", "log_level": "warn"}}
    config_file.write_bytes(tomli_w.dumps(data).encode())

    monkeypatch.setenv("WHOTALKSITRON_BACKEND", "whisper")

    cfg = load_config(
        config_path=config_file,
        cli_overrides={"backend": "gemini"},
    )
    assert cfg.backend == "gemini"  # CLI wins


def test_config_show_masks_secrets():
    cfg = Config()
    cfg.gemini_api_key = "AIzaSyD-abc123-very-secret-key"
    shown = cfg.show()
    assert "AIzaSyD-abc123-very-secret-key" not in shown
    assert "AIza...key" in shown or "****" in shown


def test_config_dir():
    cfg = Config()
    assert cfg.config_dir == Path.home() / ".config" / "whotalksitron"


def test_config_speakers_dir():
    cfg = Config()
    assert cfg.speakers_dir == cfg.config_dir / "speakers"


def test_config_keychain_retrieval(monkeypatch):
    from unittest.mock import MagicMock, patch

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "keychain-api-key-123\n"

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        cfg = load_config(config_path=None, cli_overrides={})

    # Verify security command was called with correct args
    calls = [c for c in mock_run.call_args_list if c[0][0][0] == "security"]
    assert len(calls) >= 1
    assert "find-generic-password" in calls[0][0][0]
    assert cfg.gemini_api_key == "keychain-api-key-123"


def test_config_env_beats_keychain(monkeypatch):
    from unittest.mock import MagicMock, patch

    monkeypatch.setenv("GEMINI_API_KEY", "env-key")

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "keychain-key\n"

    with patch("subprocess.run", return_value=mock_result):
        cfg = load_config(config_path=None, cli_overrides={})

    # Env var should override keychain
    assert cfg.gemini_api_key == "env-key"


_DEFAULT_LOG_FILE = str(Path.home() / ".config" / "whotalksitron" / "whotalksitron.log")


def test_default_config_logging_fields():
    cfg = Config()
    assert cfg.log_file == _DEFAULT_LOG_FILE
    assert cfg.log_file_max_bytes == 10_485_760
    assert cfg.log_file_backup_count == 5


def test_config_from_dict_logging():
    cfg = Config.from_dict(
        {
            "logging": {
                "file": "/tmp/test.log",  # noqa: S108
                "file_max_bytes": 5_000_000,
                "file_backup_count": 3,
            }
        }
    )
    assert cfg.log_file == "/tmp/test.log"  # noqa: S108
    assert cfg.log_file_max_bytes == 5_000_000
    assert cfg.log_file_backup_count == 3


def test_config_logging_tilde_expansion():
    cfg = Config.from_dict({"logging": {"file": "~/custom.log"}})
    assert cfg.log_file == str(Path.home() / "custom.log")


def test_config_logging_empty_disables():
    cfg = Config.from_dict({"logging": {"file": ""}})
    assert cfg.log_file == ""


def test_config_logging_whitespace_disables():
    cfg = Config.from_dict({"logging": {"file": "  "}})
    assert cfg.log_file == ""


def test_config_logging_max_bytes_floor():
    cfg = Config.from_dict({"logging": {"file_max_bytes": 100}})
    assert cfg.log_file_max_bytes == 10_485_760  # falls back to default


def test_config_logging_max_bytes_ceiling():
    cfg = Config.from_dict({"logging": {"file_max_bytes": 2_000_000_000}})
    assert cfg.log_file_max_bytes == 10_485_760  # falls back to default


def test_config_logging_backup_count_floor():
    cfg = Config.from_dict({"logging": {"file_backup_count": 0}})
    assert cfg.log_file_backup_count == 5  # falls back to default


def test_config_logging_backup_count_ceiling():
    cfg = Config.from_dict({"logging": {"file_backup_count": 50}})
    assert cfg.log_file_backup_count == 5  # falls back to default


def test_config_1password_retrieval(monkeypatch, tmp_path):
    from unittest.mock import MagicMock, patch

    config_file = tmp_path / "config.toml"
    import tomli_w

    data = {
        "gemini": {
            "op_reference": "op://vault/item/field",
        },
    }
    config_file.write_bytes(tomli_w.dumps(data).encode())

    # Keychain fails, 1Password succeeds
    def mock_run(cmd, **kwargs):
        result = MagicMock()
        if cmd[0] == "security":
            result.returncode = 44  # not found
            result.stdout = ""
        elif cmd[0] == "op":
            result.returncode = 0
            result.stdout = "op-api-key-456\n"
        else:
            result.returncode = 1
            result.stdout = ""
        return result

    with patch("subprocess.run", side_effect=mock_run):
        cfg = load_config(config_path=config_file, cli_overrides={})

    assert cfg.gemini_api_key == "op-api-key-456"


def test_config_has_mistral_defaults():
    cfg = Config()
    assert cfg.mistral_api_key == ""
    assert cfg.mistral_endpoint == "https://api.mistral.ai/v1"
    assert cfg.mistral_model == "voxtral-mini-latest"
    assert cfg.mistral_keychain_account == "mistral"
    assert cfg.mistral_keychain_service == "mistral-apikey"
    assert cfg.mistral_op_reference == ""


def test_config_from_dict_reads_mistral_table():
    data = {
        "mistral": {
            "api_key": "sk-test-123",
            "endpoint": "https://api.mistral.ai/v1",
            "model": "voxtral-mini-2507",
            "keychain_account": "alt-account",
            "keychain_service": "alt-service",
            "op_reference": "op://Private/mistral/key",
        }
    }
    cfg = Config.from_dict(data)
    assert cfg.mistral_api_key == "sk-test-123"
    assert cfg.mistral_model == "voxtral-mini-2507"
    assert cfg.mistral_keychain_account == "alt-account"
    assert cfg.mistral_keychain_service == "alt-service"
    assert cfg.mistral_op_reference == "op://Private/mistral/key"


def test_config_write_default_round_trips_mistral(tmp_path):
    cfg = Config()
    path = tmp_path / "config.toml"
    cfg.write_default(path)
    reloaded = Config.from_file(path)
    assert reloaded.mistral_model == "voxtral-mini-latest"
    assert reloaded.mistral_keychain_account == "mistral"
    assert reloaded.mistral_keychain_service == "mistral-apikey"
    assert reloaded.mistral_endpoint == "https://api.mistral.ai/v1"


def test_config_show_masks_mistral_key():
    cfg = Config()
    cfg.mistral_api_key = "sk-abcdefghijklmnop"
    rendered = cfg.show()
    assert "sk-abcdefghijklmnop" not in rendered
    assert "mistral.api_key" in rendered
    assert "mistral.model" in rendered


def test_resolve_secret_signature_is_keyword_only():
    from whotalksitron.config import _resolve_secret

    sig = inspect.signature(_resolve_secret)
    params = list(sig.parameters.values())
    names = {p.name for p in params}
    assert names == {"keychain_account", "keychain_service", "op_reference"}
    assert all(p.kind == inspect.Parameter.KEYWORD_ONLY for p in params)


def test_mistral_endpoint_rejects_http(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text('[mistral]\nendpoint = "http://insecure.example.com/v1"\n')
    with pytest.raises(ValueError, match="https://"):
        load_config(config_path, {})


def test_mistral_endpoint_strips_trailing_slash(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text('[mistral]\nendpoint = "https://api.mistral.ai/v1/"\n')
    cfg = load_config(config_path, {})
    assert cfg.mistral_endpoint == "https://api.mistral.ai/v1"


def test_mistral_endpoint_non_default_warns(tmp_path, caplog):
    config_path = tmp_path / "config.toml"
    config_path.write_text('[mistral]\nendpoint = "https://proxy.example.com/v1"\n')
    with caplog.at_level("WARNING", logger="whotalksitron.config"):
        load_config(config_path, {})
    assert any(
        "non-default" in r.message.lower() or "bearer token" in r.message.lower()
        for r in caplog.records
    ), [r.message for r in caplog.records]


def test_load_config_calls_resolve_secret_for_both_backends_when_empty(
    monkeypatch, tmp_path
):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_API_KEY", raising=False)
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)

    config_path = tmp_path / "config.toml"
    config_path.write_text("")

    with patch("whotalksitron.config._resolve_secret", return_value=None) as m:
        load_config(config_path, {})

    assert m.call_count == 2
    calls = [c.kwargs for c in m.call_args_list]
    assert {
        "keychain_account": "vertex",
        "keychain_service": "vertex-apikey",
        "op_reference": "",
    } in calls, calls
    assert {
        "keychain_account": "mistral",
        "keychain_service": "mistral-apikey",
        "op_reference": "",
    } in calls, calls
