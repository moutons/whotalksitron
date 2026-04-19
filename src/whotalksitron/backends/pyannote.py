from __future__ import annotations

from pathlib import Path

from whotalksitron.config import Config
from whotalksitron.models import SpeakerPool, TranscriptResult
from whotalksitron.progress import ProgressCallback


class PyAnnoteBackend:
    name = "pyannote"

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
        try:
            import faster_whisper  # noqa: F401
            import pyannote.audio  # noqa: F401
            import torch  # noqa: F401

            return True
        except (ImportError, AttributeError, Exception):
            return False
