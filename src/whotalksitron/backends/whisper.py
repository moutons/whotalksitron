from __future__ import annotations

from pathlib import Path

import httpx

from whotalksitron.config import Config
from whotalksitron.models import SpeakerPool, TranscriptResult
from whotalksitron.progress import ProgressCallback


class WhisperBackend:
    name = "whisper"

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
        return False

    def is_available(self) -> bool:
        try:
            resp = httpx.get(
                f"{self._config.whisper_endpoint}/models",
                timeout=2.0,
            )
            return resp.status_code == 200
        except httpx.ConnectError:
            return False
