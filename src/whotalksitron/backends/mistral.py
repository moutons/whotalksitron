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
from whotalksitron.retry import RetryExhausted, retry_with_backoff

logger = logging.getLogger(__name__)

# Prevent bearer token leakage via httpx DEBUG-level header logging.
logging.getLogger("httpx").setLevel(logging.WARNING)

_TRANSIENT_STATUS = {408, 429, 500, 502, 503, 504}


class _FileTooLargeError(Exception):
    pass


class _TransientHTTPError(Exception):
    def __init__(self, status_code: int, retry_after: float | None = None) -> None:
        super().__init__(f"transient http {status_code}")
        self.status_code = status_code
        self.retry_after = retry_after


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

        def _post() -> httpx.Response:
            resp = httpx.post(
                url,
                headers={"Authorization": f"Bearer {self._config.mistral_api_key}"},
                files={"file": (audio_path.name, audio_bytes, mime)},
                data={
                    "model": self._config.mistral_model,
                    "timestamp_granularities": "segment",
                },
                timeout=600.0,
            )
            if resp.status_code == 413:
                raise _FileTooLargeError()
            if resp.status_code in _TRANSIENT_STATUS:
                retry_after_hdr = (
                    resp.headers.get("Retry-After") if resp.headers else None
                )
                try:
                    retry_after = float(retry_after_hdr) if retry_after_hdr else None
                except ValueError:
                    retry_after = None
                if retry_after:
                    logger.info(
                        "Mistral asked us to retry after %.1fs (current backoff "
                        "policy will use its own delay)",
                        retry_after,
                    )
                raise _TransientHTTPError(resp.status_code, retry_after)
            resp.raise_for_status()
            return resp

        try:
            response = retry_with_backoff(
                _post,
                retries=3,
                base_delay=2.0,
                retry_on=(
                    httpx.ConnectError,
                    httpx.TimeoutException,
                    _TransientHTTPError,
                ),
            )
        except _FileTooLargeError as exc:
            raise RuntimeError(
                "Audio file exceeds Mistral's documented limits "
                "(max 3 hours of audio per request). Use the gemini backend, "
                "which supports large-file upload via the File API, or split "
                "the recording."
            ) from exc
        except RetryExhausted as exc:
            raise RuntimeError(
                "Mistral API failed after 3 retries. Check MISTRAL_API_KEY "
                "and network connectivity, or try a different backend."
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Mistral API rejected the request "
                f"(HTTP {exc.response.status_code}). Check your API key and "
                f"request parameters."
            ) from exc

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
