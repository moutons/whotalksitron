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
