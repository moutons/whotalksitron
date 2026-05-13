"""Mistral (Voxtral) transcription backend.

Calls Mistral's /v1/audio/transcriptions endpoint. Does not perform
speaker diarization in this iteration; Mistral's `diarize=true` flag is
deferred to a future release.

Security note: this module pins the httpx logger to WARNING so the
Authorization bearer header cannot leak via debug-level logging.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx

from whotalksitron.config import Config
from whotalksitron.models import SpeakerPool, TranscriptResult, TranscriptSegment
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
        audio_path = Path(audio_path)
        if audio_path.stat().st_size == 0:
            raise ValueError(f"Audio file is empty: {audio_path}")

        if speakers and speakers.speakers and not self._diarization_notice_logged:
            logger.info(
                "Mistral backend ignores speaker enrollment in this version. "
                "Use the gemini or pyannote backend for diarization."
            )
            self._diarization_notice_logged = True

        if progress:
            progress.update("transcribe", 0, "sending to Mistral API")

        endpoint = self._config.mistral_endpoint.rstrip("/")
        url = f"{endpoint}/audio/transcriptions"
        mime = _guess_mime(audio_path)
        audio_bytes = audio_path.read_bytes()

        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {self._config.mistral_api_key}"},
            files={"file": (audio_path.name, audio_bytes, mime)},
            data={
                "model": self._config.mistral_model,
                "timestamp_granularities": "segment",
            },
            timeout=600.0,
        )
        response.raise_for_status()

        if progress:
            progress.update("transcribe", 80, "parsing response")

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            preview = response.text[:200]
            raise RuntimeError(
                f"Could not parse Mistral response as JSON: {preview!r}"
            ) from exc

        raw_segments = data.get("segments") or []
        segments: list[TranscriptSegment] = []
        for seg in raw_segments:
            start = float(seg.get("start", 0.0))
            end = float(seg.get("end", start))
            if start > end:
                logger.warning(
                    "Mistral segment has start>end (start=%s, end=%s); keeping as-is",
                    start,
                    end,
                )
            segments.append(
                TranscriptSegment(
                    start=start,
                    end=end,
                    text=(seg.get("text") or "").strip(),
                    speaker=None,
                )
            )

        if not segments:
            text = (data.get("text") or "").strip()
            if text:
                logger.info(
                    "Mistral returned no segment timestamps; "
                    "emitting a single un-timestamped segment."
                )
                segments.append(
                    TranscriptSegment(start=0.0, end=0.0, text=text, speaker=None)
                )
            else:
                logger.warning("Mistral returned empty transcript")

        usage = data.get("usage") or {}
        result = TranscriptResult(
            segments=segments,
            metadata={
                "backend": "mistral",
                "model": data.get("model") or self._config.mistral_model,
                "token_count": usage.get("total_tokens"),
                "prompt_audio_seconds": usage.get("prompt_audio_seconds"),
            },
        )

        if progress:
            progress.stage_complete("transcribe", f"{len(segments)} segments")
        return result


def _guess_mime(path: Path) -> str:
    return {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".flac": "audio/flac",
        ".ogg": "audio/ogg",
        ".m4a": "audio/mp4",
        ".webm": "audio/webm",
    }.get(path.suffix.lower(), "audio/mpeg")
