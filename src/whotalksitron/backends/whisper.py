from __future__ import annotations

import logging
from pathlib import Path

import httpx

from whotalksitron.config import Config
from whotalksitron.models import SpeakerPool, TranscriptResult, TranscriptSegment
from whotalksitron.progress import ProgressCallback
from whotalksitron.retry import RetryExhausted, retry_with_backoff

logger = logging.getLogger(__name__)


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
        audio_path = Path(audio_path)

        if progress:
            progress.update("transcribe", 0, "sending to Whisper endpoint")

        url = f"{self._config.whisper_endpoint}/audio/transcriptions"
        logger.debug("Whisper endpoint: %s", url)
        logger.debug("Whisper model: %s", self._config.whisper_model)

        def _post_transcription():
            with open(audio_path, "rb") as f:
                resp = httpx.post(
                    url,
                    files={"file": (audio_path.name, f, "audio/mpeg")},
                    data={
                        "model": self._config.whisper_model,
                        "response_format": "verbose_json",
                        "timestamp_granularities[]": "segment",
                    },
                    timeout=600.0,
                )
            resp.raise_for_status()
            return resp

        try:
            response = retry_with_backoff(
                _post_transcription,
                retries=3,
                base_delay=2.0,
                retry_on=(
                    httpx.HTTPStatusError,
                    httpx.ConnectError,
                    httpx.TimeoutException,
                ),
            )
        except RetryExhausted as exc:
            raise RuntimeError(
                f"Whisper endpoint at {self._config.whisper_endpoint} failed "
                "after 3 retries. Is Ollama/LM Studio running?"
            ) from exc

        if progress:
            progress.update("transcribe", 80, "parsing response")
        data = response.json()

        segments = _parse_whisper_response(data)

        if progress:
            progress.stage_complete("transcribe", f"{len(segments)} segments")

        return TranscriptResult(
            segments=segments,
            metadata={
                "model": self._config.whisper_model,
                "backend": "whisper",
                "endpoint": self._config.whisper_endpoint,
            },
        )

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


def _parse_whisper_response(data: dict) -> list[TranscriptSegment]:
    raw_segments = data.get("segments")

    if raw_segments is None:
        text = data.get("text", "").strip()
        if not text:
            return []
        return [TranscriptSegment(start=0.0, end=0.0, text=text)]

    segments: list[TranscriptSegment] = []
    for seg in raw_segments:
        text = seg.get("text", "").strip()
        if not text:
            continue
        segments.append(
            TranscriptSegment(
                start=float(seg.get("start", 0.0)),
                end=float(seg.get("end", 0.0)),
                text=text,
            )
        )
    return segments
