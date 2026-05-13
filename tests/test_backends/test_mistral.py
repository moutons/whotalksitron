from __future__ import annotations

from whotalksitron.config import Config


def _make_config(**overrides) -> Config:
    cfg = Config()
    cfg.mistral_endpoint = "https://api.mistral.ai/v1"
    cfg.mistral_model = "voxtral-mini-latest"
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def test_backend_is_available_when_key_set():
    from whotalksitron.backends.mistral import MistralBackend
    backend = MistralBackend(_make_config(mistral_api_key="sk-test"))
    assert backend.is_available() is True


def test_backend_is_available_false_when_key_missing():
    from whotalksitron.backends.mistral import MistralBackend
    backend = MistralBackend(_make_config())
    assert backend.is_available() is False


def test_backend_name_and_diarization():
    from whotalksitron.backends.mistral import MistralBackend
    backend = MistralBackend(_make_config(mistral_api_key="sk-test"))
    assert backend.name == "mistral"
    assert backend.supports_diarization() is False
