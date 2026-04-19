from __future__ import annotations

from pathlib import Path

from whotalksitron.config import Config
from whotalksitron.models import SpeakerPool, TranscriptResult
from whotalksitron.progress import ProgressCallback


class GeminiBackend:
    name = "gemini"

    def __init__(self, config: Config) -> None:
        self._config = config

    def transcribe(
        self,
        audio_path: str | Path,
        *,
        speakers: SpeakerPool | None = None,
        progress: ProgressCallback | None = None,
    ) -> TranscriptResult:
        raise NotImplementedError

    def supports_diarization(self) -> bool:
        return True

    def is_available(self) -> bool:
        return bool(self._config.gemini_api_key or self._config.gemini_use_adc)
