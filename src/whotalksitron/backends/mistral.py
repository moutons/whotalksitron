"""Mistral (Voxtral) transcription backend.

Calls Mistral's /v1/audio/transcriptions endpoint. Does not perform
speaker diarization in this iteration; Mistral's `diarize=true` flag is
deferred to a future release.

Security note: this module pins the httpx logger to WARNING so the
Authorization bearer header cannot leak via debug-level logging.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx  # noqa: F401

from whotalksitron.config import Config
from whotalksitron.models import SpeakerPool, TranscriptResult
from whotalksitron.progress import ProgressCallback

logger = logging.getLogger(__name__)

# Prevent bearer token leakage via httpx DEBUG-level header logging.
logging.getLogger("httpx").setLevel(logging.WARNING)


class MistralBackend:
    name = "mistral"

    def __init__(self, config: Config) -> None:
        self._config = config
        self._diarization_notice_logged = False

    def is_available(self) -> bool:
        return bool(self._config.mistral_api_key)

    def supports_diarization(self) -> bool:
        return False

    def transcribe(
        self,
        audio_path: str | Path,
        *,
        speakers: SpeakerPool | None = None,
        progress: ProgressCallback | None = None,
    ) -> TranscriptResult:
        raise NotImplementedError  # filled in by later tasks
