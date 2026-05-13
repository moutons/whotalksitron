import pytest

from whotalksitron.backends import (
    Backend,
    BackendUnavailableError,
    select_backend,
)
from whotalksitron.config import Config
from whotalksitron.models import TranscriptResult


class FakeBackend:
    name = "fake"

    def __init__(self, available: bool = True, diarization: bool = True):
        self._available = available
        self._diarization = diarization

    def transcribe(
        self,
        audio_path,
        *,
        speakers=None,
        progress=None,
    ) -> TranscriptResult:
        return TranscriptResult(segments=[], metadata={})

    def supports_diarization(self) -> bool:
        return self._diarization

    def is_available(self) -> bool:
        return self._available


def test_backend_protocol_compliance():
    backend: Backend = FakeBackend()
    assert backend.name == "fake"
    assert backend.is_available()
    assert backend.supports_diarization()
    result = backend.transcribe(
        "/fake/path.mp3",
        speakers=None,
        progress=None,
    )
    assert isinstance(result, TranscriptResult)


def test_select_backend_explicit(monkeypatch):
    cfg = Config()
    cfg.backend = "whisper"
    cfg.whisper_endpoint = "http://localhost:9999/v1"

    # Should attempt whisper even if unavailable — and raise
    with pytest.raises(BackendUnavailableError, match="whisper"):
        select_backend(cfg)


def test_select_backend_auto_no_backends(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    cfg = Config()
    cfg.backend = "auto"
    cfg.gemini_api_key = ""
    cfg.gemini_use_adc = False

    with pytest.raises(BackendUnavailableError, match="No backend available"):
        select_backend(cfg)


def test_select_backend_explicit_mistral():
    from whotalksitron.backends import select_backend
    from whotalksitron.backends.mistral import MistralBackend
    from whotalksitron.config import Config

    cfg = Config()
    cfg.backend = "mistral"
    cfg.mistral_api_key = "sk-test"
    backend = select_backend(cfg)
    assert isinstance(backend, MistralBackend)


def test_select_backend_mistral_unavailable_when_no_key():
    from whotalksitron.backends import BackendUnavailableError, select_backend
    from whotalksitron.config import Config

    cfg = Config()
    cfg.backend = "mistral"
    with pytest.raises(BackendUnavailableError, match="MISTRAL_API_KEY"):
        select_backend(cfg)


def test_auto_select_does_not_pick_mistral(monkeypatch):
    """Even when Mistral is the only configured backend, auto must skip it."""
    from whotalksitron.backends import BackendUnavailableError, select_backend
    from whotalksitron.config import Config

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_API_KEY", raising=False)
    cfg = Config()
    cfg.backend = "auto"
    cfg.mistral_api_key = "sk-test"
    # Mistral is opt-in only; auto-select must NOT pick it.
    with pytest.raises(BackendUnavailableError):
        select_backend(cfg)
