from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol, runtime_checkable

from whotalksitron.config import Config
from whotalksitron.models import SpeakerPool, TranscriptResult
from whotalksitron.progress import ProgressCallback

logger = logging.getLogger(__name__)


class BackendUnavailableError(Exception):
    pass


@runtime_checkable
class Backend(Protocol):
    name: str

    def transcribe(
        self,
        audio_path: str | Path,
        *,
        speakers: SpeakerPool | None,
        progress: ProgressCallback | None,
    ) -> TranscriptResult: ...

    def supports_diarization(self) -> bool: ...

    def is_available(self) -> bool: ...


def select_backend(config: Config) -> Backend:
    if config.backend != "auto":
        logger.debug("Backend explicitly set to %r", config.backend)
        backend = _create_backend(config.backend, config)
        if not backend.is_available():
            msg = _unavailable_message(config.backend, backend)
            raise BackendUnavailableError(msg)
        logger.info("Using backend: %s", config.backend)
        return backend

    logger.debug("Auto-selecting backend")
    for name in ("gemini", "pyannote", "whisper"):
        try:
            backend = _create_backend(name, config)
            if backend.is_available():
                logger.info("Auto-selected backend: %s", name)
                return backend
            logger.debug("Backend %s not available", name)
        except BackendUnavailableError:
            logger.debug("Backend %s unavailable", name)
            continue

    raise BackendUnavailableError(
        "No backend available. Configure one of:\n"
        "  gemini:   set GEMINI_API_KEY or run `gcloud auth "
        "application-default login`\n"
        "  pyannote: install local extras with `uv tool install "
        "whotalksitron --with local`\n"
        "  whisper:  start Ollama or LM Studio at http://localhost:1234/v1"
    )


def _create_backend(name: str, config: Config) -> Backend:
    if name == "gemini":
        from whotalksitron.backends.gemini import GeminiBackend

        return GeminiBackend(config)
    elif name == "pyannote":
        from whotalksitron.backends.pyannote import PyAnnoteBackend

        return PyAnnoteBackend(config)
    elif name == "whisper":
        from whotalksitron.backends.whisper import WhisperBackend

        return WhisperBackend(config)
    else:
        raise BackendUnavailableError(f"Unknown backend: {name!r}")


def _unavailable_message(name: str, backend: Backend) -> str:
    hints = {
        "gemini": "Set GEMINI_API_KEY or run `gcloud auth application-default login`",
        "pyannote": "Install local extras: `uv tool install whotalksitron "
        "--with local`",
        "whisper": "Start Ollama or LM Studio. No response from endpoint.",
    }
    hint = hints.get(name, "Check configuration.")
    return f"Backend {name!r} is not available. {hint}"
