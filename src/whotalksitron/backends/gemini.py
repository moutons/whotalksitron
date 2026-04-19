from __future__ import annotations

import logging
import re
from pathlib import Path

from google import genai
from google.genai import types

from whotalksitron.config import Config
from whotalksitron.models import SpeakerPool, TranscriptResult, TranscriptSegment
from whotalksitron.progress import ProgressCallback
from whotalksitron.retry import RetryExhausted, retry_with_backoff

logger = logging.getLogger(__name__)

_INLINE_SIZE_LIMIT = 20 * 1024 * 1024  # 20MB


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
        audio_path = Path(audio_path)
        client = self._make_client()

        if progress:
            progress.update("transcribe", 0, "preparing Gemini request")

        contents = self._build_contents(audio_path, speakers, client)
        prompt = _build_prompt(speakers)

        if progress:
            progress.update("transcribe", 30, "sending to Gemini API")

        logger.debug("Gemini model: %s", self._config.gemini_model)
        try:
            response = retry_with_backoff(
                lambda: client.models.generate_content(
                    model=self._config.gemini_model,
                    contents=[*contents, prompt],
                ),
                retries=3,
                base_delay=2.0,
                retry_on=(Exception,),
            )
        except RetryExhausted as exc:
            raise RuntimeError(
                "Gemini API failed after 3 retries. Check your API key and "
                "network connection, or try a local backend."
            ) from exc

        if progress:
            progress.update("transcribe", 90, "parsing response")

        response_text = response.text or ""
        logger.debug("Gemini response length: %d chars", len(response_text))

        segments = _parse_response(response_text)

        token_count = None
        if response.usage_metadata:
            token_count = response.usage_metadata.total_token_count

        if progress:
            progress.stage_complete("transcribe", f"{len(segments)} segments")

        return TranscriptResult(
            segments=segments,
            metadata={
                "model": self._config.gemini_model,
                "backend": "gemini",
                "token_count": token_count,
            },
        )

    def supports_diarization(self) -> bool:
        return True

    def is_available(self) -> bool:
        return bool(self._config.gemini_api_key or self._config.gemini_use_adc)

    def _make_client(self) -> genai.Client:
        if self._config.gemini_use_adc:
            return genai.Client(
                vertexai=True,
                project=self._config.gemini_project or None,
                location=self._config.gemini_location or None,
            )
        if self._config.gemini_api_key:
            return genai.Client(api_key=self._config.gemini_api_key)
        return genai.Client()

    def _build_contents(
        self,
        audio_path: Path,
        speakers: SpeakerPool | None,
        client: genai.Client,
    ) -> list[types.Part]:
        parts: list[types.Part] = []

        if speakers:
            for _name, sample_paths in speakers.speakers.items():
                for sample_path in sample_paths:
                    part = self._upload_or_inline(sample_path, client)
                    parts.append(part)

        parts.append(self._upload_or_inline(audio_path, client))
        return parts

    def _upload_or_inline(self, path: Path, client: genai.Client) -> types.Part:
        file_size = path.stat().st_size
        mime = _guess_mime(path)

        if file_size > _INLINE_SIZE_LIMIT:
            if self._config.gemini_use_adc:
                return _upload_to_gcs(path, mime, self._config)
            logger.info("Uploading %s via File API (%d bytes)", path.name, file_size)
            uploaded = client.files.upload(file=path)
            if not uploaded.uri:
                msg = f"Gemini file upload returned no URI for {path.name}"
                raise RuntimeError(msg)
            return types.Part.from_uri(file_uri=uploaded.uri, mime_type=mime)

        logger.debug("Inlining %s (%d bytes)", path.name, file_size)
        data = path.read_bytes()
        return types.Part.from_bytes(data=data, mime_type=mime)


def _build_prompt(speakers: SpeakerPool | None) -> str:
    base = (
        "Transcribe this audio with speaker diarization. "
        "Format each line as: [HH:MM:SS] Speaker Name: text\n"
        "Use consistent speaker names throughout. "
        "If you cannot identify a speaker, use zero-padded labels: "
        "'Speaker 01', 'Speaker 02', etc."
    )
    if speakers and speakers.speakers:
        names = ", ".join(sorted(speakers.speakers.keys()))
        base += (
            f"\n\nI have provided voice samples for known speakers: {names}. "
            "The audio samples before the main recording are voice references. "
            "Match speakers in the recording against these references and use "
            "their names. For any speakers that don't match a reference, use "
            "'Speaker 01', 'Speaker 02', etc."
        )
    return base


def _parse_response(text: str) -> list[TranscriptSegment]:
    pattern = re.compile(
        r"\[(\d{1,2}:\d{2}:\d{2})\]\s*"
        r"(?:((?:(?:Speaker\s+\d+)|(?:[A-Z][a-zA-Z'-]+(?:\s+[A-Z][a-zA-Z'-]+){0,2}))):\s+(?=[A-Z]))?"
        r"(.+)"
    )
    segments: list[TranscriptSegment] = []

    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        match = pattern.match(line)
        if not match:
            logger.debug("Skipping unparseable line: %s", line)
            continue

        timestamp_str, speaker, content = match.groups()
        seconds = _parse_timestamp(timestamp_str)
        speaker = speaker.strip() if speaker else None

        segments.append(
            TranscriptSegment(
                start=seconds,
                end=seconds,
                text=content.strip(),
                speaker=speaker,
            )
        )

    for i in range(len(segments) - 1):
        segments[i] = TranscriptSegment(
            start=segments[i].start,
            end=segments[i + 1].start,
            text=segments[i].text,
            speaker=segments[i].speaker,
        )
    if segments:
        last = segments[-1]
        segments[-1] = TranscriptSegment(
            start=last.start,
            end=last.start + 30.0,
            text=last.text,
            speaker=last.speaker,
        )

    return segments


def _parse_timestamp(ts: str) -> float:
    parts = ts.split(":")
    if len(parts) != 3:
        raise ValueError(f"Invalid timestamp format: {ts!r}")
    try:
        h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError as exc:
        raise ValueError(f"Non-numeric timestamp components: {ts!r}") from exc
    return h * 3600.0 + m * 60.0 + s


def _upload_to_gcs(path: Path, mime: str, config: Config) -> types.Part:
    from google.cloud import storage  # type: ignore[import-untyped]

    bucket_name = config.gemini_gcs_bucket
    if not bucket_name:
        raise RuntimeError(
            "Vertex AI requires a GCS bucket for files larger than 20MB. "
            "Set GOOGLE_CLOUD_STORAGE_BUCKET or gemini.gcs_bucket in config."
        )

    gcs = storage.Client(project=config.gemini_project or None)
    bucket = gcs.bucket(bucket_name)
    blob_name = f"whotalksitron/{path.name}"
    blob = bucket.blob(blob_name)

    logger.info(
        "Uploading %s to gs://%s/%s (%d bytes)",
        path.name,
        bucket_name,
        blob_name,
        path.stat().st_size,
    )
    blob.upload_from_filename(str(path), content_type=mime)
    gcs_uri = f"gs://{bucket_name}/{blob_name}"
    return types.Part.from_uri(file_uri=gcs_uri, mime_type=mime)


def _guess_mime(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".flac": "audio/flac",
        ".ogg": "audio/ogg",
        ".m4a": "audio/mp4",
        ".webm": "audio/webm",
    }.get(suffix, "audio/mpeg")
